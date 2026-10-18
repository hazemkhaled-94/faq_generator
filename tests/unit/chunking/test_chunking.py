"""What the chunk reader stores and what it counts, and where it cuts.

Nothing is discarded on size: a chunk over the budget is stored and counted,
because the chunker splits on the budget it counts against.

The cut itself is Docling's, run here with a tokenizer that counts a word as
a token, so a budget is a word count and no model is downloaded.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel
from factories import Words, chunked, word_chunker
from hypothesis import given, settings
from hypothesis import strategies as st

from preprocessing.chunking.models import Chunking
from preprocessing.chunking.passages import (
    NoPassages,
    PassageBuilder,
    chunks_of,
    lead_ins_kept,
)


def test_every_chunk_is_stored_and_numbered() -> None:
    """Five chunks become five passages with contiguous ordinals."""
    result = chunked(("x", "y " * 12, "z", "w", "v"))
    assert isinstance(result, Chunking)
    assert len(result.passages) == 5, "a chunk over the budget is still stored"
    assert [p.ordinal for p in result.passages] == [1, 2, 3, 4, 5]


def test_a_chunk_over_the_budget_is_counted() -> None:
    """`oversized` reports the chunks above the token budget."""
    assert chunked(("x", "y " * 12, "z", "w", "v")).oversized == 1


def test_a_passage_is_stored_as_the_text_it_was_counted_on() -> None:
    """Surrounding whitespace is gone; every sentence offset indexes this."""
    assert chunked(("v",)).passages[0].text == "v"
    stored = chunked(("  hello\n",)).passages[0].text
    assert stored == "hello", repr(stored)


def test_a_chunk_holding_only_whitespace_is_dropped() -> None:
    """Blank chunks yield no passage."""
    assert chunked(("keep", "   ", "\n")).passages[0].text == "keep"
    assert len(chunked(("keep", "   ", "\n")).passages) == 1


def test_a_document_yielding_no_chunk_fails() -> None:
    """A document with nothing in it is refused rather than stored empty."""
    with pytest.raises(NoPassages, match="no passages"):
        chunked(("", "   "))


def test_a_fee_paragraph_keeps_its_price() -> None:
    """A price or a phone number alone in its paragraph is passage text."""
    document = DoclingDocument(name="fees")
    document.add_heading(text="Kontoführung", level=1)
    for text in (
        "Die monatliche Gebühr beträgt:",
        "4,90 €",
        "Hotline:",
        "0800 123 4567",
    ):
        document.add_text(label=DocItemLabel.TEXT, text=text)

    _, chunks = chunks_of(document, word_chunker(200), "de")
    text = "\n".join(chunk.text for chunk in chunks)

    assert "4,90 €" in text and "0800 123 4567" in text, text


def priced(text: str, row: int, col: int, top: float) -> TableCell:
    """One cell of a fee table, a line high, placed from the page's top."""
    return TableCell(
        text=text,
        start_row_offset_idx=row,
        end_row_offset_idx=row + 1,
        start_col_offset_idx=col,
        end_col_offset_idx=col + 1,
        column_header=row == 0,
        bbox=BoundingBox(
            l=60 + 200 * col,
            t=top,
            r=240 + 200 * col,
            b=top + 12,
            coord_origin=CoordOrigin.TOPLEFT,
        ),
    )


