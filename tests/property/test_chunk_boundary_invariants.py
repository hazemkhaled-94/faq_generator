"""What chunking promises of every document it cuts, furniture and all.

Generated documents of several pages: running heads naming chapters, page
numbers read as body text, paragraphs ending with and without a full stop
across page breaks, lists, headings and lone letters, in German and English.
"""

from __future__ import annotations

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker
from hypothesis import given
from hypothesis import strategies as st

from preprocessing.chunking.passages import chunks_of

WORDS = {
    "de": ["gebühr", "konto", "karte", "zahlung", "monat", "kunde", "preis", "frist"],
    "en": ["fee", "account", "card", "payment", "month", "customer", "price", "order"],
}
CHAPTERS = ["Girokonto", "Kreditkarten", "Versand", "Returns"]


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


@st.composite
def documents(draw) -> tuple[DoclingDocument, str]:
    """A document of one to five pages, and its language."""
    language = draw(st.sampled_from(["de", "en"]))
    words = st.lists(st.sampled_from(WORDS[language]), min_size=1, max_size=12)
    document = DoclingDocument(name="generated")
    count = draw(st.integers(1, 5))
    chapters = draw(st.lists(st.sampled_from(CHAPTERS), min_size=count, max_size=count))
    heads = draw(st.booleans())
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        if heads:
            document.add_text(
                label=DocItemLabel.PAGE_HEADER,
                text=f"Musterbank | {chapters[page - 1]} | {page}",
                prov=on(page, 20),
                content_layer=ContentLayer.FURNITURE,
            )
        top = 60.0
        for kind in draw(
            st.lists(
                st.sampled_from(
                    ["prose", "open", "lead-in", "list", "heading", "letter"]
                ),
                max_size=6,
            )
        ):
            text = " ".join(draw(words))
            if kind == "heading":
                # Short, so a trail of three never outgrows the budget.
                heading = " ".join(text.split()[:3]).title()
                document.add_heading(
                    text=heading, level=draw(st.integers(1, 3)), prov=on(page, top)
                )
            elif kind == "letter":
                document.add_text(
                    label=DocItemLabel.TEXT, text=text[0].upper(), prov=on(page, top)
                )
            elif kind == "list":
                group = document.add_list_group()
                for item in draw(st.lists(words, min_size=1, max_size=5)):
                    top += 20
                    document.add_list_item(
                        text=" ".join(item), parent=group, prov=on(page, top)
                    )
            else:
                ending = {"prose": ".", "open": "", "lead-in": ":"}[kind]
                document.add_text(
                    label=DocItemLabel.TEXT, text=text + ending, prov=on(page, top)
                )
            top += 40
        if draw(st.booleans()):
            document.add_text(
                label=DocItemLabel.TEXT, text=str(page), prov=on(page, 820)
            )
    return document, language


def _plain(text: str) -> str:
    """A text with spaces, punctuation and case set aside, as `tidied` compares."""
    return "".join(c for c in text.casefold() if c.isalnum())


def cut(document: DoclingDocument, language: str, budget: int):
    """The chunks and the document they index."""
    return chunks_of(document, word_chunker(budget), language)


@given(drawn=documents(), budget=st.integers(30, 80))
def test_the_document_handed_in_is_not_modified(drawn, budget) -> None:
    """chunks_of says the converted document is not modified."""
    document, language = drawn
    before = document.export_to_dict()

    cut(document, language, budget)

    assert document.export_to_dict() == before


@given(drawn=documents(), budget=st.integers(30, 80))
def test_cutting_is_deterministic(drawn, budget) -> None:
    """The same document cuts into the same passages, trails and references."""
    document, language = drawn

    def seen(chunks):
        return [
            (c.text, c.meta.headings, [i.self_ref for i in c.meta.doc_items])
            for c in chunks
        ]

    assert seen(cut(document, language, budget)[1]) == seen(
        cut(document, language, budget)[1]
    )


@given(drawn=documents(), budget=st.integers(30, 80))
def test_no_chunk_is_blank_and_every_trail_segment_names_something(
    drawn, budget
) -> None:
    """Whitespace is no passage; a trail segment holds a letter or a digit."""
    document, language = drawn
    _, chunks = cut(document, language, budget)

    for chunk in chunks:
        assert chunk.text.strip(), chunk
        assert all(any(c.isalnum() for c in s) for s in chunk.meta.headings or []), (
            chunk
        )


@given(drawn=documents(), budget=st.integers(30, 80))
def test_passages_follow_the_document_order(drawn, budget) -> None:
    """Every item a chunk holds comes after every item of the chunks before it."""
    document, language = drawn
    tidy, chunks = cut(document, language, budget)
    order = {item.self_ref: at for at, (item, _) in enumerate(tidy.iterate_items())}

    positions = [order[i.self_ref] for c in chunks for i in c.meta.doc_items]

    assert positions == sorted(positions)
    assert len(positions) == len(set(positions)), "an item is in two passages"


@given(drawn=documents(), budget=st.integers(30, 80))
def test_every_word_of_the_body_reaches_a_passage(drawn, budget) -> None:
    """Only furniture goes: each lettered body word is in some chunk's text or trail."""
    document, language = drawn
    _, chunks = cut(document, language, budget)
    held = {
        word
        for c in chunks
        for word in " ".join([c.text, *(c.meta.headings or [])])
        .lower()
        .replace(":", " ")
        .replace(".", " ")
        .split()
    }

    headings = {
        _plain(item.text)
        for item in document.texts
        if item.label == DocItemLabel.SECTION_HEADER
    }

    for item in document.texts:
        # A heading with nothing under it heads no passage; a lone letter
        # may be an index divider; a paragraph that only repeats a heading is
        # read as that heading, `tidied` says, and heads nothing either.
        if (
            item.content_layer != ContentLayer.BODY
            or item.label == DocItemLabel.SECTION_HEADER
            or len(item.text.strip()) == 1
            or _plain(item.text) in headings
        ):
            continue
        for word in item.text.lower().replace(":", " ").replace(".", " ").split():
            if word.isalpha():
                assert word in held, (word, item.text)
