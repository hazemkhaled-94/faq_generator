"""Naming a topic, and carrying a name across a refit.

A refit deletes the topics of each language it fits, so a label survives
only by being matched on top terms.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from topic_drivers import LabellerDriver

from llm.client import ModelUnavailable
from topic_modelling.labels import _EXCERPT_CHARS
from topic_modelling.models import FittedTopic
from topic_modelling.topics import _LABEL_MATCH, carry_labels

FIRST = ["lieferung", "versand", "transport", "paket", "monatlich"]
SECOND = ["wartung", "reparatur", "instandhaltung", "ersatzteil", "pruefung"]
DECIDED = datetime(2026, 10, 1, 9, tzinfo=UTC)


def previous() -> list[FittedTopic]:
    """Two named topics, one of them taken out of coverage."""
    return [
        FittedTopic(0, FIRST, label="Shipping", include_in_coverage=False),
        FittedTopic(
            1, SECOND, label="Maintenance", labelled_by="person", decided_at=DECIDED
        ),
    ]


# ── Asking the model ──────────────────────────────────────────────────────


def test_a_model_answer_becomes_the_label() -> None:
    """The label is taken as given, and the model is recorded."""
    labeller = LabellerDriver('"Anti-money laundering".')

    assert labeller.names("money", "laundering") == "Anti-money laundering"
    assert labeller.labeller.model == "test-model"


@pytest.mark.parametrize(
    ("said", "stored"),
    [
        ("Warehouse safety", "Warehouse safety"),
        ('"Warehouse safety"', "Warehouse safety"),
        ("Warehouse safety.", "Warehouse safety"),
        ('"Warehouse safety."', "Warehouse safety"),
        ("'Warehouse safety'", "Warehouse safety"),
        ("  Warehouse safety \n", "Warehouse safety"),
    ],
)
def test_the_wrapping_a_model_adds_is_taken_off(said, stored) -> None:
    """A quote around a full stop used to leave the quote behind."""
    assert LabellerDriver(said).names("a", "b") == stored


@pytest.mark.parametrize(
    "refusal",
    ["Mixed", "mixed", "MIXED", "  Mixed. ", "„Mixed“", "“Mixed”", "Gemischt"],
)
def test_a_refusal_is_not_stored_as_a_name(refusal) -> None:
    """A model that finds no subject leaves the topic unnamed."""
    assert LabellerDriver(refusal).names("a", "b") is None


@pytest.mark.parametrize("blank", ["", "   ", '"."', "..."])
def test_an_answer_with_no_words_in_it_is_not_a_name(blank) -> None:
    """Stripping can leave nothing, and nothing is not a label."""
    assert LabellerDriver(blank).names("a", "b") is None


def test_a_model_that_cannot_be_reached_answers_nothing() -> None:
    """A topic with no name beats losing the fit that produced it."""
    refusing = LabellerDriver("never said").refusing(ModelUnavailable("no route"))

    assert refusing.names("a", "b") is None


def test_only_a_model_failure_is_swallowed() -> None:
    """Anything else is a defect and must reach the run."""
    broken = LabellerDriver("never said").refusing(TypeError("bad shape"))

    with pytest.raises(TypeError):
        broken.names("a", "b")


# ── The prompt ────────────────────────────────────────────────────────────


def test_the_prompt_names_the_language_to_answer_in() -> None:
    """The report a name appears in is read in that language."""
    labeller = LabellerDriver("A name", languages={"de": "German"})

    labeller.names("lieferung", language="de")

    assert "German" in labeller.prompt, labeller.prompt


def test_a_language_with_no_name_configured_falls_back_to_its_code() -> None:
    """Better an ISO code in the prompt than the word `None`."""
    labeller = LabellerDriver("A name", languages={"de": "German"})

    labeller.names("delivery", language="fr")

    assert "fr" in labeller.prompt, labeller.prompt


def test_the_prompt_lists_the_terms_in_the_order_they_were_given() -> None:
    """The terms are weighted, and the prompt says strongest first."""
    labeller = LabellerDriver("A name")

    labeller.names("first", "second", "third")

    assert "first, second, third" in labeller.prompt, labeller.prompt


def test_a_long_excerpt_is_cut_rather_than_sent_whole() -> None:
    """A dozen full passages would not fit in one prompt."""
    labeller = LabellerDriver("A name")

    labeller.names("a", excerpts=["x" * (_EXCERPT_CHARS * 3)])

    assert "x" * _EXCERPT_CHARS in labeller.prompt
    assert "x" * (_EXCERPT_CHARS + 1) not in labeller.prompt


def test_a_topic_with_no_excerpts_is_still_asked_about() -> None:
    """Its terms alone are a thin prompt, but they are a prompt."""
    labeller = LabellerDriver("A name")

    assert labeller.names("lieferung", "versand", excerpts=[]) == "A name"


def test_the_model_is_told_to_answer_with_a_noun_phrase() -> None:
    """The system message is what keeps a name out of sentence form."""
    labeller = LabellerDriver("A name")

    labeller.names("a")

    assert "noun phrase" in labeller.system, labeller.system


def test_every_topic_of_a_language_is_named_in_one_call() -> None:
    """The model sees the whole set, so it can tell the topics apart."""
    driver = LabellerDriver("Shipping", "Maintenance")

    named = driver.labeller.label_all(
        [(FittedTopic(3, FIRST), ["a parcel"]), (FittedTopic(7, SECOND), ["a repair"])],
        "en",
    )

    assert named == {3: "Shipping", 7: "Maintenance"}
    assert driver.model.calls == 1
    assert "Topic 3" in driver.prompt and "Topic 7" in driver.prompt


def test_one_name_given_twice_in_one_answer_names_one_topic() -> None:
    """Two topics under one name read as one topic in the coverage report."""
    driver = LabellerDriver("Shipping", "Shipping")

    named = driver.labeller.label_all(
        [(FittedTopic(0, FIRST), []), (FittedTopic(1, SECOND), [])], "en"
    )

    assert named == {0: "Shipping"}


def test_a_word_takes_the_spelling_the_excerpts_give_it() -> None:
    """A Swiss corpus writes `ss`; a name the model spells `ß` is not its word."""
    driver = LabellerDriver("Konten für Großkunden")

    named = driver.labeller.label_all(
        [(FittedTopic(0, FIRST), ["Grosskunden erhalten eigene Konten."])], "de"
    )

    assert named == {0: "Konten für Grosskunden"}


def test_a_letter_the_excerpts_never_use_is_folded() -> None:
    """A compound the excerpts never print still takes their alphabet."""
    driver = LabellerDriver("Großkundenkonten")

    named = driver.labeller.label_all(
        [(FittedTopic(0, FIRST), ["Grosskunden erhalten eigene Konten."])], "de"
    )

    assert named == {0: "Grosskundenkonten"}


def test_a_word_the_excerpts_print_as_written_is_kept() -> None:
    """`Masse` and `Maße` fold to one key and are two words.

    The excerpts printing `Maße` first used to respell the `Masse` they also
    print, which named a parcel's weight after its dimensions.
    """
    driver = LabellerDriver("Masse des Pakets")

    named = driver.labeller.label_all(
        [
            (
                FittedTopic(0, FIRST),
                [
                    "Die Maße des Pakets dürfen 120 x 60 x 60 cm nicht überschreiten.",
                    "Die Masse des Pakets darf 31,5 kg nicht überschreiten.",
                ],
            )
        ],
        "de",
    )

    assert named == {0: "Masse des Pakets"}


def test_words_most_names_end_on_are_left_out() -> None:
    """The domain the whole corpus shares tells no topic apart."""
    driver = LabellerDriver(
        "Card fees in banking", "Transfers in banking", "Savings in banking"
    )

    named = driver.labeller.label_all(
        [(FittedTopic(index, [f"term{index}"]), []) for index in range(3)], "en"
    )

    assert named == {0: "Card fees", 1: "Transfers", 2: "Savings"}


def test_words_only_half_the_names_end_on_stay() -> None:
    """Two of four is a pair of topics that share something, not the domain."""
    driver = LabellerDriver(
        "Card fees in branches", "Cash in branches", "Transfers", "Savings"
    )

    named = driver.labeller.label_all(
        [(FittedTopic(index, [f"term{index}"]), []) for index in range(4)], "en"
    )

    assert named[0] == "Card fees in branches"


# ── Carrying a label across a refit ───────────────────────────────────────


def test_a_label_travels_to_the_topic_it_matches() -> None:
    """The top terms decide, not the topic number."""
    refitted = [
        FittedTopic(
            0, ["wartung", "reparatur", "instandhaltung", "ersatzteil", "intervall"]
        ),
        FittedTopic(1, ["lieferung", "versand", "transport", "paket", "jaehrlich"]),
    ]

    carried = carry_labels(refitted, previous())

    assert carried[0].label == "Maintenance", carried[0].label
    assert carried[1].label == "Shipping", carried[1].label


def test_what_named_a_label_travels_with_it() -> None:
    """A name a person typed must not come back as a model's, nor undated."""
    carried = carry_labels([FittedTopic(0, SECOND)], previous())

    assert carried[0].labelled_by == "person", carried[0]
    assert carried[0].decided_at == DECIDED, carried[0]


