"""Where the sentence splitter ends a sentence, pinned on stored passages.

Every citation resolves against these sentences, so one cut in the middle
leaves a fact's evidence holding half a rule: the word before a slash in one
sentence and the word after it in the next, a clause opened by a comma
filed under the sentence after it, an item's number left on the item
before. Each row is text a run stored, beside the sentences it must read
as; the last rows are cuts that are right and must stay.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp

#: (name, language, text, the sentences it reads as).
ROWS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "two names for one restart joined by a slash",
        "de",
        (
            "Wird der Ball nach vorne gespielt und berührt er keinen Spieler, die "
            "Querlatte oder einen Torpfosten, wird der Strafstoss/Elfmeter "
            "wiederholt."
        ),
        (
            "Wird der Ball nach vorne gespielt und berührt er keinen Spieler, die "
            "Querlatte oder einen Torpfosten, wird der Strafstoss/Elfmeter "
            "wiederholt.",
        ),
    ),
    (
        "a main clause opened by a comma after its condition",
        "de",
        (
            "Zeigt der Schiedsrichter nicht an, dass es sich um einen indirekten "
            "Freistoss handelt, und geht der Ball direkt ins Tor, so muss der "
            "indirekte Freistoss wiederholt werden."
        ),
        (
            "Zeigt der Schiedsrichter nicht an, dass es sich um einen indirekten "
            "Freistoss handelt, und geht der Ball direkt ins Tor, so muss der "
            "indirekte Freistoss wiederholt werden.",
        ),
    ),
    (
        "an item number kept with its item",
        "de",
        (
            "1. Ein VAR ist ein Spieloffizieller, der den Schiedsrichter "
            "unterstützt.\n2. Der Schiedsrichter muss immer eine Entscheidung "
            "fällen."
        ),
        (
            "1. Ein VAR ist ein Spieloffizieller, der den Schiedsrichter unterstützt.",
            "2. Der Schiedsrichter muss immer eine Entscheidung fällen.",
        ),
    ),
    (
        "etc. before a lower-case word ends nothing",
        "en",
        (
            "For a factual decision such as offside, ball out of play etc. a "
            "'VAR-only review' is usually appropriate."
        ),
        (
            "For a factual decision such as offside, ball out of play etc. a "
            "'VAR-only review' is usually appropriate.",
        ),
    ),
    (
        "etc. before a capital at a line end does end a sentence",
        "en",
        (
            "The referee keeps records of time, goals, misconduct etc.\n"
            "Competition rules must state who replaces an official."
        ),
        (
            "The referee keeps records of time, goals, misconduct etc.",
            "Competition rules must state who replaces an official.",
        ),
    ),
    (
        "a full stop with no space after it still ends a sentence",
        "en",
        "The fee is due on the first day.Payment follows within 14 days.",
        ("The fee is due on the first day.", "Payment follows within 14 days."),
    ),
    (
        "two fees joined by a slash in a bank's schedule",
        "de",
        "Die Gebühren/Entgelte werden am Monatsende belastet.",
        ("Die Gebühren/Entgelte werden am Monatsende belastet.",),
    ),
)


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [row[1:] for row in ROWS],
    ids=[row[0] for row in ROWS],
)
def test_a_stored_passage_splits_where_its_sentences_end(language, text, expected) -> None:
    """The sentences read off the text, each stripped of its spacing."""
    from nlp.analysis import sentences

    found = tuple(sentence.text.strip() for sentence in sentences(text, language))

    assert found == expected
