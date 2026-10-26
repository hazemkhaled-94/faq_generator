"""A restore puts back the deletions chosen, and nothing archived beside them."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import ServiceSetting

pytestmark = pytest.mark.integration


def seed(engine, *names: str) -> dict[str, int]:
    """One chunked document per name, with a passage and a fact each."""
    from blob_store.s3 import DocumentsBucket, ParsedBucket

    made = {}
    with Session(engine) as session:
        for name in names:
            sha = digest(name)
            source, parsed = DocumentsBucket(), ParsedBucket()
            source.put(
                source.key_for(sha, "application/pdf"),
                b"%PDF-1.7",
                content_type="application/pdf",
            )
            parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
            session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
            session.flush()
            cut = passage(sha, ordinal=1, text=f"{name} text")
            session.add(cut)
            session.flush()
            drawn = fact(cut.id, statement=f"{name} fact")
            session.add(drawn)
            session.flush()
            made[name] = drawn.id
        session.commit()
    return made


def run(engine, statement: str) -> None:
    """One transaction, so its deletions share an `archived_at`."""
    with engine.begin() as connection:
        connection.execute(text(statement))


def deleted_at(engine, table: str) -> str:
    """When the newest deletion from `table` happened, as restore names it."""
    with engine.connect() as connection:
        return (
            connection.execute(
                text(
                    "SELECT max(archived_at) FROM archived_rows WHERE table_name = :t"
                ),
                {"t": table},
            )
            .scalar_one()
            .isoformat()
        )


def count(engine, sql: str) -> int:
    """A count, read off the live tables."""
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def restore(monkeypatch, **environment: str) -> int:
    """Runs the restore with the given environment."""
    from archive import restore as module

    for name in ("SINCE", "AT", "TABLES"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return module.main()


def test_one_deletion_is_restored_and_a_later_replacement_stays(
    engine, database, buckets, monkeypatch
) -> None:
    """Delete A, re-extract B, clear a setting, restore A's deletion only."""
    ids = seed(engine, "a", "b")
    with Session(engine) as session:
        session.add(ServiceSetting(service="platform", name="LLM_BASE_URL", value="x"))
        session.commit()

    run(engine, f"DELETE FROM documents WHERE sha256 = '{digest('a')}'")
    at = deleted_at(engine, "documents")
    run(engine, f"DELETE FROM facts WHERE id = {ids['b']}")
    with Session(engine) as session:
        cut = session.execute(
            text("SELECT id FROM passages WHERE doc_sha256 = :s"), {"s": digest("b")}
        ).scalar_one()
        session.add(fact(cut, statement="b fact, second generation"))
        session.commit()
    run(engine, "DELETE FROM service_settings")

    assert restore(monkeypatch, AT=at) == 0

    assert (
        count(engine, f"SELECT count(*) FROM documents WHERE sha256 = '{digest('a')}'")
        == 1
    )
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement LIKE 'a fact'") == 1
    )
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement LIKE 'b fact%'") == 1
    ), "B keeps one generation of facts"
    assert count(engine, "SELECT count(*) FROM service_settings") == 0


