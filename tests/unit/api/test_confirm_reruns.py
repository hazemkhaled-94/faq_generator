"""A request that rebuilds a whole stage, or deletes every topic, is confirmed.

Nothing here puts back what a rerun replaces: a re-chunk or a re-extraction
rejects as `source_changed` the questions that rested on the work, reviewed
and released ones included, and a topic's label is stored nowhere else.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

HEADERS = {"x-api-token": os.environ["API_TOKEN"]}
STAGES = ("parsing", "chunking", "extraction", "questions", "assessment")


class Queue:
    """A queue that records the verbs it was asked to run."""

    def __init__(self) -> None:
        """Holds three rows and has run nothing."""
        self.ran: list[str] = []
        self.digests_asked: list[bool] = []

    def queue_state(self, within=None, *, digests=False):
        """Three rows, one of them finished."""
        from stages import QueueState

        self.digests_asked.append(digests)
        return QueueState(
            working=False,
            rows={"new": 2, "done": 1},
            digests={"new": "4f1c"} if digests else {},
        )

    def start(self, within=None, *, trigger=None) -> int:
        """Records a start."""
        self.ran.append("start")
        return 3

    def stop(self, within=None) -> int:
        """Records a stop."""
        self.ran.append("stop")
        return 0

    def retry(self, within=None, *, trigger=None) -> int:
        """Records a retry."""
        self.ran.append("retry")
        return 0

    def reset(self, within=None, *, trigger=None) -> int:
        """Records a rerun."""
        self.ran.append("rerun")
        return 3

    def reclaim(self, within=None, *, trigger=None) -> int:
        """Records a reclaim."""
        self.ran.append("reclaim")
        return 0

    def narrowed(self, scope, value):
        """Accepts any scope."""
        return


@pytest.fixture
def stage() -> tuple[TestClient, Queue]:
    """One stage router over a recording queue."""
    from api.routes.stage import stage_router

    queue = Queue()
    app = FastAPI()
    from api import errors

    errors.install(app)
    app.include_router(stage_router(name="chunking", repository=queue))  # type: ignore[arg-type]
    return TestClient(app, headers=HEADERS), queue


def test_an_unnarrowed_rerun_without_confirm_is_refused_before_a_row_moves(
    stage,
) -> None:
    """400 confirm_required, naming the stage and what it holds."""
    client, queue = stage

    answered = client.post("/chunking/rerun")

    assert answered.status_code == 400
    body = answered.json()
    assert body["code"] == "confirm_required"
    assert "chunking" in body["detail"]
    assert "3" in body["detail"]
    assert queue.ran == []


class Resting(Queue):
    """A queue that can say which questions rest on what it holds."""

    def resting(self, within=None):
        """Four questions, one released, two accepted, one reviewed."""
        from stages.resting import Resting as Counted

        return Counted(questions=4, released=1, accepted=2, reviewed=1)


def test_the_refusal_names_the_questions_at_stake_and_deletes_none() -> None:
    """Where the stage can count them: rejected as source_changed, kept."""
    from api import errors
    from api.routes.stage import stage_router

    queue = Resting()
    app = FastAPI()
    errors.install(app)
    app.include_router(stage_router(name="extraction", repository=queue))  # type: ignore[arg-type]

    detail = TestClient(app, headers=HEADERS).post("/extraction/rerun").json()["detail"]

    assert "4 question(s)" in detail
    assert "source_changed" in detail
    assert "delete" not in detail
    assert queue.ran == []


def test_a_stage_that_counts_no_questions_says_nothing_is_deleted(stage) -> None:
    """Parsing or assessment: the rows, and no claim of a deletion."""
    client, _ = stage

    detail = client.post("/chunking/rerun").json()["detail"]

    assert "delete" not in detail
    assert "question" not in detail


def test_an_unnarrowed_rerun_with_confirm_is_queued(stage) -> None:
    """The same request, confirmed."""
    client, queue = stage

    answered = client.post("/chunking/rerun?confirm=true")

    assert answered.status_code == 202
    assert queue.ran == ["rerun"]


@pytest.mark.parametrize("path", ["/chunking/status", "/chunking/passage/7/status"])
def test_a_status_read_asks_for_no_digests_unless_told_to(stage, path: str) -> None:
    """A page polls this, and the digests hash the whole queue."""
    client, queue = stage

    plain = client.get(path)
    asked = client.get(path + "?digests=true")

    assert plain.json()["digests"] == {}
    assert asked.json()["digests"] == {"new": "4f1c"}
    assert queue.digests_asked == [False, True]


@pytest.mark.parametrize("scope", ["document/" + "a" * 64, "passage/7"])
def test_a_narrowed_rerun_needs_no_confirm(stage, scope: str) -> None:
    """One item, which is what a person picked."""
    client, queue = stage

    answered = client.post(f"/chunking/{scope}/rerun")

    assert answered.status_code == 202, answered.text
    assert queue.ran == ["rerun"]


@pytest.mark.parametrize("verb", ["start", "stop", "retry"])
def test_the_other_verbs_need_no_confirm(stage, verb: str) -> None:
    """They replace nothing."""
    client, queue = stage

    assert client.post(f"/chunking/{verb}").status_code == 202
    assert queue.ran == [verb]


@pytest.mark.parametrize("name", STAGES)
def test_every_stage_built_from_the_factory_asks(name: str) -> None:
    """Parsing, chunking, extraction, questions and assessment alike."""
    from api import errors
    from api.routes.stage import stage_router

    queue = Queue()
    app = FastAPI()
    errors.install(app)
    app.include_router(stage_router(name=name, repository=queue))  # type: ignore[arg-type]

    answered = TestClient(app, headers=HEADERS).post(f"/{name}/rerun")

    assert answered.json()["code"] == "confirm_required"
    assert queue.ran == []


class Topics:
    """A topic catalogue and queue that count what a delete would take."""

    def __init__(self) -> None:
        """Holds four topics and has deleted nothing."""
        self.deleted = 0

    def counts_by_status(self) -> dict[str, int]:
        """Four topics, one fit."""
        return {"modelled": 4, "completed": 1}

    def delete_all(self):
        """Records the deletion."""
        from topic_modelling.models import TopicRemoval

        self.deleted += 1
        return TopicRemoval(topics=4, memberships=0)


@pytest.fixture
def topics(monkeypatch) -> tuple[TestClient, Topics]:
    """The topics routes over a recording catalogue."""
    from api.main import app
    from api.routes import topics as routes

    held = Topics()
    monkeypatch.setattr(routes, "topic_catalog", held)
    monkeypatch.setattr(routes, "topics_queue", held)
    return TestClient(app, base_url="http://localhost:8000", headers=HEADERS), held


def test_deleting_every_topic_without_confirm_is_refused_naming_the_count(
    topics,
) -> None:
    """Their labels are stored nowhere else."""
    client, held = topics

    answered = client.delete("/topics")

    assert answered.status_code == 400
    assert answered.json()["code"] == "confirm_required"
    assert "4" in answered.json()["detail"]
    assert held.deleted == 0


def test_deleting_every_topic_with_confirm_is_done(topics) -> None:
    """The same request, confirmed."""
    client, held = topics

    answered = client.delete("/topics?confirm=true")

    assert answered.status_code == 200, answered.text
    assert held.deleted == 1
