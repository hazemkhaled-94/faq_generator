"""What the rows still to do will take and cost, from the rates a build measured.

`make estimate` prints it before a run is started. The rates are the reviewed
build's own, 30 documents, 1,973 passages and 41 topics in 5 h 41 min and USD
75.53, divided by the rows each stage had: another corpus, another model split
or another provider moves them, and a deployment that has run its own build
reads its own off the log (`make spend`). docs/operations.md "Sizing a
corpus" is the same table with the arithmetic worked for a corpus ten times
the size.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

#: Passages a document held, topics a passage made and questions a topic
#: left accepted, in the reviewed build: how a stage's rows are projected
#: from those of the stage before it, where that has not run.
PASSAGES_PER_DOCUMENT = 1_973 / 30
TOPICS_PER_PASSAGE = 41 / 1_973
ACCEPTED_PER_TOPIC = 2_175 / 41


@dataclass(frozen=True)
class Rate:
    """What one row of a stage took in the reviewed build."""

    stage: str
    #: What a row is.
    unit: str
    #: Seconds of one drain.
    seconds: float
    usd: float
    #: Model calls.
    calls: float
    #: Whether another drain of the stage divides its time.
    scales: bool


#: Per row, from P/build/logs/full-build.out's stage markers and the runner's
#: priced calls: parse 199 s over 30 documents, chunk 79 s, extract 7,272 s
#: and USD 13.11 and 2,541 calls over 1,973 passages, the topic fit 65 s, the
#: bridge pass 721 s and USD 2.14 over 41 topics (one call to a group, twelve
#: groups to a topic, and untraced), the questions 334 drain
#: minutes (two drains of 167) and USD 55.17 and 13,128 calls over 41 topics,
#: the release draw 702 s and USD 1.47 over 2,175 accepted questions, and the
#: assessment, a fixed sample, 1,392 s and USD 3.59 and 1,862 calls.
RATES = (
    Rate("parse", "document", 6.6, 0.0, 0.0, True),
    Rate("chunk", "document", 2.6, 0.0, 0.0, True),
    Rate("extract", "passage", 3.69, 0.00664, 1.29, True),
    Rate("topics", "passage", 0.033, 0.00002, 0.001, False),
    Rate("bridges", "topic", 17.6, 0.0522, 12.0, False),
    Rate("questions", "topic", 489.0, 1.35, 320.0, True),
    Rate("release", "accepted question", 0.323, 0.000676, 0.54, False),
    Rate("assess", "sample of 441", 1392.0, 3.59, 1862.0, False),
)


@dataclass(frozen=True)
class Rows:
    """The rows still to do, as the stages count them."""

    #: Documents still to parse and chunk.
    documents: int
    #: Passages still to extract, and the corpus the topics are fitted over.
    passages: int
    #: Topics still to write bridges and questions for.
    topics: int
    #: Accepted questions, which the release is drawn from and the sample.
    accepted: int


@dataclass(frozen=True)
class Line:
    """One stage's estimate."""

    stage: str
    unit: str
    rows: int
    seconds: float
    usd: float
    calls: float


def projected(documents: int, passages: int, topics: int, accepted: int) -> Rows:
    """The rows, with those a stage has not reached read from the stage before.

    A corpus that has not been chunked has no passages yet, and one whose
    topics are not fitted has none, so what is to come is the ratio the
    reviewed build had. A count that is there is kept.
    """
    passages = passages or round(documents * PASSAGES_PER_DOCUMENT)
    topics = topics or round(passages * TOPICS_PER_PASSAGE)
    accepted = accepted or round(topics * ACCEPTED_PER_TOPIC)
    return Rows(documents, passages, topics, accepted)


def estimate(rows: Rows, drains: Mapping[str, int] | None = None) -> list[Line]:
    """Each stage's time, spend and model calls for these rows.

    Args:
        rows: What is still to do.
        drains: How many drains work each stage at once, by stage name. A
            stage whose workers scale takes its time divided by them, and its
            spend is the same whatever their number.
    """
    counted = {
        "parse": rows.documents,
        "chunk": rows.documents,
        "extract": rows.passages,
        "topics": rows.passages,
        "bridges": rows.topics,
        "questions": rows.topics,
        "release": rows.accepted,
        "assess": 1 if rows.accepted else 0,
    }
    lines = []
    for rate in RATES:
        count = counted[rate.stage]
        parallel = max((drains or {}).get(rate.stage, 1), 1) if rate.scales else 1
        lines.append(
            Line(
                stage=rate.stage,
                unit=rate.unit,
                rows=count,
                seconds=count * rate.seconds / parallel,
                usd=count * rate.usd,
                calls=count * rate.calls,
            )
        )
    return lines


def _span(seconds: float) -> str:
    """A time as minutes under two hours and hours past it."""
    return f"{seconds / 60:.1f} min" if seconds < 7_200 else f"{seconds / 3_600:.1f} h"


def report(lines: Sequence[Line]) -> None:
    """Prints the table `make estimate` ends in."""
    print(
        f"{'stage':<10} {'rows':>9}  {'unit':<18} {'time':>10} {'USD':>10} {'calls':>9}"
    )
    for line in lines:
        print(
            f"{line.stage:<10} {line.rows:>9,}  {line.unit:<18} "
            f"{_span(line.seconds):>10} {line.usd:>10,.2f} {line.calls:>9,.0f}"
        )
    print(
        f"{'total':<10} {'':>9}  {'':<18} "
        f"{_span(sum(one.seconds for one in lines)):>10} "
        f"{sum(one.usd for one in lines):>10,.2f} "
        f"{sum(one.calls for one in lines):>9,.0f}"
    )


def counted() -> Rows:
    """The rows still to do, counted in the database `DATABASE_URL` names."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from database.qa_generator import (
        Document,
        Passage,
        Question,
        QuestionStatus,
        Status,
        Topic,
        engine,
    )

    with Session(engine()) as session:

        def count(*conditions) -> int:
            return session.scalar(select(func.count()).where(*conditions)) or 0

        return Rows(
            documents=session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.chunk_status != Status.CHUNKED)
            )
            or 0,
            passages=session.scalar(
                select(func.count())
                .select_from(Passage)
                .where(Passage.extract_status != Status.EXTRACTED)
            )
            or 0,
            topics=session.scalar(
                select(func.count())
                .select_from(Topic)
                .where(
                    Topic.topic_index.is_not(None),
                    Topic.question_status != Status.GENERATED,
                )
            )
            or 0,
            accepted=session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.status == QuestionStatus.ACCEPTED)
            )
            or 0,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Prints the estimate for the rows still to do.

    Returns:
        The exit status.
    """
    built = argparse.ArgumentParser(prog="python -m stages.estimate")
    built.add_argument(
        "--drains",
        default="",
        metavar="STAGE=N,...",
        help="how many drains work a stage at once, as questions=4,extract=2",
    )
    args = built.parse_args(sys.argv[1:] if argv is None else argv)
    drains = {
        stage: int(number)
        for stage, _, number in (
            part.partition("=") for part in args.drains.split(",") if part
        )
    }
    report(estimate(projected(**asdict(counted())), drains))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
