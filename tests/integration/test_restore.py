"""Putting back what a wipe took, from the archive it left.

The corpus is deleted the way `make wipe` deletes it, so the triggers and
the removal paths fill the archive and nothing here writes to it directly.
"""

from __future__ import annotations

import uuid

import pytest
from seed import (
    digest,
    document,
    event,
    fact,
    fitted,
    link,
    membership,
    passage,
    question,
)
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database.qa_generator import Assessment, AssessmentMetric, Base

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\nnot really a document\n"

#: Every table the triggers archive.
TABLES = sorted(set(Base.metadata.tables) - {"archived_rows"})


@pytest.fixture
def corpus(engine, database, buckets) -> str:
    """A document and everything a run and a person built on it."""
    from blob_store.s3 import DocumentsBucket, ExportBucket, ModelsBucket, ParsedBucket

    sha = digest()
    source, parsed = DocumentsBucket(), ParsedBucket()
    source.put(
        source.key_for(sha, "application/pdf"), PDF, content_type="application/pdf"
    )
    parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
    figure, model = ExportBucket(), ModelsBucket()
    figure.put(
        figure.topic_visualisation_key("de"),
        b"<html>de</html>",
        content_type=figure.TOPIC_VISUALISATION_TYPE,
    )
    model.put(model.topic_model_key("de"), b"npz", content_type=model.TOPIC_MODEL_TYPE)

    with Session(engine) as session:
        session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
        session.add(event(sha256=sha))
        session.flush()
        cut = passage(sha, ordinal=1)
        session.add(cut)
        session.flush()
        drawn = fact(cut.id, reviewed_verdict="accepted", reviewed_at=func.now())
        session.add(drawn)
        subject = fitted(0, language="de", label="Lieferzeiten", labelled_by="person")
        session.add(subject)
        session.flush()
        session.add(membership(cut.id, subject.id))
        asked = question()
        session.add(asked)
        session.flush()
        followed = question(follows_id=asked.id, thread_position=2)
        session.add(followed)
        session.flush()
        session.add_all([link(asked.id, drawn.id), link(followed.id, drawn.id)])
        session.add(
            Assessment(
                artifact_kind="topic",
                topic_id=subject.id,
                assess_status="assessed",
                approved=True,
                assessed_at=func.now(),
                metrics=[
                    AssessmentMetric(
                        metric="relevance", label="relevant", score=1.0, approved=True
                    )
                ],
            )
        )
        replaced = fact(cut.id, statement="The device weighs 5 kg.")
        session.add(replaced)
        session.commit()
        replaced_id = replaced.id

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM facts WHERE id = :id"), {"id": replaced_id}
        )
    return sha


def rows(engine) -> dict[str, list[str]]:
    """Every live row of every archived table, as text, minus its vector."""
    with engine.connect() as connection:
        return {
            table: sorted(
                connection.execute(
                    text(f"SELECT (to_jsonb(t) - 'embedding')::text FROM {table} t")
                ).scalars()
            )
            for table in TABLES
        }


def objects() -> dict[str, dict[str, bytes]]:
    """Every object in every bucket, by key."""
    from blob_store.s3 import s3_client

    client = s3_client()
    return {
        bucket: {
            held["Key"]: client.get_object(Bucket=bucket, Key=held["Key"])[
                "Body"
            ].read()
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
            for held in page.get("Contents", [])
        }
        for bucket in ("documents", "parsed", "export", "models", "archive")
    }


def archived(engine) -> int:
    """How many rows the archive holds."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM archived_rows")
        ).scalar_one()


def now(engine) -> str:
    """The database's clock, which is the one `archived_at` is written by."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT now()")).scalar_one().isoformat()


def chosen(engine, since: str) -> str:
    """Every deleting transaction since `since`, as AT names them."""
    with engine.connect() as connection:
        return ",".join(
            moment.isoformat()
            for moment in connection.execute(
                text(
                    "SELECT DISTINCT archived_at FROM archived_rows "
                    "WHERE archived_at >= CAST(:since AS timestamptz)"
                ),
                {"since": since},
            ).scalars()
        )


def wipe() -> None:
    """The two deletions `make wipe` starts with."""
    from ingestion.run import main as ingestion
    from topic_modelling.run import main as topics

    assert ingestion(["--delete-all"]) == 0
    assert topics(["--delete"]) == 0


