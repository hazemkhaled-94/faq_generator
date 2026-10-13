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


def _stored(
    embedder, read, *statements: str, twin: Twin | None = None, bar: float = 0.0
):
    """What the service stores for scripted candidates citing the excerpt.

    `bar` is the cosine the gate refuses at, the configured one when 0.
    """
    from extraction.config import Settings
    from extraction.extractors import ExtractorRegistry, LlmExtractor, TableExtractor
    from extraction.service import ExtractionService
    from extraction.validation import FactChecker

    queue = Queue(read)
    queue.twin = twin
    cited = [one.index for one in read.sentences]
    model = Model(
        {"facts": [{"sentences": cited, "statement": one} for one in statements]}
    )
    settings = Settings.load()
    ExtractionService(
        repository=queue,  # type: ignore[arg-type]
        extractors=ExtractorRegistry(
            extractors=(TableExtractor(),),
            default=LlmExtractor(model),  # type: ignore[arg-type]
        ),
        checker=FactChecker(DIGEST_SHARE),
        embedder=embedder,
        duplicate_cosine=bar or settings.duplicate_cosine,
        duplicate_floor=settings.duplicate_floor,
    ).process_next()
    return queue.stored[read.id]


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
    (stored,) = _stored(
        embedder,
        passage(sentence, language=language, id=9),
        statement,
        twin=Twin(fact_id=twin_id, statement=twin, similarity=similarity),
    )

    if expected is None:
        assert stored.validated, (
            f"refused at cosine {similarity:.3f} as F{twin_id}: "
            f"{stored.validation_error}"
        )
    else:
        assert stored.rejection_code == expected, stored.validation_error
        assert stored.twin_id == twin_id


#: (name, the passage's excerpt, its language, the claim kept, its sibling).
SIBLINGS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "touchlines and goal lines",
        (
            "Rechteckige, von den Seitenlinien und Torlinien begrenzte Fläche, "
            "auf der Fussball gespielt wird."
        ),
        "de",
        "Das Spielfeld wird von den Seitenlinien begrenzt.",
        "Das Spielfeld wird von den Torlinien begrenzt.",
    ),
    (
        "no goals or an equal number",
        (
            "Wenn beide Teams keine oder die gleiche Anzahl an Toren erzielen, "
            "endet das Spiel unentschieden."
        ),
        "de",
        "Das Spiel endet unentschieden, wenn beide Teams keine Tore erzielen.",
        (
            "Das Spiel endet unentschieden, wenn beide Teams die gleiche Anzahl "
            "an Toren erzielen."
        ),
    ),
    (
        "a caution or a sending-off",
        (
            "- A temporarily dismissed player who commits a cautionable (YC) or "
            "sending-off (RC) offence during their temporary dismissal period "
            "will take no further part in the match and may not be replaced or "
            "substituted"
        ),
        "en",
        (
            "A temporarily dismissed player who commits a cautionable offence "
            "during the temporary dismissal period takes no further part in the "
            "match."
        ),
        (
            "A temporarily dismissed player who commits a sending-off offence "
            "during the temporary dismissal period takes no further part in the "
            "match."
        ),
    ),
    (
        "two conditions of one rule",
        (
            "A player is in an offside position if:\n"
            "- any part of the head, body or feet is in the opponents' half "
            "(excluding the halfway line) and\n"
            "- any part of the head, body or feet is nearer to the opponents' "
            "goal line than both the ball and the second-last opponent"
        ),
        "en",
        (
            "A player is in an offside position if any part of the head, body or "
            "feet is in the opponents' half excluding the halfway line."
        ),
        (
            "A player is in an offside position if any part of the head, body or "
            "feet is nearer to the opponents' goal line than both the ball and "
            "the second-last opponent."
        ),
    ),
    (
        "the least and the most of one length",
        (
            "Die Seitenlinie muss länger als die Torlinie sein.\n"
            "- Länge der Seitenlinie: mindestens 90 m (100 yds) höchstens 120 m "
            "(130 yds)"
        ),
        "de",
        "Die Seitenlinie hat eine Mindestlänge von 90 m (100 yds).",
        "Die Seitenlinie hat eine Höchstlänge von 120 m (130 yds).",
    ),
)

#: A bar every sibling pair clears, so it is the scan's rule that keeps the
#: second claim and not the bar.
_LOW = 0.9


@pytest.mark.parametrize(
    ("excerpt", "language", "kept", "sibling"),
    [row[1:] for row in SIBLINGS],
    ids=[row[0] for row in SIBLINGS],
)
def test_a_sibling_claim_of_one_passage_is_kept(
    embedder, excerpt, language, kept, sibling
) -> None:
    """Two list items, two conditions, a least and a most: two facts."""
    first, second = _stored(
        embedder, passage(excerpt, language=language, id=9), kept, sibling, bar=_LOW
    )

    assert first.validated, first.validation_error
    assert second.validated, second.validation_error
