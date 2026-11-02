"""A hyphen that ends a printed line reaches the project's own repair.

The converter's page assembly and its reading-order merge drop a hyphen
that ends a line, so `Online-` over `Händler` became `OnlineHändler` and
`14-` over `30` became `1430` before the per-language repair read them. The
converter now keeps the hyphen for `rejoined`, which closes a compound broken
at its own hyphen and joins a word the page broke.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


#: language: (lines of one paragraph, what the text must hold, what it must not)
CASES = {
    "de": (
        [
            "Ewa hat einige Bücher bei einem Online-",
            "Händler gekauft und die Rückgabe innerhalb von 14-",
            "30 Tagen beantragt. Die Zahlung erfolgte vom Giro-",
            "oder Sparkonto, die Bestätigung kam per E-",
            "Mail an ihre Adresse. Der Händler hat seinen Sitz in Polen.",
        ],
        ["Online-Händler", "14-30", "Giro- oder", "E-Mail"],
        ["OnlineHändler", "1430", "Girooder", "EMail"],
    ),
    "en": (
        [
            "A buyer ordered some books from a third-party seller with a 2-",
            "year guarantee and asked for a refund within 14-",
            "30 days. The order was paid from a non-",
            "EU account and the seller replied by e-",
            "mail within one week of the request being sent.",
        ],
        ["2-year", "14-30", "non-EU"],
        ["2year", "1430", "nonEU"],
    ),
    "pl": (
        [
            "Klient kupił książki u sprzedawcy z UE-",
            "Polska i złożył wniosek o zwrot w ciągu 14-",
            "30 dni od daty dostawy towaru do domu klienta.",
        ],
        ["14-30"],
        ["1430"],
    ),
    "el": (
        [
            "Ο πελάτης αγόρασε βιβλία και ζήτησε επιστροφή εντός 14-",
            "30 ημερών από την παράδοση του προϊόντος στο σπίτι του.",
        ],
        ["14-30"],
        ["1430"],
    ),
}


def _pdf(lines: list[str]) -> bytes:
    import pymupdf

    book = pymupdf.open()
    page = book.new_page()
    # The font mupdf carries inside itself, which has Latin, Greek and Cyrillic
    # on every machine; embedded so the text layer reads back as drawn.
    page.insert_font(fontname="uni", fontbuffer=pymupdf.Font("helv").buffer)
    page.insert_text((72, 80), "Rückgabe und Zahlung", fontsize=16, fontname="uni")
    for at, line in enumerate(lines):
        page.insert_text((72, 120 + at * 14), line, fontsize=11, fontname="uni")
    return book.tobytes()


def _converted_text(data: bytes) -> str:
    from preprocessing.parsing.models import SourceDocument
    from preprocessing.parsing.pipelines.pdf import PdfPipeline

    pipeline = PdfPipeline(
        table_mode="accurate",
        heading_hierarchy=True,
        document_timeout_seconds=600,
        artifacts_path=None,
    )
    conversion = pipeline.convert(
        SourceDocument(
            sha256=hashlib.sha256(data).hexdigest(), data=data, scanned=False
        )
    )
    return " ".join(item.text for item in conversion.document.texts)


@pytest.mark.parametrize("language", list(CASES))
def test_a_line_end_hyphen_is_kept_for_the_repair_to_decide(language: str) -> None:
    """A real PDF through the real converter keeps a compound and a range."""
    lines, kept, fused = CASES[language]
    text = _converted_text(_pdf(lines))
    assert [one for one in fused if one in text] == [], text
    assert [one for one in kept if one not in text] == [], text


MERGES = {
    # A suspended hyphen before a word the repair keeps apart.
    "de": (
        "Die Zahlung erfolgte vom Giro-",
        "oder Sparkonto der Kundin.",
        "Giro- oder",
    ),
    "en": ("Fees apply to pre-", "or post-sale changes of the order.", "pre- or"),
    # A compound broken at its own hyphen, and a number range.
    "fr": ("Les frais de la carte Visa-", "Premier sont dus.", "Visa-Premier"),
    "el": ("εντός 14-", "30 ημερών από την παράδοση.", "14-30"),
}


@pytest.mark.parametrize("language", list(MERGES))
def test_the_converter_merge_keeps_the_hyphen_for_the_repair(language: str) -> None:
    """The merge across a page or a column no longer drops the hyphen."""
    from docling.models.stages.reading_order.readingorder_model import (
        ReadingOrderOptions,
    )
    from docling_core.types.doc.base import BoundingBox
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    from preprocessing.parsing.pipelines.pdf import _mend, _ReadingOrder

    first, second, kept = MERGES[language]
    document = DoclingDocument(name="terms")
    item = document.add_text(label=DocItemLabel.TEXT, text=first, orig=first)
    element = SimpleNamespace(label=DocItemLabel.TEXT)
    continued = SimpleNamespace(
        label=DocItemLabel.TEXT,
        text=second,
        page_no=2,
        hyperlink=None,
        cluster=SimpleNamespace(bbox=BoundingBox(l=54, t=60, r=500, b=72)),
    )
    model = _ReadingOrder(options=ReadingOrderOptions())
    model._merge_elements(element, continued, item, 842)
    assert kept in _mend(item.text), item.text


@pytest.mark.parametrize(
    ("lines", "mended"),
    [
        # The hyphen that ends a line is the repair's to read, in any language.
        (["eine Bank-", "karte"], "eine Bankkarte"),
        (["a card ban-", "caire"], "a card bancaire"),
        (["les cartes ban-", "caires"], "les cartes bancaires"),
        (["karty u sprzedawcy z UE-", "Polska"], "karty u sprzedawcy z UE-Polska"),
        (["εντός 14-", "30 ημερών"], "εντός 14-30 ημερών"),
        (["für Kredit-", "und Debitkarten"], "für Kredit- und Debitkarten"),
        (["für Bau-", "/Renovierungsarbeiten"], "für Bau-/Renovierungsarbeiten"),
    ],
)
def test_a_hyphen_at_the_end_of_a_line_is_read_by_the_repair(lines, mended) -> None:
    """A page assembly joins the lines of a block and leaves the hyphen in."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleOptions,
    )

    from preprocessing.parsing.pipelines.pdf import _Assembler, _mend

    text = _Assembler(options=PageAssembleOptions()).sanitize_text(list(lines))
    assert _mend(text) == mended


