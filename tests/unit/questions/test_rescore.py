"""Rewriting a stored question's scopes and band from its citations.

A question stores the criteria its facts made when it was written. When a
fact loses a citation - `make extract-dedup` takes out the ones a duplicate
refusal folded in - the stored scopes describe evidence the question no
longer has, and `reverify` rejects the row as `source_changed`. The rescore
reads them again the way `reverify` does and writes the ones that moved.
"""

from __future__ import annotations

from dataclasses import replace

from database.qa_generator import (
    Difficulty,
    DocumentScope,
    PassageScope,
    QuestionRejection,
    TopicScope,
)
from question_generation.config import Settings
from question_generation.models import JudgedQuestion
from question_generation.service import _recheck, rescore


def _stored(**columns) -> JudgedQuestion:
    """An accepted question stored as spanning two passages, now citing one."""
    return JudgedQuestion(
        **{
            "id": 2,
            "question_text": "What does the device weigh?",
            "target_answer": "4 kg",
            "answerable": True,
            "difficulty": Difficulty.MEDIUM,
            "passage_scope": PassageScope.MULTI,
            "document_scope": DocumentScope.SINGLE,
            "topic_scope": TopicScope.MULTI,
            "language": "en",
            "status": "accepted",
            "embedding": None,
            "statements": ("The device weighs 4 kg.",),
            "facts_validated": True,
            "documents": 1,
            "passages": 1,
            "topics": 1,
            "follows_id": None,
            **columns,
        }
    )


class _Catalog:
    """Holds stored questions and records what a rescore writes."""

    def __init__(self, *questions: JudgedQuestion) -> None:
        self.questions = list(questions)
        self.written: list[tuple[int, object]] = []

    def judged(self, within=None):
        yield from self.questions

    def rescore(self, rows) -> int:
        self.written += rows
        return len(rows)


def test_a_question_whose_citations_moved_is_rescored() -> None:
    """Its scopes and its band are read off what it cites now."""
    catalog = _Catalog(_stored())

    assert rescore(catalog, Settings.load()) == 1  # type: ignore[arg-type]
    ((question_id, now),) = catalog.written
    assert question_id == 2
    assert (
        now.passage_scope,
        now.document_scope,
        now.topic_scope,
        now.difficulty,
    ) == (PassageScope.SINGLE, DocumentScope.SINGLE, TopicScope.SINGLE, Difficulty.EASY)


def test_a_question_whose_citations_did_not_move_is_left_alone() -> None:
    """Nothing to write, so nothing is written."""
    still = _stored(
        passage_scope=PassageScope.SINGLE,
        topic_scope=TopicScope.SINGLE,
        difficulty=Difficulty.EASY,
    )
    catalog = _Catalog(still)

    assert rescore(catalog, Settings.load()) == 0  # type: ignore[arg-type]
    assert catalog.written == []


def test_re_verify_does_not_reject_a_row_that_was_only_rescored() -> None:
    """The footgun: scope moved under it, so re-verify rejected it before."""
    stored = _stored()
    catalog = _Catalog(stored)
    settings = Settings.load()

    before = _recheck(None, settings, stored)  # type: ignore[arg-type]
    rescore(catalog, settings)  # type: ignore[arg-type]
    ((_, now),) = catalog.written
    rescored = replace(
        stored,
        passage_scope=now.passage_scope,
        document_scope=now.document_scope,
        topic_scope=now.topic_scope,
        difficulty=now.difficulty,
    )

    assert before is not None and before[0] == QuestionRejection.SOURCE_CHANGED
    assert _recheck(None, settings, rescored) is None  # type: ignore[arg-type]


def test_a_question_on_a_fact_left_only_its_fold_is_not_rescored() -> None:
    """Its fact lost its own citation; the fold `unfold` cannot take out remains.

    Rescoring would band it by a passage its fact was only refused against,
    so it is left for re-verify, which rejects it as `source_changed`.
    """
    stranded = _stored(stranded=True)
    catalog = _Catalog(stranded)

    assert rescore(catalog, Settings.load()) == 0  # type: ignore[arg-type]
    assert catalog.written == []
    failed = _recheck(None, Settings.load(), stranded)  # type: ignore[arg-type]
    assert failed is not None and failed[0] == QuestionRejection.SOURCE_CHANGED


def test_rescore_reads_the_stored_kind(monkeypatch) -> None:
    """A row whose kind fixes a band keeps it; one that cites one passage is single."""
    from dataclasses import replace as swap

    from question_generation import kinds

    monkeypatch.setitem(
        kinds.KINDS,
        "compound",
        swap(kinds.KINDS["needs_both"], name="compound", band="medium"),
    )
    two = _stored(kind="compound", passages=2, documents=2, topics=2)
    one = _stored(id=3, kind="compound", passages=1, topics=1)
    catalog = _Catalog(two, one)

    rescore(catalog, Settings.load())  # type: ignore[arg-type]

    now = dict(catalog.written)
    assert now[2].difficulty == Difficulty.MEDIUM
    assert now[3].difficulty == Difficulty.EASY
