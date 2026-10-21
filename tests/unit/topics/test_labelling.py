"""Naming a topic, and carrying a person's decision across a refit.

A refit deletes the topics of each language it fits, so a decision survives
only on the topic that holds most of the passages it was made for.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from topic_drivers import LabellerDriver

from llm.client import ModelUnavailable
from topic_modelling.labels import _EXCERPT_CHARS, _unshared
from topic_modelling.models import FittedTopic, PassageWeight
from topic_modelling.topics import carry_labels, dominant

FIRST = ["lieferung", "versand", "transport", "paket", "monatlich"]
SECOND = ["wartung", "reparatur", "instandhaltung", "ersatzteil", "pruefung"]
DECIDED = datetime(2026, 10, 1, 9, tzinfo=UTC)


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


# Names and each topic's top terms; the word that is the subject must survive.
SUBJECTS = {
    "bank-en": (
        [
            "Credit card payment",
            "Debit card payment",
            "Prepaid card payment",
            "Account statements",
        ],
        [
            ["credit", "card", "payment"],
            ["debit", "card", "payment"],
            ["prepaid", "card", "payment"],
            ["account", "statement"],
        ],
        "card",
    ),
    "shop-en": (
        [
            "Gift voucher redemption",
            "Store voucher redemption",
            "Birthday voucher redemption",
            "Returns",
        ],
        [
            ["gift", "voucher", "redempt"],
            ["store", "voucher", "redempt"],
            ["birthday", "voucher", "redempt"],
            ["return"],
        ],
        "voucher",
    ),
    "bank-de": (
        [
            "Kreditkarte Zahlung Ausland",
            "Debitkarte Zahlung Ausland",
            "Prepaidkarte Zahlung Ausland",
            "Kontoauszüge",
        ],
        [
            ["kreditkarte", "zahlung", "ausland"],
            ["debitkarte", "zahlung", "ausland"],
            ["prepaidkarte", "zahlung", "ausland"],
            ["kontoauszug"],
        ],
        "Zahlung",
    ),
    "shop-de": (
        [
            "Online Bestellung Rückgabe",
            "Laden Bestellung Rückgabe",
            "Telefon Bestellung Rückgabe",
            "Gutscheine",
        ],
        [
            ["online", "bestellung", "rückgabe"],
            ["laden", "bestellung", "rückgabe"],
            ["telefon", "bestellung", "rückgabe"],
            ["gutschein"],
        ],
        "Rückgabe",
    ),
}


@pytest.mark.parametrize("key", SUBJECTS)
def test_a_shared_ending_that_is_the_subject_is_kept(key) -> None:
    """`Credit card payment` was stored as `Credit`.

    The strip read any ending most names share as the corpus's domain. A
    sub-subject several topics share is a top term of theirs; the domain is
    in too many passages to be one.
    """
    names, terms, subject = SUBJECTS[key]

    out = _unshared(dict(enumerate(names)), dict(enumerate(terms)))

    for index in (0, 1, 2):
        assert subject.casefold() in out[index].casefold(), out


def test_one_topic_carrying_the_domain_as_a_term_does_not_keep_it_for_all() -> None:
    """The domain is a term of at most a few topics; the rest still lose it."""
    names = {
        0: "Transfers in banking",
        1: "Cards in banking",
        2: "Loans in banking",
        3: "Savings in banking",
    }
    terms = {0: ["transfer", "banking"], 1: ["card"], 2: ["loan"], 3: ["saving"]}

    assert _unshared(names, terms) == {
        0: "Transfers",
        1: "Cards",
        2: "Loans",
        3: "Savings",
    }


@pytest.mark.parametrize(
    ("ending", "term"), [("in coffee shop", "fee"), ("im Handel", "and")]
)
def test_a_term_inside_a_word_is_not_the_word(ending, term) -> None:
    """Three letters inside `coffee` or `Handel` are not the subject."""
    names = {i: f"{head} {ending}" for i, head in enumerate(["Beans", "Tea", "Milk"])}
    terms = {i: [term] for i in names}

    assert _unshared(names, terms) == {0: "Beans", 1: "Tea", 2: "Milk"}


def test_a_domain_ending_no_term_carries_is_still_taken_off() -> None:
    """The domain tells no topic apart and is no term, so it goes."""
    names = {
        0: "Anträge für Kreditkarten im Bankwesen",
        1: "Gebühren im Bankwesen",
        2: "Konten im Bankwesen",
    }
    terms = {0: ["antrag", "kreditkarte"], 1: ["gebühr"], 2: ["konto"]}

    assert _unshared(names, terms) == {
        0: "Anträge für Kreditkarten",
        1: "Gebühren",
        2: "Konten",
    }


# ── Carrying a decision across a refit ────────────────────────────────────
#
# `before` is each passage's dominant topic in the fit being replaced, and
# `after` its dominant topic in the new one.


def test_a_person_name_travels_to_the_topic_holding_most_of_its_passages() -> None:
    """The passages decide, not the topic number or the terms."""
    carried, dropped = carry_labels(
        [FittedTopic(0, ["card", "fee"]), FittedTopic(1, ["transfer", "abroad"])],
        [
            FittedTopic(
                0,
                ["card", "fee"],
                label="Card fees",
                labelled_by="person",
                decided_at=DECIDED,
            )
        ],
        before={1: 0, 2: 0, 3: 0, 4: 0},
        after={1: 1, 2: 1, 3: 1, 4: 0},
    )

    assert carried[1].label == "Card fees", carried
    assert (carried[1].labelled_by, carried[1].decided_at) == ("person", DECIDED)
    assert carried[0].label is None, carried[0]
    assert dropped == 0


def test_a_name_does_not_travel_on_shared_terms_alone() -> None:
    """A topic with the old one's very terms may hold few of its passages.

    Matched on terms, this carried at an overlap of 1.0.
    """
    terms = ["return", "refund", "parcel"]

    carried, dropped = carry_labels(
        [
            FittedTopic(0, terms),
            FittedTopic(1, ["voucher", "gift"]),
            FittedTopic(2, ["delivery", "courier"]),
        ],
        [FittedTopic(0, terms, label="Returns", labelled_by="person")],
        before={1: 0, 2: 0, 3: 0, 4: 0},
        after={1: 0, 2: 1, 3: 2, 4: 2},
    )

    assert [one.label for one in carried] == [None, None, None], carried
    assert dropped == 1


def test_an_exclusion_does_not_ride_into_a_merged_topic() -> None:
    """Two passages of five are not the topic a person took out of coverage."""
    carried, dropped = carry_labels(
        [FittedTopic(0, ["consent", "data", "partner"])],
        [
            FittedTopic(
                0,
                ["consent", "newsletter"],
                label="Marketing consent",
                labelled_by="person",
                include_in_coverage=False,
            )
        ],
        before={1: 0, 2: 0, 3: 1, 4: 1, 5: 1},
        after={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
    )

    assert carried[0].include_in_coverage is True, carried[0]
    assert carried[0].label is None, carried[0]
    assert dropped == 1


def test_a_model_given_name_never_travels() -> None:
    """It is named afresh, against the names this fit gives."""
    carried, _ = carry_labels(
        [FittedTopic(0, ["card", "fee"])],
        [FittedTopic(0, ["card", "fee"], label="Card fees", labelled_by="azure/x")],
        before={1: 0, 2: 0, 3: 0},
        after={1: 0, 2: 0, 3: 0},
    )

    assert (carried[0].label, carried[0].labelled_by) == (None, None), carried[0]


def test_a_coverage_choice_on_a_model_named_topic_travels_without_the_name() -> None:
    """The exclusion is a person's decision; the name was not."""
    carried, _ = carry_labels(
        [FittedTopic(0, ["card", "fee"])],
        [
            FittedTopic(
                0,
                ["card", "fee"],
                label="Card fees",
                labelled_by="azure/x",
                include_in_coverage=False,
                decided_at=DECIDED,
            )
        ],
        before={1: 0, 2: 0, 3: 0},
        after={1: 0, 2: 0, 3: 0},
    )

    assert carried[0].label is None, carried[0]
    assert carried[0].include_in_coverage is False, carried[0]
    assert carried[0].decided_at == DECIDED, carried[0]


