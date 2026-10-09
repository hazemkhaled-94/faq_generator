"""The queue surface every stage shares, over HTTP.

Four verbs, each twice: once for the whole queue and once narrowed to what
a scope names. None of them does the work; they move rows between statuses
and answer with how many moved.
"""

from __future__ import annotations

import pytest
from seed import digest, document, passage
from sqlalchemy.orm import Session

from database.qa_generator import Status

pytestmark = pytest.mark.integration

#: Every stage built from `stage_router`, and a scope each accepts.
STAGES = ("parsing", "chunking", "extraction")


@pytest.fixture
def corpus(client, engine):
    """Two documents, one with two passages, all waiting to be asked for.

    `a` is parsed and `b` is not, so both stages that queue over `documents`
    have something to move: parsing has the row it has not done, chunking
    has the one it can. A corpus where neither was parsed had nothing
    chunking could queue - `ChunkQueue.ready` refuses a document with no
    parsed form, because the only outcome of queueing one is a failure.
    """
    with Session(engine) as session:
        session.add_all(
            [
                document(digest("a"), parse_status=Status.PARSED),
                document(digest("b")),
            ]
        )
        session.flush()
        session.add_all(
            [
                passage(digest("a"), ordinal=1),
                passage(digest("a"), ordinal=2),
                passage(digest("b"), ordinal=1),
            ]
        )
        session.commit()
    return client


@pytest.mark.parametrize("stage", STAGES)
def test_a_stage_reports_its_queue(corpus, stage) -> None:
    """One shape for every stage, whatever it queues over."""
    answered = corpus.get(f"/{stage}/status")

    assert answered.status_code == 200
    body = answered.json()
    assert body["stage"] == stage
    assert body["working"] is False
    assert body["scope"] is None and body["value"] is None
    assert sum(body["rows"].values()) > 0


@pytest.mark.parametrize("stage", STAGES)
def test_starting_a_stage_answers_202_with_what_moved(corpus, stage) -> None:
    """Returns at once: the worker picks the rows up on its next poll."""
    answered = corpus.post(f"/{stage}/start")

    assert answered.status_code == 202
    body = answered.json()
    assert body["action"] == "start"
    assert body["rows"] > 0
    assert "queued" in body["detail"]


@pytest.mark.parametrize(
    ("stage", "column"),
    [
        ("parsing", "documents.parse_trigger"),
        ("chunking", "documents.chunk_trigger"),
        ("extraction", "passages.extract_trigger"),
    ],
)
def test_a_verb_that_queues_answers_with_the_run_it_queued_under(
    corpus, engine, stage, column
) -> None:
    """Minted here when the caller names none, and answered back.

    Somebody who pressed a button has to be able to find the rows it
    produced afterwards, and the row carries this and not the id of the
    worker that happens to claim it.
    """
    from sqlalchemy import text

    answered = corpus.post(f"/{stage}/start").json()

    table, name = column.split(".")
    with engine.connect() as connection:
        stamped = connection.execute(
            text(f"SELECT DISTINCT {name} FROM {table} WHERE {name} IS NOT NULL")
        ).scalars()
        assert set(stamped) == {answered["run"]}


@pytest.mark.parametrize("stage", STAGES)
def test_a_caller_that_already_has_a_run_keeps_it(corpus, stage) -> None:
    """Dagster passes its own, which is what joins a run to its rows."""
    answered = corpus.post(f"/{stage}/start?run=dagster-run-7").json()

    assert answered["run"] == "dagster-run-7"


@pytest.mark.parametrize("stage", STAGES)
def test_stop_queues_nothing_and_so_names_no_run(corpus, stage) -> None:
    """There is nothing to attribute: the rows went back to `new`."""
    corpus.post(f"/{stage}/start")

    assert corpus.post(f"/{stage}/stop").json()["run"] is None


@pytest.mark.parametrize("stage", STAGES)
def test_a_verb_that_moves_nothing_says_so(corpus, stage) -> None:
    """The count and the wording come from the same place."""
    answered = corpus.post(f"/{stage}/retry")

    assert answered.status_code == 202
    assert answered.json()["rows"] == 0
    assert "nothing has failed" in answered.json()["detail"]


@pytest.mark.parametrize("stage", STAGES)
def test_the_verbs_round_trip_the_queue(corpus, stage) -> None:
    """Start makes rows claimable, stop makes them new again."""
    queued = corpus.post(f"/{stage}/start").json()["rows"]

    taken_back = corpus.post(f"/{stage}/stop").json()["rows"]

    assert taken_back == queued
    assert corpus.get(f"/{stage}/status").json()["rows"].get("pending", 0) == 0


@pytest.mark.parametrize("stage", STAGES)
def test_a_verb_no_stage_has_is_refused(corpus, stage) -> None:
    """The verbs are a Literal, so anything else never reaches a queue."""
    assert corpus.post(f"/{stage}/obliterate").status_code == 422


@pytest.mark.parametrize(
    ("stage", "held"), [("parsing", 1), ("chunking", 1), ("extraction", 2)]
)
def test_a_stage_narrowed_to_a_document_reports_only_that_one(
    corpus, stage, held
) -> None:
    """The same shape, with the scope and value it was asked about."""
    answered = corpus.get(f"/{stage}/document/{digest('a')}/status")

    assert answered.status_code == 200
    body = answered.json()
    assert body["scope"] == "document"
    assert body["value"] == digest("a")
    assert sum(body["rows"].values()) == held, body["rows"]


