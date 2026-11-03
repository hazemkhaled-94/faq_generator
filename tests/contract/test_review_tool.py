"""What every review tool adapter does, run against each one there is.

`ArgillaTool` is today's, over a stand-in for Argilla's client that keeps
records, takes a reviewer's responses and answers the REST listing the pull
reads times from. The fake is the in-memory port. A reviewer is whoever
`submit`s: the rig plays them for each.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("argilla", reason="the observability group is not installed")

from fakes import FakeArgilla, FakeReviewTool

from review import datasets, service
from review.config import Settings
from review.judged import UNJUDGED
from review.records import FactRow

#: Statements in the languages of the corpus, one nobody configured, and another script.
SHOWN = {
    1: "Die Gebühr beträgt 12 Euro.",
    2: "The fee is 12 euro.",
    3: "Les frais sont de 12 euros.",
    4: "Τα τέλη είναι 12 ευρώ.",
}


def facts() -> list[tuple[FactRow, object]]:
    """Four facts, as the sample hands them over."""
    return [
        (FactRow(i, text, "Beleg", "atomic", True, None, None, "de"), UNJUDGED)
        for i, text in SHOWN.items()
    ]


class ArgillaRig:
    """`ArgillaTool` over the stand-in client."""

    def __init__(self, monkeypatch) -> None:
        """Wires the tool to the client with the facts dataset made."""
        self.client = FakeArgilla()
        self.dataset = self.client.make(datasets.dataset_name(datasets.FACTS))
        monkeypatch.setattr(datasets, "connect", lambda settings: self.client)
        self.tool = datasets.ArgillaTool(
            Settings(
                api_url="http://argilla.invalid", api_key="k", workspace="w", sample=10
            )
        )

    def submit(
        self, row_id: int, answers: dict[str, str], status: str = "submitted"
    ) -> None:
        """A reviewer answers one record."""
        self.dataset.responses.setdefault(str(row_id), []).extend(
            SimpleNamespace(question_name=q, value=v, status=status)
            for q, v in answers.items()
        )

    def empty(self) -> None:
        """Nothing pushed anywhere."""
        self.client.held.clear()


class FakeRig:
    """The fake port."""

    def __init__(self, monkeypatch) -> None:
        """Builds it."""
        self.tool = FakeReviewTool()

    def submit(
        self, row_id: int, answers: dict[str, str], status: str = "submitted"
    ) -> None:
        """A reviewer answers one record."""
        self.tool.submit(datasets.FACTS, row_id, answers, status)

    def empty(self) -> None:
        """Nothing pushed anywhere."""


@pytest.fixture(params=[ArgillaRig, FakeRig], ids=["argilla", "fake"])
def rig(request, monkeypatch):
    """Each adapter in turn."""
    return request.param(monkeypatch)


def test_pushed_rows_are_written_once_each(rig) -> None:
    """Pushing again updates rather than doubling."""
    assert rig.tool.push(datasets.FACTS, facts()) == 4
    rig.tool.push(datasets.FACTS, facts())

    assert rig.tool.pull(datasets.FACTS) == []


def test_a_submitted_answer_comes_back_with_the_text_the_reviewer_read(rig) -> None:
    """In any language, with the row it was about."""
    rig.tool.push(datasets.FACTS, facts())
    rig.submit(4, {"verdict": "rejected"})

    (answer,) = rig.tool.pull(datasets.FACTS)

    assert (answer.row_id, answer.shown, answer.values["verdict"]) == (
        4,
        SHOWN[4],
        "rejected",
    )
    assert answer.disputed is False


def test_a_draft_is_not_an_answer(rig) -> None:
    """Somebody part-way through is not a decision."""
    rig.tool.push(datasets.FACTS, facts())
    rig.submit(1, {"verdict": "accepted"}, status="draft")

    assert rig.tool.pull(datasets.FACTS) == []
    assert rig.tool.answered(datasets.FACTS) == set()


def test_two_reviewers_who_differ_make_a_disputed_answer(rig) -> None:
    """Both answers stay for a person to settle."""
    rig.tool.push(datasets.FACTS, facts())
    rig.submit(2, {"verdict": "accepted"})
    rig.submit(2, {"verdict": "rejected"})

    (answer,) = rig.tool.pull(datasets.FACTS)

    assert answer.disputed is True


def test_the_answered_records_are_the_ones_with_a_submitted_response(rig) -> None:
    """What a second push leaves out."""
    rig.tool.push(datasets.FACTS, facts())
    rig.submit(3, {"verdict": "accepted"})

    assert rig.tool.answered(datasets.FACTS) == {"3"}


def test_a_dataset_never_pushed_pulls_as_nothing_and_drop_deletes_what_there_is(
    rig,
) -> None:
    """None for never pushed; a count for what a drop took."""
    rig.tool.push(datasets.FACTS, facts())

    assert rig.tool.drop() == 1
    rig.empty()
    assert rig.tool.pull(datasets.FACTS) is None


def test_check_asks_and_creates_nothing(rig, monkeypatch) -> None:
    """A preflight."""
    if isinstance(rig, ArgillaRig):
        monkeypatch.setattr(datasets, "check", lambda settings: None)

    rig.tool.check()


def test_the_service_pulls_through_the_port(rig, monkeypatch) -> None:
    """Above the port, one answer written back by whichever adapter holds it."""
    monkeypatch.setattr(service, "review_tool", lambda settings: rig.tool)
    rig.tool.push(datasets.FACTS, facts())
    rig.submit(1, {"verdict": "accepted"})
    written = []

    class Catalog:
        def held(self, name, ids):
            return {i: SimpleNamespace(text=SHOWN[i], decided=None) for i in ids}

        def review_facts(self, verdicts):
            written.extend(verdicts)
            return len(verdicts)

    catalogs = service.Catalogs(facts=Catalog(), questions=None, topics=None)  # type: ignore[arg-type]

    assert service.pull(datasets.FACTS, None, catalogs) == 1  # type: ignore[arg-type]
    assert [(i, v) for i, v, _ in written] == [(1, "accepted")]


def test_review_tool_names_the_adapter(monkeypatch) -> None:
    """`argilla` is the default; an unknown name is refused."""
    settings = Settings(api_url="u", api_key="k", workspace="w", sample=1)
    monkeypatch.delenv("REVIEW_TOOL", raising=False)
    assert isinstance(service.review_tool(settings), datasets.ArgillaTool)
    # compose hands an unset name over empty
    monkeypatch.setenv("REVIEW_TOOL", "")
    assert isinstance(service.review_tool(settings), datasets.ArgillaTool)

    monkeypatch.setenv("REVIEW_TOOL", "elsewhere")
    with pytest.raises(ValueError, match="REVIEW_TOOL"):
        service.review_tool(settings)
