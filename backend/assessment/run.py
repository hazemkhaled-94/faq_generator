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
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from functools import lru_cache
from math import floor, isnan
from pathlib import Path
from typing import TYPE_CHECKING

import telemetry
from assessment import prompts
from assessment.config import OFF, UNNAMED, Settings, judged_kinds
from assessment.factory import build_service, judge_model
from assessment.repository import AssessmentQueue
from llm.check import before_work
from llm.config import Settings as ModelSettings
from settings import decimal, integer, required
from settings.store import snapshot
from stages.cli import queue_main
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
        source, version = snapshot()
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
    if not Settings.load(snapshot()[0]).enabled:
        telemetry.configure("assessment", tracing=False)
        log.info("%s", OFF)
        # A worker waits in place rather than exiting: under `restart:
        # unless-stopped` an exit is a restart every few seconds, and the
        # Assessment page switches the flag on without restarting anything.
        # ponytail: argv read by hand, as for --status below.
        if "--watch" not in argv:
            return 0
        while not Settings.load(snapshot()[0]).enabled:
            time.sleep(decimal("WORKER_POLL_SECONDS"))
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
    if "--status" in argv and not Settings.load(snapshot()[0]).judge_model:
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
    language on its own. Where the workbook holds the paper's judge, its
    mean scores follow, over the same groups.
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
        "--by", choices=("category",), help="one row per category of each language"
    )
    args = parser.parse_args(argv)
    for named in (args.file, args.against):
        if named is not None and not named.is_file():
            parser.error(f"{named} is not a file")
    if args.size is not None and args.size < 1:
        parser.error("--size takes a whole number of at least 1")
    if args.size is not None and args.against is not None:
        parser.error("--against draws 80% of the smaller set; it takes no --size")
    if args.by is not None and args.against is not None:
        parser.error("--by measures one workbook; it takes no --against")

    from assessment.diversity import subsamples

    groups = _read(args.file, args.language, by_category=args.by == "category")
    if args.by and not groups:
        parser.error(f"{args.file} holds no categories to split by")
    tagged_by: dict[str, str] = {}
    if args.against is not None:
        _compare(_texts(groups), _texts(_read(args.against, args.language)), tagged_by)
    else:
        named = f"{'category':<36}" if args.by else ""
        print(
            f"{'language':<9}{named}{'n':>6}" + "".join(f"{one:>9}" for one in METRICS)
        )
        for (language, label), asked in sorted(groups.items()):
            texts = [text for _, text in asked]
            shown = f"{label:<36}" if args.by else ""
            if args.size:
                if len(texts) < args.size:
                    print(
                        f"{language:<9}{shown}{len(texts):>6}  question, fewer "
                        f"than {args.size}"
                    )
                    continue
                texts = [
                    texts[i] for i in subsamples(len(texts), args.size, draws=1)[0]
                ]
            tags, tagged_by[language] = _tags(texts, language)
            scores = _metrics(texts, tags, _vectors(texts) if len(texts) > 1 else [])
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
    if args.against is None:
        _judged(args.file, groups, args.by is not None)
    return 0


#: The report's columns, in the paper's order.
METRICS = ("NGD", "SR", "word-CR", "PoS-CR", "HS")


def _read(
    path: Path, only: str | None, by_category: bool = False
) -> dict[tuple[str, str], list[tuple[int, str]]]:
    """A workbook's questions and their ids by language, in the order of their ids.

    Grouped by language under an empty label, or with `by_category` by
    language and each `categorization=category` label in the Categories
    cell, so a question counts once in each of its categories and a
    question told none in no group.
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
    if by_category and "Categories" not in frame:
        return {}
    labels = frame["Categories"] if by_category else [""] * len(frame)
    asked: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for id, language, text, held in zip(
        frame["ID"], frame["Language"], frame["Question"], labels, strict=True
    ):
        if only not in (None, language):
            continue
        # A comma never stands in a name, so it only ever separates labels.
        for label in str(held).split(", ") if by_category else [""]:
            if label or not by_category:
                asked[(language, label)].append((int(id), str(text)))
    return asked


def _texts(
    groups: dict[tuple[str, str], list[tuple[int, str]]],
) -> dict[str, list[str]]:
    """The questions by language alone."""
    return {
        language: [text for _, text in asked] for (language, _), asked in groups.items()
    }


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
    path: Path, groups: dict[tuple[str, str], list[tuple[int, str]]], by: bool
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
    named = f"{'category':<36}" if by else ""
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
