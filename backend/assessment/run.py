"""Command-line entry point for the assessment phase.

Every flag is the same operation as the route beside it under /assessment.
Run with --help for the list. `--diversity` is the exception: a report on an
exported workbook, which no route serves and no setting governs.

The one thing this stage does that no other does is refuse to run at all:
`ASSESSMENT_ENABLED` off means the queue verbs move nothing and a drain
claims nothing, said once and clearly rather than by silently finding an
empty queue.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from functools import cache, lru_cache
from math import floor, isnan
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import telemetry
from assessment import prompts
from assessment.config import OFF, UNNAMED, Settings, judged_kinds
from assessment.factory import build_service, judge_model
from assessment.repository import AssessmentQueue
from llm.check import before_work
from llm.config import Settings as ModelSettings
from settings import decimal, integer, optional, required
from settings.store import snapshot
from stages.cli import _ready, queue_main
from stages.prompts import record

if TYPE_CHECKING:
    # For the annotation only: the assess-worker never loads numpy.
    from numpy.typing import ArrayLike

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Runs the assessment command line."""

    def configured() -> tuple[Settings, ModelSettings, str]:
        """Reads the settings as they stand, and what that configuration is.

        Called rather than captured, so every operation below answers to a
        value written since this process started.
        """
        source, version = snapshot("assessment")
        return Settings.load(source), ModelSettings.load(source), version

    argv = sys.argv[1:] if argv is None else argv

    # Before the flag: the report reads a workbook and asks no model, so the
    # phase being off is no reason to refuse it. By hand, because
    # queue_main's parser takes the queue verbs only.
    if "--diversity" in argv:
        return diversity([one for one in argv if one != "--diversity"])

    # The flag alone, and deliberately not through `configured`: that one
    # also reads the model settings, which are required and have no
    # default. A deployment with this phase off and no LLM_MODEL set is a
    # perfectly ordinary deployment, and it must not be stopped at
    # start-up by a setting for a model nothing is going to call.
    #
    # Read through `_ready`, the wait every worker's first read goes through,
    # so a stored row the catalogue refuses makes a worker wait in place, as
    # the other stages do, and a one-off run say so and exit 1.
    # ponytail: argv read by hand, as for --status below.
    watching = "--watch" in argv
    phase: list[bool] = []

    def switched() -> None:
        """Reads ASSESSMENT_ENABLED as the stored rows leave it."""
        phase[:] = [Settings.load(snapshot("assessment")[0]).enabled]

    if not _ready("assessment", switched, watching):
        return 1
    if not phase[0]:
        telemetry.configure("assessment", tracing=False)
        log.info("%s", OFF)
        # A worker waits in place rather than exiting: under `restart:
        # unless-stopped` an exit is a restart every few seconds, and the
        # Assessment page switches the flag on without restarting anything.
        if not watching:
            return 0
        _ready("assessment", switched, True)
        while not phase[0]:
            time.sleep(decimal("WORKER_POLL_SECONDS"))
            _ready("assessment", switched, True)
        log.info("ASSESSMENT_ENABLED is on, so the worker starts claiming work")

    def build():
        """Builds the service, naming the model it will ask."""
        settings, model, version = configured()
        asked = judge_model(settings, model)
        log.info(
            "judging %s with %s",
            ", ".join(judged_kinds(settings)),
            asked.model,
        )
        return build_service(settings, model, version)

    def preflight() -> None:
        """Proves the judge answers before an artefact is claimed."""
        settings, model, _ = configured()
        before_work(judge_model(settings, model))

    def record_prompts() -> int:
        """Records what the judge asks, under the model that judges.

        `judge_model` and not the shared one: ASSESSMENT_JUDGE_MODEL is the
        whole point of this phase - an opinion the pipeline did not already
        hold - and a template published against the writer's model is one
        the playground replays against the wrong model.
        """
        settings, model, _ = configured()
        return record(
            prompts.SERVICE, prompts.catalogue(), judge_model(settings, model)
        )

    def queue() -> AssessmentQueue:
        """The queue this stage claims from."""
        settings, _, _ = configured()
        return AssessmentQueue(
            kinds=judged_kinds(settings),
            sample=settings.sample,
        )

    #: Enrolling without queuing: it writes the `new` rows and says how many
    #: artefacts this phase would judge before anybody commits to paying for
    #: them.
    extra = {
        "enrol": (
            (
                "create an assessment for every artefact that has none, "
                "without queuing any of them. What `--start` does first, "
                "on its own"
            ),
            "enrolled",
            lambda within: queue().enrol(),
        ),
    }

    code = queue_main(
        name="assessment",
        module="assessment.run",
        repository=queue,
        build_service=build,
        argv=argv,
        extra=extra,
        preflight=preflight,
        prompts=record_prompts,
    )
    # Logged after queue_main, which configures the logs.
    # ponytail: argv read by hand, so an abbreviated `--stat` skips this line;
    # the upgrade is a status hook on queue_main.
    if "--status" in argv and not Settings.load(snapshot("assessment")[0]).judge_model:
        log.warning("%s", UNNAMED)
    return code