def test_since_only_lists_what_was_deleted(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Naming a time restores nothing: it lists, by deleting transaction."""
    seed(engine, "a")
    run(engine, "DELETE FROM documents")

    assert restore(monkeypatch, SINCE="2000-01-01") == 2

    assert count(engine, "SELECT count(*) FROM documents") == 0
    shown = capsys.readouterr().out
    assert "documents" in shown and "AT=" in shown


def test_settings_and_prompts_come_back_only_when_named(
    engine, database, buckets, monkeypatch
) -> None:
    """One transaction took a document and a setting; the setting is skipped."""
    seed(engine, "a")
    with Session(engine) as session:
        session.add(ServiceSetting(service="platform", name="LLM_BASE_URL", value="x"))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))
        connection.execute(text("DELETE FROM service_settings"))
    at = deleted_at(engine, "documents")

    assert restore(monkeypatch, AT=at) == 0
    assert count(engine, "SELECT count(*) FROM documents") == 1
    assert count(engine, "SELECT count(*) FROM service_settings") == 0

    assert restore(monkeypatch, AT=at, TABLES="service_settings") == 0
    assert count(engine, "SELECT count(*) FROM service_settings") == 1


def test_a_refit_is_listed_as_not_restorable(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Its topics were replaced under their unique key; offering them is a trap."""
    with Session(engine) as session:
        session.add(fitted(0, language="de", label="Lieferzeiten"))
        session.commit()
    run(engine, "DELETE FROM topics")
    at = deleted_at(engine, "topics")
    with Session(engine) as session:
        session.add(fitted(0, language="de", label="Neu"))
        session.commit()

    assert restore(monkeypatch, SINCE="2000-01-01") == 2
    assert "not restorable" in capsys.readouterr().out

    assert restore(monkeypatch, AT=at) == 1
    assert count(engine, "SELECT count(*) FROM topics") == 1
    assert count(engine, "SELECT count(*) FROM topics WHERE label = 'Neu'") == 1


def test_a_restored_document_with_passages_is_marked_chunked(
    engine, database, buckets, monkeypatch
) -> None:
    """The delete-derived left it `new`; its passages are back."""
    seed(engine, "a")
    run(engine, "DELETE FROM passages")
    run(engine, "UPDATE documents SET chunk_status = 'new'")
    at = deleted_at(engine, "passages")

    assert restore(monkeypatch, AT=at) == 0

    assert count(engine, "SELECT count(*) FROM passages") == 1
    assert (
        count(engine, "SELECT count(*) FROM documents WHERE chunk_status = 'chunked'")
        == 1
    )


def test_a_column_added_since_is_filled_from_its_default(
    engine, database, buckets, monkeypatch
) -> None:
    """The archived payload lacks a key: its default, or a refusal naming it."""
    seed(engine, "a")
    run(engine, "DELETE FROM facts")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE archived_rows SET payload = payload - 'statement_predicates' "
                "WHERE table_name = 'facts'"
            )
        )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 0
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement_predicates = 0") == 1
    )