def test_a_wipe_comes_back_as_it_was_and_only_once(corpus, engine, monkeypatch) -> None:
    """Rows and objects back, the archive untouched, a second run a no-op."""
    from archive import restore

    before, stored, since = rows(engine), objects(), now(engine)

    wipe()

    gone = rows(engine)
    assert not any(gone.values()), {t: len(r) for t, r in gone.items() if r}
    kept, held = archived(engine), objects()["archive"]

    monkeypatch.setenv("AT", chosen(engine, since))
    assert restore.main() == 0

    after = rows(engine)
    assert after == before, {t: after[t] for t in TABLES if after[t] != before[t]}
    assert "Lieferzeiten" in after["topics"][0], "the label a person gave"
    assert {k: v for k, v in objects().items() if k != "archive"} == {
        k: v for k, v in stored.items() if k != "archive"
    }
    assert archived(engine) == kept, "a restore is a copy, not a move"
    assert objects()["archive"] == held

    assert restore.main() == 0

    assert rows(engine) == before
    assert archived(engine) == kept
    assert objects()["archive"] == held


def test_an_object_written_since_is_left_alone(corpus, engine, monkeypatch) -> None:
    """A fit after the wipe drew its own figure; the archived one stays archived."""
    from archive import restore
    from blob_store.s3 import ExportBucket

    since = now(engine)
    wipe()
    key = ExportBucket.topic_visualisation_key("de")
    ExportBucket().put(
        key, b"<html>refit</html>", content_type=ExportBucket.TOPIC_VISUALISATION_TYPE
    )

    monkeypatch.setenv("AT", chosen(engine, since))
    assert restore.main() == 0

    assert ExportBucket().find(key) == b"<html>refit</html>"


def test_the_newest_copy_of_a_row_is_the_one_restored(
    corpus, engine, monkeypatch
) -> None:
    """A document deleted, uploaded again and deleted again is archived twice."""
    from archive import restore
    from ingestion.factory import build_removal

    since = now(engine)
    build_removal().delete(corpus)
    with Session(engine) as session:
        session.add(document(corpus, title="Uploaded again"))
        session.commit()
    build_removal().delete(corpus)

    monkeypatch.setenv("AT", chosen(engine, since))
    assert restore.main() == 0

    with engine.connect() as connection:
        title = connection.execute(text("SELECT title FROM documents")).scalar_one()
    assert title == "Uploaded again"


def test_a_row_whose_parent_was_replaced_is_left_behind(
    corpus, engine, monkeypatch
) -> None:
    """A re-chunk since the wipe holds the passage's key; the citations stay behind."""
    from archive import restore

    since = now(engine)
    wipe()
    with Session(engine) as session:
        session.add(document(corpus))
        session.flush()
        session.add(passage(corpus, ordinal=1, text="Chunked again."))
        session.commit()
    rebuilt = rows(engine)

    monkeypatch.setenv("AT", chosen(engine, since))
    assert restore.main() == 0

    after = rows(engine)
    assert after["passages"] == rebuilt["passages"]
    assert after["fact_passages"] == rebuilt["fact_passages"] == []
    assert after["documents"] == rebuilt["documents"]


def test_without_a_time_nothing_is_restored(corpus, engine, monkeypatch) -> None:
    """The archive holds every deletion ever made, reruns included."""
    from archive import restore

    wipe()
    monkeypatch.delenv("SINCE", raising=False)

    assert restore.main() == 2

    assert not any(rows(engine).values())


def test_a_question_resting_on_two_documents_comes_back_accepted(
    engine, database, buckets, monkeypatch
) -> None:
    """A wipe takes every document at once, so no question is rejected on the way."""
    from archive import restore
    from blob_store.s3 import DocumentsBucket

    source = DocumentsBucket()
    with Session(engine) as session:
        facts = []
        for seed in ("one", "two"):
            sha = digest(seed)
            source.put(
                source.key_for(sha, "application/pdf"),
                PDF,
                content_type="application/pdf",
            )
            session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
            session.flush()
            cut = passage(sha, ordinal=1)
            session.add(cut)
            session.flush()
            drawn = fact(cut.id)
            session.add(drawn)
            session.flush()
            facts.append(drawn.id)
        asked = question(status="accepted")
        session.add(asked)
        session.flush()
        session.add_all([link(asked.id, one) for one in facts])
        session.commit()
        asked_id = asked.id
    since = now(engine)

    wipe()
    monkeypatch.setenv("AT", chosen(engine, since))
    assert restore.main() == 0

    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status::text FROM questions WHERE id = :id"), {"id": asked_id}
        ).scalar_one()
    assert status == "accepted"