def test_a_table_joined_across_a_page_cites_both_pages() -> None:
    """A fee schedule's rest on page 4 joined it; its rows are printed there."""
    document = DoclingDocument(name="fees")
    for page in (3, 4):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    rows = (
        ("Leistung", "Entgelt", 700),
        ("Kontoführung", "4,90 EUR", 720),
        ("Girocard", "12,00 EUR", 740),
        ("Kreditkarte", "39,00 EUR", 60),
        ("Ersatzkarte", "15,00 EUR", 80),
    )
    cells = [
        priced(text, row, col, top)
        for row, (*texts, top) in enumerate(rows)
        for col, text in enumerate(texts)
    ]
    document.add_table(
        data=TableData(num_rows=len(rows), num_cols=2, table_cells=cells),
        prov=ProvenanceItem(
            page_no=3,
            bbox=BoundingBox(
                l=60, t=700, r=440, b=752, coord_origin=CoordOrigin.TOPLEFT
            ),
            charspan=(0, 0),
        ),
    )
    document.tables[0].prov.append(
        ProvenanceItem(
            page_no=4,
            bbox=BoundingBox(l=60, t=60, r=440, b=92, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 0),
        )
    )

    tidy, (chunk,) = chunks_of(document, word_chunker(200), "de")
    passage = PassageBuilder._passage(tidy, 1, chunk)

    assert (passage.page_from, passage.page_to) == (3, 4)
    assert passage.bbox == [
        {"page": 3, "l": 60.0, "t": 720.0, "r": 440.0, "b": 752.0},
        {"page": 4, "l": 60.0, "t": 60.0, "r": 440.0, "b": 92.0},
    ]


# ── A list keeps its lead-in ─────────────────────────────────────────────


def cut(document: DoclingDocument, budget: int, **options: Any) -> list:
    """The chunks the builder hands to the reader."""
    cutting = word_chunker(budget, **options)
    return lead_ins_kept(list(cutting.chunk(document)), cutting, document)


def refs(chunk) -> list[str]:
    """The items a chunk was cut from, by reference.

    The chunker hands them over as bare copies, so a reference is what
    names one.
    """
    return [item.self_ref for item in chunk.meta.doc_items]


PROSE = "A business card carries the fees the price list sets for its account."
LEAD_IN = "For every other card payment:"
ITEMS = ("the issuing bank charges a flat fee", "the merchant pays nothing")
LONG_ITEMS = (
    "the issuing bank charges a flat fee for each payment",
    "the merchant pays nothing and the card holder pays nothing",
)


def listed(
    items: tuple[str, ...] = ITEMS, sub_heading: str | None = None
) -> DoclingDocument:
    """A paragraph, a lead-in and the list it introduces, under one heading."""
    document = DoclingDocument(name="fees")
    document.add_heading(text="Card fees", level=1)
    document.add_text(label=DocItemLabel.TEXT, text=PROSE)
    document.add_text(label=DocItemLabel.TEXT, text=LEAD_IN)
    if sub_heading is not None:
        document.add_heading(text=sub_heading, level=2)
    group = document.add_list_group()
    for item in items:
        document.add_list_item(text=item, parent=group)
    return document


def cut_after_the_lead_in(document: DoclingDocument, budget: int) -> None:
    """Asserts the chunker alone closes a chunk on the lead-in."""
    *_, before, after = word_chunker(budget).chunk(document)
    assert before.text.endswith(LEAD_IN), "the chunker no longer cuts here"
    assert after.text.startswith("- "), "the chunker no longer cuts here"


def test_a_lead_in_that_fits_moves_to_its_list() -> None:
    """The budget ran out after the lead-in, and lead-in and list fit together."""
    document = listed()
    cut_after_the_lead_in(document, budget=24)

    first, second = cut(document, budget=24)

    assert first.text == PROSE
    assert second.text == f"{LEAD_IN}\n- {ITEMS[0]}\n- {ITEMS[1]}"
    assert second.meta.headings == ["Card fees"]
    assert refs(first) == [document.texts[1].self_ref]
    assert refs(second)[0] == document.texts[2].self_ref


def test_a_lead_in_that_does_not_fit_heads_its_list() -> None:
    """The list alone fills the budget, so the lead-in joins its heading trail."""
    cut_after_the_lead_in(listed(LONG_ITEMS), budget=24)

    first, second = cut(listed(LONG_ITEMS), budget=24)

    assert first.text == f"{PROSE}\n{LEAD_IN}", "the lead-in stays where it is"
    assert second.text.startswith(f"- {LONG_ITEMS[0]}")
    assert second.meta.headings == ["Card fees", LEAD_IN]


