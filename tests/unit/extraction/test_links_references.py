"""How a passage's references to other sections are read into links."""

from __future__ import annotations

from dataclasses import replace

import pytest
from drivers import passage

from extraction.links import linked

pytestmark = pytest.mark.nlp


def one(text, path, ident, doc, language):
    """Builds one passage of a document under a heading trail."""
    return replace(
        passage(text, language=language, section_path=path, id=ident), doc_sha256=doc
    )


def references(language, rows, head=1):
    """The reference links of passage `head`, as tuples of passage ids."""
    made = [one(t, p, i + 1, d, language) for i, (t, p, d) in enumerate(rows)]
    got = linked([made[head - 1]], made, {m.id: m.id for m in made}, 5, 2)
    return [
        tuple(p.id for p in link.passages) for link in got if link.kind == "reference"
    ]


@pytest.mark.parametrize(
    "language,rows",
    [
        (
            "en",
            [
                (
                    "Fees for dormant accounts are set out in Section 7.",
                    "Card Terms > Section 2 > Dormant accounts",
                    "bank",
                ),
                (
                    "A dormant card account is charged 10 EUR a year.",
                    "Card Terms > Section 7 > Yearly fees",
                    "bank",
                ),
                (
                    "Returned goods are refunded within 14 days.",
                    "Section 7 > Refunds",
                    "shop",
                ),
            ],
        ),
        (
            "de",
            [
                (
                    "Die Gebühren für ruhende Konten regelt Abschnitt 7.",
                    "Kartenbedingungen > Abschnitt 2 > Ruhende Konten",
                    "bank",
                ),
                (
                    "Für ein ruhendes Kartenkonto werden 10 EUR im Jahr berechnet.",
                    "Kartenbedingungen > Abschnitt 7 > Jahresgebühren",
                    "bank",
                ),
                (
                    "Zurückgesandte Waren werden binnen 14 Tagen erstattet.",
                    "Abschnitt 7 > Erstattungen",
                    "shop",
                ),
            ],
        ),
    ],
)
def test_a_numbered_reference_resolves_in_the_heads_own_document(language, rows):
    """Two documents both hold a Section 7: the head reads its own."""
    assert references(language, rows) == [(1, 2)]


@pytest.mark.parametrize(
    "language,rows",
    [
        (
            "en",
            [
                (
                    "Fees are charged as Section 7 of the Payment Services Act requires.",
                    "Card Terms > Section 2 > Fees",
                    "bank",
                ),
                (
                    "Returned goods are refunded within 14 days.",
                    "Section 7 > Refunds",
                    "shop",
                ),
            ],
        ),
        (
            "de",
            [
                (
                    "Gebühren fallen an, wie es Abschnitt 7 des Zahlungsdienstegesetzes verlangt.",
                    "Kartenbedingungen > Abschnitt 2 > Gebühren",
                    "bank",
                ),
                (
                    "Zurückgesandte Waren werden binnen 14 Tagen erstattet.",
                    "Abschnitt 7 > Erstattungen",
                    "shop",
                ),
            ],
        ),
    ],
)
def test_a_numbered_reference_is_dropped_when_the_heads_document_lacks_it(
    language, rows
):
    """A Section 7 the head's document lacks names another document's."""
    assert references(language, rows) == []


@pytest.mark.parametrize(
    "language,text,path,target",
    [
        (
            "en",
            "Refunds for faulty goods follow “Customers’ rights”.",
            "Returns > Customers’ rights",
            "A faulty item is refunded in full.",
        ),
        (
            "en",
            "A minor's account is opened as set out in “Children’s accounts”.",
            "Accounts > Children’s accounts",
            "A parent signs for a child under 16.",
        ),
        (
            "de",
            "Erstattungen bei Mängeln regelt „Rechte des Kunden’s Wahl“.",
            "Rückgabe > Rechte des Kunden’s Wahl",
            "Ein defekter Artikel wird voll erstattet.",
        ),
        (
            "fr",
            "Voir «Conditions d’accès» pour les cartes.",
            "Cartes > Conditions d’accès",
            "Une carte est délivrée à 18 ans.",
        ),
    ],
)
def test_a_quoted_heading_with_a_typographic_apostrophe_is_linked(
    language, text, path, target
):
    """A ’ followed by a letter or inside a double-quoted span does not end it."""
    rows = [(text, "Orders > Refunds", "d"), (target, path, "d")]
    assert references(language, rows) == [(1, 2)]


@pytest.mark.parametrize(
    "language,text,path,target",
    [
        (
            "en",
            "Fees follow ‘Customers’ fees’ in all cases.",
            "Fees > Customers’ fees",
            "A customer pays 2 EUR per order.",
        ),
        (
            "en",
            "Fees follow 'Customers' fees' in all cases.",
            "Fees > Customers' fees",
            "A customer pays 2 EUR per order.",
        ),
        (
            "de",
            "Die Kosten regelt ‚Hans’ Konten‘ im Einzelnen.",
            "Konten > Hans’ Konten",
            "Ein Konto kostet 2 EUR im Monat.",
        ),
    ],
)
def test_a_single_quoted_heading_ending_in_a_possessive_is_linked(
    language, text, path, target
):
    """A possessive ’ before a space closes no span that a later mark closes as a heading."""
    rows = [(text, "Shop > Overview", "d"), (target, path, "d")]
    assert references(language, rows) == [(1, 2)]