def diversity(argv: list[str]) -> int:
    """Prints how varied a workbook's questions are, one row per language.

    The workbook is what `make questions-export` writes, and its filter
    chooses the set: the paper measured answerable questions, which is
    `--status accepted --answerable --roots-only`. Each language is measured
    on its own, and with `--size` at that many questions drawn from each, so
    two sets are compared at one size. `--against` compares two workbooks
    the way the paper tests two methods: each language of both drawn fifty
    times to 80% of the smaller, and every metric's two lists of scores put
    to Welch's t-test. `--by category` measures each category of each
    language on its own, then says how many of each category's questions
    keep to its word bounds and how many are factoid and open-ended, and
    `--by kind` measures each kind. Where the workbook holds the paper's
    judge, its mean scores follow, over the same groups. With `--labels`, each
    share a reviewer labelled on some of the questions follows, corrected by
    the judge's verdict on all of them.
    """
    parser = argparse.ArgumentParser(
        prog="python -m assessment.run --diversity",
        description="How varied an exported workbook's questions are.",
    )
    parser.add_argument("--file", required=True, type=Path, help="an exported workbook")
    parser.add_argument(
        "--against", type=Path, metavar="FILE", help="a second workbook to compare with"
    )
    parser.add_argument("--language", metavar="CODE", help="measure one language only")
    parser.add_argument(
        "--size", type=int, metavar="N", help="draw N questions from each language"
    )
    parser.add_argument(
        "--by",
        choices=(*_BY, "document"),
        help="one row per category or per kind of each language, or the "
        "few-documents curve",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        metavar="FILE",
        help="reviewers' labels of some questions, to correct each share by the "
        "judge's verdict",
    )
    args = parser.parse_args(argv)
    for named in (args.file, args.against, args.labels):
        if named is not None and not named.is_file():
            parser.error(f"{named} is not a file")
    if args.size is not None and args.size < 1:
        parser.error("--size takes a whole number of at least 1")
    if args.size is not None and args.against is not None:
        parser.error("--against draws 80% of the smaller set; it takes no --size")
    if args.by is not None and args.against is not None:
        parser.error("--by measures one workbook; it takes no --against")
    if args.labels is not None and (args.against is not None or args.by == "document"):
        parser.error(
            "--labels corrects one workbook's shares; it takes no --against "
            "and no --by document"
        )

    if args.by == "document":
        return _curve(args.file, args.language, args.size or 200)

    from assessment.diversity import subsamples

    groups = _read(args.file, args.language, by=args.by)
    if args.by and not groups:
        parser.error(f"{args.file} holds no {_BY[args.by][1]} to split by")
    tagged_by: dict[str, str] = {}
    if args.against is not None:
        _compare(_texts(groups), _texts(_read(args.against, args.language)), tagged_by)
    else:
        named = f"{args.by:<36}" if args.by else ""
        print(
            f"{'language':<9}{named}{'n':>6}"
            + "".join(f"{one:>9}" for one in (*METRICS, "held"))
        )
        evidence = _evidence(args.file)
        for (language, label), asked in sorted(groups.items()):
            shown = f"{label:<36}" if args.by else ""
            if args.size:
                if len(asked) < args.size:
                    print(
                        f"{language:<9}{shown}{len(asked):>6}  question, fewer "
                        f"than {args.size}"
                    )
                    continue
                asked = [
                    asked[i] for i in subsamples(len(asked), args.size, draws=1)[0]
                ]
            texts = [text for _, text in asked]
            tags, tagged_by[language] = _tags(texts, language)
            scores = _metrics(texts, tags, _vectors(texts) if len(texts) > 1 else [])
            read = [
                share
                for id, text in asked
                if (share := _held(text, evidence.get(id, ""), language)) is not None
            ]
            scores["held"] = sum(read) / len(read) if read else float("nan")
            print(
                f"{language:<9}{shown}{len(texts):>6}"
                + "".join(
                    f"{'-':>9}" if isnan(score) else f"{score:>9.3f}"
                    for score in scores.values()
                )
            )
    print()
    for language, pipeline in tagged_by.items():
        print(f"{language}: UPOS tags from {pipeline}")
    print(
        "HS: the cosine of EMBEDDING_MODEL's vectors, which is not on the "
        "paper's MiniLM scale; compare it only between sets embedded alike"
    )
    if args.by:
        _conformance(args.file, groups, args.by)
    if args.against is None:
        _judged(args.file, groups, args.by)
        if args.labels is not None:
            _corrected(args.file, groups, args.labels, args.by)
    return 0