@pytest.mark.parametrize(
    ("language", "first", "second"),
    [
        (
            "de",
            "Die Kontoführung kostet 5 EUR im Monat.",
            "Pro Tag sind 1000 EUR abhebbar.",
        ),
        (
            "en",
            "Goods may be returned within 30 days.",
            "Delivery takes 3 working days.",
        ),
    ],
)
def test_a_restored_question_does_not_rejoin_a_superseded_release(
    engine, database, buckets, monkeypatch, language, first, second
) -> None:
    """A draw made after the deletion keeps the only release there is."""
    from archive import restore
    from ingestion.repository import DocumentRepository
    from question_generation.catalog import QuestionCatalog

    one, other = digest(f"one-{language}"), digest(f"other-{language}")
    old = uuid.uuid4()
    with Session(engine) as session:
        session.add_all([document(one), document(other)])
        session.flush()
        cut_one = passage(one, language=language)
        cut_other = passage(other, language=language)
        session.add_all([cut_one, cut_other])
        session.flush()
        fact_one = fact(cut_one.id, statement=first)
        fact_other = fact(cut_other.id, statement=second)
        session.add_all([fact_one, fact_other])
        session.flush()
        gone = question(status="accepted", release_id=old, language=language)
        kept = question(status="accepted", release_id=old, language=language)
        session.add_all([gone, kept])
        session.flush()
        session.add_all([link(gone.id, fact_one.id), link(kept.id, fact_other.id)])
        session.commit()
        gone_id, kept_id = gone.id, kept.id
    since = now(engine)

    DocumentRepository().delete(one)
    QuestionCatalog().release([kept_id])
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    with engine.connect() as connection:
        live = {
            row.id: row.release_id
            for row in connection.execute(text("SELECT id, release_id FROM questions"))
        }
    assert set(live) == {gone_id, kept_id}
    assert live[gone_id] is None
    assert live[kept_id] is not None


