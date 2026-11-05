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
    "segment",
    [
        "iPhone 15 Pro",
        "Windows 11 Home",
        "Tarif 2025 Privatkunden",
        "Plan 3 Gold card",
        "Step 1 Register your account",
        "Schritt 1 Konto eröffnen",
    ],
)
def test_a_product_or_year_heading_is_no_numbered_section(segment: str) -> None:
    """A word, a number and more is a title, not the document's own label of a part."""
    from extraction.validation import HEADING_LABEL

    assert HEADING_LABEL.match(segment) is None


@pytest.mark.parametrize("segment", ["Section 7", "Regel 5.1", "§ 3", "Artikel 12"])
def test_a_word_and_a_number_alone_is_a_numbered_section(segment: str) -> None:
    """The label the document gives a part stays read."""
    from extraction.validation import HEADING_LABEL

    assert HEADING_LABEL.match(segment) is not None


@pytest.mark.parametrize(
    "language,text,paths",
    [
        (
            "en",
            "The Gold plan costs 9 EUR; see Plan 2.",
            ("Plan 1 Basic", "Plan 2 Silver", "Plan 3 Gold"),
        ),
        (
            "en",
            "Delivery to Zone 2 takes four days.",
            ("Zone 1 Inner city", "Zone 2 Suburbs", "Zone 3 Rural"),
        ),
        (
            "de",
            "Ab Pflegegrad 2 gilt ein höherer Satz.",
            ("Pflegegrad 1 Geringe", "Pflegegrad 2 Erhebliche", "Pflegegrad 3 Schwere"),
        ),
        (
            "fr",
            "Le tarif de la zone 2 s'applique.",
            ("Zone 1 Centre", "Zone 2 Banlieue", "Zone 3 Rural"),
        ),
        (
            "el",
            "Η χρέωση της ζώνης 2 ισχύει.",
            ("Ζώνη 1 Κέντρο", "Ζώνη 2 Προάστια", "Ζώνη 3 Επαρχία"),
        ),
        (
            "en",
            "Warranty on iPhone 15 is two years.",
            ("iPhone 15 Pro", "iPhone 16 Pro", "iPhone 17 Pro"),
        ),
        (
            "de",
            "Der Tarif 2025 gilt für Privatkunden.",
            ("Tarif 2025 Privatkunden", "Tarif 2026 Geschäftskunden"),
        ),
    ],
)
def test_an_entity_series_with_a_title_is_no_section_numbering(language, text, paths):
    """Plan 1 Basic, Zone 2 Suburbs: a numbered tier or product, not the document's parts."""
    rows = [(text, "Shop > Intro", "d")] + [
        (f"Passage {i}.", f"Shop > {path}", "d") for i, path in enumerate(paths)
    ]
    assert references(language, rows) == []


#: (language, a shop page quoting a label, its trail, another document's
#: section of that name, its trail)
_QUOTED = [
    (
        "de",
        "Zum Ändern Ihrer Adresse klicken Sie im Kundenkonto auf „Kontakt“ und speichern die neue Anschrift.",
        "Kundenkonto > Adresse ändern",
        "Die Bank ist montags bis freitags von 9 bis 17 Uhr telefonisch erreichbar.",
        "Kontakt",
    ),
    (
        "en",
        'To change your address, open your account, click "Contact" and save the new address.',
        "Your account > Change address",
        "The bank can be reached by phone from Monday to Friday, 9 am to 5 pm.",
        "Contact",
    ),
    (
        "fr",
        "Pour changer votre adresse, ouvrez votre compte, cliquez sur « Contact » et enregistrez la nouvelle adresse.",
        "Votre compte > Changer d'adresse",
        "La banque est joignable par téléphone du lundi au vendredi, de 9 h à 17 h.",
        "Contact",
    ),
    (
        "el",
        "Για να αλλάξετε τη διεύθυνσή σας, ανοίξτε τον λογαριασμό σας, πατήστε «Επικοινωνία» και αποθηκεύστε τη νέα διεύθυνση.",
        "Ο λογαριασμός σας > Αλλαγή διεύθυνσης",
        "Η τράπεζα είναι διαθέσιμη τηλεφωνικά από Δευτέρα έως Παρασκευή, 9:00 έως 17:00.",
        "Επικοινωνία",
    ),
]


def _quoting(language, quoting, trail, other, heading, same, named=""):
    """The reference links of a page quoting a label, the section of that name in the same or another document."""
    shop = titled(quoting + named, trail, 1, "shop-a", language, "Online shop help")
    section = titled(
        other,
        heading,
        2,
        "shop-a" if same else "bank-b",
        language,
        "Online shop help" if same else "Current account terms",
    )
    got = linked([shop], [shop, section], {1: 1, 2: 1}, 5, 2)
    return [(k.kind, k.named) for k in got if k.kind == "reference"]


@pytest.mark.parametrize(("language", "quoting", "trail", "other", "heading"), _QUOTED)
def test_a_quoted_span_names_no_heading_of_another_document(
    language, quoting, trail, other, heading
):
    """A button label a shop page quotes is no reference to a bank's section of that name."""
    assert _quoting(language, quoting, trail, other, heading, same=False) == []


@pytest.mark.parametrize(
    ("language", "quoting", "trail", "other", "heading"), _QUOTED[:2]
)
def test_a_quoted_span_names_a_heading_of_its_own_document(
    language, quoting, trail, other, heading
):
    """Under one document the quoted heading is a reference."""
    got = _quoting(language, quoting, trail, other, heading, same=True)
    assert got == [("reference", heading)]


