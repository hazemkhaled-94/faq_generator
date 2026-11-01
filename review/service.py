"""Pushing rows out for review, and pulling the verdicts back.

Two directions and one rule: the database decides. Argilla holds a copy of
what was put in front of somebody and the answers they gave, and `pull`
brings the answers home. Delete the Argilla dataset and nothing in the
pipeline is lost; delete the rows and the copy is meaningless.

A pull takes only submitted answers. Argilla keeps a draft the moment a
reviewer touches a record, and a draft is somebody part-way through
thinking rather than a decision.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from review import datasets
from review.config import Settings
from review.judged import UNJUDGED, Opinion, opinions
from review.records import ReviewRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """One record somebody answered, as the tool hands it back."""

    #: The database id of the row it was about.
    row_id: int
    #: The text the reviewer read, to see the row still reads that way.
    shown: str
    #: When the latest submitted answer was given.
    at: datetime
    #: Whether two reviewers submitted different answers to one question.
    disputed: bool
    #: What was submitted for each question, a draft not counting.
    values: dict[str, str | None]


class ReviewTool(Protocol):
    """Where a person looks at what the models decided, and says whether they agree.

    The sample, and what is done with an answer, stay above it: the database
    decides. The tool shows rows and returns what was submitted.
    `REVIEW_TOOL` names the adapter, and `argilla` is the only one there is.
    """

    def check(self) -> None:
        """Asks the tool who it is, creating nothing.

        Raises:
            Exception: Whatever it raises when the address is wrong or the key
                is refused, which is what a preflight is for.
        """
        ...

    def answered(self, name: str) -> set[str]:
        """The ids of the records of one dataset that carry a submitted answer."""
        ...

    def push(self, name: str, rows: Sequence[tuple[Any, Opinion]]) -> int:
        """Shows rows, each with the machine's verdict, and returns how many were written."""
        ...

    def pull(self, name: str) -> list[Answer] | None:
        """Every submitted answer, or None when nothing has been pushed there yet."""
        ...

    def drop(self) -> int:
        """Deletes the datasets, answers and all, and returns how many went."""
        ...


def review_tool(settings: Settings) -> ReviewTool:
    """The adapter REVIEW_TOOL names, `argilla` unless told otherwise.

    Raises:
        ValueError: If it names none that exists.
    """
    adapter = os.environ.get("REVIEW_TOOL", "argilla")
    if adapter == "argilla":
        return datasets.ArgillaTool(settings)
    raise ValueError(
        f"REVIEW_TOOL={adapter!r} names no adapter; the one there is is argilla"
    )


@dataclass(frozen=True)
class Catalogs:
    """Where each kind of verdict is read from and written back to.

    The existing catalogues, not new queries. A topic renamed here and a
    topic renamed on the Topics page have to be the same write, or the
    provenance the two record drifts apart - `describe` is what sets
    labelled_by to `person`, and a second path that forgot to would leave
    a human label looking like the model's.
    """

    #: Facts: the sample, and the only verdict with no route of its own.
    facts: ReviewRepository
    #: Questions: `decide`, which PATCH /questions/{id} also calls.
    questions: Any
    #: Topics: `describe`, which PATCH /topics/{id} also calls.
    topics: Any
    #: What the LLM judge said about each row, attached to the record so a
    #: reviewer sees both machine verdicts. None reads as "nobody judged
    #: anything", which is the honest answer for a deployment with the
    #: evaluation phase switched off - and is what keeps a push working
    #: without one.
    judge: Any = None


def check(settings: Settings) -> None:
    """Asks the review tool who it is, creating nothing.

    Raises:
        Exception: Whatever the tool raises when the address is wrong or the
            key is refused, which is what a preflight is for.
    """
    review_tool(settings).check()


def push(
    name: str,
    settings: Settings,
    catalogs: Catalogs,
    ids: Sequence[int] | None = None,
    everything: bool = False,
) -> int:
    """Puts one kind of row in front of a reviewer.

    `ids` names exactly which questions to push instead of sampling, which
    is how a queue built elsewhere - the Assessment page's
    disagreements - reaches a reviewer. Questions only; the other two sets
    have no such queue behind them.

    `everything` pushes the corpus rather than a draw from it. The two
    answer different questions and both are worth having: a sample is
    "is the checker right", small enough that somebody finishes it; the
    whole set is "where is the artefact I am looking for", which a draw
    cannot answer because the row wanted may not be in it. One dataset per
    kind either way, so the two never mix in one place.

    Returns:
        How many records were written.
    """
    tool = review_tool(settings)
    draw = None if everything else settings.sample

    if name == datasets.FACTS:
        # Less what the tool holds an answer to, as for questions below.
        judged = tool.answered(name)
        rows = [one for one in catalogs.facts.facts(draw) if str(one.id) not in judged]
        kind = "fact"
    elif name == datasets.QUESTIONS:
        # What says a sample has nothing left to ask about this row. The
        # draw already skips one `questions.reviewed_verdict` holds; this
        # reads the tool as well, because the two are not the same set: a
        # verdict submitted in the UI and not yet pulled is in the tool and
        # not in the column, and pushing that row again asks somebody to
        # judge it twice.
        # Never for an explicit queue: naming an id asks for that row.
        judged = set() if ids else tool.answered(name)
        rows = [
            one
            for one in catalogs.facts.questions(draw, ids)
            if str(one.id) not in judged
        ]
        kind = "question"
    else:
        # Every topic, not a sample. A corpus has dozens, not thousands,
        # and a topic left unreviewed is one whose name nobody checked.
        rows = catalogs.topics.topics()
        kind = "topic"
    said = opinions(catalogs.judge, kind, [one.id for one in rows])
    shown = [(one, said.get(one.id, UNJUDGED)) for one in rows]

    if not shown:
        log.info("%s: nothing left to review", name)
        return 0
    return tool.push(name, shown)


