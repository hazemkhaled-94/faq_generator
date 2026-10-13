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
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import Words, chunked, word_chunker
from hypothesis import given, settings
from hypothesis import strategies as st

from preprocessing.chunking.models import Chunking
from preprocessing.chunking.passages import NoPassages, lead_ins_kept


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


def test_a_list_under_a_sub_heading_is_left_as_cut() -> None:
    """Its own heading says what it is under; the lead-in ends the section."""
    document = listed(sub_heading="Debit cards")

    first, second = cut(document, budget=40)

    assert first.text == f"{PROSE}\n{LEAD_IN}"
    assert second.text.startswith("- ")
    assert second.meta.headings == ["Card fees", "Debit cards"]


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
                st.lists(
                    st.lists(VOCABULARY, min_size=1, max_size=8), min_size=1, max_size=4
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


def _lead_ins(document: DoclingDocument) -> list[tuple[Any, Any]]:
    """Every lead-in ending in ":" with the first item of the list right after it."""
    found = []
    previous = None
    for item, _ in document.iterate_items():
        if (
            item.label == DocItemLabel.LIST_ITEM
            and previous is not None
            and previous.label == DocItemLabel.TEXT
            and previous.text.endswith(":")
        ):
            found.append((previous, item))
        previous = None if item.label == DocItemLabel.LIST_ITEM else item
    return found


@given(document=documents(), budget=st.integers(14, 40))
@settings(deadline=None)
def test_no_passage_opens_on_a_list_cut_from_its_lead_in(document, budget) -> None:
    """Its lead-in is in the passage or at the end of its heading trail."""
    chunks = cut(document, budget)

    for lead_in, first in _lead_ins(document):
        (holding,) = [c for c in chunks if first.self_ref in refs(c)]
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
