"""Extracting a passage again keeps the facts that come back as they were.

A fact re-emitted word for word keeps its id, its embedding and the questions
resting on it, so a re-extraction under unchanged code changes nothing a
question can notice. Only a fact the new reading does not repeat is deleted,
and the questions resting on it are rejected as `source_changed`, never
deleted (see `test_source_change_keeps_questions`).
"""

from __future__ import annotations

import pytest
from facts import FactStore, checked
from sqlalchemy import text

pytestmark = pytest.mark.integration

#: A passage, two statements it yields and one it yields instead, by language.
CASES = [
    (
        "de",
        "Die Karte kostet 30 EUR im Jahr. Die Gebühr wird jährlich abgebucht.",
        "Die Karte kostet 30 EUR im Jahr.",
        "Die Gebühr wird jährlich abgebucht.",
        "Die Karte kostet 40 EUR im Jahr.",
    ),
    (
        "en",
        "Goods may be returned within 30 days. Refunds are paid within 14 days.",
        "Goods may be returned within 30 days.",
        "Refunds are paid within 14 days.",
        "Refunds are paid within 10 days.",
    ),
]


@pytest.fixture
def store(engine, database):
    """A fact driver on the migrated database."""
    return FactStore(engine)


def _written(store, engine, lang, body, first, second):
    """One passage, two facts on it, and a released question on the first."""
    store.language = lang
    ids = store.corpus((f"reextract-{lang}", [body]))[f"reextract-{lang}"]
    store.store(ids[0], checked(ids[0], first), checked(ids[0], second))
    one, two = (row[0] for row in store.rows("id"))
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE facts SET embedding = array_fill(0.5::real, ARRAY[1024])::vector"
            )
        )
        asked = connection.execute(
            text(
                "INSERT INTO questions (question_text, answerable, language, status, "
                "release_id) VALUES ('Q?', true, :lang, 'accepted', gen_random_uuid()) "
                "RETURNING id"
            ),
            {"lang": lang},
        ).scalar_one()
        connection.execute(
            text("INSERT INTO question_facts VALUES (:q, :f)"), {"q": asked, "f": one}
        )
    return ids[0], one, two, asked


@pytest.mark.parametrize("lang,body,first,second,other", CASES)
def test_a_fact_that_comes_back_identical_keeps_its_id_and_questions(
    store, engine, lang, body, first, second, other
) -> None:
    """The same reading again, with the whitespace the model happened to use."""
    held, one, two, asked = _written(store, engine, lang, body, first, second)

    store.store(
        held,
        checked(held, first.replace(" ", "  ", 1), evidence_end=len(first)),
        checked(held, second),
    )

    assert [row[0] for row in store.rows("id")] == [one, two]
    assert store.rows("embedding IS NOT NULL") == [(True,), (True,)]
    assert store._execute("SELECT status, release_id IS NOT NULL FROM questions") == [
        ("accepted", True)
    ]
    assert store._execute("SELECT question_id, fact_id FROM question_facts") == [
        (asked, one)
    ]
    assert len(store.links()) == 2


@pytest.mark.parametrize("lang,body,first,second,other", CASES)
def test_a_fact_that_does_not_come_back_is_replaced_and_its_question_rejected(
    store, engine, lang, body, first, second, other
) -> None:
    """One of two facts changes: the other keeps its id, the question is kept."""
    held, one, two, asked = _written(store, engine, lang, body, first, second)

    store.store(held, checked(held, other), checked(held, second))

    ids = [row[0] for row in store.rows("id")]
    assert two in ids and one not in ids and len(ids) == 2
    assert store._execute(
        "SELECT id, status, rejected_reason, release_id FROM questions"
    ) == [(asked, "rejected", "source_changed", None)]


def test_a_fact_changing_its_citation_is_a_new_fact(store, engine) -> None:
    """The same statement over a different sentence is not the same claim."""
    store.language = "en"
    held = store.corpus(("cites", ["One. Two."]))["cites"][0]
    store.store(held, checked(held, "A claim.", evidence_sentence_ids=[0]))
    (before,) = (row[0] for row in store.rows("id"))

    store.store(held, checked(held, "A claim.", evidence_sentence_ids=[1]))

    assert [row[0] for row in store.rows("id")] != [before]


def test_another_passages_facts_are_not_touched(store, engine) -> None:
    """Two passages of one document: storing one leaves the other's facts."""
    store.language = "en"
    one, other = store.corpus(("two", ["First.", "Second."]))["two"]
    store.store(one, checked(one, "First."))
    store.store(other, checked(other, "Second."))
    ids = [row[0] for row in store.rows("id")]

    store.store(one, checked(one, "First."))

    assert [row[0] for row in store.rows("id")] == ids
