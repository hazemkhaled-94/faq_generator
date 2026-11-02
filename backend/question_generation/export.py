"""The questions as a spreadsheet, and the command line that writes one.

The dataset had no way out. Every other reader of these rows is a service -
the API pages them, the frontend tables them, Argilla samples them - and a
person who wanted the set itself had psql and nothing else. Argilla is not
that way out either, and it is the near miss worth naming: it holds a
**disposable copy of a stratified sample** pushed for review, so exporting
from it gives back the hundred rows somebody was asked to look at rather
than the set. The database is what has the set.

So: one workbook, four sheets.

- **Questions** - one row per question, the columns a reader filters on,
  and what that question rests on: the facts it cites, the evidence under
  them, its subjects, the documents by name, the answer at length and why
  the judge said what it did. One row is readable on its own, because a
  reader filtering this sheet to the refused questions should not have to
  join another by id to see what any of them cited.
- **Citations** - one row per (question, fact, passage), which is what an
  answer is checked against. A bridge cites two passages and so takes two
  rows. Still here beside the folded-up version above: this is the grain
  that carries the page number and the passage ordinal, which is what
  somebody checking an answer against the source needs.
- **Assessment** - one row per (question, judgement), which is what an
  independent model made of each answer. Empty unless the evaluation phase
  has run.
- **Summary** - what the filter selected, as counts. Written so a workbook
  mailed to somebody says what it is without them having to pivot it.

The judgements arrive as an argument rather than being read here. This
package must not import `assessment` - no backend service imports another,
which `.importlinter` enforces - so the two callers that already hold a
catalogue each look them up and hand them over.

**The filter is the caller's and there is no default scope.** Not "the
release", not "everything accepted": whatever the same filter the listing
and the quality report take says, so the workbook is the thing on screen
and a reader cannot be handed a set narrower than they asked for without
having asked for it.

The workbook is written as it is read: openpyxl's write-only mode, from rows
drawn through a server-side cursor, so the api holds a batch of them and not
the corpus. Nothing here builds a frame.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict
from functools import partial
from itertools import islice
from typing import IO, Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from database.qa_generator.outcomes import AnswerForm, QuestionType
from question_generation.models import Citation, QuestionQuality, StoredQuestion
from question_generation.queue import NeverAsked

log = logging.getLogger(__name__)

#: The Summary rows that say what no accepted question reaches. `assessment`
#: reads them back by these words (no service imports another), and a test
#: holds the two together.
NEVER_DOCUMENTS = "Documents with facts and no accepted question"
NEVER_PASSAGES = "Passages with facts never asked"

#: The Questions sheet, as (column in the frame, heading in the workbook).
#: Named rather than dumped, because a dataclass field order is not a thing
#: to show somebody and `answer_chars` beside `target_answer` reads as two
#: answers.
_COLUMNS = (
    ("id", "ID"),
    ("question_text", "Question"),
    ("target_answer", "Answer"),
    ("answer_explanation", "Answer in full"),
    # Filled after the frame is built, as the judge's columns are: the turns
    # before a follow-up and the documents, pages and sections a question
    # was drawn from. A row a tester reads should stand on its own.
    ("earlier", "Earlier turns"),
    ("source", "Source"),
    ("answerable", "Answerable"),
    ("question_type", "Type"),
    # The span of the answer's passages (single, needs_both, compound), so a
    # question with no answer reads `single`: filter on Answerable first. The
    # heading carries that note, for the tester who reads only the workbook.
    ("kind", "Kind"),
    ("answer_form", "Answer form"),
    ("cognitive_level", "Cognitive level"),
    # The band is how far a question's sources are spread, not how hard it is
    # to reason about: see `_SPREAD`.
    ("difficulty", "Retrieval spread"),
    ("passage_scope", "Passage scope"),
    ("document_scope", "Document scope"),
    ("topic_scope", "Topic scope"),
    ("thread_position", "Turn"),
    ("follows_id", "Follows"),
    ("language", "Language"),
    # What its writer was told the question is, as `categorization=category`.
    # Blank where it was told nothing, which a compound question and a
    # follow-up always are, and an unanswerable one told no kind.
    ("categories", "Categories"),
    ("status", "Status"),
    ("released", "Released"),
    ("reviewed_verdict", "Reviewed"),
    # Filled from the `judged` argument rather than off the row: a question
    # carries no judgement of its own, and this package cannot read the
    # table that does. Blank where the evaluation phase has not run.
    ("judge", "Judge"),
    ("judge_refused", "Judge refused by"),
    ("judge_why", "Why the judge said so"),
    ("facts", "Facts cited"),
    # Two sets, not pairs: each is de-duplicated on its own, so the nth
    # line of one is not the nth line of the other. The Citations sheet is
    # what puts a fact beside the sentence it was drawn from.
    ("statements", "The facts it cites"),
    ("evidence", "The evidence they rest on"),
    ("topics", "Topics"),
    ("documents", "Documents"),
    ("document_ids", "Document IDs"),
    ("created_at", "Written"),
    # What the pipeline kept about it, after everything a tester reads.
    ("planned_difficulty", "Spread planned"),
    ("attempt", "Attempt"),
    ("rejected_reason", "Gate"),
    # How close the weakest measuring gate came to refusing it. A margin
    # and not a probability - see `confidence.py` - and blank on a question
    # no measuring gate read, which is not the same as a low one.
    ("confidence", "Confidence"),
)

#: What the `difficulty` band measures, which is not how hard a question is
#: to reason about: a question's points are the passages, the documents and the
#: subjects it rests on, a long answer and following another question, and
#: nothing weighs them. Said in the workbook because a tester reads a score by
#: band, and a band that reads as hardness invites the wrong conclusion.
_SPREAD = (
    "easy, medium or hard by how many passages, documents and subjects a "
    "question rests on, a long answer and a follow-up counting a point each: "
    "the spread a retriever has to cover, not of how hard the question is to "
    "reason about"
)

#: Fields whose list is written one item per line rather than comma-joined.
#: A comma between two sentences reads as one sentence, and both of these
#: hold sentences. The cells are wrapped, so the lines show.
_LINES = frozenset({"statements", "evidence"})

_CITATION_COLUMNS = (
    ("question_id", "Question ID"),
    ("statement", "Fact"),
    ("evidence_text", "Evidence"),
    ("validated", "Fact still valid"),
    ("document", "Document"),
    ("doc_sha256", "Document ID"),
    ("first_page", "First page"),
    ("last_page", "Last page"),
    ("section_path", "Section"),
    ("ordinal", "Passage"),
    ("fact_id", "Fact ID"),
)

#: The Assessment sheet. One row per judgement rather than per question,
#: because a question is judged six times and a reader wants to sort on
#: which judgement failed.
_ASSESSMENT_COLUMNS = (
    "Question ID",
    "Judgement",
    "Answer",
    "Approved",
    "Score",
    "Why",
    "Judge",
)

#: How wide each heading's column is drawn, by the heading. Anything not
#: named here is sized from its heading, which is right for the short
#: coded columns and wrong for exactly the four long ones.
_WIDTHS = {
    "Earlier turns": 60,
    "Source": 50,
    "Question": 60,
    "Answer": 50,
    "Answer in full": 60,
    "Fact": 60,
    "Evidence": 60,
    "Topics": 30,
    "Documents": 30,
    "Why": 70,
    "Judge refused by": 26,
    "Why the judge said so": 70,
    "The facts it cites": 60,
    "The evidence they rest on": 60,
}

#: Columns whose text is wrapped rather than run off under the next cell.
_WRAPPED = frozenset(_WIDTHS)

#: Data rows an .xlsx sheet holds below its header: Excel's 1,048,576 rows,
#: less the heading. A sheet that would pass it goes on in a numbered one.
_SHEET_ROWS = 1_048_575

#: Rows read, looked up and written together. The judge's verdicts are asked
#: for in batches this size, so the lookup never holds every question.
_CHUNK = 500

#: What a cell starting with one of these is to a spreadsheet: a formula, or a
#: signed number when edited, or re-imported as CSV. Marked as text.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

#: Beyond this, a cell is truncated. Excel refuses a cell over 32,767
#: characters outright, and a workbook that raises at the last row is worse
#: than one that marks the row.
_CELL_LIMIT = 32_000


#: How much of a document's digest the sheets carry as its id.
_ID_CHARS = 12


def _flatten(value: Any, joiner: str = ", ") -> Any:
    """Renders one field as a cell.

    Lists become a joined string - a spreadsheet has no cell type for a
    list, and `str(list)` would put Python's brackets and quotes in front
    of a reader. Long text is cut at the limit Excel enforces, with the cut
    marked so nobody reads a truncated answer as a short one.

    `joiner` is a comma for the short coded lists and a newline for the two
    holding sentences, which a comma would run together into one.
    """
    if isinstance(value, (list, tuple)):
        value = joiner.join(str(item) for item in value)
    if isinstance(value, str) and len(value) > _CELL_LIMIT:
        return value[:_CELL_LIMIT] + "… [truncated]"
    return value


_WRAP = Alignment(wrap_text=True, vertical="top")

#: A note on a heading whose values read wrong without it.
_NOTES = {
    "Kind": (
        "The span of the answer's passages: single, needs_both or compound. A "
        "question with no answer reads single, so filter on Answerable first."
    ),
}
_BOLD = Font(bold=True)


def _printable(value: Any) -> Any:
    """Drops the control characters openpyxl refuses from one cell."""
    return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value


class _Sheet:
    """One sheet of the workbook, written row by row.

    Continued in a numbered sheet (`Citations 2`) with the same headings
    where it would pass Excel's row limit, which nothing else checks.
    """

    def __init__(self, book: Workbook, name: str, headings: Sequence[str]) -> None:
        """Opens the first sheet, headings written."""
        self._book = book
        self._name = name
        self._headings = list(headings)
        self._part = 0
        self._title = name
        self._rows = 0
        self.total = 0
        self._open()

    def _open(self) -> None:
        """Starts the next sheet: frozen headings, sized columns, bold heading row."""
        self._part += 1
        title = self._name if self._part == 1 else f"{self._name} {self._part}"
        # Beside the sheet it continues, not after the Summary.
        beside = (
            None if self._part == 1 else self._book.sheetnames.index(self._title) + 1
        )
        self._title = title
        sheet = self._book.create_sheet(title, beside)
        sheet.freeze_panes = "A2"
        for index, heading in enumerate(self._headings, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = _WIDTHS.get(
                heading, min(max(len(str(heading)) + 2, 10), 24)
            )
        row = []
        for heading in self._headings:
            cell = WriteOnlyCell(sheet, value=heading)
            cell.font = _BOLD
            if heading in _NOTES:
                cell.comment = Comment(_NOTES[heading], "qa_generator")
            row.append(cell)
        sheet.append(row)
        self._sheet = sheet
        self._rows = 0

    def _cell(self, heading: str, value: Any) -> Any:
        """One value as a cell: text kept text, wrapped where the column is."""
        value = _printable(_flatten(value))
        quoted = isinstance(value, str) and value.startswith(_FORMULA_STARTS)
        wrapped = heading in _WRAPPED
        if not (quoted or wrapped):
            return value
        cell = WriteOnlyCell(self._sheet, value=value)
        if isinstance(value, str):
            # openpyxl stores a string starting with = as a formula, which
            # Excel runs when the workbook is opened.
            cell.data_type = "s"
        if quoted:
            cell.quotePrefix = True
        if wrapped:
            cell.alignment = _WRAP
        return cell

    def append(self, values: Sequence[Any]) -> None:
        """Writes one row, in a new sheet if this one is full."""
        if self._rows >= _SHEET_ROWS:
            self._seal()
            self._open()
        self._sheet.append(
            [
                self._cell(head, value)
                for head, value in zip(self._headings, values, strict=True)
            ]
        )
        self._rows += 1
        self.total += 1

    def _seal(self) -> None:
        """Filters the headings of the sheet being left, if it holds a row."""
        if self._rows:
            last = get_column_letter(len(self._headings))
            self._sheet.auto_filter.ref = f"A1:{last}{self._rows + 1}"

    def close(self) -> None:
        """Finishes the last sheet."""
        self._seal()


def _turns(turns: Sequence[tuple[str, str | None]]) -> str:
    """The turns before a question, a line each for what was asked and the key."""
    return "\n".join(
        f"Q: {question}\nA: {answer or 'not in the material'}"
        for question, answer in turns
    )


def _source(question: StoredQuestion, cited: Sequence[Citation]) -> str:
    """Where a question was drawn from: document, pages and section, a line each.

    Without citation rows, the documents are all there is to name.
    """
    lines: list[str] = []
    for one in cited:
        pages = ""
        if one.first_page is not None:
            last = one.last_page
            pages = f"p. {one.first_page}" + (
                f"–{last}" if last not in (None, one.first_page) else ""
            )
        line = ", ".join(
            part for part in (one.document, pages, one.section_path or "") if part
        )
        if line not in lines:
            lines.append(line)
    return "\n".join(lines) or "\n".join(question.documents)


def _question_row(
    question: StoredQuestion,
    found: Any,
    earlier: Sequence[tuple[str, str | None]] = (),
    cited: Sequence[Citation] = (),
) -> list[Any]:
    """One question as the Questions sheet's cells, in `_COLUMNS` order.

    The judge's three columns are filled from `found` rather than read off
    the row, because `StoredQuestion` carries no judgement and this package
    cannot read the table that does. An unanswerable question has no key:
    what a good reply does for its kind stands in, a criterion for a judge
    or a person, never a string to match. Blank where none was stored.
    """
    fields = asdict(question)
    row = {
        heading: _flatten(fields.get(field), "\n" if field in _LINES else ", ")
        for field, heading in _COLUMNS
    }
    row["Earlier turns"] = _turns(earlier)
    row["Source"] = _source(question, cited)
    if not question.answerable and question.behaviour:
        row["Answer"] = _flatten(f"Expected behaviour: {question.behaviour}")
    row["Judge"] = _verdict(found)
    row["Judge refused by"] = (
        ", ".join(getattr(found, "refused", ()) or ()) if found is not None else ""
    )
    row["Why the judge said so"] = _reasoning(found)
    return [row[heading] for _, heading in _COLUMNS]


def _reasoning(one: Any) -> str:
    """Every judgement about one question, one per line.

    Beside the verdict rather than only on the Assessment sheet: a reader
    sorting the questions by what the judge refused wants the reason in the
    row they are looking at, and a judgement with no reasoning beside it is
    a label nobody can check.

    The same rendering `review/judged.py` gives a reviewer, written twice
    because it cannot be imported: that module reaches the assessments
    through `assessment.repository`, and no backend service imports
    another.
    """
    if one is None:
        return ""
    return "\n".join(
        f"{metric.metric}: {metric.label} — {metric.explanation}"
        for metric in one.metrics or ()
    )


def _verdict(one: Any) -> str:
    """How one question's judgement reads in a cell.

    `not judged` rather than blank, and the distinction is the point: a
    blank cell in a spreadsheet reads as "no problem found", and a question
    nobody judged is not one the judge approved.
    """
    if one is None or one.approved is None:
        return "not judged"
    return "approved" if one.approved else "refused"


#: What the judge's figures are and are not, said where they are read.
_JUDGE_READING = (
    "a model's opinion of the questions in this workbook, which is not a "
    "random draw of the set: a count of approvals is not a quality estimate"
)


class _Tally:
    """What the Summary counts of the questions written, kept as they pass.

    Counted while the rows go by, so the Summary needs neither the questions
    nor their verdicts after the batch they came in.
    """

    def __init__(self) -> None:
        """Starts with nothing written."""
        self.languages: Counter[str] = Counter()
        self.judgeable = 0
        self.judged: Counter[str] = Counter()
        self.approved = 0
        self.disagreeing = 0
        self.models: set[str] = set()
        self.templates: set[str] = set()

    def add(self, question: StoredQuestion, found: Any) -> None:
        """Counts one question and the verdict it was found with, if any."""
        self.languages[question.language] += 1
        if (
            question.answerable
            and question.target_answer
            and question.status != "draft"
        ):
            self.judgeable += 1
        if found is None or found.approved is None:
            return
        self.judged[question.language] += 1
        self.approved += bool(found.approved)
        self.disagreeing += bool(found.disagrees)
        if found.judge_model:
            self.models.add(str(found.judge_model))
        if found.prompt_version:
            self.templates.add(str(found.prompt_version))


def _summary(
    quality: QuestionQuality | None,
    tally: _Tally,
    cited: int,
    judged: bool,
    never: NeverAsked | None = None,
) -> list[tuple[str, Any, str | None]]:
    """The Summary sheet's rows: what this workbook holds, as counts and notes.

    Reads the quality report the API already serves rather than counting
    again, so the figures in the workbook are the figures on the page it
    was exported from.

    The judge's figures are counted over THIS workbook's questions
    rather than read off the corpus-wide report, because a workbook that
    says "38 disagreements" about a filter holding twelve questions is
    describing something the reader cannot see. What they are counted
    against goes beside them: how many of the questions the judge can judge,
    by language, and which model and template judged. `judged` is whether
    anything was asked of the judge at all.

    A count is a number, so a measure that is words (a model, a template, how
    to read a band) goes in the Note column, and the Count column stays
    numeric.
    """
    rows: list[tuple[str, Any, str | None]] = [
        ("Questions in this workbook", sum(tally.languages.values()), None),
        *(
            (f"Questions in this workbook: {code}", n, None)
            for code, n in sorted(tally.languages.items())
        ),
        ("Citation rows", cited, None),
    ]
    if judged:
        rows += [
            ("Judgeable (answerable)", tally.judgeable, None),
            ("Judged by a model", sum(tally.judged.values()), None),
            *(
                (f"Judged by a model: {code}", tally.judged[code], None)
                for code in sorted(tally.languages)
                if tally.judged.get(code)
            ),
            ("Judge approved", tally.approved, None),
            (
                "Kept by the pipeline, refused by the judge",
                tally.disagreeing,
                None,
            ),
            ("Judge model", None, ", ".join(sorted(tally.models)) or None),
            ("Judge template", None, ", ".join(sorted(tally.templates)) or None),
            ("Reading the judge", None, _JUDGE_READING),
        ]
    if never is not None:
        # Under the filter, as every count here: what no accepted question it
        # selects reaches, in its documents and topic.
        rows += [
            (NEVER_DOCUMENTS, len(never.documents), None),
            (NEVER_PASSAGES, never.passages, None),
            *(
                (f"{NEVER_DOCUMENTS}: {name}", held, None)
                for name, held in never.documents
            ),
        ]
    if quality is not None:
        measured = asdict(quality)
        rows += [
            ("Matching the filter", measured.get("total"), None),
            ("Accepted", measured.get("accepted"), None),
            ("Unanswerable", measured.get("unanswerable"), None),
            ("Subjects covered", measured.get("topics_covered"), None),
            ("Subjects in coverage", measured.get("topics_in_coverage"), None),
            ("Retrieval spread", None, _SPREAD),
        ]
        for name in (
            "difficulty",
            "question_type",
            "kind",
            "categories",
            "writer_model",
            "verifier_model",
            "phrasing_model",
            "cognitive_level",
            "rejected",
        ):
            shown = "retrieval spread" if name == "difficulty" else name
            for key, value in sorted((measured.get(name) or {}).items()):
                rows.append((f"{shown}: {key}", value, None))
    return rows


#: What the judge is asked about a batch of questions: the verdicts by
#: question id, whatever holds them.
Verdicts = Callable[[list[int]], Mapping[int, Any]]

#: The turns before each follow-up of a batch of questions, by question id.
Earlier = Callable[
    [list[StoredQuestion]], Mapping[int, Sequence[tuple[str, str | None]]]
]


def _held(held: Mapping[int, Any], ids: list[int]) -> Mapping[int, Any]:
    """The verdicts a mapping holds for these questions."""
    return {one: held[one] for one in ids if one in held}


def _turns_held(
    held: Mapping[int, Sequence[tuple[str, str | None]]], batch: list[StoredQuestion]
) -> Mapping[int, Sequence[tuple[str, str | None]]]:
    """The turns a mapping holds for these questions."""
    return {one.id: held[one.id] for one in batch if one.id in held}


def write(
    target: str | IO[bytes],
    questions: Iterable[StoredQuestion],
    citations: Iterable[Citation] = (),
    quality: QuestionQuality | None = None,
    judged: Mapping[int, Any] | Verdicts | None = None,
    never: NeverAsked | None = None,
    earlier: Mapping[int, Sequence[tuple[str, str | None]]] | Earlier | None = None,
) -> None:
    """Writes the workbook to a path or a file, a batch at a time.

    Rows are taken from `questions` and `citations` as they are written, the
    judge's verdicts and the turns before each follow-up are asked for per
    batch, so what is held at once is a batch whatever the corpus. Pass
    generators. Both are read in question order: a batch's Source column is
    made of the citations up to its last question, which is how they arrive
    from the catalogue.

    `judged` is either a mapping of a question's id to what an independent
    model made of it, as `assessment.models.StoredAssessment`, or a function
    taking a list of ids and returning that mapping for them. Passed in
    rather than read here, and typed loosely for the same reason: no backend
    service imports another, so this one is handed the verdicts by whichever
    caller already holds a catalogue. None leaves the Assessment sheet empty
    and the three Judge columns reading `not judged`, which is a deployment
    that has never run the evaluation phase. `earlier` is the same, a mapping
    or a function of a batch of questions.
    """
    lookup = judged if judged is None or callable(judged) else partial(_held, judged)
    turns = (
        earlier
        if earlier is None or callable(earlier)
        else partial(_turns_held, earlier)
    )

    book = Workbook(write_only=True)
    asked = _Sheet(book, "Questions", [head for _, head in _COLUMNS])
    cites = _Sheet(book, "Citations", [head for _, head in _CITATION_COLUMNS])
    judgements = _Sheet(book, "Assessment", _ASSESSMENT_COLUMNS)
    summary = _Sheet(book, "Summary", ["Measure", "Count", "Note"])

    tally = _Tally()
    drawn = iter(citations)
    waiting = next(drawn, None)
    stream = iter(questions)
    while batch := list(islice(stream, _CHUNK)):
        found = lookup([one.id for one in batch]) if lookup is not None else {}
        before = turns(batch) if turns is not None else {}
        # The citations of every question up to the batch's last, written to
        # their sheet as they are taken and kept for the batch's Source column.
        cited: dict[int, list[Citation]] = {}
        while waiting is not None and waiting.question_id <= batch[-1].id:
            cited.setdefault(waiting.question_id, []).append(waiting)
            _append_citation(cites, waiting)
            waiting = next(drawn, None)
        for question in batch:
            one = found.get(question.id)
            asked.append(
                _question_row(
                    question,
                    one,
                    before.get(question.id, ()),
                    cited.get(question.id, ()),
                )
            )
            tally.add(question, one)
            if one is None:
                continue
            for metric in one.metrics or ():
                judgements.append(
                    [
                        question.id,
                        metric.metric,
                        metric.label,
                        "yes" if metric.approved else "no",
                        metric.score,
                        metric.explanation,
                        one.judge_model,
                    ]
                )
    while waiting is not None:
        _append_citation(cites, waiting)
        waiting = next(drawn, None)
    for measure in _summary(quality, tally, cites.total, judged is not None, never):
        summary.append(list(measure))
    for sheet in (asked, cites, judgements, summary):
        sheet.close()
    book.save(target)
    log.info(
        "wrote a workbook of %d question(s), %d citation row(s) and %d "
        "judgement row(s)",
        asked.total,
        cites.total,
        judgements.total,
    )


def _append_citation(sheet: _Sheet, citation: Citation) -> None:
    """One citation as a row of the Citations sheet."""
    fields = asdict(citation)
    # The document column carries the digest's head.
    fields["doc_sha256"] = fields["doc_sha256"][:_ID_CHARS]
    sheet.append([fields.get(field) for field, _ in _CITATION_COLUMNS])


def workbook(
    questions: Iterable[StoredQuestion],
    citations: Iterable[Citation] = (),
    quality: QuestionQuality | None = None,
    judged: Mapping[int, Any] | Verdicts | None = None,
    never: NeverAsked | None = None,
    earlier: Mapping[int, Sequence[tuple[str, str | None]]] | Earlier | None = None,
) -> bytes:
    """Builds the workbook, and returns it as the bytes of an .xlsx file.

    For a caller that wants the bytes: the frontend hands them to a download
    button and the tests read them back. The api and the command line call
    :func:`write`, which keeps no more than a batch in memory. Questions and
    citations are put in question order here, as `write` takes them.
    """
    buffer = io.BytesIO()
    write(
        buffer,
        sorted(questions, key=lambda one: one.id),
        sorted(citations, key=lambda one: one.question_id),
        quality,
        judged,
        never,
        earlier,
    )
    return buffer.getvalue()


def parser() -> argparse.ArgumentParser:
    """Builds the export command line.

    Every filter is the one the listing route takes, spelled the same way,
    so a workbook can be asked for with what a page was narrowed by.
    """
    built = argparse.ArgumentParser(
        prog="python -m question_generation.export",
        description="Write the questions a filter selects to an .xlsx file.",
    )
    built.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="where to write the workbook",
    )
    built.add_argument("--status", choices=("draft", "accepted", "rejected"))
    built.add_argument("--document", metavar="SHA256", help="one document's sha256")
    built.add_argument("--topic", type=int, metavar="ID")
    built.add_argument(
        "--question-type",
        dest="question_type",
        choices=[one.value for one in QuestionType],
    )
    built.add_argument("--difficulty", choices=("easy", "medium", "hard"))
    built.add_argument(
        "--planned-difficulty",
        dest="planned_difficulty",
        choices=("easy", "medium", "hard"),
        help="the band the plan asked for, as against the one it came out",
    )
    built.add_argument(
        "--cognitive-level",
        dest="cognitive_level",
        choices=("recall", "understand", "apply", "analyse"),
    )
    built.add_argument(
        "--answer-form",
        dest="answer_form",
        choices=[one.value for one in AnswerForm],
    )
    built.add_argument(
        "--passage-scope",
        dest="passage_scope",
        choices=("single_passage", "multi_passage"),
    )
    built.add_argument(
        "--document-scope",
        dest="document_scope",
        choices=("single_document", "cross_document"),
    )
    built.add_argument(
        "--topic-scope", dest="topic_scope", choices=("single_topic", "multi_topic")
    )
    built.add_argument("--search", metavar="TEXT", help="what the search box takes")
    built.add_argument(
        "--field", choices=("question", "answer", "both"), default="both"
    )
    answerable = built.add_mutually_exclusive_group()
    answerable.add_argument(
        "--answerable", action="store_true", help="only the ones with an answer"
    )
    answerable.add_argument(
        "--unanswerable", action="store_true", help="only the ones without"
    )
    # A follow-up cannot be read without the turn before it, so an exam set
    # wants `--roots-only` and a conversational benchmark wants the threads.
    follows = built.add_mutually_exclusive_group()
    follows.add_argument(
        "--roots-only",
        action="store_true",
        help="drop the follow-ups, which cannot be asked on their own",
    )
    follows.add_argument(
        "--followups-only", action="store_true", help="only the follow-ups"
    )
    built.add_argument(
        "--released",
        action="store_true",
        help="only the release the last questions-balance drew",
    )
    built.add_argument(
        "--no-citations",
        action="store_true",
        help="leave the Citations sheet empty, which is much faster on a "
        "whole corpus and enough when only the questions are wanted",
    )
    return built


def main(argv: list[str] | None = None) -> int:
    """Writes one workbook from the command line.

    Returns:
        The process exit code.
    """
    import telemetry
    from assessment.repository import AssessmentCatalog
    from database.qa_generator import engine
    from question_generation.catalog import QuestionCatalog

    args = parser().parse_args(sys.argv[1:] if argv is None else argv)

    telemetry.configure("questions-export")
    telemetry.trace_engine(engine())

    answerable = True if args.answerable else (False if args.unanswerable else None)
    follows = True if args.followups_only else (False if args.roots_only else None)
    where: dict[str, Any] = {
        "document": args.document,
        "topic": args.topic,
        "search": args.search,
        "field": args.field,
        "status": args.status,
        "answerable": answerable,
        "follows": follows,
        "released": True if args.released else None,
        "question_type": args.question_type,
        "difficulty": args.difficulty,
        "planned_difficulty": args.planned_difficulty,
        "cognitive_level": args.cognitive_level,
        "answer_form": args.answer_form,
        "passage_scope": args.passage_scope,
        "document_scope": args.document_scope,
        "topic_scope": args.topic_scope,
    }

    catalog = QuestionCatalog()
    assessments = AssessmentCatalog()

    def verdicts(ids: list[int]) -> Mapping[int, Any]:
        """What the judge made of these questions.

        The catalogue is imported inside `main`, like the one beside it:
        `write` is also called by the api, and no backend service may import
        another - this is the command line rather than the library, and it
        is allowed to know about both.
        """
        return assessments.verdicts_for("question", ids)

    # Every row, from one snapshot, drawn as they are written: the rows, the
    # citations and the counts are one moment, and the process holds a batch.
    with catalog.snapshot() as read, open(args.out, "wb") as handle:
        write(
            handle,
            catalog.stream(read=read, **where),
            () if args.no_citations else catalog.citations(read=read, **where),
            catalog.quality(read=read, **where),
            verdicts,
            catalog.never_asked(read=read, **where),
            lambda batch: catalog.earlier(batch, read=read),
        )
    log.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
