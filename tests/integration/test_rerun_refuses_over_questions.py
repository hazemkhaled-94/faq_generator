"""A rerun that would replace what questions rest on refuses without force.

`chunk-rerun` and `extract-rerun` replace passages and facts, and a question
resting on what they replace is rejected as `source_changed`. A person who
accepted, reviewed or released those questions has to say so (FORCE=1, or
`force=true` on the route) after being told how many there are.
"""

from __future__ import annotations

import uuid

import pytest
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import Status

pytestmark = pytest.mark.integration

CASES = [
    ("de", "Die Karte kostet 30 EUR im Jahr."),
    ("en", "Goods may be returned within 30 days."),
]


@pytest.fixture
def written(engine, database):
    """Two parsed documents; questions rest on the first one only.

    Three questions rest on `a`: one released, one accepted and not released,
    and one rejected that a person reviewed. A draft, which counts for nothing,
    rests on it too.
    """

    def write(lang: str, statement: str):
        with Session(engine) as session:
            session.add_all(
                [
                    document(digest("a"), language=lang, parse_status=Status.PARSED),
                    document(digest("b"), language=lang, parse_status=Status.PARSED),
                ]
            )
            session.flush()
            held = passage(digest("a"), text=statement, language=lang)
            other = passage(digest("b"), text=statement, language=lang)
            session.add_all([held, other])
            session.flush()
            one, two = fact(held.id, statement=statement), fact(other.id)
            session.add_all([one, two])
            session.flush()
            asked = [
                question(status="accepted", release_id=uuid.uuid4(), language=lang),
                question(status="accepted", language=lang),
                question(
                    status="rejected",
                    language=lang,
                    reviewed_verdict="rejected",
                    reviewed_at=text("now()"),
                ),
                question(status="draft", language=lang),
            ]
            session.add_all(asked)
            session.flush()
            session.add_all(link(one_question.id, one.id) for one_question in asked)
            session.commit()
            return held.id, other.id

    return write


def _rerun(stage: str, *argv: str) -> None:
    """Runs one stage's command line with a service that does nothing."""
    from extraction.repository import PassageQueue
    from preprocessing.chunking.repository import ChunkQueue
    from stages import cli

    class Service:
        """Drains nothing."""

        def drain(self, stopping=None) -> int:
            """Drains nothing."""
            return 0

    cli.queue_main(
        name=stage,
        module=f"{stage}.run",
        repository={"chunking": ChunkQueue, "extraction": PassageQueue}[stage],
        build_service=Service,  # pyright: ignore[reportArgumentType]
        argv=list(argv),
    )


def _statuses(engine, column: str) -> list[str]:
    table = "documents" if column == "chunk_status" else "passages"
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                text(f"SELECT {column} FROM {table} ORDER BY id")
                if table == "passages"
                else text(f"SELECT {column} FROM {table} ORDER BY sha256")
            )
        ]


@pytest.fixture(autouse=True)
def _no_telemetry(monkeypatch):
    """The command line sets up tracing for a drain; none is wanted here."""
    from stages import cli

    monkeypatch.setattr(cli.telemetry, "configure", lambda *a, **k: None)
    monkeypatch.setattr(cli.telemetry, "trace_engine", lambda engine: None)


@pytest.mark.parametrize("lang,statement", CASES)
@pytest.mark.parametrize(
    "stage,column", [("chunking", "chunk_status"), ("extraction", "extract_status")]
)
def test_a_rerun_over_questions_refuses_and_names_them(
    engine, written, lang, statement, stage, column
) -> None:
    """Nothing is queued, and the message counts what rests on it."""
    written(lang, statement)
    before = _statuses(engine, column)

    with pytest.raises(SystemExit) as refusal:
        _rerun(stage, "--rerun")

    message = str(refusal.value)
    assert "3 question(s)" in message
    assert "1 released" in message and "2 accepted" in message
    assert "1 reviewed" in message
    assert "FORCE=1" in message
    assert _statuses(engine, column) == before


@pytest.mark.parametrize("lang,statement", CASES)
@pytest.mark.parametrize(
    "stage,column", [("chunking", "chunk_status"), ("extraction", "extract_status")]
)
def test_a_forced_rerun_queues_everything(
    engine, written, lang, statement, stage, column
) -> None:
    """With --force the rerun goes ahead as it always did."""
    written(lang, statement)

    _rerun(stage, "--rerun", "--force")

    assert set(_statuses(engine, column)) == {"pending"}


@pytest.mark.parametrize("lang,statement", CASES)
def test_a_rerun_narrowed_to_a_document_nothing_rests_on_is_not_refused(
    engine, written, lang, statement
) -> None:
    """Only what the narrowing would replace is counted."""
    written(lang, statement)

    _rerun("chunking", "--rerun", "--only", f"document={digest('b')}")
    _rerun("extraction", "--rerun", "--only", f"document={digest('b')}")

    assert _statuses(engine, "chunk_status").count("pending") == 1
    assert _statuses(engine, "extract_status").count("pending") == 1


def test_a_rerun_narrowed_to_the_document_the_questions_rest_on_is_refused(
    engine, written
) -> None:
    """The same narrowing as the route's, by document and by passage."""
    held, _ = written("en", "Goods may be returned within 30 days.")

    with pytest.raises(SystemExit, match="3 question"):
        _rerun("chunking", "--rerun", "--only", f"document={digest('a')}")
    with pytest.raises(SystemExit, match="3 question"):
        _rerun("extraction", "--rerun", "--only", f"passage={held}")


@pytest.mark.parametrize("lang,statement", CASES)
@pytest.mark.parametrize("stage", ["chunking", "extraction"])
def test_the_route_refuses_the_same_rerun_with_a_409(
    client, written, lang, statement, stage
) -> None:
    """Whole-queue and narrowed, until force=true is sent."""
    held, _ = written(lang, statement)
    scoped = (
        f"/chunking/document/{digest('a')}/rerun"
        if stage == "chunking"
        else f"/extraction/passage/{held}/rerun"
    )

    for path in (f"/{stage}/rerun", scoped):
        refused = client.post(path)
        assert refused.status_code == 409, path
        assert refused.json()["code"] == "questions_rest_on_it"
        assert "3 question(s)" in refused.json()["detail"]

        assert client.post(path, params={"force": "true"}).status_code == 202


@pytest.mark.parametrize("stage", ["chunking", "extraction"])
def test_the_route_does_not_refuse_a_corpus_no_question_rests_on(
    client, engine, database, stage
) -> None:
    """Nothing to lose, nothing to refuse."""
    with Session(engine) as session:
        session.add(document(digest("c"), parse_status=Status.PARSED))
        session.flush()
        session.add(passage(digest("c")))
        session.commit()

    assert client.post(f"/{stage}/rerun").status_code == 202
