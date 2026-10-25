"""Which words point at something outside the text they sit in.

Three readings, because no one of them covers both languages: `PronType=Dem`
off the morphology, a noun made definite AND counted, and the anaphoric
adjectives that carry no feature at all. Both configured languages are
checked, because a rule that held only for the one the corpus happened to be
in is the thing this project is not allowed to be.
"""

from __future__ import annotations

import pytest

from nlp.analysis import _counted, interrogatives, pointing

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Wie groß ist der Unterschied zwischen diesen beiden Lehrplänen?", "de"),
        ("Was wurde in dieser Version geändert?", "de"),
        ("How long is the gap between these two editions?", "en"),
        ("What changed in this version?", "en"),
    ],
)
def test_a_pointing_word_is_found(text: str, language: str) -> None:
    """The determiner carries it, and the noun beside it hides it."""
    assert pointing(text, language), "nothing was read as pointing"


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Wie groß ist der Unterschied zwischen den beiden Lehrplänen?", "de"),
        ("How large is the gap between the two editions?", "en"),
    ],
)
def test_a_definite_count_points_without_a_demonstrative(
    text: str, language: str
) -> None:
    """The reading this gate used to miss.

    `den beiden` is an article plus `PronType=Ind` and `the two` is an
    article plus `NumType=Card`, so neither is `PronType=Dem` and the
    measurement never saw either. A set of a known size the question never
    introduced points outward as surely as `diesen beiden` does.
    """
    assert pointing(text, language), "a definite count was read as pointing at nothing"


def test_an_indefinite_article_does_not_make_a_count_definite() -> None:
    """German `ein` carries `PronType=Art` as `den` does, with `Definite=Ind`."""
    from types import SimpleNamespace

    def child(pos: str, **features: str) -> SimpleNamespace:
        morph = {name: [value] for name, value in features.items()}
        return SimpleNamespace(text="", pos_=pos, morph=SimpleNamespace(get=morph.get))

    noun = SimpleNamespace(
        children=[
            child("DET", Definite="Ind", PronType="Art"),
            child("DET", PronType="Ind"),
        ]
    )

    assert _counted(noun) is None


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("How do the aforementioned parties differ?", "en"),
        ("What does the latter require?", "en"),
    ],
)
def test_an_anaphoric_adjective_points(text: str, language: str) -> None:
    """These carry no feature at all: every tagset reads them as adjectives."""
    assert pointing(text, language), "an anaphoric adjective was not read"


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Wie lange dauert die Beantwortung einer Standardanfrage?", "de"),
        ("How long is allowed for answering a standard support request?", "en"),
    ],
)
def test_a_question_pointing_nowhere_is_clean(text: str, language: str) -> None:
    """The measurement must not fire on an ordinary question."""
    assert pointing(text, language) == ()


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Wie lange dauert die Beantwortung einer Standardanfrage?", "de"),
        ("How long is allowed for answering a standard support request?", "en"),
        ("Welche Verfahren gelten für Abnahmekriterien?", "de"),
        ("Which techniques apply to acceptance criteria?", "en"),
    ],
)
def test_a_question_word_is_found_under_either_naming(text: str, language: str) -> None:
    """Penn and STTS say so in the tag; a UD tagset says so in the morphology.

    English `What` carries no PronType at all and German `Wie` carries no W
    tag, so reading only one of the two conventions reports nothing for one
    of the two languages that ship.
    """
    assert interrogatives(text, language), "no question word was read"


@pytest.mark.parametrize(
    ("text", "language"),
    [
        # An `unanchored` rejection a real topic produced, and it was
        # wrong. `die im Korrekturverzeichnis genannten Abschnitte` says
        # inside the question where to look, so `genannt` points at nothing
        # outside it. Bare `genannt` is no longer a trigger; the compounds
        # that carry the pointing in the word itself still are.
        (
            (
                "Wie viele Abschnitte des Lehrplans wurden geändert, wenn man "
                "die im Korrekturverzeichnis genannten Abschnitte zusammenzählt?"
            ),
            "de",
        ),
        # `said` is the past tense of `say` far more often than it is `the
        # said document`, and the tagger is what tells them apart.
        ("What did the manager say about the deadline?", "en"),
    ],
)
def test_a_participle_specified_in_the_question_points_nowhere(
    text: str, language: str
) -> None:
    """The measurement may over-fire, but not on an ordinary phrasing."""
    assert pointing(text, language) == ()


def test_an_unambiguous_compound_still_points() -> None:
    """`vorgenannt` carries the pointing in the word, where `genannt` does not."""
    assert pointing("Wie unterscheiden sich die vorgenannten Verfahren?", "de")


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("What is the fee for the 2026/27 budget?", "en"),
        ("When does the 2026/27 term start?", "en"),
        ("Welche Gebühr gilt für das 2026/27 Budget?", "de"),
        ("Wann beginnt das Semester 2026/27?", "de"),
    ],
)
def test_a_slashed_figure_is_not_a_count(text: str, language: str) -> None:
    """`2026/27` is a period the question names, not a set of a known size."""
    assert pointing(text, language) == ()


def test_a_slashed_figure_does_not_hide_a_count_beside_it() -> None:
    """The figure is skipped, the other quantifier still counts."""
    assert pointing("What are the two instalments of the 2026/27 plan?", "en")


def test_a_language_no_configuration_names_points_at_nothing() -> None:
    """Inert, not wrong: nothing is read for a language without a model."""
    assert pointing("ステータス 2026/27 の期間は？", "ja") == ()