def test_a_lead_in_moves_when_every_block_is_its_own_chunk() -> None:
    """Without merging, a lead-in is always a chunk apart from its list."""
    _, second = cut(listed(), budget=24, merge_peers=False)

    assert second.text.startswith(f"{LEAD_IN}\n- ")


#: A list three passages long at a budget of 24 words.
MANY_ITEMS = tuple(
    f"the {ordinal} card pays a fee"
    for ordinal in (
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
    )
)


def test_a_list_longer_than_a_passage_carries_its_lead_in_on_every_passage() -> None:
    """Each item after the first passage is as conditional as the first."""
    as_cut = [chunk.text for chunk in word_chunker(24).chunk(listed(MANY_ITEMS))]
    assert len(as_cut) == 4, "the chunker no longer cuts the list in three"

    first, *rest = cut(listed(MANY_ITEMS), budget=24)

    assert first.text == f"{PROSE}\n{LEAD_IN}"
    assert len(rest) == 3, [chunk.text for chunk in rest]
    assert [chunk.meta.headings for chunk in rest] == [["Card fees", LEAD_IN]] * 3


def test_a_list_under_a_sub_heading_takes_its_lead_in() -> None:
    """The sub-heading names one case; the lead-in still says what the list is."""
    document = listed(sub_heading="Debit cards")

    first, second = cut(document, budget=40)

    assert first.text == PROSE
    assert second.text.startswith(f"{LEAD_IN}\n- ")
    assert second.meta.headings == ["Card fees", "Debit cards"]


def sectioned(*sections: tuple[str, tuple[str, ...]]) -> DoclingDocument:
    """A lead-in under one heading, sub-sections each opening on a list, then a chapter."""
    document = DoclingDocument(name="fees")
    document.add_heading(text="Fees", level=1)
    document.add_text(label=DocItemLabel.TEXT, text="The bank charges a fee when:")
    for heading, items in sections:
        document.add_heading(text=heading, level=2)
        group = document.add_list_group()
        for item in items:
            document.add_list_item(text=item, parent=group)
    document.add_heading(text="Cards", level=1)
    document.add_text(label=DocItemLabel.TEXT, text="Cards are free.")
    return document


def test_a_lead_in_reaches_its_list_across_a_sub_heading_and_no_further() -> None:
    """A heading at the lead-in's own depth ends what it introduces."""
    document = sectioned(
        (
            "Transfers abroad",
            ("a transfer leaves the euro area", "a card is used abroad"),
        )
    )

    chunks = cut(document, budget=40)

    listing = next(chunk for chunk in chunks if "a card is used abroad" in chunk.text)
    cards = next(chunk for chunk in chunks if "Cards are free." in chunk.text)
    assert listing.text.startswith("The bank charges a fee when:\n- a transfer")
    assert "The bank charges a fee when:" not in cards.text
    assert "The bank charges a fee when:" not in (cards.meta.headings or [])


def test_a_lead_in_heads_each_sub_section_it_introduces() -> None:
    """The second case is as conditional as the first."""
    document = sectioned(
        ("Transfers abroad", ("a transfer leaves the euro area",)),
        ("Cash", ("cash is drawn abroad",)),
    )

    chunks = cut(document, budget=40)

    cash = next(chunk for chunk in chunks if "cash is drawn abroad" in chunk.text)
    assert cash.meta.headings == ["Fees", "Cash", "The bank charges a fee when:"]