def drop(settings: Settings) -> int:
    """Deletes the three review datasets, and says how many went.

    The facts, the topic labels and the questions, by their current names.
    A dataset under any other name in the workspace is left.

    The opposite decision from a push, which reuses what it finds
    precisely so a push never throws away an answer nobody has pulled. This
    throws them away on purpose: `make wipe` deletes the corpus, and a
    dataset of facts that no longer exist is a reviewer being asked about
    rows nothing can apply their verdict to.

    Pull before wiping if the verdicts matter. Nothing here warns about
    that, because `wipe` already says what it is about to do and asks for CONFIRM.

    Returns:
        How many datasets were deleted.
    """
    return review_tool(settings).drop()


def pull(name: str, settings: Settings, catalogs: Catalogs) -> int:
    """Brings submitted verdicts back into the database.

    Returns:
        How many rows were written.
    """
    submitted = review_tool(settings).pull(name)
    if submitted is None:
        log.info("%s: no such dataset; nothing has been pushed yet", name)
        return 0

    rows = catalogs.facts.held(name, [one.row_id for one in submitted])
    answered, moved, later, disputed = [], 0, 0, []
    for one in submitted:
        row = rows.get(one.row_id)
        if row is None or row.text != one.shown:
            moved += 1
        elif row.decided is not None and row.decided >= one.at:
            later += 1
        elif one.disputed:
            disputed.append(one.row_id)
        else:
            answered.append(one)
    if moved:
        log.warning(
            "%s: %d answer(s) skipped because the row with that id no longer "
            "reads as the record does, so the answer is about another row",
            name,
            moved,
        )
    if later:
        log.info(
            "%s: %d answer(s) skipped because the row was decided at or after "
            "the answer was given: pulled already, or decided since",
            name,
            later,
        )
    if disputed:
        log.warning(
            "%s: %d record(s) skipped because their reviewers disagree; both "
            "answers stay in the review tool for a person to settle: %s",
            name,
            len(disputed),
            ", ".join(map(str, disputed)),
        )

    if name == datasets.FACTS:
        written = catalogs.facts.review_facts(
            [
                (one.row_id, verdict, one.at)
                for one in answered
                if (verdict := one.values.get("verdict")) is not None
            ]
        )
    elif name == datasets.QUESTIONS:
        dated = [
            (one.row_id, one.at)
            for one in answered
            if (verdict := one.values.get("verdict")) is not None
            and catalogs.questions.decide(one.row_id, verdict)
        ]
        catalogs.facts.date_questions(dated)
        written = len(dated)
    else:
        written = 0
        overlong: list[int] = []
        for one in answered:
            label = (one.values.get("corrected_label") or "").strip()
            if len(label) > LABEL_MAX:
                overlong.append(one.row_id)
                continue
            coverage = one.values.get("in_coverage")
            # Unanswered leaves the coverage as it is.
            include = None if coverage is None else coverage != "no"
            if label:
                written += bool(
                    catalogs.topics.describe(
                        one.row_id,
                        label=label,
                        include_in_coverage=include,
                        at=one.at,
                    )
                )
            elif include is not None:
                # No name keeps the topic's label and its labelled_by.
                written += catalogs.facts.cover(one.row_id, include, one.at)
        if overlong:
            # Stored, the page would draw the name cut and a Save write it so.
            log.warning(
                "%s: %d answer(s) skipped because the corrected name is longer "
                "than the %d characters PATCH /topics and the Topics page take; "
                "shorten it and pull again: %s",
                name,
                len(overlong),
                LABEL_MAX,
                ", ".join(map(str, overlong)),
            )

    log.info("%s: %d verdict(s) written", name, written)
    return written


#: The longest topic name PATCH /topics takes, which the Topics page holds
#: too; a static test holds it to the route's.
LABEL_MAX = 120