def test_a_missing_key_with_no_default_refuses_naming_the_column(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Rolled back whole, as a NOT NULL violation did, but saying which column."""
    seed(engine, "a")
    run(engine, "DELETE FROM facts")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE archived_rows SET payload = payload - 'statement' "
                "WHERE table_name = 'facts'"
            )
        )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 1
    assert "statement" in capsys.readouterr().out
    assert count(engine, "SELECT count(*) FROM facts") == 0


def test_a_thousand_reopenable_questions_print_the_count_and_twenty_ids(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """One line of thousands of ids was unreadable."""
    ids = seed(engine, "a")
    with Session(engine) as session:
        for _ in range(30):
            asked = question()
            session.add(asked)
            session.flush()
            session.add(link(asked.id, ids["a"]))
        session.commit()
    run(engine, f"DELETE FROM facts WHERE id = {ids['a']}")
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 0

    shown = capsys.readouterr().out
    line = next(
        one for one in shown.splitlines() if "rejected as source_changed" in one
    )
    assert "30 rejected as source_changed" in line
    assert len(line.split("(the first 20:")[1].split(")")[0].split(",")) == 20


def test_questions_whose_facts_are_back_are_listed_for_reverification(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Rejected source_changed when the fact went; the fact is back, the verdict stays."""
    ids = seed(engine, "a")
    with Session(engine) as session:
        asked = question()
        session.add(asked)
        session.flush()
        session.add(link(asked.id, ids["a"]))
        session.commit()
        asked_id = asked.id
    run(engine, f"DELETE FROM facts WHERE id = {ids['a']}")
    assert (
        count(
            engine,
            "SELECT count(*) FROM questions WHERE rejected_reason = 'source_changed'",
        )
        == 1
    )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 0

    shown = capsys.readouterr().out
    assert str(asked_id) in shown
    # reverify skips every rejected question: the printed remedy must be what reopens one.
    assert "make questions-reverify" not in shown and "PATCH /questions/" in shown


#: A duplicate refusal and the fact it repeats, in each configured language and
#: in one no configuration names, which the restore must not read differently.
TWINS = {
    "de": "Die Gebühr beträgt 12 EUR im Jahr.",
    "en": "The fee is EUR 12 a year.",
    "sw": "Ada ni EUR 12 kwa mwaka.",
}


def twinned(engine, language: str) -> dict[str, int | str]:
    """Documents a and b; a holds a fact of its own and a refusal twinned to b's fact."""
    from blob_store.s3 import DocumentsBucket, ParsedBucket

    made: dict[str, int | str] = {}
    with Session(engine) as session:
        for name in ("a", "b"):
            sha = digest(name + language)
            source, parsed = DocumentsBucket(), ParsedBucket()
            source.put(
                source.key_for(sha, "application/pdf"),
                b"%PDF-1.7",
                content_type="application/pdf",
            )
            parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
            session.add(
                document(
                    sha,
                    parse_status="parsed",
                    chunk_status="chunked",
                    language=language,
                )
            )
            session.flush()
            cut = passage(sha, ordinal=1, text=TWINS[language], language=language)
            session.add(cut)
            session.flush()
            made[name], made[name + "_sha"] = cut.id, sha
        twin = fact(made["b"], statement=TWINS[language])
        session.add(twin)
        session.flush()
        refusal = fact(
            made["a"],
            statement=TWINS[language],
            validated=False,
            rejection_code="duplicate",
            twin_id=twin.id,
        )
        session.add_all([refusal, fact(made["a"], statement=f"a {language} fact")])
        session.commit()
        made["twin"], made["refusal"] = twin.id, refusal.id
    return made


def twin_of(engine, refusal: int) -> int | None:
    """The twin a restored refusal points at, None for none."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT twin_id FROM facts WHERE id = :id"), {"id": refusal}
        ).scalar_one()


@pytest.mark.parametrize("language", sorted(TWINS))
def test_a_refusal_whose_twin_a_later_deletion_took_comes_back_pointing_at_none(
    engine, database, buckets, monkeypatch, capsys, language
) -> None:
    """The deletion of a alone is put back; b's, which took the twin, is not."""
    made = twinned(engine, language)
    run(engine, f"DELETE FROM documents WHERE sha256 = '{made['a_sha']}'")
    first = deleted_at(engine, "documents")
    run(engine, f"DELETE FROM documents WHERE sha256 = '{made['b_sha']}'")

    assert restore(monkeypatch, AT=first) == 0

    assert "Nothing restored" not in capsys.readouterr().out
    assert (
        count(
            engine, f"SELECT count(*) FROM facts WHERE statement = 'a {language} fact'"
        )
        == 1
    )
    assert twin_of(engine, int(made["refusal"])) is None


@pytest.mark.parametrize("language", sorted(TWINS))
def test_a_refusal_whose_twin_was_read_again_comes_back_pointing_at_none(
    engine, database, buckets, monkeypatch, capsys, language
) -> None:
    """The twin went when b's passage was read again and said something else."""
    from facts import checked

    from extraction.repository import PassageQueue

    made = twinned(engine, language)
    run(engine, f"DELETE FROM documents WHERE sha256 = '{made['a_sha']}'")
    first = deleted_at(engine, "documents")
    PassageQueue().store(
        int(made["b"]), [checked(int(made["b"]), "A changed reading.")]
    )

    assert restore(monkeypatch, AT=first) == 0

    assert "Nothing restored" not in capsys.readouterr().out
    assert twin_of(engine, int(made["refusal"])) is None


@pytest.mark.parametrize("language", sorted(TWINS))
def test_a_refusal_whose_twin_is_live_or_restored_beside_it_keeps_it(
    engine, database, buckets, monkeypatch, language
) -> None:
    """Live, or put back by the same restore: the refusal still names it.

    The second deletion takes the refusal before its twin in one transaction,
    so the archive holds the refusal still naming the twin beside the twin.
    """
    made = twinned(engine, language)
    run(engine, f"DELETE FROM documents WHERE sha256 = '{made['a_sha']}'")

    assert restore(monkeypatch, AT=deleted_at(engine, "documents")) == 0
    assert twin_of(engine, int(made["refusal"])) == made["twin"]

    with engine.begin() as connection:
        for name in ("a_sha", "b_sha"):
            connection.execute(
                text("DELETE FROM documents WHERE sha256 = :sha"), {"sha": made[name]}
            )

    assert restore(monkeypatch, AT=deleted_at(engine, "documents")) == 0
    assert twin_of(engine, int(made["refusal"])) == made["twin"]