def indented(left: float, top: float, height: float = 10.0) -> ProvenanceItem:
    """Provenance on page 1 at a left edge, `height` points tall."""
    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(
            l=left, t=top, r=400, b=top + height, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def test_an_item_indented_under_another_is_nested_under_it() -> None:
    """The converter flattens a nested list; the indent is all that says so."""
    document = DoclingDocument(name="restarts")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    document.add_heading(text="Restarts", level=1, prov=indented(54, 40))
    group = document.add_list_group()
    for top, (left, text) in enumerate(
        (
            (54, "a stoppage in play"),
            (54, "the halfway line"),
            (72, "when the referee signals"),
            (54, "after the player left"),
        )
    ):
        document.add_list_item(
            text=text, parent=group, prov=indented(left, 100 + 14 * top)
        )

    _, chunks = chunks_of(document, word_chunker(200), "en")
    lines = chunks[0].text.splitlines()

    at = lines.index("- the halfway line")
    assert lines[at + 1].startswith((" ", "\t")), lines
    assert lines[at + 1].strip() == "- when the referee signals", lines
    assert lines[at + 2] == "- after the player left", lines


def test_items_side_by_side_in_two_columns_are_not_nested() -> None:
    """The next column starts right of the last item, not inside it."""
    document = DoclingDocument(name="restarts")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    group = document.add_list_group()
    for left, top, text in ((54, 100, "a stoppage in play"), (420, 100, "a goal kick")):
        prov = ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=left,
                t=top,
                r=left + 120,
                b=top + 10,
                coord_origin=CoordOrigin.TOPLEFT,
            ),
            charspan=(0, 1),
        )
        document.add_list_item(text=text, parent=group, prov=prov)

    _, chunks = chunks_of(document, word_chunker(200), "en")

    assert chunks[0].text.splitlines() == ["- a stoppage in play", "- a goal kick"]


def placed(page: int, left: float, top: float, height: float = 10.0) -> ProvenanceItem:
    """Provenance 200 points wide at a left edge of a page."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left,
            t=top,
            r=left + 200,
            b=top + height,
            coord_origin=CoordOrigin.TOPLEFT,
        ),
        charspan=(0, 1),
    )


def listed_at(
    pages: int, *items: tuple[int, float, float, str], height: float = 10.0
) -> list[str]:
    """The lines a list cuts to, each item at (page, left edge, top, text)."""
    document = DoclingDocument(name="terms")
    for page in range(1, pages + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    group = document.add_list_group()
    for page, left, top, text in items:
        document.add_list_item(
            text=text, parent=group, prov=placed(page, left, top, height)
        )

    _, chunks = chunks_of(document, word_chunker(200), "de")
    return chunks[0].text.splitlines()


def test_depth_open_at_a_column_foot_does_not_carry_into_the_next_column() -> None:
    """A shop's returns list goes on at the top of the next column, outer again."""
    lines = listed_at(
        1,
        (1, 54, 700, "Returns are free within 30 days."),
        (1, 54, 714, "A refund is paid:"),
        (1, 72, 728, "to the card the order was paid with"),
        (1, 72, 742, "within 14 days of the return"),
        (1, 310, 60, "Sale items cannot be returned."),
        (1, 310, 74, "Gift cards cannot be returned."),
    )

    assert lines == [
        "- Returns are free within 30 days.",
        "- A refund is paid:",
        "    - to the card the order was paid with",
        "    - within 14 days of the return",
        "- Sale items cannot be returned.",
        "- Gift cards cannot be returned.",
    ]


def test_depth_survives_a_page_break() -> None:
    """A bank's sub-items go on on a page whose margin lies further left."""
    lines = listed_at(
        2,
        (1, 70, 700, "Die Bank sperrt die Karte, wenn:"),
        (1, 88, 714, "der Karteninhaber die Sperre verlangt,"),
        (2, 72, 60, "der Verdacht einer missbräuchlichen Nutzung besteht."),
        (2, 54, 74, "Die Sperre wird dem Karteninhaber mitgeteilt."),
    )

    assert lines == [
        "- Die Bank sperrt die Karte, wenn:",
        "    - der Karteninhaber die Sperre verlangt,",
        "    - der Verdacht einer missbräuchlichen Nutzung besteht.",
        "- Die Sperre wird dem Karteninhaber mitgeteilt.",
    ]