#: A paragraph in each language no configuration names, in a German or English
#: document: the line the converter ends on a syllable, and what it joins to.
FOREIGN = {
    "fr": (
        [
            "Le vendeur doit vous rembourser tous les paie-",
            "ments reçus, y compris les frais.",
        ],
        "paiements reçus",
    ),
    "pl": (
        [
            "Sprzedawca musi zwrócić wszystkie wpłaty w ciągu czter-",
            "nastu dni od dnia otrzymania.",
        ],
        "czternastu dni",
    ),
    "el": (
        [
            "Ο πωλητής πρέπει να επιστρέψει όλες τις πληρω-",
            "μές που έλαβε, μαζί με τα έξοδα.",
        ],
        "πληρωμές που",
    ),
    "ru": (
        [
            "Продавец обязан вернуть все полученные пла-",
            "тежи, включая расходы на доставку.",
        ],
        "платежи, включая",
    ),
}


@pytest.mark.parametrize("language", sorted(FOREIGN))
def test_a_break_in_a_language_the_repair_leaves_alone_is_joined_as_the_converter_did(
    language: str,
) -> None:
    """Where the mend stays inert the converter's own join closes the word."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleOptions,
    )

    from preprocessing.parsing.pipelines.pdf import _Assembler, _mend

    lines, joined = FOREIGN[language]
    text = _Assembler(options=PageAssembleOptions()).sanitize_text(list(lines))

    assert joined in _mend(text), text


@pytest.mark.parametrize("language", sorted(FOREIGN))
def test_the_merge_of_two_blocks_in_such_a_language_is_joined_as_the_converter_did(
    language: str,
) -> None:
    """The reading-order merge across a page or column follows the same rule."""
    from docling.models.stages.reading_order.readingorder_model import (
        ReadingOrderOptions,
    )
    from docling_core.types.doc.base import BoundingBox
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    from preprocessing.parsing.pipelines.pdf import _mend, _ReadingOrder

    lines, joined = FOREIGN[language]
    document = DoclingDocument(name="terms")
    item = document.add_text(label=DocItemLabel.TEXT, text=lines[0], orig=lines[0])
    continued = SimpleNamespace(
        label=DocItemLabel.TEXT,
        text=lines[1],
        page_no=2,
        hyperlink=None,
        cluster=SimpleNamespace(bbox=BoundingBox(l=54, t=60, r=500, b=72)),
    )
    _ReadingOrder(options=ReadingOrderOptions())._merge_elements(
        SimpleNamespace(label=DocItemLabel.TEXT), continued, item, 842
    )

    assert joined in _mend(item.text), item.text