def test_a_single_quote_still_closes_at_the_first_mark_naming_no_heading() -> None:
    """'Returns' is the heading; the possessive after it opens nothing longer."""
    rows = [
        ("See 'Returns' or the customers' desk.", "Shop > Overview", "d"),
        ("Items are returned within 30 days.", "Shop > Returns", "d"),
    ]
    assert references("en", rows) == [(1, 2)]


@pytest.mark.parametrize(
    "language,text,paths",
    [
        (
            "en",
            "For details, see Sections 7, 9 and 11.",
            ("Section 7 > Fees", "Section 9 > Limits", "Section 11 > Closing"),
        ),
        (
            "en",
            "The fees in Sections 4 and 5 apply.",
            ("Section 4 > Fees", "Section 5 > Limits", "Section 6 > Closing"),
        ),
        (
            "de",
            "Die Gebühren regeln die Abschnitte 4 und 5.",
            ("Abschnitt 4 > Gebühren", "Abschnitt 5 > Limits", "Abschnitt 6 > Schluss"),
        ),
    ],
)
def test_a_plural_label_word_before_numbers_is_a_reference(language, text, paths):
    """'Sections 7, 9 and 11' names sections whatever the tagger calls the word."""
    rows = [(text, "Terms > Intro", "d")] + [
        (f"Passage {i}.", path, "d") for i, path in enumerate(paths)
    ]
    assert references(language, rows) == [(1, 2)]


def titled(text, path, ident, doc, language, title):
    """One passage of a document with a title."""
    return replace(one(text, path, ident, doc, language), title=title)


@pytest.mark.parametrize(
    "language,rows",
    [
        (
            "en",
            [
                (
                    "Fees for dormant accounts follow Section 7 of the General Terms.",
                    "Card Terms > Section 2 > Dormant accounts",
                    "bank",
                    "Card Terms",
                ),
                (
                    "A dormant card account is charged 10 EUR a year.",
                    "Section 7 > Yearly fees",
                    "terms",
                    "General Terms",
                ),
                (
                    "Returned goods are refunded within 14 days.",
                    "Section 7 > Refunds",
                    "shop",
                    "Shop Rules",
                ),
            ],
        ),
        (
            "de",
            [
                (
                    "Gebühren für ruhende Konten folgen Abschnitt 7 der Allgemeinen Geschäftsbedingungen.",
                    "Kartenbedingungen > Abschnitt 2 > Ruhende Konten",
                    "bank",
                    "Kartenbedingungen",
                ),
                (
                    "Für ein ruhendes Kartenkonto werden 10 EUR im Jahr berechnet.",
                    "Abschnitt 7 > Jahresgebühren",
                    "agb",
                    "Allgemeine Geschäftsbedingungen",
                ),
                (
                    "Zurückgesandte Waren werden binnen 14 Tagen erstattet.",
                    "Abschnitt 7 > Erstattungen",
                    "shop",
                    "Ladenregeln",
                ),
            ],
        ),
    ],
)
def test_a_numbered_reference_names_another_document_by_its_title(language, rows):
    """'Section 7 of the General Terms' goes to the document of that title."""
    made = [
        titled(t, p, i + 1, d, language, ti) for i, (t, p, d, ti) in enumerate(rows)
    ]
    got = linked([made[0]], made, {m.id: m.id for m in made}, 5, 2)
    refs = [tuple(p.id for p in k.passages) for k in got if k.kind == "reference"]
    assert refs == [(1, 2)]


@pytest.mark.parametrize(
    "language,rows",
    [
        (
            "en",
            [
                (
                    "Fees for dormant accounts are set out in Article 17.",
                    "Card Terms > Article 2 Dormant accounts",
                    "bank",
                ),
                (
                    "A dormant card account is charged 10 EUR a year.",
                    "Card Terms > Article 17 Ethical provisions",
                    "bank",
                ),
            ],
        ),
        (
            "de",
            [
                (
                    "Die Kündigung regelt gemäß § 5 der Vertrag.",
                    "Bedingungen > § 2 Laufzeit",
                    "shop",
                ),
                (
                    "Der Kunde kann jederzeit mit einer Frist von 14 Tagen kündigen.",
                    "Bedingungen > § 5 Kündigung",
                    "shop",
                ),
            ],
        ),
        (
            "en",
            [
                (
                    "Fees are set out in Section 7.",
                    "Terms > Section 2: Scope",
                    "bank",
                ),
                (
                    "A dormant card account is charged 10 EUR a year.",
                    "Terms > Section 7: Fees",
                    "bank",
                ),
            ],
        ),
    ],
)
def test_a_heading_with_a_title_after_its_number_is_a_reference_target(language, rows):
    """`Article 17 Ethical provisions` teaches `article` and is what `Article 17` names."""
    assert references(language, rows) == [(1, 2)]


def test_a_heading_with_no_number_teaches_no_label() -> None:
    """`Overview` is a heading, not a numbered part."""
    rows = [
        ("See Overview 7 for details.", "Terms > Section 2 Scope", "bank"),
        (
            "A dormant card account is charged 10 EUR a year.",
            "Terms > Overview",
            "bank",
        ),
    ]

    assert references("en", rows) == []