def test_side_by_side_min_max_columns_are_not_nested() -> None:
    """Under a paragraph across both, a fee's minimum and maximum stay apart."""
    document = DoclingDocument(name="fees")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Für Auslandsüberweisungen gilt:",
        prov=ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(l=54, t=80, r=546, b=90, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 1),
        ),
    )
    group = document.add_list_group()
    for left, text in (
        (54, "Mindestentgelt 5,00 EUR"),
        (310, "Höchstentgelt 25,00 EUR"),
    ):
        document.add_list_item(text=text, parent=group, prov=placed(1, left, 100))

    _, chunks = chunks_of(document, word_chunker(200), "de")

    assert chunks[0].text.splitlines()[-2:] == [
        "- Mindestentgelt 5,00 EUR",
        "- Höchstentgelt 25,00 EUR",
    ]


#: Words the generated documents are written in.
VOCABULARY = st.sampled_from(
    ["card", "fee", "bank", "account", "payment", "charge", "merchant", "limit"]
)


@st.composite
def documents(draw) -> DoclingDocument:
    """A heading, then paragraphs, lead-ins, lists and sub-headings in any order."""
    document = DoclingDocument(name="generated")
    document.add_heading(text="Card fees", level=1)
    for kind in draw(
        st.lists(
            st.sampled_from(["prose", "lead-in", "list", "sub-heading"]),
            min_size=1,
            max_size=10,
        )
    ):
        if kind == "list":
            group = document.add_list_group()
            for item in draw(
                # Up to twelve items: a list longer than the budget is cut
                # across passages.
                st.lists(
                    st.lists(VOCABULARY, min_size=1, max_size=8),
                    min_size=1,
                    max_size=12,
                )
            ):
                document.add_list_item(text=" ".join(item), parent=group)
        elif kind == "sub-heading":
            document.add_heading(text=draw(VOCABULARY).title(), level=2)
        else:
            words = draw(
                st.lists(
                    VOCABULARY, min_size=1, max_size=6 if kind == "lead-in" else 15
                )
            )
            document.add_text(
                label=DocItemLabel.TEXT,
                text=" ".join(words) + (":" if kind == "lead-in" else "."),
            )
    return document


def _lead_ins(document: DoclingDocument) -> list[tuple[Any, list[str]]]:
    """Every lead-in ending in ":" with the items of the list right after it."""
    found: list[tuple[Any, list[str]]] = []
    previous = None
    for item, _ in document.iterate_items():
        if (
            item.label == DocItemLabel.LIST_ITEM
            and previous is not None
            and previous.label == DocItemLabel.TEXT
            and previous.text.endswith(":")
        ):
            found.append(
                (
                    previous,
                    [child.cref for child in item.parent.resolve(document).children],
                )
            )
        previous = None if item.label == DocItemLabel.LIST_ITEM else item
    return found


@given(document=documents(), budget=st.integers(14, 40))
@settings(deadline=None)
def test_no_passage_holds_a_list_cut_from_its_lead_in(document, budget) -> None:
    """Every passage of the list holds its lead-in or ends its trail with it."""
    chunks = cut(document, budget)

    for lead_in, items in _lead_ins(document):
        for holding in [c for c in chunks if set(items) & set(refs(c))]:
            assert lead_in.self_ref in refs(holding) or (
                holding.meta.headings and holding.meta.headings[-1] == lead_in.text
            ), (holding.text, holding.meta.headings)
    assert all(Words(max_tokens=budget).count_tokens(c.text) <= budget for c in chunks)


@pytest.mark.nlp
def test_the_builder_keeps_a_lead_in_with_its_list() -> None:
    """Through the passage builder as the chunking factory wires it."""
    from preprocessing.chunking.passages import PassageBuilder

    try:
        builder = PassageBuilder(
            embedding_model=os.environ["EMBEDDING_MODEL"],
            max_tokens=int(os.environ["EMBEDDING_MAX_TOKENS"]),
            merge_peers=False,
        )
    except Exception as exc:  # noqa: BLE001 - any failure is the same answer
        pytest.skip(f"the chunker's tokenizer is unavailable: {exc}")

    passages = builder.build(listed(), "en").passages

    (holding,) = [p for p in passages if ITEMS[0] in p.text]
    assert holding.text.startswith(LEAD_IN), holding.text
