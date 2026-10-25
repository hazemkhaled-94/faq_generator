"""Real PDFs through the real converter and the real chunker, against a record.

Everything else in the suite stands the converter in, so a Docling release
that merges two paragraphs, moves a heading down a level, drops a table row or
shifts a page reaches a build with every test green. This converts small
PDFs - two pages of the shop corpus, German and English, and one made here with
a ruled table - and compares what comes out with a stored snapshot: the
passages' text, heading trail and pages, and each table's rows and columns.

A difference fails with a diff, never a skip: the weights are read from the
cache (`HF_HUB_OFFLINE=1`), and where they are missing the conversion itself
fails. Slow, so `make test` leaves it out; `make test-golden` runs it, and
`make golden-refresh` rewrites the snapshots after a change that is meant.
The shop pages are Your Europe's, CC BY 4.0, see pdfs/ATTRIBUTION.txt.
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).parent
PDFS = HERE / "pdfs"
SNAPSHOTS = HERE / "snapshots"

pytestmark = [
    pytest.mark.slow,
    # Docling reads one of its own deprecated fields while it converts a table,
    # and the suite turns every warning into a failure. Third party, and only
    # here, where a real conversion runs.
    pytest.mark.filterwarnings("ignore:This field is deprecated:DeprecationWarning"),
]

#: The documents, and the language each is read in.
DOCUMENTS = {"shopping_de": "de", "shopping_en": "en", "price_table": "en"}


def synthetic() -> bytes:
    """A one-page shop price list: a heading, a sentence and a ruled table.

    Built here rather than stored, so the one file that exercises a table is
    not somebody's document. Ruled cells, because that is what the table model
    reads most reliably.
    """
    import pymupdf

    book = pymupdf.open()
    page = book.new_page()
    page.insert_text((72, 80), "Delivery prices", fontsize=18)
    page.insert_text(
        (72, 110),
        "The price of a delivery depends on the weight of the parcel.",
        fontsize=11,
    )
    rows = [
        ("Weight", "Price", "Days"),
        ("up to 2 kg", "4 euros", "2"),
        ("up to 10 kg", "9 euros", "3"),
        ("up to 30 kg", "19 euros", "5"),
    ]
    left, top, wide, high = 72, 140, 120, 24
    for at, row in enumerate(rows):
        for column, cell in enumerate(row):
            box = pymupdf.Rect(
                left + column * wide,
                top + at * high,
                left + (column + 1) * wide,
                top + (at + 1) * high,
            )
            page.draw_rect(box, width=0.8)
            page.insert_text(
                (box.x0 + 6, box.y0 + 16), cell, fontsize=10, fontname="helv"
            )
    return book.tobytes()


def pdf(name: str) -> bytes:
    """The bytes of one document."""
    return synthetic() if name == "price_table" else (PDFS / f"{name}.pdf").read_bytes()


@pytest.fixture(scope="module")
def converted():
    """What the converter and the chunker make of each document, once."""
    from preprocessing.chunking.config import Settings as Chunking
    from preprocessing.chunking.passages import PassageBuilder
    from preprocessing.parsing.config import Settings
    from preprocessing.parsing.models import SourceDocument
    from preprocessing.parsing.pipelines.pdf import PdfPipeline

    settings = Settings.load()
    pipeline = PdfPipeline(
        table_mode=settings.table_mode,
        heading_hierarchy=settings.heading_hierarchy,
        document_timeout_seconds=settings.document_timeout_seconds,
        artifacts_path=settings.artifacts_path,
        ocr_char_threshold=settings.ocr_char_threshold,
    )
    chunking = Chunking.load()
    builder = PassageBuilder(
        embedding_model=chunking.embedding_model,
        max_tokens=chunking.max_tokens,
        merge_peers=chunking.merge_peers,
    )
    seen = {}
    for name, language in DOCUMENTS.items():
        data = pdf(name)
        conversion = pipeline.convert(SourceDocument(name, data, scanned=False))
        chunks = builder.build(conversion.document, language).passages
        seen[name] = observed(conversion.document, chunks)
    return seen


def observed(document, chunks) -> dict:
    """What a snapshot records of one conversion."""
    return {
        "passages": [
            {
                "section_path": one.section_path,
                "pages": [one.page_from, one.page_to],
                "block_type": one.block_type,
                "text": one.text,
            }
            for one in chunks
        ],
        "tables": [
            {"rows": item.data.num_rows, "columns": item.data.num_cols}
            for item in document.tables
        ],
    }


def shown(value: dict) -> list[str]:
    """One snapshot as lines a diff can read."""
    return json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True).splitlines()


def difference(recorded: dict, found: dict) -> str:
    """The lines that moved, or an empty string."""
    return "\n".join(
        difflib.unified_diff(
            shown(recorded), shown(found), "recorded", "converted", lineterm="", n=2
        )
    )


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_a_real_pdf_converts_and_chunks_as_recorded(name: str, converted) -> None:
    """Text, heading trail, pages and tables, as the last intended change left them."""
    path = SNAPSHOTS / f"{name}.json"
    if os.environ.get("GOLDEN_REFRESH") == "1":
        path.write_text(
            json.dumps(converted[name], indent=1, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
    recorded = json.loads(path.read_text())

    assert not difference(recorded, converted[name]), difference(
        recorded, converted[name]
    )


def test_the_synthetic_table_is_read_as_a_table(converted) -> None:
    """The one document that carries a table: four rows of three columns."""
    assert converted["price_table"]["tables"] == [{"rows": 4, "columns": 3}]


def test_a_changed_conversion_is_reported_as_a_difference() -> None:
    """The comparison itself: a row dropped from a table, a heading moved."""
    recorded = {
        "passages": [{"section_path": "Shipping", "pages": [1, 1], "text": "a\nb"}],
        "tables": [{"rows": 4, "columns": 3}],
    }
    dropped = {
        "passages": [{"section_path": "Delivery", "pages": [1, 1], "text": "a\nb"}],
        "tables": [{"rows": 3, "columns": 3}],
    }

    assert difference(recorded, recorded) == ""
    moved = difference(recorded, dropped)
    assert "Shipping" in moved and "Delivery" in moved and '"rows": 3' in moved
