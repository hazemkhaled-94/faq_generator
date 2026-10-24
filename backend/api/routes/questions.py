"""The question generation stage, and the questions it produced.

One router for both, unlike every other stage, whose queue is under its own
verb and whose output is under a noun - `/extraction` and `/facts`. Here the
queue and the output share the word, so they share the router: the five queue
routes are declared first by `stage_router`, and the read routes are added
after it, which is what keeps `/questions/status` from being read as
`/questions/{question_id}` with a question id of `status`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Query, Response
from pydantic import BaseModel

from api.dependencies import assessment_catalog, question_catalog, questions_queue
from api.errors import ApiError, ErrorBody
from api.params import DocumentFilter, Limit, Offset, RowId, SearchText, TopicId
from api.routes.stage import stage_router
from database.qa_generator import QuestionStatus
from question_generation.config import Settings as QuestionSettings
from question_generation.models import (
    QuestionDetail,
    QuestionQuality,
    StoredQuestion,
)
from settings.store import resolved

log = logging.getLogger(__name__)

#: The columns `q` may look in, and the states a question may be filtered to
#: or moved to. Literals rather than free strings, so the OpenAPI document
#: lists them and the frontend's pickers cannot drift from what is accepted.
SearchField = Literal["question", "answer", "both"]
Decision = Literal["draft", "accepted", "rejected"]

#: The three criteria a question is classified by, and the band they feed.
#: Each is a filter on the listing and a column of the quality report, so a
#: reader can ask for the cross-document ones or the hard ones alone.
PassageScope = Literal["single_passage", "multi_passage"]
DocumentScope = Literal["single_document", "cross_document"]
TopicScope = Literal["single_topic", "multi_topic"]
Band = Literal["easy", "medium", "hard"]

#: What a question asks for, and what shape of answer that wants. Requested
#: before the question is written, so a reader can ask for the reasons or the
#: comparisons alone and a report can say which kinds came out.
QuestionType = Literal[
    "factoid",
    "definition",
    "entity",
    "enumeration",
    "condition",
    "reason",
    "procedure",
    "consequence",
    "comparison",
    "aggregation",
    "temporal",
    "implication",
    "application",
]
AnswerForm = Literal["value", "list", "explanation"]

#: How much a question asks of whoever answers it, declared by its type.
#: A different axis from the band: `difficulty` says how far the answer is
#: spread and so how hard it is to FIND, and a question reaching two
#: documents can still be a bare lookup once both are in hand.
CognitiveLevel = Literal["recall", "understand", "apply", "analyse"]

#: What an .xlsx is on the wire. Spelled out rather than guessed from the
#: extension, because a browser handed `application/octet-stream` offers to
#: save a file Excel then has to be told the type of.
WORKBOOK = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = stage_router(name="questions", repository=questions_queue)


@dataclass(frozen=True)
class GenerationPlan:
    """What generation was asked to write, as the settings say.

    Served so a reader can put the mix that was asked for beside the mix that
    came out. Every figure here is a setting, not a measurement.
    """

    types: dict[str, int]
    difficulty: dict[str, int]
    followup_types: list[str]
    per_topic: int
    unanswerable_share: float
    followup_share: float
    max_followups: int
    answer_chars: dict[str, list[int]]


@dataclass(frozen=True)
class QuestionPage:
    """One page of questions, and the total behind it."""

    total: int
    questions: list[StoredQuestion]


class QuestionFilter(BaseModel):
    """The listing's filter, which the quality report and the export share."""

    document: DocumentFilter = None
    topic: TopicId = None
    q: SearchText = None
    field: SearchField = "both"
    status: Decision | None = None
    answerable: bool | None = None
    passage_scope: PassageScope | None = None
    document_scope: DocumentScope | None = None
    topic_scope: TopicScope | None = None
    difficulty: Band | None = None
    planned_difficulty: Band | None = None
    question_type: QuestionType | None = None
    cognitive_level: CognitiveLevel | None = None
    answer_form: AnswerForm | None = None
    follows: bool | None = None
    released: bool | None = None


class QuestionWindow(QuestionFilter):
    """The filter, and the page of it the listing answers."""

    limit: Limit = 50
    offset: Offset = 0


class QuestionExport(QuestionFilter):
    """The filter, and whether the export names the facts behind each row."""

    citations: bool = True


def _where(chosen: QuestionFilter) -> dict[str, Any]:
    """The filter as the catalogue takes it, `q` as its `search`."""
    where = chosen.model_dump(include=set(QuestionFilter.model_fields))
    where["search"] = where.pop("q")
    return where


class QuestionVerdict(BaseModel):
    """What a person decided about one question.

    Only the three states the column holds. Accepting leaves the gate's
    reason on the row, beside the person's verdict.
    """

    status: Decision


@router.get("")
def questions(chosen: Annotated[QuestionWindow, Query()]) -> QuestionPage:
    """Lists generated questions, including those a gate rejected.

    `follows` narrows to the follow-ups or to the roots: true for questions
    asked after another, false for the ones that start a thread.

    `released` narrows to the release the last balanced draw chose: true for
    the questions in it, false for every other.

    `difficulty` is the band the question turned out to be and
    `planned_difficulty` is the one the plan asked for; the two disagreeing is
    what says how often a wide sample produced a wide question.
    """
    total, rows = question_catalog.page(
        limit=chosen.limit, offset=chosen.offset, **_where(chosen)
    )
    return QuestionPage(total=total, questions=rows)


