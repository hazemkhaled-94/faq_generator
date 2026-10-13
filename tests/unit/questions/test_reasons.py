"""Whether the material states why, which is what a `reason` slot is dealt.

A why question written from a fact that gives no reason has two outcomes,
both bad: a key that restates the rule, or a reason the writer invented. So
the deal reads the evidence for a purpose marker before it hands a `reason`
slot anything, and a language with no markers is not read at all.
"""

from __future__ import annotations

import pytest

from question_generation.gates import states_a_reason

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Gloves are worn to prevent injury to the hands.", "en"),
        ("Requests are confirmed in writing so that the time can be evidenced.", "en"),
        ("The account is frozen because the card was reported stolen.", "en"),
        ("The fee is paid in order to keep the account open.", "en"),
        ("Das Konto wird gesperrt, um weitere Abbuchungen zu verhindern.", "de"),
        ("Der Antrag wird geprüft, um die Frist einzuhalten.", "de"),
        ("Die Karte wird gesperrt, damit niemand sie benutzen kann.", "de"),
        ("Der Zweck der Sperre ist der Schutz des Kontos.", "de"),
        ("Die Lieferung verzögert sich, weil das Lager geschlossen ist.", "de"),
    ],
)
def test_a_stated_purpose_is_read_as_a_reason(text: str, language: str) -> None:
    """Each marker of each language, in a sentence of its own."""
    assert states_a_reason(text, language) is True


@pytest.mark.parametrize(
    ("text", "language"),
    [
        # A scope, named with the word for a purpose, and no reason given.
        ("For the purposes of this section, a device is any insured item.", "en"),
        ("A standard request is answered within 48 hours.", "en"),
        # `um` as a preposition, and `damit` as an adverb, state no purpose.
        ("Die Filiale öffnet um 9 Uhr zu den üblichen Zeiten.", "de"),
        ("Damit ist das Girokonto gemeint.", "de"),
        ("Eine Standardanfrage wird innerhalb von 48 Stunden beantwortet.", "de"),
    ],
)
def test_a_rule_with_no_purpose_is_not_a_reason(text: str, language: str) -> None:
    """A marker read as a raw substring would take every one of these."""
    assert states_a_reason(text, language) is False


def test_a_language_with_no_markers_is_not_read() -> None:
    """None, so a caller filters nothing and the language keeps today's deal."""
    assert states_a_reason("La tarjeta se bloquea para evitar fraudes.", "es") is None
    assert states_a_reason("The device weighs 4 kg.", None) is None