def test_an_unnamed_previous_topic_out_of_coverage_still_travels() -> None:
    """The exclusion is a decision, and it is recorded without a name."""
    carried, _ = carry_labels(
        [FittedTopic(0, FIRST)],
        [FittedTopic(0, FIRST, include_in_coverage=False)],
        before={1: 0, 2: 0},
        after={1: 0, 2: 0},
    )

    assert carried[0].label is None
    assert carried[0].include_in_coverage is False, carried[0]


def test_the_coverage_choice_travels_with_a_person_name() -> None:
    """A topic taken out of coverage by hand stays out across a refit."""
    carried, _ = carry_labels(
        [FittedTopic(0, FIRST)],
        [
            FittedTopic(
                0,
                FIRST,
                label="Shipping",
                labelled_by="person",
                include_in_coverage=False,
            )
        ],
        before={1: 0, 2: 0},
        after={1: 0, 2: 0},
    )

    assert carried[0].label == "Shipping"
    assert carried[0].include_in_coverage is False, carried[0]


def test_passages_new_to_the_corpus_do_not_dilute_the_match() -> None:
    """The new topic counts only the passages both fits hold, so it can grow."""
    carried, _ = carry_labels(
        [FittedTopic(0, ["return", "refund"])],
        [FittedTopic(0, ["return", "refund"], label="Returns", labelled_by="person")],
        before={1: 0, 2: 0, 3: 0},
        after={1: 0, 2: 0, 3: 0} | dict.fromkeys(range(10, 20), 0),
    )

    assert carried[0].label == "Returns", carried[0]


