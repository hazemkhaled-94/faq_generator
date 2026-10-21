"""Where a bank or shop sentence ends: a figure, an abbreviation, a third language.

Every citation resolves against these sentences, so a cut inside one leaves a
fact's evidence holding half a rule, and a number moved to the next sentence
is a number the fact citing its own sentence is refused for.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from nlp.analysis import sentences

pytestmark = pytest.mark.nlp


def texts(text: str, language: str | None) -> list[str]:
    """The text of each sentence the passage splits into."""
    return [one.text for one in sentences(text, language)]


@pytest.mark.parametrize(
    ("text", "language", "first"),
    [
        (
            "Die Gebühr beträgt EUR 5. Die Bank bucht sie ab.",
            "de",
            "Die Gebühr beträgt EUR 5.",
        ),
        (
            "Es gilt Ziffer 3. Die Bank zahlt Zinsen.",
            "de",
            "Es gilt Ziffer 3.",
        ),
        (
            "Maßgeblich ist Kapitel 2. Dort stehen die Preise.",
            "de",
            "Maßgeblich ist Kapitel 2.",
        ),
        (
            "Die Gebühr regelt Nr. 2. Die Bank zahlt Zinsen.",
            "de",
            "Die Gebühr regelt Nr. 2.",
        ),
        (
            "Fees are listed in Sect. 4. The bank pays interest.",
            "en",
            "Fees are listed in Sect. 4.",
        ),
    ],
)
def test_a_figure_ending_a_sentence_stays_in_it(text, language, first) -> None:
    """Only a number opening its line numbers an item; one ending a sentence is its figure."""
    assert texts(text, language)[0] == first


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("1. Die Karte kostet 5 EUR.\n2. Die Überweisung ist frei.", "de"),
        ("1. The card costs EUR 5.\n2. A transfer is free.", "en"),
    ],
)
def test_an_item_number_opening_its_line_opens_its_item(text, language) -> None:
    """The cut the figure rule must keep: the number belongs to the item after it."""
    assert texts(text, language)[1].startswith("2.")


@pytest.mark.parametrize(
    "text",
    [
        "See the rules (cf. Section 4) for details. The bank pays.",
        'Customers pay a fee "incl. VAT" here. The shop ships.',
    ],
)
def test_an_abbreviation_inside_brackets_ends_nothing(text) -> None:
    """The bracket or quote before the word hides no abbreviation."""
    assert len(texts(text, "en")) == 2


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Interest is 2.5% p.a. on all balances. The bank pays it yearly.", "en"),
        ("Die Gebühr beträgt 5 EUR/Mon. zzgl. MwSt. Die Bank bucht sie ab.", "de"),
    ],
)
def test_a_price_abbreviation_before_a_lower_case_word_ends_nothing(
    text, language
) -> None:
    """A rate per year or a price per month ends no sentence before what it qualifies."""
    assert len(texts(text, language)) == 2


@pytest.mark.parametrize(
    ("text", "language", "count"),
    [
        ("Bitte nennen Sie Ihre Kunden-Nr. Die Bank prüft dann den Auftrag.", "de", 2),
        ("Ihre Bestell-Nr. 12345 steht auf der Rechnung. Die Bank zahlt.", "de", 2),
        ("Wir liefern Mo.–Fr. Die Bank ist geschlossen.", "de", 2),
        ("Die Gebühr beträgt 5 € zzgl. MwSt. Der Versand kostet 4,90 €.", "de", 2),
        (
            "Der Zins beträgt 2,5 % p. a. für alle Guthaben. Die Bank zahlt ihn.",
            "de",
            2,
        ),
        ("Das Limit beträgt 1 Mio. Euro pro Jahr. Die Bank prüft es.", "de", 2),
        ("The order no. 123 is printed on the invoice. The shop ships.", "en", 2),
        ("Our opening hours are Mon.–Fri. The shop is closed on Sundays.", "en", 2),
        ("The fee is approx. EUR 5 per month. The bank debits it.", "en", 2),
        ("Die Karte kostet mtl. 5 Euro und jährl. 50 Euro.", "de", 1),
        ("Fees are listed in Sect. 4 and Sect. 5 of these terms.", "en", 1),
    ],
)
def test_a_bank_or_shop_abbreviation_ends_where_its_sentence_does(
    text, language, count
) -> None:
    """Compounds and ranges ending on an abbreviation, and amounts beside one."""
    assert len(texts(text, language)) == count


#: Bank and shop sentences in two languages no table has a row for.
_THIRD = (
    ("fr", "Le prix comprend la TVA, env. 20 %. La livraison est gratuite."),
    ("fr", "Les frais sont fixés à l'art. 7. Le client paie 4,90 € par mois."),
    ("es", "El precio incluye IVA aprox. 5 EUR. El envío es gratis."),
    ("es", "La comisión es de 1 000 EUR, p. ej. por transferencia. Se cobra al mes."),
)


@pytest.mark.parametrize(("language", "text"), _THIRD)
def test_a_language_no_table_names_is_split_without_failing(language, text) -> None:
    """The tables are read with `.get`, so a third language falls back, never raises."""
    found = sentences(text, language)

    assert found
    assert [one.index for one in found] == list(range(len(found)))


#: Fragments a bank or shop passage is made of, abbreviations and figures among them.
_PIECES = st.sampled_from(
    [
        "Die Gebühr beträgt EUR 5.",
        "Es gilt Ziffer 3.",
        "inkl. MwSt.",
        "ca. 3 Tage",
        "Kunden-Nr.",
        "Mo.–Fr.",
        "z. B. Visa",
        "The fee is EUR 4.90 a month.",
        "incl. VAT",
        "(cf. Section 4)",
        "1 000 EUR",
        "4,90 €",
        "\n2. ",
        "- ",
        "/",
        " ",
        "Le prix est de 5 €.",
        "El envío es gratis.",
    ]
)


@given(
    pieces=st.lists(_PIECES, min_size=1, max_size=8),
    language=st.sampled_from(["de", "en", "fr", "es", None]),
)
def test_sentences_cover_their_passage_in_order(pieces, language) -> None:
    """Each sentence is the text between its offsets, and they never overlap.

    Stripped, as chunking stores a passage: a blank prefix reads as a blank sentence.
    """
    text = " ".join(pieces).strip()
    assume(text)
    found = sentences(text, language)

    for one in found:
        assert text[one.start : one.end] == one.text
        assert one.text.strip()
    for before, after in pairwise(found):
        assert before.end <= after.start
    covered = "".join(one.text for one in found)
    assert "".join(covered.split()) == "".join(text.split())


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Bitte geben Sie Ihre Nr.\nDie Bank prüft den Auftrag.", "de"),
        ("Prices are shown incl.\nShipping is charged extra.", "en"),
    ],
)
def test_an_abbreviation_ending_its_line_may_end_its_sentence(text, language) -> None:
    """One that never ends a sentence does so only on its line: a line break can."""
    assert len(texts(text, language)) == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        "After a medial abbreviation the parser misreads (gem.), its next cut "
        "before a lower-case word stays: gem. Preisverzeichnis | eine Gebühr"
    ),
)
@pytest.mark.parametrize(
    "text",
    [
        "Der Kunde zahlt gem. Preisverzeichnis eine Gebühr.",
        "Der Kunde zahlt gem. Ziff. 3 eine Gebühr.",
        "Die Gebühr wird gem. AGB berechnet.",
    ],
)
def test_a_cut_before_a_lower_case_word_after_an_abbreviation_is_dropped(text) -> None:
    """The parser's later cut before a lower-case word ends no sentence either."""
    assert texts(text, "de") == [text]
