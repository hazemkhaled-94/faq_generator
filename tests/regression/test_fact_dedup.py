"""The verdicts the fact dedup gate reaches on stored pairs, pinned as a table.

Each row is a candidate a run refused as `duplicate`, beside the fact it was
refused against, and the sentence the candidate cites. The service is the
real `ExtractionService` with the real checker and EMBEDDING_MODEL, read from
the Hugging Face cache and skipped when it is not there; only the served
model is scripted, answering with the statement the run recorded, and the
index probe answers with the stored fact at the cosine the embedder reads
between the two. `EXTRACTION_DUPLICATE_COSINE` is the configured one.
"""

from __future__ import annotations

import os

import pytest
from drivers import DIGEST_SHARE, Model, Queue, passage

from database.qa_generator import Rejection
from extraction.models import Twin

pytestmark = pytest.mark.nlp

MODEL = os.environ["EMBEDDING_MODEL"]


@pytest.fixture(scope="module")
def embedder():
    """The real embedder, or a skip when its weights are not cached."""
    from transformers import AutoConfig

    try:
        AutoConfig.from_pretrained(MODEL, local_files_only=True)
    except Exception as exc:  # noqa: BLE001 - any failure is the same answer
        pytest.skip(f"{MODEL} is not in the cache: {exc}")
    from nlp.embedding import Embedder

    return Embedder(MODEL, max_tokens=int(os.environ["EMBEDDING_MAX_TOKENS"]))


def _stored(embedder, read, statement: str, twin: Twin | None):
    """What the service stores for one scripted candidate citing the excerpt."""
    from extraction.config import Settings
    from extraction.extractors import ExtractorRegistry, LlmExtractor, TableExtractor
    from extraction.service import ExtractionService
    from extraction.validation import FactChecker

    queue = Queue(read)
    queue.twin = twin
    cited = [one.index for one in read.sentences]
    model = Model({"facts": [{"sentences": cited, "statement": statement}]})
    settings = Settings.load()
    ExtractionService(
        repository=queue,  # type: ignore[arg-type]
        extractors=ExtractorRegistry(
            extractors=(TableExtractor(),),
            default=LlmExtractor(model),  # type: ignore[arg-type]
        ),
        checker=FactChecker(DIGEST_SHARE),
        embedder=embedder,
        duplicate_cosine=settings.duplicate_cosine,
        duplicate_floor=settings.duplicate_floor,
    ).process_next()
    (stored,) = queue.stored[read.id]
    return stored


#: (name, stored fact, its statement, the candidate's sentence, its language,
#:  the candidate as the run recorded it, expected code or None).
CROSS: tuple[tuple[str, int, str, str, str, str, str | None], ...] = (
    (
        "a goal is not a goal kick",
        2154,
        "A goal is scored when the whole of the ball passes over the goal line.",
        (
            "A goal kick is awarded when the whole of the ball passes over the "
            "goal line, on the ground or in the air, having last touched a "
            "player of the attacking team, and a goal is not scored (see also "
            "Laws 8, 10, 13 and 15)."
        ),
        "en",
        "A goal kick is awarded when the whole of the ball passes over the goal line.",
        None,
    ),
    (
        "a direct free kick is not an indirect one",
        354,
        "Das Spiel wird mit einem indirekten Freistoss fortgesetzt.",
        (
            "Wenn der Schiedsrichter das Spiel unterbricht, wird das Spiel wie "
            "folgt fortgesetzt:\n"
            "- mit einem direkten Freistoss an der Stelle, an der der Spieler "
            "ins Spiel eingegriffen hat\n"
            "- mit einem indirekten Freistoss an der Stelle, an der sich der "
            "Ball zum Zeitpunkt der Unterbrechung befand, wenn der Spieler "
            "nicht ins Spiel eingegriffen hat"
        ),
        "de",
        (
            "Das Spiel wird mit einem direkten Freistoss an der Stelle "
            "fortgesetzt, an der der Spieler ins Spiel eingegriffen hat."
        ),
        None,
    ),
    (
        "only some is not all",
        172,
        "Alle verwarnungswürdigen Vergehen werden mit einer Zeitstrafe geahndet.",
        (
            "- Nur bestimmte verwarnungswürdige Vergehen werden mit einer "
            "Zeitstrafe geahndet."
        ),
        "de",
        (
            "Nur bestimmte verwarnungswürdige Vergehen werden mit einer "
            "Zeitstrafe geahndet."
        ),
        None,
    ),
    (
        "another distance is another line",
        234,
        (
            "Zwei Linien verlaufen im Abstand von jeweils 5,5 m (6 yds) zur "
            "Innenseite der Torpfosten."
        ),
        (
            "Im Abstand von jeweils 16,5 m (18 yds) zur Innenseite der "
            "Torpfosten verlaufen rechtwinklig zur Torlinie zwei Linien."
        ),
        "de",
        (
            "Zwei Linien verlaufen im Abstand von jeweils 16,5 m (18 yds) zur "
            "Innenseite der Torpfosten."
        ),
        None,
    ),
    (
        "the penalty area is not the goal area",
        2950,
        (
            "One assistant referee must be positioned at the intersection of "
            "the goal line and the goal area."
        ),
        (
            "The AR must be positioned at the intersection of the goal line and"
            " the penalty area."
        ),
        "en",
        (
            "The assistant referee must be positioned at the intersection of "
            "the goal line and the penalty area."
        ),
        None,
    ),
    (
        "a penalty incident is not a goal",
        2433,
        (
            "A reviewable incident includes an attacking team offence in the "
            "build-up to a goal."
        ),
        (
            "- attacking team offence in the build-up to the penalty incident "
            "(handball, foul, offside etc.)\n"
            "- ball out of play prior to the incident\n"
            "- location of offence (inside or outside the penalty area)\n"
            "- penalty kick incorrectly awarded\n"
            "- penalty kick offence not penalised"
        ),
        "en",
        (
            "An attacking team offence in the build-up to the penalty incident "
            "is reviewable."
        ),
        None,
    ),
    (
        "the same rule in other words is still one fact",
        2047,
        "The referee will make the final decision.",
        (
            "They will assist the referee in controlling the match in "
            "accordance with the Laws of the Game but the final decision will "
            "always be taken by the referee."
        ),
        "en",
        "The referee takes the final decision.",
        Rejection.DUPLICATE,
    ),
)


@pytest.mark.parametrize(
    ("twin_id", "twin", "sentence", "language", "statement", "expected"),
    [row[1:] for row in CROSS],
    ids=[row[0] for row in CROSS],
)
def test_a_stored_pair_reaches_its_recorded_verdict(
    embedder, twin_id, twin, sentence, language, statement, expected
) -> None:
    """A different rule is its own fact; a restatement is still refused."""
    from nlp.embedding import cosine

    similarity = cosine(embedder.embed(statement), embedder.embed(twin))
    stored = _stored(
        embedder,
        passage(sentence, language=language, id=9),
        statement,
        Twin(fact_id=twin_id, statement=twin, similarity=similarity),
    )

    if expected is None:
        assert stored.rejection_code != Rejection.DUPLICATE, (
            f"refused at cosine {similarity:.3f} as F{twin_id}: "
            f"{stored.validation_error}"
        )
    else:
        assert stored.rejection_code == expected, stored.validation_error
        assert stored.twin_id == twin_id