def test_a_decision_does_not_ride_one_surviving_passage_onto_another_subject() -> None:
    """One passage of ten left in the new fit is not the topic it was.

    It is the only one of them both fits hold, so over those alone it was
    all of the old topic, and the twenty new passages beside it in the new
    topic are about something else.
    """
    carried, dropped = carry_labels(
        [FittedTopic(0, ["mortgage"]), FittedTopic(1, ["loan"])],
        [
            FittedTopic(
                0, ["card"], label="Card fees", labelled_by="person", decided_at=DECIDED
            )
        ],
        before=dict.fromkeys(range(1, 11), 0) | dict.fromkeys(range(11, 21), 1),
        after={10: 0}
        | dict.fromkeys(range(100, 120), 0)
        | dict.fromkeys(range(11, 21), 1),
    )

    assert [one.label for one in carried] == [None, None], carried
    assert dropped == 1


def test_an_even_split_does_not_carry() -> None:
    """Half is not most, and two topics cannot both hold most of one."""
    carried, dropped = carry_labels(
        [FittedTopic(0, ["card"]), FittedTopic(1, ["fee"])],
        [FittedTopic(0, ["card", "fee"], label="Card fees", labelled_by="person")],
        before={1: 0, 2: 0, 3: 0, 4: 0},
        after={1: 0, 2: 0, 3: 1, 4: 1},
    )

    assert [one.label for one in carried] == [None, None], carried
    assert dropped == 1


def test_after_a_rechunk_nothing_travels_and_the_loss_is_logged(caplog) -> None:
    """Re-chunking took the old memberships, so no passage is held by both fits."""
    with caplog.at_level("WARNING"):
        carried, dropped = carry_labels(
            [FittedTopic(0, FIRST)],
            [FittedTopic(0, FIRST, label="Shipping", labelled_by="person")],
            before={},
            after={1: 0, 2: 0},
        )

    assert carried[0].label is None, carried[0]
    assert dropped == 1
    assert "Shipping" in caplog.text, caplog.text


def test_a_first_fit_carries_nothing() -> None:
    """There is no previous fit, and that is not an error."""
    first, dropped = carry_labels(
        [FittedTopic(0, FIRST), FittedTopic(1, SECOND)], [], before={}, after={1: 0}
    )

    assert [one.label for one in first] == [None, None]
    assert dropped == 0


def test_a_refit_that_produced_no_topic_carries_nothing() -> None:
    """An empty list in, an empty list out, and the decision counted as lost."""
    carried, dropped = carry_labels(
        [],
        [FittedTopic(0, FIRST, label="Shipping", labelled_by="person")],
        before={1: 0},
        after={},
    )

    assert carried == []
    assert dropped == 1


def test_every_topic_keeps_its_own_index_and_terms() -> None:
    """Carrying a decision must not carry the topic it came from."""
    carried, _ = carry_labels(
        [FittedTopic(7, SECOND)],
        [FittedTopic(1, FIRST, label="Maintenance", labelled_by="person")],
        before={1: 1, 2: 1},
        after={1: 7, 2: 7},
    )

    assert carried[0].label == "Maintenance", carried[0]
    assert carried[0].topic_index == 7, carried[0]
    assert carried[0].top_terms == SECOND, carried[0]


def test_a_passage_tied_between_two_topics_is_dominant_in_the_lower_index() -> None:
    """As the store breaks the tie, so a fit and the one it replaces agree."""
    weights = [
        PassageWeight(1, 3, 0.5),
        PassageWeight(1, 2, 0.5),
        PassageWeight(2, 0, 0.2),
        PassageWeight(2, 1, 0.7),
    ]

    assert dominant(weights) == {1: 2, 2: 1}


def test_a_name_taken_that_carries_a_placeholder_is_shown_as_written() -> None:
    """A label naming `{{excerpts}}` pulled the excerpts into the taken line."""
    from topic_modelling.models import FittedTopic

    driver = LabellerDriver("Warehouse safety")

    driver.labeller.label_all(
        [(FittedTopic(0, ["a", "b"]), ["an excerpt"])],
        "en",
        ["the {{excerpts}} topic"],
    )

    assert "the {{excerpts}} topic" in driver.prompt
