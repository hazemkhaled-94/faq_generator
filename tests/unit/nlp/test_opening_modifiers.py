"""What a bank or shop fact opening on a pointing word or a polite Sie leaves unresolved.

`_opens` reads a modifier by its lemma or as written, and the polite reading
reads the passage the fact was drawn from. These pin both where the suite
held only one example, and hold two gaps as strict expected failures.
"""

from __future__ import annotations

import pytest

from nlp.analysis import claim

pytestmark = pytest.mark.nlp


def references(text: str, language: str, *passages: str) -> tuple[str, ...]:
    """What the statement points to outside itself, read against its passages."""
    return claim(text, language, passages).references


@pytest.mark.parametrize(
    "text",
    [
        "Nachstehende Bedingungen gelten für alle Konten.",
        "Besagter Kunde zahlt keine Gebühr.",
        "Obengenannte Gebühren gelten für jedes Konto.",
    ],
)
def test_an_inflected_modifier_opening_a_statement_points_outside(text) -> None:
    """The lemmatizer leaves a capitalised opening inflected; the table names its base."""
    assert references(text, "de")


@pytest.mark.parametrize(
    "text",
    [
        "Die nachstehenden Bedingungen gelten für alle Konten.",
        "Besagte Karte wird sofort gesperrt.",
        "Vorgenannte Gebühren gelten für jedes Konto.",
        "Eine solche Karte wird nach drei falschen PIN-Eingaben gesperrt.",
    ],
)
def test_a_modifier_the_lemmatizer_reads_points_outside(text) -> None:
    """The same words where the lemma comes back as the table writes it."""
    assert references(text, "de")


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("The above fees apply to every account.", "en"),
        ("The said card is blocked at once.", "en"),
        ("Die oben genannten Gebühren gelten für jedes Konto.", "de"),
        ("Die vorstehenden Bedingungen gelten für alle Konten.", "de"),
    ],
)
def test_a_back_pointing_modifier_points_outside(text, language) -> None:
    """Each names something said before the fact, which the fact does not hold."""
    assert references(text, language)


@pytest.mark.parametrize(
    "text",
    [
        "Above EUR 500, a fee of 1% applies.",
        "Above EUR 50, shipping is free.",
        "Following the price changes, the bank charges EUR 5 per month.",
        "Following customer complaints, the shop extends its return period.",
    ],
)
def test_a_preposition_opening_a_fact_points_nowhere(text) -> None:
    """A preposition heading its object is no modifier, whatever word it is."""
    assert references(text, "en") == ()


@pytest.mark.parametrize(
    "between",
    [
        "Wir prüfen alle Angaben.",
        "Die Bank prüft alle Angaben.",
    ],
)
def test_sie_after_a_sentence_with_no_plural_noun_subject_addresses_the_reader(
    between,
) -> None:
    """Only a plural noun subject before it could be what an opening Sie stands for.

    A plural pronoun subject (`Wir`) or a plural object (`alle Angaben`) is not.
    """
    passage = (
        f"Bitte geben Sie Ihre IBAN an. {between} Sie erhalten dann eine Bestätigung."
    )

    assert references("Sie erhalten dann eine Bestätigung.", "de", passage) == ()


def test_sie_after_a_plural_noun_subject_stays_a_reference() -> None:
    """Händler is what Sie may stand for, polite address elsewhere or not."""
    passage = (
        "Bitte geben Sie Ihre IBAN an. Händler prüfen alle Angaben. "
        "Sie erhalten dann eine Bestätigung."
    )

    assert references("Sie erhalten dann eine Bestätigung.", "de", passage) == ("sie",)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Ces frais s'appliquent à chaque compte.", "fr"),
        ("Les frais suivants s'appliquent.", "fr"),
        ("Estas comisiones se aplican a cada cuenta.", "es"),
        ("Vous recevez une confirmation par e-mail.", "fr"),
    ],
)
def test_a_language_no_table_names_is_read_without_failing(text, language) -> None:
    """Every per-language table is read with `.get`, so a third language falls back."""
    found = claim(text, language, (text,))

    assert isinstance(found.references, tuple)


@pytest.mark.parametrize(
    "opened",
    ["„Sie erhalten eine Provision.“", "\n- Sie erhalten eine Provision."],
    ids=["quoted", "bulleted"],
)
def test_sie_opening_a_quoted_or_bulleted_sentence_after_a_plural_subject_stays_a_reference(
    opened,
) -> None:
    """The mark before it opens the sentence; Sie is still its first word."""
    passage = f"Bitte geben Sie Ihre IBAN an. Händler werben Kunden. {opened}"

    assert references("Sie erhalten eine Provision.", "de", passage) == ("sie",)


def test_sie_behind_an_opening_quote_is_no_polite_form_inside_a_sentence() -> None:
    """Only a word before it makes a capital Sie polite; a quote mark is none."""
    passage = "Die Bank prüft den Auftrag. „Sie erhalten eine Bestätigung.“"

    assert references("Sie erhalten eine Bestätigung.", "de", passage) == ("sie",)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Die folgenden Gebühren fallen an:", "de"),
        ("The following fees apply:", "en"),
        ("Kontoführung: Die folgenden Gebühren fallen monatlich an.", "de"),
        ("Account fees: The following fees apply monthly.", "en"),
    ],
    ids=["de-colon-ends", "en-colon-ends", "de-colon-before", "en-colon-before"],
)
def test_a_following_list_no_colon_after_it_gives_points_outside(
    text, language
) -> None:
    """A colon spares the list only where words follow it, after the modifier."""
    assert references(text, language)