def test_the_coverage_choice_travels_with_the_label() -> None:
    """A topic taken out of coverage by hand stays out across a refit."""
    carried = carry_labels([FittedTopic(0, FIRST)], previous())

    assert carried[0].label == "Shipping"
    assert carried[0].include_in_coverage is False, carried[0]


def test_a_label_is_dropped_rather_than_put_on_an_unrelated_topic() -> None:
    """No match means no name."""
    unrelated = carry_labels(
        [FittedTopic(0, ["farbe", "lack", "oberflaeche"])], previous()
    )

    assert unrelated[0].label is None, unrelated[0].label
    assert unrelated[0].labelled_by is None
    assert unrelated[0].include_in_coverage is True


def test_a_label_is_used_once() -> None:
    """Two topics matching the same label take it between them."""
    twice = carry_labels([FittedTopic(0, FIRST), FittedTopic(1, FIRST)], previous())

    assert [t.label for t in twice].count("Shipping") == 1, [t.label for t in twice]


def test_an_overlap_at_the_threshold_carries() -> None:
    """The bound is inclusive, so a label at it is kept rather than lost."""
    at = carry_labels(
        [FittedTopic(0, ["a", "b", "c"])],
        [FittedTopic(0, ["a", "b", "d", "e"], label="Kept")],
    )

    assert _LABEL_MATCH == 0.4, "this case is built around the threshold"
    assert at[0].label == "Kept", at[0]