def _evidence(path: Path) -> dict[int, str]:
    """Each question's cited evidence, one sentence a line, by id; empty without the column."""
    import pandas as pd

    frame = pd.read_excel(
        path, sheet_name="Questions", dtype={_EVIDENCE: str}, keep_default_na=False
    )
    if _EVIDENCE not in frame:
        return {}
    return dict(zip(frame["ID"].astype(int), frame[_EVIDENCE], strict=True))


#: The Questions sheet's column of the sentences a question's facts rest on.
_EVIDENCE = "The evidence they rest on"


def _held(text: str, evidence: str, language: str) -> float | None:
    """How much of a question its cited evidence already holds: an easiness reading.

    The share of the question's content lemmas (nouns, proper nouns and
    adjectives) that its evidence carries too. A proxy for the surface
    overlap van Elburg et al. (2025, section 6.2) name as one reason generated
    questions run easy, which they did not measure; read against the
    evidence sentences, which are narrower than the passages. None where
    either side has no content word: nothing to measure is not a zero.
    """
    held = _content(evidence, language)
    asked = _content(text, language) if held else frozenset()
    if not asked:
        return None
    return len(asked & held) / len(asked)


@cache
def _content(text: str, language: str) -> frozenset[str]:
    """The content lemmas of a text, through the language's spaCy pipeline.

    Cached: a question counts in each of its categories, and one parse a
    text is enough for all of them.
    """
    from nlp.analysis import content

    return content(text, language)


#: The report's columns, in the paper's order.
METRICS = ("NGD", "SR", "word-CR", "PoS-CR", "HS")

#: What `--by` splits a language on: the Questions sheet's column, and what
#: its labels are called where a workbook holds none.
_BY = {"category": ("Categories", "categories"), "kind": ("Kind", "kinds")}


def _read(
    path: Path, only: str | None, by: str | None = None
) -> dict[tuple[str, str], list[tuple[int, str]]]:
    """A workbook's questions and their ids by language, in the order of their ids.

    Grouped by language under an empty label, or with `by` by language and
    each label of the column `_BY` names: a question's kind, or each
    `categorization=category` label in the Categories cell, so a question
    counts once in each of its categories and a question told none in no
    group.
    """
    # Here rather than above: the assess-worker imports this module and
    # never reads a workbook.
    import pandas as pd

    # Text as written: pandas would otherwise read a question "None" or "N/A"
    # as missing, and measure it as the word "nan".
    frame = pd.read_excel(
        path,
        sheet_name="Questions",
        dtype={"Question": str, "Language": str},
        keep_default_na=False,
    ).sort_values("ID")
    column = _BY[by][0] if by else None
    if column is not None and column not in frame:
        return {}
    labels = frame[column] if column else [""] * len(frame)
    asked: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for id, language, text, held in zip(
        frame["ID"], frame["Language"], frame["Question"], labels, strict=True
    ):
        if only not in (None, language):
            continue
        # A comma never stands in a name, so it only ever separates labels.
        for label in str(held).split(", ") if column else [""]:
            if label or not column:
                asked[(language, label)].append((int(id), str(text)))
    return asked