@router.get("/plan")
def plan() -> GenerationPlan:
    """Reports what generation is configured to write.

    The mix of types and bands, the shares, and the answer bounds each form
    is held to. Read per request, stored values included: what the next run
    will do rather than what the last one did.

    A stored value that no longer loads, one written before a check that
    now refuses it, is logged and the files' values are reported instead.
    The worker still refuses to start on it; the page drawing this plan
    draws the panel that clears it, and a 500 here drew neither.
    """
    try:
        settings = QuestionSettings.load(resolved())
    except ValueError as refused:
        log.warning(
            "questions plan: the stored settings do not load, so the plan "
            "reports the files' values: %s",
            refused,
        )
        settings = QuestionSettings.load()
    return GenerationPlan(
        types=settings.type_mix,
        difficulty=settings.difficulty_mix,
        followup_types=list(settings.followup_types),
        per_topic=settings.per_topic,
        unanswerable_share=settings.unanswerable_share,
        followup_share=settings.followup_share,
        max_followups=settings.max_followups,
        answer_chars={
            form: list(bounds) for form, bounds in settings.answer_chars.items()
        },
    )


@router.get("/quality")
def quality(chosen: Annotated[QuestionFilter, Query()]) -> QuestionQuality:
    """Reports how generation is doing, under the same filter.

    The numbers that say whether the questions are questions: how many
    cleared every gate, which gate stopped the rest, which kinds were written,
    how the three criteria are spread, and how much of the corpus's subject
    matter is covered at all.
    """
    return question_catalog.quality(**_where(chosen))


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {WORKBOOK: {}}, "description": "An .xlsx workbook"}},
)
def export(chosen: Annotated[QuestionExport, Query()]) -> Response:
    """Writes the questions this filter selects to an .xlsx workbook.

    Every filter is the listing's, so what downloads is what the page was
    showing rather than a set chosen here. There is no default scope: a
    request naming nothing gets everything, the rejected questions
    included, because that is what the same request to the listing gets.

    `citations` turns off the sheet naming the facts behind each question.
    It is the expensive half over a whole corpus and the questions alone
    are enough to run a benchmark from.

    What an independent judge made of each question goes in too, where the
    evaluation phase has run. Not optional, unlike the citations: it is one
    query over the questions already selected, and a benchmark shipped
    without the second opinion recorded against it is the workbook this
    phase exists to stop somebody sending.

    Declared before `/{question_id}` so `export` is not read as an id.
    """
    # Imported here rather than at the top of the module: `export` loads
    # pandas and openpyxl, this process serves JSON, and one route that is
    # called by hand should not be a cost every other route pays for at
    # start-up. The same deferral `topic_modelling` uses for pyLDAvis.
    # `tests/static/test_api_stays_light.py` reads imports as syntax and
    # skips the ones inside a function, which is what makes the two agree.
    from question_generation.export import workbook

    where = _where(chosen)
    # Unlimited, rather than counting and then asking for a window that
    # size. Those were two statements with a gap between them: a question
    # written into the gap did not fit the window the count had already
    # decided on, and the export quietly came up one row short of the
    # figure printed on its own Summary sheet.
    # And the citations and the counts from that same session, one moment.
    with question_catalog.snapshot() as read:
        _, rows = question_catalog.page(limit=None, read=read, **where)
        cited = (
            question_catalog.citations(read=read, **where) if chosen.citations else ()
        )
        quality = question_catalog.quality(read=read, **where)
    # ponytail: the whole workbook is built in memory before the first byte
    # is sent; the upgrade is a StreamingResponse over openpyxl's write-only
    # mode.
    drawn = workbook(
        rows,
        cited,
        quality,
        assessment_catalog.verdicts_for("question", [one.id for one in rows]),
        questions_queue.never_asked(),
    )
    return Response(
        content=drawn,
        media_type=WORKBOOK,
        headers={"content-disposition": 'attachment; filename="questions.xlsx"'},
    )


@router.get("/{question_id}", responses={404: {"model": ErrorBody}})
def question(question_id: RowId) -> QuestionDetail:
    """Reads one question with the facts it was written from.

    Raises:
        ApiError: 404 `unknown_question` if no question has that id.
    """
    found = question_catalog.detail(question_id)
    if found is None:
        raise ApiError(404, "unknown_question", "no question with that id")
    return found


@router.patch("/{question_id}", responses={404: {"model": ErrorBody}})
def decide(question_id: RowId, verdict: QuestionVerdict) -> StoredQuestion:
    """Accepts or rejects one question.

    A rejected question keeps its row whoever rejected it: the share that
    was thrown away is the evidence behind the coverage report, and a
    deleted row is a drop nobody can count.

    Raises:
        ApiError: 404 `unknown_question` if no question has that id.
    """
    decided = question_catalog.decide(question_id, QuestionStatus(verdict.status))
    if decided is None:
        raise ApiError(404, "unknown_question", "no question with that id")
    return decided
