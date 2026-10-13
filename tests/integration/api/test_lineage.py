"""How one artefact was produced, over HTTP.

A corpus of one document, one passage, one fact, one topic and one
question, so the chain a question reports is the whole pipeline and every
edge in it is one this walks.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, membership, passage
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.qa_generator import (
    Assessment,
    AssessmentMetric,
    JudgeMetric,
    QuestionFact,
    Status,
)
from database.qa_generator import Question as QuestionRow

pytestmark = pytest.mark.integration


@pytest.fixture
def corpus(engine, database) -> dict:
    """One of each artefact, joined the way the pipeline joins them."""
    sha = digest("a")
    with Session(engine) as session:
        session.add(document(sha, title="A report", parse_status=Status.PARSED))
        held = fitted(0, label="Delivery")
        session.add(held)
        session.flush()

        at = passage(sha, ordinal=1, text="Requests are answered in 48 hours.")
        session.add(at)
        session.flush()
        session.add(membership(at.id, held.id))

        drawn = fact(at.id, statement="Requests are answered within 48 hours.")
        session.add(drawn)
        session.flush()

        asked = QuestionRow(
            question_text="How long do requests take?",
            target_answer="48 hours",
            answerable=True,
            language="en",
            status="rejected",
            rejected_reason="leaks_source",
            gates_ran=["structural", "near_duplicate", "phrasing"],
        )
        session.add(asked)
        session.flush()
        session.add(QuestionFact(question_id=asked.id, fact_id=drawn.id))
        found = {
            "document": sha,
            "passage": at.id,
            "fact": drawn.id,
            "topic": held.id,
            "question": asked.id,
        }
        session.commit()
    return found


def test_a_question_reports_the_whole_pipeline_in_order(client, corpus) -> None:
    """Five steps, numbered by the stage that produced each."""
    answered = client.get(f"/lineage/question/{corpus['question']}")

    assert answered.status_code == 200
    chain = answered.json()
    assert [(one["position"], one["kind"]) for one in chain["steps"]] == [
        (2, "document"),
        (3, "passage"),
        (4, "fact"),
        (5, "topic"),
        (6, "question"),
    ]
    assert [one["stage"] for one in chain["steps"]] == [
        "parsing",
        "chunking",
        "extraction",
        "topic_modelling",
        "question_generation",
    ]


def test_each_step_carries_the_artefact_it_produced(client, corpus) -> None:
    """The ids are the rows the corpus was built from."""
    chain = client.get(f"/lineage/question/{corpus['question']}").json()
    at = {one["kind"]: one for one in chain["steps"]}

    assert at["document"]["artifacts"][0]["id"] == corpus["document"]
    assert at["document"]["artifacts"][0]["label"] == "A report"
    assert at["fact"]["artifacts"][0]["id"] == str(corpus["fact"])
    assert at["topic"]["artifacts"][0]["label"] == "Delivery"
    assert at["question"]["artifacts"][0]["verdict"] == "rejected"
    assert at["question"]["artifacts"][0]["reason"] == "leaks_source"


def test_a_thin_verdict_reads_as_no_judgement(client, corpus, engine) -> None:
    """One metric of three answered is neither an approval nor a refusal."""
    with Session(engine) as session:
        for kind, column, metrics_due in (
            ("fact", "fact_id", 3),
            ("question", "question_id", None),
        ):
            judged = Assessment(
                artifact_kind=kind,
                assess_status=Status.ASSESSED,
                approved=False,
                assessed_at=func.now(),
                metrics_due=metrics_due,
                **{column: corpus[kind]},
            )
            session.add(judged)
            session.flush()
            session.add(
                AssessmentMetric(
                    assessment_id=judged.id,
                    metric=JudgeMetric.RELEVANCE,
                    label="relevant",
                    score=1.0,
                    approved=True,
                    explanation="on subject",
                )
            )
        session.commit()

    chain = client.get(f"/lineage/question/{corpus['question']}").json()
    at = {one["kind"]: one["artifacts"][0] for one in chain["steps"]}

    assert at["fact"]["judge"] is None
    assert at["question"]["judge"] == "refused"


def test_a_question_reports_every_gate_that_read_it(client, corpus) -> None:
    """At its fixed position, the one that refused it last and failed."""
    chain = client.get(f"/lineage/question/{corpus['question']}").json()

    assert chain["gates_recorded"] is True
    assert [
        (one["position"], one["name"], one["passed"]) for one in chain["gates"]
    ] == [
        (1, "structural", True),
        (4, "near_duplicate", True),
        (5, "phrasing", False),
    ]


def test_a_draft_a_retry_superseded_shows_no_gate_refusing_it(
    client, corpus, engine
) -> None:
    """It cleared every gate; what set it aside is the marker after them."""
    with Session(engine) as session:
        superseded = QuestionRow(
            question_text="How long do requests take to answer?",
            target_answer="48 hours",
            answerable=True,
            language="en",
            status="rejected",
            rejected_reason="duplicate",
            gates_ran=["structural", "near_duplicate", "phrasing", "round_trip"]
            + ["superseded"],
        )
        session.add(superseded)
        session.flush()
        session.add(QuestionFact(question_id=superseded.id, fact_id=corpus["fact"]))
        session.commit()
        asked = superseded.id

    chain = client.get(f"/lineage/question/{asked}").json()

    refused = [one["name"] for one in chain["gates"] if not one["passed"]]
    assert refused == ["superseded"]


def test_a_document_is_the_root_of_its_own_chain(client, corpus) -> None:
    """Nothing produced it, so it is the only step and there are no gates."""
    chain = client.get(f"/lineage/document/{corpus['document']}").json()

    assert [one["kind"] for one in chain["steps"]] == ["document"]
    assert chain["gates"] == []
    assert chain["gates_recorded"] is False


def test_a_fact_reaches_its_passage_its_document_and_its_topic(client, corpus) -> None:
    """Upwards to the two, and sideways to the topic its passage sits in."""
    chain = client.get(f"/lineage/fact/{corpus['fact']}").json()

    assert [one["kind"] for one in chain["steps"]] == [
        "document",
        "passage",
        "fact",
        "topic",
    ]


def test_an_id_nothing_holds_is_a_404(client, corpus) -> None:
    """Rather than an empty chain, which reads as an artefact with no past."""
    assert client.get("/lineage/fact/99999999").status_code == 404


def test_an_id_that_is_not_a_number_names_nothing(client, corpus) -> None:
    """Every kind but a document is keyed by a row id, and int() raises."""
    assert client.get("/lineage/fact/not-a-number").status_code == 404
    assert client.get("/lineage/question/:").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/lineage/fact/\u00b2",
        "/lineage/fact/9223372036854775808",
        "/lineage/document/a%00",
    ],
)
def test_an_id_that_names_no_row_is_not_found_rather_than_an_error(
    client, path
) -> None:
    """A Unicode digit, an id past bigint and a NUL each reached the driver."""
    assert client.get(path).status_code == 404


def test_a_step_longer_than_the_page_shows_its_first_twenty(
    client, engine, database
) -> None:
    """The twenty shown are the lowest ids, not whichever the set gave up."""
    sha = digest("b")
    with Session(engine) as session:
        session.add(document(sha, title="A long report", parse_status=Status.PARSED))
        held = fitted(0, label="Delivery")
        session.add(held)
        session.flush()
        ids = []
        for ordinal in range(1, 31):
            at = passage(sha, ordinal=ordinal, text=f"Passage {ordinal}.")
            session.add(at)
            session.flush()
            session.add(membership(at.id, held.id))
            ids.append(at.id)
        session.commit()
        topic_id = held.id

    steps = client.get(f"/lineage/topic/{topic_id}").json()["steps"]
    (passages,) = [one for one in steps if one["kind"] == "passage"]

    assert passages["total"] == 30
    assert [one["id"] for one in passages["artifacts"]] == [
        str(one) for one in sorted(ids)[:20]
    ]