def _curve(path: Path, only: str | None, n: int) -> int:
    """Prints the paper's Figure 1: PoS-CR of n questions drawn from k documents.

    Each question's document is the first its Citations rows name, by its id
    where the workbook carries one and by its title otherwise, so a question
    citing two counts under the first. k runs 5, 10, 15 ... up to
    the language's documents and that count itself; a k too few documents
    can fill is left out. Drawn from questions already written, so it reads
    lower than writing n anew from k documents would: those questions were
    deduplicated against the whole corpus.
    """
    import pandas as pd

    from assessment.diversity import few_documents

    groups = _read(path, only)
    cited = pd.read_excel(path, sheet_name="Citations")
    # The first row citing a question names its document.
    first = {
        int(id): str(document)
        for id, document in cited.drop_duplicates("Question ID")[
            ["Question ID", "Document ID" if "Document ID" in cited else "Document"]
        ].itertuples(index=False, name=None)
    }
    print(f"{'language':<9}{'documents':>10}{'n':>6}{'PoS-CR':>9}{'sd':>8}")
    notes = []
    for (language, _), asked in sorted(groups.items()):
        held = [(first[id], text) for id, text in asked if id in first]
        if len(held) < len(asked):
            notes.append(
                f"{language}: {len(asked) - len(held)} question(s) cite no document"
            )
        units = [unit for unit, _ in held]
        tags, pipeline = _tags([text for _, text in held], language)
        count = len(set(units))
        ks = sorted({*range(5, count + 1, 5), count})
        curve = few_documents(units, tags, ks, n)
        if not curve:
            notes.append(
                f"{language}: too few documents or questions for any point at n={n}"
            )
        for k, mean, spread in curve:
            print(f"{language:<9}{k:>10}{n:>6}{mean:>9.3f}{spread:>8.3f}")
        notes.append(f"{language}: UPOS tags from {pipeline}, {count} documents")
    print()
    for line in notes:
        print(line)
    _never_asked(path)
    return 0


#: The Summary rows `question_generation.export` writes for what no accepted
#: question reaches: the words are its `NEVER_DOCUMENTS` and `NEVER_PASSAGES`.
_NEVER = (
    "Documents with facts and no accepted question",
    "Passages with facts never asked",
)


def _never_asked(path: Path) -> None:
    """Prints the documents and passages the workbook says no question reaches.

    Beside the curve because a curve over the documents that have questions
    cannot show the ones that have none. Nothing is printed for a workbook
    that carries no such rows, which is one written before they existed.
    """
    import pandas as pd

    summary = pd.read_excel(path, sheet_name="Summary")
    if "Measure" not in summary:
        return
    held = dict(zip(summary["Measure"].astype(str), summary["Count"], strict=True))
    if not all(label in held for label in _NEVER):
        return
    print()
    # A Summary with notes has rows with no count, so pandas reads the
    # column as floats: these counts are whole, and are printed as such.
    for label in _NEVER:
        print(f"{label}: {int(held[label])}")
    for measure, count in held.items():
        if measure.startswith(f"{_NEVER[0]}: "):
            print(
                f"  {measure.removeprefix(f'{_NEVER[0]}: ')} ({int(count)} passage(s))"
            )


def _texts(
    groups: dict[tuple[str, str], list[tuple[int, str]]],
) -> dict[str, list[str]]:
    """The questions by language alone."""
    return {
        language: [text for _, text in asked] for (language, _), asked in groups.items()
    }


