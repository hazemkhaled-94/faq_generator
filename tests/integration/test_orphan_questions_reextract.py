"""A question a re-extraction left with no fact goes with its document too, the stage that replaces facts included."""

from __future__ import annotations

import uuid

import pytest
from facts import FactStore, checked
from seed import digest, link, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

#: The statement before and after the model reads the passage again: German,
#: English, and Swahili, which no configuration names.
READINGS = [
    ("de", "Die Karte kostet 30 EUR im Jahr.", "Die Karte kostet 40 EUR im Jahr."),
    (
        "en",
        "Goods may be returned within 30 days.",
        "Goods may be returned within 14 days.",
    ),
    (
        "sw",
        "Kadi inagharimu shilingi 300 kwa mwaka.",
        "Kadi inagharimu shilingi 400 kwa mwaka.",
    ),
]


@pytest.fixture
def store(engine, database):
    """The fact store over the container's database."""
    return FactStore(engine)


def asked(engine, fact_id: int, language: str) -> int:
    """A released, reviewed question on one fact."""
    with engine.begin() as connection:
        found = connection.execute(
            text(
                "INSERT INTO questions (question_text, answerable, language, status, "
                "release_id, reviewed_verdict, reviewed_at) VALUES ('Q?', true, :lang, "
                "'accepted', gen_random_uuid(), 'accepted', now()) RETURNING id"
            ),
            {"lang": language},
        ).scalar_one()
        connection.execute(
            text("INSERT INTO question_facts VALUES (:q, :f)"),
            {"q": found, "f": fact_id},
        )
    return found


@pytest.mark.parametrize("how", ["delete", "delete_all", "delete_derived"])
@pytest.mark.parametrize(("lang", "before", "after"), READINGS)
def test_a_question_a_reextraction_left_with_no_fact_goes_with_its_document(
    store, engine, lang, before, after, how
) -> None:
    """PassageQueue.store deletes the stale citation first, so the document is read there."""
    from ingestion.repository import DocumentRepository

    store.language = lang
    seed = f"y2-{lang}-{how}"
    (held,) = store.corpus((seed, [before]))[seed]
    store.store(held, checked(held, before))
    ((fact_id,),) = store.rows("id")
    question_id = asked(engine, fact_id, lang)

    other = f"{seed}-other"
    (kept,) = store.corpus((other, ["Delivery takes 3 days."]))[other]
    store.store(kept, checked(kept, "Delivery takes 3 days."))
    ((other_fact,),) = store.rows("id", where="id <> :f", f=fact_id)
    asked(engine, other_fact, "en")

    store.store(held, checked(held, after))
    status = store._execute(
        "SELECT status, rejected_reason FROM questions WHERE id = :q", q=question_id
    )
    assert status == [("rejected", "source_changed")], status

    repository = DocumentRepository()
    if how == "delete_all":
        repository.delete_all([digest(seed)])
    else:
        getattr(repository, how)(digest(seed))

    left = store._execute("SELECT id FROM questions ORDER BY id")
    assert question_id not in [row[0] for row in left], left
    assert len(left) == 1, "the other document's question stays"


@pytest.mark.parametrize(
    ("lang", "before", "after"),
    [
        ("de", "Die Gebühr beträgt 5 EUR.", "Die Gebühr beträgt 6 EUR."),
        ("en", "The fee is 5 EUR.", "The fee is 6 EUR."),
        ("sw", "Ada ni shilingi 500.", "Ada ni shilingi 600."),
    ],
)
def test_a_wipe_after_a_reextraction_leaves_no_question(
    store, engine, lang, before, after
) -> None:
    """The wipe: delete_all over every document, after one passage was read again."""
    from ingestion.repository import DocumentRepository

    store.language = lang
    seed = f"y2-wipe-{lang}"
    (held,) = store.corpus((seed, [before]))[seed]
    store.store(held, checked(held, before))
    ((fact_id,),) = store.rows("id")
    with Session(engine) as session:
        one = question(status="accepted", release_id=uuid.uuid4(), language=lang)
        session.add(one)
        session.flush()
        session.add(link(one.id, fact_id))
        session.commit()

    store.store(held, checked(held, after))
    DocumentRepository().delete_all([digest(seed)])

    assert store._execute("SELECT count(*) FROM documents") == [(0,)]
    assert store._execute("SELECT id FROM questions") == []


@pytest.mark.parametrize(
    ("lang", "own", "repeat"),
    [
        ("de", "Die Karte kostet 30 EUR im Jahr.", "Die Karte kostet 30 EUR im Jahr."),
        ("en", "The card costs 30 EUR a year.", "The card costs 30 EUR a year."),
    ],
)
def test_deleting_a_document_that_only_repeats_a_fact_keeps_the_question_on_it(
    store, engine, lang, own, repeat
) -> None:
    """A folded fact, read from B with a further citation onto A's passage, survives A's deletion whole."""
    from ingestion.repository import DocumentRepository

    store.language = lang
    ids = store.corpus(("y2-b", [own]), ("y2-a", [repeat]))
    (on_b,), (on_a,) = ids["y2-b"], ids["y2-a"]
    store.store(on_b, checked(on_b, own))
    ((fact_id,),) = store.rows("id")
    store.folded(fact_id, on_a)
    question_id = asked(engine, fact_id, lang)

    DocumentRepository().delete(digest("y2-a"))

    assert store.rows("id") == [(fact_id,)], "the fact stays, resting on B"
    assert store._execute("SELECT id, status FROM questions") == [
        (question_id, "accepted")
    ]