def test_a_narrowed_verb_moves_only_that_documents_rows(corpus) -> None:
    """One document's passages, not the corpus's."""
    answered = corpus.post(f"/extraction/document/{digest('a')}/start")

    assert answered.status_code == 202
    assert answered.json()["rows"] == 2


def test_extraction_narrows_to_one_passage(corpus, engine) -> None:
    """It queues over passages, so it answers for one of those too."""
    from sqlalchemy import text

    with engine.connect() as connection:
        first = connection.execute(text("SELECT min(id) FROM passages")).scalar_one()

    answered = corpus.post(f"/extraction/passage/{first}/start")

    assert answered.status_code == 202
    assert answered.json()["rows"] == 1


def test_a_scope_a_stage_does_not_take_is_refused_as_404(corpus) -> None:
    """Parsing queues over documents and knows nothing of a passage."""
    answered = corpus.get("/parsing/passage/1/status")

    assert answered.status_code == 404
    assert answered.json()["code"] == "unknown_scope"
    assert "document" in answered.json()["detail"]


def test_a_value_the_column_cannot_hold_is_refused_as_400(corpus) -> None:
    """Refused here rather than as a database error."""
    answered = corpus.get("/extraction/passage/not-a-number/status")

    assert answered.status_code == 400
    assert answered.json()["code"] == "invalid_value"


@pytest.mark.parametrize(
    "path",
    [
        "/extraction/passage/99999999999999999999/status",
        "/parsing/document/a%00/status",
        "/extraction/passage/99999999999999999999/start",
    ],
)
def test_a_value_past_what_a_column_holds_is_refused_not_an_error(corpus, path) -> None:
    """An id past bigint and a NUL each reached the driver and answered 500."""
    verb = corpus.post if path.endswith("start") else corpus.get

    assert verb(path).status_code in (400, 422)


@pytest.mark.parametrize("run", ["a%00b", "r" * 200])
def test_a_run_name_no_column_should_hold_is_refused(corpus, run) -> None:
    """`run` is written into every queued row's run column."""
    assert corpus.post(f"/parsing/start?run={run}").status_code == 422
    assert (
        corpus.post(f"/parsing/document/{digest('b')}/start?run={run}").status_code
        == 422
    )
    assert corpus.post(f"/topics/discover?run={run}").status_code == 422
    assert corpus.post(f"/topics/retry?run={run}").status_code == 422


def test_a_narrowing_that_selects_nothing_is_not_an_error(corpus) -> None:
    """A document with no rows for this stage is a count of zero."""
    answered = corpus.post(f"/parsing/document/{digest('unknown')}/start")

    assert answered.status_code == 202
    assert answered.json()["rows"] == 0


# ── reclaim ────────────────────────────────────────────────────────────────
#
# The one verb that had no route. It used to be command-line only because
# "the api cannot know a worker is gone" - but neither can the command line,
# and a person driving this over HTTP was left with the single stuck row that
# `retry` (which takes the failed), `rerun` (which skips what is held) and
# `stop` (which takes back only what has not begun) all step over.
#
# What the danger needs is a narrowing, not an absence: nothing can tell a
# dead claim from a live one, so the whole-stage form asks to be confirmed.


@pytest.fixture
def held(client, engine):
    """A document a worker claimed and never came back from."""
    with Session(engine) as session:
        session.add(document(digest("a"), parse_status=Status.IN_PROGRESS))
        session.commit()
    return client


def test_reclaiming_one_item_returns_it_to_the_queue(held) -> None:
    """Narrowed, which is how it is meant to be used while a worker is up."""
    answered = held.post(f"/parsing/document/{digest('a')}/reclaim")

    assert answered.status_code == 202
    body = answered.json()
    assert body["action"] == "reclaim" and body["rows"] == 1
    assert held.get("/parsing/status").json()["rows"] == {"pending": 1}


def test_reclaiming_a_whole_stage_is_refused_without_a_confirmation(held) -> None:
    """It can take a row from a worker that is still on it."""
    answered = held.post("/parsing/reclaim")

    assert answered.status_code == 400
    assert answered.json()["code"] == "confirm_required"
    assert "Narrow it" in answered.json()["detail"]
    assert held.get("/parsing/status").json()["rows"] == {"in_progress": 1}


def test_a_confirmed_reclaim_over_a_whole_stage_is_allowed(held) -> None:
    """For when the stage is stopped and the person knows it."""
    answered = held.post("/parsing/reclaim?confirm=true")

    assert answered.status_code == 202
    assert answered.json()["rows"] == 1


def test_reclaim_leaves_rows_no_worker_holds_alone(corpus) -> None:
    """Only `in_progress` is its business."""
    assert corpus.post("/parsing/reclaim?confirm=true").json()["rows"] == 0


def test_confirming_is_only_asked_for_reclaim(corpus) -> None:
    """The other four verbs cannot hand a live worker's row to a second."""
    assert corpus.post("/parsing/start").status_code == 202


# ── enrol ──────────────────────────────────────────────────────────────────


def test_enrolling_creates_the_rows_without_queuing_any(client, engine) -> None:
    """The dry run: what `start` would cost, before paying for it."""
    answered = client.post("/assessment/enrol")

    assert answered.status_code == 202
    assert answered.json()["action"] == "enrol"
    assert client.get("/assessment/status").json()["rows"].get("pending", 0) == 0


def test_enrol_is_not_read_as_a_queue_verb(client) -> None:
    """`POST /assessment/{action}` would otherwise match it first."""
    assert client.post("/assessment/enrol").status_code != 422