def _conformance(
    path: Path, groups: dict[tuple[str, str], list[tuple[int, str]]], by: str
) -> None:
    """Prints, per group, the share in its word bounds, factoid and open-ended.

    Word bounds are a category's, so a kind is held to none and prints no
    bounds column; factoid and open-ended hold for either. The bounds are
    today's QUESTIONS_CATEGORIZATIONS, read as the question stage reads it,
    because a question stores the words it was told and not the bounds: a
    row written under other bounds is counted against these.
    A category with no bounds today shows none. Factoid and open-ended are
    read off the Answer form column, so neither counts a question with no
    answer.
    """
    import pandas as pd

    from assessment.diversity import factuality, words
    from question_generation.config import DEFAULT_CATEGORIZATIONS, categorizations

    bounds = {}
    if by == "category":
        source, _ = snapshot("questions")
        bounds = {
            category.label: category.words
            for one in categorizations(
                optional("QUESTIONS_CATEGORIZATIONS", source) or DEFAULT_CATEGORIZATIONS
            )
            for category in one.categories
        }
    frame = pd.read_excel(
        path, sheet_name="Questions", dtype={"Answer form": str}, keep_default_na=False
    )
    forms = dict(zip(frame["ID"], frame["Answer form"], strict=True))
    if by == "category":
        print(
            "\nWord bounds as QUESTIONS_CATEGORIZATIONS sets them today, which need "
            "not be the ones a question was written under; answer forms as stored:"
        )
    else:
        print("\nAnswer forms as stored:")
    bound = f"{'in bounds':>11}" if by == "category" else ""
    print(f"{'language':<9}{by:<36}{'n':>6}{bound}{'factoid':>9}{'open-ended':>12}")
    for (language, label), asked in sorted(groups.items()):
        least, most = bounds.get(label, (None, None))
        inside = ""
        if by == "category":
            inside = f"{'-':>11}"
            if least is not None or most is not None:
                counts = [words(text) for _, text in asked]
                kept = sum((least or 0) <= n <= (most or n) for n in counts)
                inside = f"{kept / len(asked):>11.3f}"
        kinds = [factuality(forms.get(id)) for id, _ in asked]
        print(
            f"{language:<9}{label:<36}{len(asked):>6}{inside}"
            f"{kinds.count('factoid') / len(asked):>9.3f}"
            f"{kinds.count('open-ended') / len(asked):>12.3f}"
        )


#: The paper's six scores, in its order, as the judge stores them.
_PAPER_ORDER = (
    "rubric_fluency",
    "rubric_clarity",
    "rubric_conciseness",
    "rubric_relevance",
    "rubric_consistency",
    "rubric_answerability",
)


def _judged(
    path: Path, groups: dict[tuple[str, str], list[tuple[int, str]]], by: str | None
) -> None:
    """Prints the paper's judge's mean scores per group, where the workbook holds any.

    The mean of the stored score, (s - 1) / 2, is the paper's normalised
    mean, as its Table 3 reports it. n is how many of the group were judged.
    """
    import pandas as pd

    sheet = pd.read_excel(path, sheet_name="Assessment")
    scored = sheet.loc[sheet["Judgement"].astype(str).isin(_PAPER_ORDER)]
    if scored.empty:
        return
    metrics = [one for one in _PAPER_ORDER if one in set(scored["Judgement"])]
    named = f"{by:<36}" if by else ""
    print("\nThe paper's judge, mean scores from 0 to 1:")
    print(
        f"{'language':<9}{named}{'n':>6}"
        + "".join(f"{one.removeprefix('rubric_'):>14}" for one in metrics)
    )
    for (language, label), asked in sorted(groups.items()):
        held = scored.loc[scored["Question ID"].isin([id for id, _ in asked])]
        if held.empty:
            continue
        means = held.groupby("Judgement")["Score"].mean()
        shown = f"{label:<36}" if by else ""
        print(
            f"{language:<9}{shown}{held['Question ID'].nunique():>6}"
            + "".join(
                f"{means[one]:>14.3f}" if one in means else f"{'-':>14}"
                for one in metrics
            )
        )


