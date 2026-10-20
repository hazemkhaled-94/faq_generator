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