def test_an_overlap_below_the_threshold_drops() -> None:
    """Two unrelated topics sharing a term or two are still unrelated."""
    below = carry_labels(
        [FittedTopic(0, ["a", "b", "c", "d", "e"])],
        [FittedTopic(0, ["a", "b", "x", "y", "z"], label="Dropped")],
    )

    assert below[0].label is None, below[0]


def test_a_first_fit_carries_nothing() -> None:
    """There is no previous fit, and that is not an error."""
    first = carry_labels([FittedTopic(0, FIRST), FittedTopic(1, SECOND)], [])

    assert [one.label for one in first] == [None, None]


def test_a_refit_that_produced_no_topic_carries_nothing() -> None:
    """An empty list in, an empty list out."""
    assert carry_labels([], previous()) == []


def test_a_previous_topic_with_no_terms_matches_nothing() -> None:
    """A signature nobody can read cannot be matched on."""
    carried = carry_labels(
        [FittedTopic(0, FIRST)], [FittedTopic(0, [], label="Unmatchable")]
    )

    assert carried[0].label is None, carried[0]


def test_a_new_topic_with_no_terms_takes_no_label() -> None:
    """Two empty signatures are not a match."""
    carried = carry_labels([FittedTopic(0, [])], previous())

    assert carried[0].label is None, carried[0]


def test_an_unnamed_previous_topic_out_of_coverage_still_travels() -> None:
    """The exclusion is a decision, and it is recorded without a name."""
    carried = carry_labels(
        [FittedTopic(0, FIRST)],
        [FittedTopic(0, FIRST, include_in_coverage=False)],
    )

    assert carried[0].label is None
    assert carried[0].include_in_coverage is False, carried[0]


def test_every_topic_keeps_its_own_index_and_terms() -> None:
    """Carrying a label must not carry the topic it came from."""
    carried = carry_labels([FittedTopic(7, SECOND)], previous())

    assert carried[0].topic_index == 7, carried[0]
    assert carried[0].top_terms == SECOND, carried[0]


def test_a_name_taken_that_carries_a_placeholder_is_shown_as_written() -> None:
    """A label naming `{{excerpts}}` pulled the excerpts into the taken line."""
    from topic_modelling.models import FittedTopic

    driver = LabellerDriver("Warehouse safety")

    driver.labeller.label(
        FittedTopic(0, ["a", "b"]), "en", ["an excerpt"], ["the {{excerpts}} topic"]
    )

    assert "the {{excerpts}} topic" in driver.prompt