def _refuse(message: str) -> NoReturn:
    """Says why on stderr and exits 2, as a parser error does."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


#: What a labels file may say: one place where a label is normalised.
_YES, _NO = ("yes", "true"), ("no", "false")


def _labels(path: Path) -> tuple[dict[int, dict[str, int]], dict[int, str]]:
    """Reads a JSONL file of an integer `id`, an optional `question` and labels.

    Every other field is a label: yes or true is 1, no or false 0 in any
    case, na or null no label. Anything else is refused, naming the field
    and the line. The questions are by id, for the check that the labels
    belong to the workbook.
    """
    labels: dict[int, dict[str, int]] = {}
    questions: dict[int, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            _refuse(f"{path} line {number} is not JSON")
        id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(id, int) or isinstance(id, bool):
            _refuse(f"{path} line {number} has no integer id")
        if id in labels:
            _refuse(f"{path} line {number} labels id {id} again")
        labels[id] = {}
        if row.get("question") is not None:
            questions[id] = str(row["question"])
        for field, value in row.items():
            if field in ("id", "question"):
                continue
            word = str(value).lower() if value is not None else "na"
            if word in ("na", "none"):
                continue
            if word not in (*_YES, *_NO):
                _refuse(f"{path} line {number}: {field} is {value!r}, not yes or no")
            labels[id][field] = int(word in _YES)
    if not any(labels.values()):
        _refuse(f"{path} holds no labels")
    return labels, questions


def _corrected(
    path: Path,
    groups: dict[tuple[str, str], list[tuple[int, str]]],
    labels: Path,
    by: str | None,
) -> None:
    """Prints each labelled share corrected by the judge's verdict on every row.

    The verdict is the Questions sheet's Judge column, approved 1 and
    refused 0, and a row not judged is left out. Per group and label, the
    labelled rows give the label and the judged rows without one give what
    the judge says alone; prediction-powered inference (ARES, Saad-Falcon et
    al., NAACL 2024, section 3.3) corrects the second by the first. The
    languages of each label are then pooled by their size as the row `all`.
    """
    import pandas as pd

    from assessment import ppi

    given, asked = _labels(labels)
    frame = pd.read_excel(
        path,
        sheet_name="Questions",
        dtype={"Question": str, "Judge": str},
        keep_default_na=False,
    )
    if "Judge" not in frame:
        _refuse(f"{path} has no Judge column to correct by")
    texts = dict(zip(frame["ID"], frame["Question"], strict=True))
    # Only these two are verdicts: "not judged", and a blank cell, are none.
    verdict = {
        int(id): int(one == "approved")
        for id, one in zip(frame["ID"], frame["Judge"], strict=True)
        if one in ("approved", "refused")
    }
    for id in sorted(asked):
        if id in texts and asked[id].strip() != str(texts[id]).strip():
            _refuse(f"label {id} is for another question than the workbook's id {id}")
    unjudged = sum(id in texts and id not in verdict for id in given)
    absent = sum(id not in texts for id in given)

    named = f"{by:<36}" if by else ""
    print("\nLabelled shares corrected by the paper's judge:")
    print(
        f"{'language':<9}{named}{'label':<16}{'n':>5}{'N':>6}{'judge':>8}"
        f"{'labels':>8}{'corrected':>11}  {'95% interval':<18}{'weight':>7}"
    )
    pool: dict[tuple[str, str], list] = defaultdict(list)
    # Languages a label could not be measured in, which leave it unpooled:
    # an `all` row over the others would pass for every language.
    unmeasured: dict[tuple[str, str], list[str]] = defaultdict(list)
    fields = sorted({f for id in verdict for f in given.get(id, {})})
    for (language, label), group in sorted(groups.items()):
        ids = [id for id, _ in group if id in verdict]
        for field in fields:
            tagged = [id for id in ids if field in given.get(id, {})]
            rest = [id for id in ids if field not in given.get(id, {})]
            shown = f"{language:<9}{label:<36}" if by else f"{language:<9}"
            if len(tagged) < 2:
                print(
                    f"{shown}{field:<16}{len(tagged):>5}{len(rest):>6}  "
                    "fewer than 2 labelled"
                )
                unmeasured[(label, field)].append(language)
                continue
            one = ppi.corrected_mean(
                [verdict[id] for id in rest],
                [verdict[id] for id in tagged],
                [given[id][field] for id in tagged],
            )
            pool[(label, field)].append((one, tagged, rest))
            _print_corrected(shown, field, one, tagged + rest, tagged, verdict, given)
    for (label, field), parts in sorted(pool.items()):
        shown = f"{'all':<9}{label:<36}" if by else f"{'all':<9}"
        if unmeasured[(label, field)]:
            missing = ", ".join(unmeasured[(label, field)])
            print(f"{shown}{field} not pooled: {missing} not measured")
            continue
        tagged = [id for _, t, _ in parts for id in t]
        ids = tagged + [id for _, _, rest in parts for id in rest]
        _print_corrected(
            shown, field, ppi.pooled([p[0] for p in parts]), ids, tagged, verdict, given
        )
    print()
    if unjudged:
        print(
            f"{unjudged} labelled row{' was' if unjudged == 1 else 's were'} not judged"
        )
    if absent:
        print(
            f"{absent} labelled id{' is' if absent == 1 else 's are'} not in the workbook"
        )


def _print_corrected(
    shown: str,
    field: str,
    one,
    ids: list[int],
    tagged: list[int],
    verdict: dict[int, int],
    given: dict[int, dict[str, int]],
) -> None:
    """One row of the corrected table; the interval is clipped to [0, 1] to show.

    Labels that all agree, under a judge given no weight, leave no spread to
    build an interval from, and an interval of one point would read as
    certainty.
    """
    low, high = (min(max(end, 0.0), 1.0) for end in one.interval())
    interval = "no spread" if one.se == 0 else f"[{low:.3f}, {high:.3f}]"
    weight = "-" if isnan(one.weight) else f"{one.weight:.3f}"
    print(
        f"{shown}{field:<16}{one.labelled:>5}{one.judged:>6}"
        f"{sum(verdict[id] for id in ids) / len(ids):>8.3f}"
        f"{sum(given[id][field] for id in tagged) / len(tagged):>8.3f}"
        f"{one.estimate:>11.3f}  {interval:<18}{weight:>7}"
    )


def _metrics(texts: list[str], tags: list[str], vectors: ArrayLike) -> dict[str, float]:
    """The five scores of one set; HS is NaN for a set with no pair in it."""
    from assessment.diversity import (
        compression_ratio,
        homogenization,
        ngram_diversity,
        self_repetition,
    )

    return {
        "NGD": ngram_diversity(texts),
        "SR": self_repetition(texts),
        "word-CR": compression_ratio(texts),
        "PoS-CR": compression_ratio(tags),
        "HS": homogenization(vectors) if len(texts) > 1 else float("nan"),
    }


def _compare(
    first: dict[str, list[str]], second: dict[str, list[str]], tagged_by: dict[str, str]
) -> None:
    """Prints each metric's mean over the draws of both sets, and Welch's p."""
    import numpy as np

    from assessment.diversity import ALPHA, DRAWS, SHARE, p_value, subsamples

    print(
        f"{'language':<9}{'metric':<9}{'file':>16}{'against':>16}"
        f"{'difference':>12}{'p':>8}"
    )
    drawn = []
    for language in sorted(first.keys() | second.keys()):
        if language not in first or language not in second:
            drawn.append(f"{language}: in one workbook only")
            continue
        size = floor(SHARE * min(len(first[language]), len(second[language])))
        if size < 2:
            drawn.append(f"{language}: too few questions to draw two")
            continue
        scores = []
        for seed, texts in enumerate((first[language], second[language])):
            tags, tagged_by[language] = _tags(texts, language)
            vectors = np.asarray(_vectors(texts))
            scores.append(
                [
                    _metrics(
                        [texts[i] for i in places],
                        [tags[i] for i in places],
                        vectors[places],
                    )
                    for places in subsamples(len(texts), size, DRAWS, seed)
                ]
            )
        for metric in METRICS:
            a, b = ([draw[metric] for draw in side] for side in scores)
            p = p_value(a, b)
            shown = "      -" if isnan(p) else f"{p:>7.3f}"
            print(
                f"{language:<9}{metric:<9}{_spread(a):>16}{_spread(b):>16}"
                f"{np.mean(a) - np.mean(b):>+12.3f}{shown}{'*' if p < ALPHA else ' '}"
            )
        drawn.append(
            f"{language}: {DRAWS} draws of {size} from {len(first[language])} "
            f"and from {len(second[language])}"
        )
    print()
    for line in drawn:
        print(line)


def _spread(scores: Sequence[float]) -> str:
    """A mean and its standard deviation over the draws, as `0.123 (0.004)`."""
    import numpy as np

    return f"{np.mean(scores):.3f} ({np.std(scores, ddof=1):.3f})"


def _tags(texts: list[str], language: str) -> tuple[list[str], str]:
    """Each question's part-of-speech tags, and the pipeline that read them.

    UPOS, the tagset every language's pipeline shares, so German and English
    are tagged alike; it moves the ratio, so the pipeline is named.
    """
    from nlp.pipelines import name, pipeline, version

    tagged = [
        " ".join(token.pos_ for token in doc) for doc in pipeline(language).pipe(texts)
    ]
    return tagged, f"{name(language)} {version(language)}"


def _vectors(texts: list[str]) -> list[list[float]]:
    """Each question's vector, from the model that embeds the corpus.

    Embedded here rather than read from the stored column: a workbook holds
    none, and every set measured through one model is comparable.
    """
    return _embedder().embed_all(texts)


@lru_cache(maxsize=1)
def _embedder():
    """The embedding model, loaded once and only when a set is measured."""
    from nlp.embedding import Embedder

    return Embedder(required("EMBEDDING_MODEL"), integer("EMBEDDING_MAX_TOKENS"))


if __name__ == "__main__":
    raise SystemExit(main())
