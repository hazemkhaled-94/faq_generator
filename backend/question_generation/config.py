"""Configuration for the question generation service."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from database.qa_generator import AnswerForm, Difficulty, QuestionKind
from question_generation.kinds import KINDS
from question_generation.queue import ASKABLE
from question_generation.types import SPECS
from settings import Source, csv, decimal, integer, mapping, optional, required


def _weights(
    name: str,
    allowed: Mapping[str, object] | tuple[str, ...],
    source: Source = None,
) -> dict[str, int]:
    """Reads a `name:weight` mix, refusing a name nothing answers to.

    Raises:
        KeyError: If the setting is unset or empty.
        ValueError: If a name is not one of `allowed`, or a weight is not a
            whole number, or every weight is zero.
    """
    read = {}
    for key, value in mapping(name, source).items():
        if key not in allowed:
            raise ValueError(
                f"{name} names {key!r}, which is not one of "
                f"{', '.join(sorted(allowed))}"
            )
        try:
            read[key] = int(value)
        except ValueError:
            raise ValueError(
                f"{name} gives {key!r} the weight {value!r}, which is not a "
                f"whole number"
            ) from None
    if not any(weight > 0 for weight in read.values()):
        raise ValueError(f"{name} gives every entry a weight of 0, so nothing is asked")
    return read


#: QUESTIONS_KIND_MIX when it is not set: every spanning slot needs both
#: passages. `compound` is written and checked but holds no weight here: its
#: calibration (v0.3.12 pairs, 13 of 24 accepted, 4 of 12 in English) missed
#: the bar of 14 and 6 per language. `needs_both:5,compound:1` deals one slot
#: in six; a kind written later adds its weight only once its gate has passed.
_KIND_MIX: dict[str, int] = {QuestionKind.NEEDS_BOTH: 1}

#: A language as every `language` column holds one: an ISO 639-1 code.
_LANGUAGE = re.compile(r"[a-z]{2}")

#: QUESTIONS_MEETS_SHARE as configs/env/backend.env ships it, read when a
#: backend.env written before the setting existed has no line for it.
MEETS_SHARE = 0.02


def _languages(name: str, source: Source = None) -> dict[str, int]:
    """Reads a `language:weight` mix, taking any ISO 639-1 code.

    `_weights` over an open set of names: which languages a corpus holds is
    the deployment's business, so a third one is a value to set and not a
    change to this list.

    Raises:
        KeyError: If the setting is unset or empty.
        ValueError: If a name is not an ISO 639-1 code, or a weight is not a
            whole number, or every weight is zero.
    """
    codes = tuple(mapping(name, source))
    wrong = [code for code in codes if not _LANGUAGE.fullmatch(code)]
    if wrong:
        raise ValueError(
            f"{name} names {', '.join(map(repr, wrong))}, which is not an "
            f"ISO 639-1 code such as de or en"
        )
    return _weights(name, codes, source)


def _bounds(name: str, source: Source = None) -> dict[str, tuple[int, int]]:
    """Reads the `form:min:max` length bounds of each answer form.

    Raises:
        KeyError: If the setting is unset or empty.
        ValueError: If a form is unknown, a bound is not a whole number, a
            floor is above its ceiling, or a form is missing.
    """
    read = {}
    for form, value in mapping(name, source).items():
        if form not in tuple(AnswerForm):
            raise ValueError(
                f"{name} names the answer form {form!r}, which is not one of "
                f"{', '.join(AnswerForm)}"
            )
        low, _, high = value.partition(":")
        try:
            read[form] = (int(low), int(high))
        except ValueError:
            raise ValueError(
                f"{name} gives {form!r} the bounds {value!r}; it takes "
                f"form:min:max, as value:1:80"
            ) from None
        # An inverted pair parses and then refuses every answer of the form,
        # as `_span` refuses one for the same reason.
        if read[form][0] > read[form][1]:
            raise ValueError(
                f"{name} gives {form!r} a floor of {read[form][0]} above its "
                f"ceiling of {read[form][1]}, so no answer of that form could "
                f"pass"
            )
    missing = [form for form in AnswerForm if form not in read]
    if missing:
        raise ValueError(f"{name} says nothing about {', '.join(missing)}")
    return read


def _span(name: str, source: Source = None) -> tuple[int, int]:
    """Reads one `min:max` pair of character bounds.

    Raises:
        KeyError: If the setting is unset or empty.
        ValueError: If either bound is not a whole number, or the floor is
            above the ceiling.
    """
    low, _, high = required(name, source).partition(":")
    try:
        span = (int(low), int(high))
    except ValueError:
        raise ValueError(
            f"{name} gives the bounds {low}:{high}; it takes min:max, as 150:900"
        ) from None
    if span[0] > span[1]:
        raise ValueError(f"{name} gives a floor of {span[0]} above its ceiling")
    return span


@dataclass(frozen=True)
class Settings:
    """What to write per topic, of what kinds, and what to hold it to.

    Where a model is served is not here: that is `llm.config.Settings`,
    which every stage that calls a model shares. The writer's, the
    verifier's and the phrasing judge's names are here.
    """

    per_topic: int
    sample_size: int
    #: How many times one passage may be offered, each time with facts no
    #: earlier sample took. The ceiling on it; what really stops a passage
    #: is running out of facts nothing has been written from.
    samples_per_passage: int
    #: Which kinds of fact a question may be written from. Extraction reads a
    #: passage four ways and each shape seeds a different question: an atomic
    #: claim a factoid, a summary a definition, an outline an enumeration,
    #: and a bridge a cross-document one.
    fact_kinds: tuple[str, ...]
    #: Which question types are written, and in what proportion. A type with a
    #: weight of 0, or absent, is never planned; a follow-up takes its type
    #: from QUESTIONS_FOLLOWUP_TYPES.
    type_mix: dict[str, int]
    #: Which difficulty bands the plan aims for, in what proportion. A request
    #: for a shape of sample, not a verdict: `difficulty` is still read off
    #: what the question turned out to cite.
    difficulty_mix: dict[str, int]
    #: The types a follow-up may take, cycled in order down a thread.
    followup_types: tuple[str, ...]
    unanswerable_share: float
    followup_share: float
    max_followups: int
    #: How many more times a question may be written when a gate refused the
    #: draft, or when it came out below the band its slot asked for. 0 keeps
    #: the first draft whatever it is.
    retries: int
    #: Shortest and longest target answer per form.
    answer_chars: dict[str, tuple[int, int]]
    #: Shortest and longest explanation, whatever form the target took. One
    #: pair rather than one per form, because the explanation is the same
    #: job every time: the target is what changes shape, not the reading of
    #: it. A floor at all because a one-line explanation is the target said
    #: twice, which is the failure this column was added to fix.
    explanation_chars: tuple[int, int]
    #: How much of a list or an explanation has to come back for the verifier
    #: to be agreeing with it.
    answer_overlap: float
    #: How much of what the verifier recovered the target has to account for
    #: before the target is read as an incomplete key. The same recovery as
    #: `answer_overlap`, read the other way round. 0 turns the reading off.
    answer_coverage: float
    #: How much of a passage may be the names of people before it is read as
    #: a credits page and never asked about. 0 turns the reading off.
    party_density: float
    #: How much a candidate fact must have in common with the head of its
    #: sample before a second passage is offered at all. 0 offers one
    #: whatever it holds.
    #:
    #: Off by default: the mechanism is here to be tuned against a corpus,
    #: not because a threshold is known.
    meets_floor: float
    #: How much of what an unanswerable question is about has to occur in the
    #: material it was drawn from. Below it the question is off topic: any
    #: chatbot declines one about something the corpus never mentions.
    off_topic_overlap: float
    #: How many passages the corpus-wide probe shows the verifier before an
    #: unanswerable question is accepted. 0 judges one against its own
    #: passages alone, as every other gate does.
    elsewhere_passages: int
    long_answer_chars: int
    duplicate_cosine: float
    #: The cosine two unrelated questions score. Calibration for the stored
    #: confidence only; it decides no verdict.
    duplicate_floor: float
    #: How alike a passage must be to one in ANOTHER document before it is
    #: read as boilerplate and never asked about. 0 turns the reading off.
    #:
    #: A corpus repeats its own furniture: a copyright notice, a table of
    #: contents, an accreditation clause, a revision table. Each is real
    #: text that a fact can be extracted from and a question can be written
    #: about, and no gate refuses the result, because nothing is wrong with
    #: it except that nobody wants to know. What separates it from subject
    #: matter is that it appears in document after document nearly
    #: unchanged, which is a measurement rather than a word list: no
    #: language, no domain and no section name is assumed.
    #:
    #: A corpus of one document has no other document to repeat into, so
    #: nothing is excluded, which is the right answer rather than a gap.
    boilerplate_cosine: float
    #: How many questions a balanced release holds. 0 draws the largest one
    #: the accepted pool can fill without missing a quota.
    release_size: int
    #: The most of a release that may be questions with no answer. A ceiling
    #: and not a target, unlike the two mixes: too few tests a little less
    #: than it could, too many tests mostly whether a chatbot can say no.
    release_unanswerable: float
    #: How a release spreads over the difficulty bands. The whole set, so
    #: the unanswerable questions are counted in it - they are always easy.
    #: Not the same thing as difficulty_mix, which is what the planner aims
    #: the answerable ones at. None follows the bands the answerable pool
    #: holds.
    release_difficulty: dict[str, int] | None
    embedding_model: str
    max_tokens: int
    #: The model that writes a question, or None for the shared one.
    model: str | None
    verifier_model: str | None
    #: The model asked what a question's wording amounts to where a rule has
    #: not settled it, or None to ask the verifier's.
    phrasing_model: str | None = None
    #: A local NLI encoder for the entailment pass, or None to ask the
    #: verifier. Not an LLM_MODEL: it is loaded in the worker like the
    #: embedding model is.
    entailment_model: str | None = None
    entailment_threshold: float = 0.5
    entailment_overlap: float = 0.3
    #: A local extractive QA encoder for the recall half, or None to ask the
    #: verifier for every question. Not an LLM_MODEL either.
    answer_model: str | None = None
    answer_confidence: float = 0.9
    #: The longest pair either encoder reads, in tokens.
    encoder_max_tokens: int = 512
    #: How a release spreads over the kinds, or None for type_mix.
    release_types: dict[str, int] | None = None
    #: How a release spreads over the languages, or None for the accepted
    #: pool's own language split.
    release_languages: dict[str, int] | None = None
    #: How alike two questions resting on the same fact must be to be one,
    #: or None to hold them to duplicate_cosine.
    duplicate_shared_cosine: float | None = None
    #: The share of a topic's closest cross-passage fact pairs a second
    #: passage must be among before it is offered. Read off the topic's own
    #: vectors, so no cosine is tuned to a corpus. 0 sets no relative floor.
    meets_share: float = 0.0
    #: Which kind each spanning slot is dealt, in what proportion.
    kind_mix: dict[str, int] = field(default_factory=lambda: dict(_KIND_MIX))

    @classmethod
    def load(cls, source: Source = None) -> Settings:
        """Reads settings from the environment, or from an override.

        Args:
            source: Where to read them, or None for the process environment.

        Raises:
            KeyError: If any required setting is missing.
            ValueError: If a numeric setting is not a number, or a mix names
                a type, a band or an answer form that does not exist.
        """
        followups = csv("QUESTIONS_FOLLOWUP_TYPES", source)
        unknown = [name for name in followups if name not in SPECS]
        if unknown:
            raise ValueError(
                f"QUESTIONS_FOLLOWUP_TYPES names {', '.join(unknown)}, which is "
                f"not among {', '.join(sorted(SPECS))}"
            )
        kinds = csv("QUESTIONS_FACT_KINDS", source)
        unusable = [kind for kind in kinds if kind not in ASKABLE]
        if unusable:
            raise ValueError(
                f"QUESTIONS_FACT_KINDS names {', '.join(unusable)}, which this "
                f"stage cannot write a question from. It takes "
                f"{', '.join(ASKABLE)}; see the note beside ASKABLE for what "
                f"each other kind would need first."
            )
        return cls(
            per_topic=integer("QUESTIONS_PER_TOPIC", source),
            sample_size=integer("QUESTIONS_FACT_SAMPLE", source),
            samples_per_passage=integer("QUESTIONS_SAMPLES_PER_PASSAGE", source),
            fact_kinds=kinds,
            type_mix=_weights("QUESTIONS_TYPE_MIX", SPECS, source),
            difficulty_mix=_weights(
                "QUESTIONS_DIFFICULTY_MIX", tuple(Difficulty), source
            ),
            followup_types=followups,
            unanswerable_share=decimal("QUESTIONS_UNANSWERABLE_SHARE", source),
            followup_share=decimal("QUESTIONS_FOLLOWUP_SHARE", source),
            max_followups=integer("QUESTIONS_MAX_FOLLOWUPS", source),
            retries=integer("QUESTIONS_RETRIES", source),
            answer_chars=_bounds("QUESTIONS_ANSWER_CHARS", source),
            explanation_chars=_span("QUESTIONS_EXPLANATION_CHARS", source),
            answer_overlap=decimal("QUESTIONS_ANSWER_OVERLAP", source),
            answer_coverage=decimal("QUESTIONS_ANSWER_COVERAGE", source),
            party_density=decimal("QUESTIONS_PARTY_DENSITY", source),
            meets_floor=decimal("QUESTIONS_MEETS_FLOOR", source),
            # Absent reads the shipped share rather than none, so an older
            # backend.env starts the worker and still keeps the floor on.
            meets_share=(
                decimal("QUESTIONS_MEETS_SHARE", source)
                if optional("QUESTIONS_MEETS_SHARE", source)
                else MEETS_SHARE
            ),
            # Absent deals the code default mix.
            kind_mix=(
                _weights(
                    "QUESTIONS_KIND_MIX",
                    {name: one for name, one in KINDS.items() if one.passages > 1},
                    source,
                )
                if optional("QUESTIONS_KIND_MIX", source)
                else dict(_KIND_MIX)
            ),
            off_topic_overlap=decimal("QUESTIONS_OFF_TOPIC_OVERLAP", source),
            elsewhere_passages=integer("QUESTIONS_ELSEWHERE_PASSAGES", source),
            long_answer_chars=integer("QUESTIONS_LONG_ANSWER_CHARS", source),
            duplicate_cosine=decimal("QUESTIONS_DUPLICATE_COSINE", source),
            # Absent holds a shared fact to QUESTIONS_DUPLICATE_COSINE, so a
            # backend.env written before the setting existed still loads.
            duplicate_shared_cosine=(
                decimal("QUESTIONS_DUPLICATE_SHARED_COSINE", source)
                if optional("QUESTIONS_DUPLICATE_SHARED_COSINE", source)
                else None
            ),
            duplicate_floor=decimal("QUESTIONS_DUPLICATE_FLOOR", source),
            boilerplate_cosine=decimal("QUESTIONS_BOILERPLATE_COSINE", source),
            release_size=integer("QUESTIONS_RELEASE_SIZE", source),
            release_unanswerable=decimal("QUESTIONS_RELEASE_UNANSWERABLE", source),
            release_difficulty=(
                _weights("QUESTIONS_RELEASE_DIFFICULTY", tuple(Difficulty), source)
                if optional("QUESTIONS_RELEASE_DIFFICULTY", source)
                else None
            ),
            # The one embedding model, as chunking reads it: a question
            # embedded by a model other than the one a passage was sized by
            # measures distance in a space the corpus was never put in.
            embedding_model=required("EMBEDDING_MODEL", source),
            max_tokens=integer("EMBEDDING_MAX_TOKENS", source),
            # Absent means the model LLM_MODEL names.
            model=optional("QUESTIONS_MODEL", source),
            # Absent means the model LLM_MODEL names. A verifier that is the
            # writer is worth knowing about rather than guessing at, so the
            # service warns rather than failing.
            verifier_model=optional("QUESTIONS_VERIFIER_MODEL", source),
            phrasing_model=optional("QUESTIONS_PHRASING_MODEL", source),
            entailment_model=optional("NLI_MODEL", source),
            entailment_threshold=decimal("NLI_ENTAILMENT_THRESHOLD", source),
            entailment_overlap=decimal("QUESTIONS_ENTAILMENT_OVERLAP", source),
            encoder_max_tokens=integer("ENCODER_MAX_TOKENS", source),
            answer_model=optional("QA_MODEL", source),
            answer_confidence=decimal("QA_ANSWER_CONFIDENCE", source),
            release_types=(
                _weights("QUESTIONS_RELEASE_TYPES", SPECS, source)
                if optional("QUESTIONS_RELEASE_TYPES", source)
                else None
            ),
            release_languages=(
                _languages("QUESTIONS_RELEASE_LANGUAGES", source)
                if optional("QUESTIONS_RELEASE_LANGUAGES", source)
                else None
            ),
        )