@pytest.mark.parametrize(
    ("language", "text", "title"),
    [
        (
            "de",
            "Zum Ändern Ihrer Adresse klicken Sie laut den Allgemeinen Geschäftsbedingungen auf „Kontakt“.",
            "Allgemeine Geschäftsbedingungen",
        ),
        (
            "en",
            'To change your address, click "Contact" as the Current account terms of the bank say.',
            "Current account terms of the bank",
        ),
    ],
)
def test_a_quoted_span_names_a_heading_of_another_document_the_sentence_names(
    language, text, title
):
    """A sentence naming the other document's title makes the quote that document's section."""
    shop = titled(text, "Kundenkonto > Adresse", 1, "shop-a", language, "Online shop")
    bank = titled("Die Bank ist erreichbar.", "Kontakt", 2, "bank-b", language, title)
    bank = replace(bank, section_path="Contact" if language == "en" else "Kontakt")
    got = linked([shop], [shop, bank], {1: 1, 2: 1}, 5, 2)
    assert [(k.kind, k.named) for k in got if k.kind == "reference"] == [
        ("reference", bank.section_path)
    ]


#: (language, the quoting sentence, the quoting trail, the target heading, the target document's title)
_TITLED = [
    (
        "en",
        'See "Cancellation" in our Terms and Conditions.',
        "Orders > Cancelling",
        "Cancellation",
        "Terms and Conditions",
    ),
    (
        "en",
        'See "Cancellation" in our Terms and Conditions.',
        "Orders > Cancelling",
        "Cancellation",
        "Terms and Conditions of Example Shop Ltd",
    ),
    (
        "en",
        'Notice periods are set out under "Termination" in our General Terms and Conditions.',
        "Account > Closing",
        "Termination",
        "General Terms and Conditions",
    ),
    (
        "en",
        'The fees are listed under "Current account" in the Price List.',
        "Accounts > Fees",
        "Current account",
        "Price List - Example Bank plc (valid from 1 January 2026)",
    ),
    (
        "en",
        'Fees are listed under "Charges" in the Account Terms.',
        "Accounts > Fees",
        "Charges",
        "Account Terms",
    ),
    (
        "de",
        "Die Widerrufsfrist ist im Abschnitt „Widerruf“ unserer AGB geregelt.",
        "Bestellung > Rücksendung",
        "Widerruf",
        "Allgemeine Geschäftsbedingungen (AGB) der Beispiel-Shop GmbH",
    ),
    (
        "de",
        "Die Entgelte finden Sie im Preis- und Leistungsverzeichnis unter „Girokonto“.",
        "Konto > Kosten",
        "Girokonto",
        "Preis- und Leistungsverzeichnis der Musterbank, Stand 1. Januar 2026",
    ),
    (
        "de",
        "Einzelheiten regelt der Abschnitt „Kündigung“ der Allgemeinen Geschäftsbedingungen der Musterbank.",
        "Girokonto > Konto schließen",
        "Kündigung",
        "Allgemeine Geschäftsbedingungen der Musterbank AG",
    ),
    (
        "en",
        'Apply online through the Citizens Portal under "Applications".',
        "Registration > Moving",
        "Applications",
        "Citizens Portal of Example Town",
    ),
]


@pytest.mark.parametrize(("language", "text", "trail", "heading", "title"), _TITLED)
def test_a_quoted_heading_of_a_document_the_sentence_names_by_its_title_links(
    language, text, trail, heading, title
):
    """A title as a bank or a shop writes it, with its issuer, edition or abbreviation."""
    shop = titled(text, trail, 1, "shop-a", language, "Help centre")
    other = titled("Text of the section.", heading, 2, "doc-b", language, title)
    got = linked([shop], [shop, other], {1: 1, 2: 1}, 5, 2)
    assert [(k.kind, k.named) for k in got if k.kind == "reference"] == [
        ("reference", heading)
    ]


@pytest.mark.parametrize(
    ("language", "text", "heading", "title"),
    [
        (
            "de",
            "Zum Ändern Ihrer Adresse klicken Sie im Kundenkonto auf „Kontakt“.",
            "Kontakt",
            "Kontakt",
        ),
        (
            "en",
            'To change your address, click "Contact" in your account.',
            "Contact",
            "Contact",
        ),
        (
            "de",
            "Klicken Sie auf „Kontakt“. Kontaktdaten der Bank stehen in den Kontobedingungen.",
            "Kontakt",
            "Kontobedingungen",
        ),
        (
            "en",
            'Click "Contact" to write to us. Bank details are in the Account Terms.',
            "Contact",
            "Account Terms",
        ),
        (
            "en",
            'Under "Returns" your account lists the direct debits returned to the bank.',
            "Returns",
            "Returns",
        ),
    ],
)
def test_a_quote_is_no_naming_of_a_title_by_itself_or_by_another_sentence(
    language, text, heading, title
):
    """The title is read in the sentence of the quote with the quote taken out."""
    shop = titled(text, "Account > Address", 1, "shop-a", language, "Help centre")
    other = titled("Text of the section.", heading, 2, "doc-b", language, title)
    got = linked([shop], [shop, other], {1: 1, 2: 1}, 5, 2)
    assert [k for k in got if k.kind == "reference"] == []