@pytest.mark.parametrize(
    ("language", "text_one", "text_other", "drawn_after", "expected"),
    [
        (
            "de",
            "Die Kontoführung kostet 5 EUR im Monat.",
            "Pro Tag sind 1000 EUR abhebbar.",
            False,
            False,
        ),
        (
            "en",
            "Goods may be returned within 30 days.",
            "Delivery takes 3 working days.",
            False,
            False,
        ),
        (
            "de",
            "Die Kontoführung kostet 5 EUR im Monat.",
            "Pro Tag sind 1000 EUR abhebbar.",
            True,
            True,
        ),
        (
            "en",
            "Goods may be returned within 30 days.",
            "Delivery takes 3 working days.",
            True,
            True,
        ),
    ],
)
def test_a_restored_question_keeps_its_release_only_where_a_live_one_holds_it(
    engine,
    database,
    buckets,
    monkeypatch,
    language,
    text_one,
    text_other,
    drawn_after,
    expected,
) -> None:
    """With no live question in its release, the release was cleared on purpose."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    one, other = digest(f"one-{language}"), digest(f"other-{language}")
    old = uuid.uuid4()
    with Session(engine) as session:
        session.add_all([document(one), document(other)])
        session.flush()
        cut_one = passage(one, language=language)
        cut_other = passage(other, language=language)
        session.add_all([cut_one, cut_other])
        session.flush()
        fact_one = fact(cut_one.id, statement=text_one)
        fact_other = fact(cut_other.id, statement=text_other)
        session.add_all([fact_one, fact_other])
        session.flush()
        gone = question(status="accepted", release_id=old, language=language)
        kept = question(
            status="accepted",
            release_id=old if drawn_after else None,
            language=language,
        )
        session.add_all([gone, kept])
        session.flush()
        session.add_all([link(gone.id, fact_one.id), link(kept.id, fact_other.id)])
        session.commit()
        gone_id = gone.id
    since = now(engine)

    DocumentRepository().delete(one)
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    with engine.connect() as connection:
        release = connection.execute(
            text("SELECT release_id FROM questions WHERE id = :id"), {"id": gone_id}
        ).scalar_one()
    assert (release == old) is expected


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_refit_after_a_deletion_does_not_make_it_unrestorable(
    engine, database, buckets, monkeypatch, capsys, language
) -> None:
    """The refit's topics hold the archived ones' key; their memberships stay behind."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    one, other = digest(f"bank-{language}"), digest(f"shop-{language}")
    with Session(engine) as session:
        session.add_all([document(one), document(other)])
        old = fitted(0, language=language)
        session.add(old)
        session.flush()
        cut_one = passage(one, language=language)
        cut_other = passage(other, language=language)
        session.add_all([cut_one, cut_other])
        session.flush()
        session.add_all(
            [membership(cut_one.id, old.id), membership(cut_other.id, old.id)]
        )
        session.add_all([fact(cut_one.id), fact(cut_other.id)])
        session.commit()
        other_id = cut_other.id
    since = now(engine)

    DocumentRepository().delete(one)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM topics"))
    with Session(engine) as session:
        again = fitted(0, language=language)
        session.add(again)
        session.flush()
        session.add(membership(other_id, again.id))
        session.commit()

    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    with engine.connect() as connection:
        documents = connection.execute(
            text("SELECT count(*) FROM documents")
        ).scalar_one()
        memberships = connection.execute(
            text("SELECT count(*) FROM passage_topics")
        ).scalar_one()
    assert documents == 2
    assert memberships == 1, "the deleted passage waits for the next fit"
    out = capsys.readouterr().out
    assert "Nothing restored" not in out
    assert "left behind" in out


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_re_chunk_after_delete_derived_does_not_make_it_unrestorable(
    engine, database, buckets, monkeypatch, capsys, language
) -> None:
    """The new passages hold the archived ones' key; their citations stay behind."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    sha = digest(f"terms-{language}")
    with Session(engine) as session:
        session.add(document(sha))
        session.flush()
        cut = passage(sha, language=language)
        session.add(cut)
        session.flush()
        session.add(fact(cut.id))
        session.commit()
    since = now(engine)

    DocumentRepository().delete_derived(sha)
    with Session(engine) as session:
        session.add(passage(sha, language=language, text="Returns need a receipt."))
        session.commit()

    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    with engine.connect() as connection:
        passages = connection.execute(
            text("SELECT count(*) FROM passages")
        ).scalar_one()
    out = capsys.readouterr().out
    assert "Nothing restored" not in out
    assert passages == 1, "the re-cut passage is kept"
    assert "left behind" in out


@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("de", "Rückgaben sind 30 Tage lang möglich."),
        ("en", "Goods may be returned within 30 days."),
    ],
)
def test_a_fact_left_resting_on_no_passage_is_dropped_and_its_question_rejected(
    engine, database, buckets, monkeypatch, capsys, language, statement
) -> None:
    """A re-chunk replaced the passage, so the fact has no source and its question is rejected."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    sha = digest(f"shop-{language}")
    with Session(engine) as session:
        session.add(document(sha))
        session.flush()
        cut = passage(sha, language=language)
        session.add(cut)
        session.flush()
        held = fact(cut.id, statement=statement)
        session.add(held)
        session.flush()
        asked = question(status="accepted", language=language)
        session.add(asked)
        session.flush()
        session.add(link(asked.id, held.id))
        session.commit()
    since = now(engine)

    DocumentRepository().delete_derived(sha)
    with Session(engine) as session:
        session.add(passage(sha, language=language, text="Returns need a receipt."))
        session.commit()

    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    with engine.connect() as connection:
        counts = [
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in ("facts", "question_facts", "questions")
        ]
    assert counts == [0, 0, 1]
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT status, rejected_reason FROM questions")
        ).all() == [("rejected", "source_changed")], (
            "no accepted question rests on no passage"
        )
    assert "facts: " in capsys.readouterr().out


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_bridge_left_with_one_passage_is_dropped(
    engine, database, buckets, monkeypatch, language
) -> None:
    """A bridge needs two passages; one was replaced by a re-chunk."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    one, other = digest(f"bank-{language}"), digest(f"terms-{language}")
    with Session(engine) as session:
        session.add_all([document(one), document(other)])
        session.flush()
        cut_one = passage(one, language=language)
        cut_other = passage(other, language=language)
        session.add_all([cut_one, cut_other])
        session.flush()
        session.add(fact(cut_one.id, cut_other.id, kind="bridge"))
        session.commit()
    since = now(engine)

    DocumentRepository().delete_derived(one)
    with Session(engine) as session:
        session.add(passage(one, language=language, text="Fees are listed online."))
        session.commit()

    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded documents have no upload in the bucket

    with engine.connect() as connection:
        facts = connection.execute(text("SELECT count(*) FROM facts")).scalar_one()
    assert facts == 0


FOLLOW_UP_CASES = [
    (
        "de",
        "Die Kontoführung kostet 5 EUR im Monat.",
        "Pro Tag sind 1000 EUR abhebbar.",
        "Und ab wann gilt das?",
    ),
    (
        "en",
        "Goods may be returned within 30 days.",
        "Refunds are paid within 14 days.",
        "And where does the money go?",
    ),
]


def _now(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT now()")).scalar_one().isoformat()


def _rows(engine) -> dict[int, tuple[str, object]]:
    with engine.connect() as connection:
        return {
            row.id: (row.status, row.release_id)
            for row in connection.execute(
                text("SELECT id, status::text AS status, release_id FROM questions")
            )
        }


@pytest.mark.parametrize(
    ("language", "first", "second", "follow_text"), FOLLOW_UP_CASES
)
def test_a_restored_follow_up_does_not_rejoin_a_release_its_root_left(
    engine, database, buckets, monkeypatch, language, first, second, follow_text
) -> None:
    """A follow-up archived released comes back undrawn once its root left the release.

    Root and sibling on one document, the follow-up on another; the root leaves after.
    """
    from archive import restore
    from ingestion.repository import DocumentRepository
    from question_generation.catalog import QuestionCatalog

    kept_doc, gone_doc = digest(f"kept-{language}"), digest(f"gone-{language}")
    drawn = uuid.uuid4()
    with Session(engine) as session:
        session.add_all([document(kept_doc), document(gone_doc)])
        session.flush()
        on_kept = passage(kept_doc, language=language, text=first)
        on_gone = passage(gone_doc, language=language, text=second)
        session.add_all([on_kept, on_gone])
        session.flush()
        root_fact = fact(on_kept.id, statement=first)
        sibling_fact = fact(on_kept.id, statement=first + " Immer.")
        follow_fact = fact(on_gone.id, statement=second)
        session.add_all([root_fact, sibling_fact, follow_fact])
        session.flush()
        root = question(status="accepted", release_id=drawn, language=language)
        sibling = question(status="accepted", release_id=drawn, language=language)
        session.add_all([root, sibling])
        session.flush()
        follow = question(
            status="accepted",
            release_id=drawn,
            language=language,
            follows_id=root.id,
            thread_position=2,
            question_text=follow_text,
        )
        session.add(follow)
        session.flush()
        session.add_all(
            [
                link(root.id, root_fact.id),
                link(sibling.id, sibling_fact.id),
                link(follow.id, follow_fact.id),
            ]
        )
        session.commit()
        root_id, follow_id = root.id, follow.id
    since = _now(engine)

    DocumentRepository().delete(gone_doc)  # the follow-up goes, archived released
    QuestionCatalog().decide(root_id, "rejected")  # then a person rejects the root
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()  # 1: the seeded document has no upload in the bucket

    live = _rows(engine)
    assert live[root_id] == ("rejected", None)
    assert live[follow_id][1] is None, (
        f"follow-up {follow_id} came back released under rejected root {root_id}"
    )


def _thread_across_two_documents(engine, language: str, turns: int):
    """Root and sibling on a kept document; follow-ups 2..turns on a gone one."""
    kept_doc, gone_doc = (
        digest(f"kept-{language}-{turns}"),
        digest(f"gone-{language}-{turns}"),
    )
    drawn = uuid.uuid4()
    with Session(engine) as session:
        session.add_all([document(kept_doc), document(gone_doc)])
        session.flush()
        on_kept = passage(kept_doc, language=language, text="Konto kostet 5 EUR.")
        on_gone = passage(gone_doc, language=language, text="Refunds take 14 days.")
        session.add_all([on_kept, on_gone])
        session.flush()
        root_fact = fact(on_kept.id, statement="Konto kostet 5 EUR.")
        sibling_fact = fact(on_kept.id, statement="Konto kostet 5 EUR. Immer.")
        session.add_all([root_fact, sibling_fact])
        session.flush()
        root = question(status="accepted", release_id=drawn, language=language)
        sibling = question(status="accepted", release_id=drawn, language=language)
        session.add_all([root, sibling])
        session.flush()
        session.add_all(
            [link(root.id, root_fact.id), link(sibling.id, sibling_fact.id)]
        )
        parent, ids = root.id, []
        for position in range(2, turns + 1):
            follow_fact = fact(on_gone.id, statement=f"Refunds take {position} days.")
            session.add(follow_fact)
            session.flush()
            follow = question(
                status="accepted",
                release_id=drawn,
                language=language,
                follows_id=parent,
                thread_position=position,
                question_text=f"Und dann, Teil {position}?",
            )
            session.add(follow)
            session.flush()
            session.add(link(follow.id, follow_fact.id))
            parent = follow.id
            ids.append(follow.id)
        session.commit()
        return gone_doc, root.id, sibling.id, ids, drawn


@pytest.mark.parametrize("language", ["de", "en", "fr"])
def test_a_follow_up_restored_under_a_re_accepted_root_is_not_released_alone(
    engine, database, buckets, monkeypatch, language
) -> None:
    """Root rejected then accepted again while its follow-up sat in the archive.

    The re-accept leaves the root accepted but undrawn (decide clears release_id
    on reject, and accept keeps what is there: NULL). The thread rule says a
    follow-up is released only with the turn it follows; the restore keeps the
    follow-up in the old release because a live sibling still holds it.
    """
    from archive import restore
    from ingestion.repository import DocumentRepository
    from question_generation.catalog import QuestionCatalog

    gone_doc, root_id, sibling_id, (follow_id,), drawn = _thread_across_two_documents(
        engine, language, 2
    )
    since = _now(engine)
    DocumentRepository().delete(gone_doc)
    QuestionCatalog().decide(root_id, "rejected")
    QuestionCatalog().decide(root_id, "accepted")
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()

    live = _rows(engine)
    assert live[root_id] == ("accepted", None)
    assert live[sibling_id][1] == drawn
    assert live[follow_id][1] is None, (
        f"follow-up {follow_id} released in {live[follow_id][1]} while root {root_id} is in no release"
    )


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_three_turn_thread_restored_under_a_rejected_root_leaves_the_release(
    engine, database, buckets, monkeypatch, language
) -> None:
    """Every turn below a rejected root comes back undrawn, and still accepted."""
    from archive import restore
    from ingestion.repository import DocumentRepository
    from question_generation.catalog import QuestionCatalog

    gone_doc, root_id, _, follows, _ = _thread_across_two_documents(engine, language, 3)
    since = _now(engine)
    DocumentRepository().delete(gone_doc)
    QuestionCatalog().decide(root_id, "rejected")
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()

    live = _rows(engine)
    assert set(follows) <= set(live)
    assert [live[one][1] for one in follows] == [None, None]
    assert [live[one][0] for one in follows] == ["accepted", "accepted"]


def test_a_follow_up_under_a_root_still_released_keeps_its_release(
    engine, database, buckets, monkeypatch
) -> None:
    """Control: nothing happened to the root, so the thread comes back whole."""
    from archive import restore
    from ingestion.repository import DocumentRepository

    gone_doc, root_id, _, follows, drawn = _thread_across_two_documents(engine, "de", 3)
    since = _now(engine)
    DocumentRepository().delete(gone_doc)
    monkeypatch.setenv("AT", chosen(engine, since))
    restore.main()

    live = _rows(engine)
    assert live[root_id][1] == drawn
    assert [live[one][1] for one in follows] == [drawn, drawn]


def test_a_fact_archived_before_it_carried_a_language_comes_back_with_one(
    corpus, engine, monkeypatch
) -> None:
    """Read again from its citation, as the revision that added the column did."""
    from archive import restore

    with engine.begin() as connection:
        connection.execute(text("UPDATE documents SET language = 'en'"))
        connection.execute(text("UPDATE facts SET language = 'en'"))
    before, since = rows(engine), now(engine)
    wipe()
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE archived_rows SET payload = payload - 'language' "
                "WHERE table_name = 'facts'"
            )
        )

    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 0

    assert rows(engine)["facts"] == before["facts"]
    assert all('"language": "en"' in one for one in before["facts"])
