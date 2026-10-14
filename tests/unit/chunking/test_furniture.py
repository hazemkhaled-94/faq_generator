"""What a document's running heads and feet change about its passages.

A chapter opening on a decorative title the converter never takes as a
heading inherits the last numbered heading of the chapter before. The
running foot names the chapter each page is in, so it is read for that; and
when the converter reads a running foot as body text, it is not passage
text. A document with neither keeps today's cut.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.furniture import fields
from preprocessing.chunking.passages import chunks_of, lead_ins_kept

GUIDE = "Retail Banking Guide 2026"


def on(page: int, top: float = 100.0) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=370, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def paged(count: int) -> DoclingDocument:
    """An empty converted document of `count` pages."""
    document = DoclingDocument(name="guide")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


def foot(document: DoclingDocument, page: int, text: str) -> None:
    """Prints a running foot on a page, and the page's number beside it."""
    for printed in (text, str(page + 10)):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=printed,
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )


def head(document: DoclingDocument, page: int, text: str) -> None:
    """Prints a running head on a page."""
    document.add_text(
        label=DocItemLabel.PAGE_HEADER,
        text=text,
        prov=on(page, 20),
        content_layer=ContentLayer.FURNITURE,
    )


def say(document: DoclingDocument, page: int, text: str) -> None:
    """Adds a paragraph on a page."""
    document.add_text(label=DocItemLabel.TEXT, text=text, prov=on(page))


def cut(document: DoclingDocument, language: str | None = None) -> list:
    """The chunks the builder hands to the reader, with room for everything."""
    return chunks_of(document, word_chunker(200), language)[1]


def trails(document: DoclingDocument, language: str | None = None) -> list:
    """Every chunk's text and heading trail."""
    return [(chunk.text, chunk.meta.headings) for chunk in cut(document, language)]


def two_chapters() -> DoclingDocument:
    """A numbered chapter, then a glossary whose title is only in its foot."""
    document = paged(4)
    for page, chapter in (
        (1, "Accounts"),
        (2, "Accounts"),
        (3, "Glossary"),
        (4, "Glossary"),
    ):
        foot(document, page, f"{GUIDE} | {chapter}")
    document.add_heading(text="1. Opening an account", level=1, prov=on(1, 60))
    say(document, 1, "An account opens once the bank has checked the holder.")
    say(document, 2, "A joint account needs both holders to sign.")
    say(document, 3, "Overdraft: a negative balance on a current account.")
    say(document, 4, "Standing order: a payment the bank repeats on fixed dates.")
    return document


def test_a_chapter_does_not_inherit_the_last_numbered_heading() -> None:
    """The glossary is under its own chapter, not under section 1 of the last."""
    assert trails(two_chapters()) == [
        (
            (
                "An account opens once the bank has checked the holder.\n"
                "A joint account needs both holders to sign."
            ),
            ["Accounts", "1. Opening an account"],
        ),
        (
            (
                "Overdraft: a negative balance on a current account.\n"
                "Standing order: a payment the bank repeats on fixed dates."
            ),
            ["Glossary"],
        ),
    ]


def test_a_path_that_names_its_chapter_already_is_not_prefixed_twice() -> None:
    """A chapter's own heading, matching its foot, heads the path once."""
    document = paged(2)
    foot(document, 1, f"{GUIDE} | Accounts")
    foot(document, 2, f"{GUIDE} | Cards")
    document.add_heading(text="Accounts", level=1, prov=on(1, 60))
    say(document, 1, "An account opens once the bank has checked the holder.")
    document.add_heading(text="Cards", level=1, prov=on(2, 60))
    document.add_heading(text="Debit cards", level=2, prov=on(2, 80))
    say(document, 2, "A debit card draws on the current account.")

    assert [headings for _, headings in trails(document)] == [
        ["Accounts"],
        ["Cards", "Debit cards"],
    ]


def test_a_running_foot_read_as_body_text_is_not_passage_text() -> None:
    """The neighbouring pages carry it as furniture; the converter split a word."""
    document = paged(3)
    foot(document, 1, f"{GUIDE} | Accounts | Fees and charges")
    foot(document, 3, f"{GUIDE} | Accounts | Fees and charges")
    say(document, 1, "A current account costs a monthly fee.")
    say(document, 2, "Each transfer abroad costs a flat fee.")
    say(document, 2, f"{GUIDE} | Accounts | Fees and char ges")
    say(document, 3, "Cash withdrawals at the bank's machines are free.")

    texts = [text for text, _ in trails(document)]

    assert not [text for text in texts if GUIDE in text], texts
    assert "Each transfer abroad costs a flat fee." in texts[0]


def test_a_paragraph_that_only_begins_like_the_foot_is_kept() -> None:
    """A field is matched whole, so prose naming the title is still prose."""
    document = paged(2)
    foot(document, 1, GUIDE)
    foot(document, 2, GUIDE)
    say(document, 1, f"{GUIDE} covers every account the bank offers.")

    assert [text for text, _ in trails(document)] == [
        f"{GUIDE} covers every account the bank offers."
    ]


def test_a_one_letter_paragraph_is_not_passage_text() -> None:
    """A glossary's index letter is a divider, not part of the entry before it."""
    document = DoclingDocument(name="glossary")
    document.add_heading(text="Glossary", level=1)
    for text in (
        "O",
        "Overdraft: a negative balance.",
        "P",
        "Payee: whoever is paid.",
    ):
        document.add_text(label=DocItemLabel.TEXT, text=text)

    assert trails(document) == [
        ("Overdraft: a negative balance.\nPayee: whoever is paid.", ["Glossary"])
    ]


def test_a_lone_letter_that_heads_nothing_is_content() -> None:
    """A divider is followed by entries under its letter; an energy class is not."""
    document = DoclingDocument(name="sheet")
    document.add_heading(text="Fridge", level=1)
    for text in ("Energy class", "A", "The fridge uses 150 kWh a year."):
        document.add_text(label=DocItemLabel.TEXT, text=text)

    assert trails(document) == [
        ("Energy class\nA\nThe fridge uses 150 kWh a year.", ["Fridge"])
    ]


@pytest.mark.parametrize(
    "lines",
    [
        ("Energy class", "A", "Annual consumption: 150 kWh."),
        (
            "Energy class",
            "C",
            "Consumption: 150 kWh a year.",
            "Noise class",
            "B",
            "Built-in width: 60 cm.",
        ),
    ],
)
def test_a_value_of_one_letter_is_content_whatever_the_line_after_it(
    lines: tuple[str, ...],
) -> None:
    """An index has two letters or more, and they run in alphabetical order."""
    document = DoclingDocument(name="sheet")
    document.add_heading(text="Fridge", level=1)
    for text in lines:
        document.add_text(label=DocItemLabel.TEXT, text=text)

    assert trails(document) == [("\n".join(lines), ["Fridge"])]


@pytest.mark.parametrize("segment", ["(…)", "...", "–"])
def test_an_ellipsis_is_not_a_path_segment(segment: str) -> None:
    """A heading holding no word names nothing."""
    document = DoclingDocument(name="fees")
    document.add_heading(text="Fees", level=1)
    document.add_heading(text=segment, level=2)
    document.add_text(label=DocItemLabel.TEXT, text="A transfer costs a flat fee.")

    assert trails(document) == [("A transfer costs a flat fee.", ["Fees"])]


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "heading", "conjunction", "text"),
    [
        ("de", "Gebühren", "oder", "Eine Überweisung kostet eine Gebühr."),
        ("en", "Fees", "or", "A transfer costs a flat fee."),
    ],
)
def test_a_lone_conjunction_is_not_a_path_segment(
    language: str, heading: str, conjunction: str, text: str
) -> None:
    """The layout read the word between two headings as a heading of its own."""
    document = DoclingDocument(name="fees")
    document.add_heading(text=heading, level=1)
    document.add_heading(text=conjunction, level=2)
    document.add_text(label=DocItemLabel.TEXT, text=text)

    assert trails(document, language) == [(text, [heading])]


@pytest.mark.nlp
def test_a_heading_that_is_a_noun_stays_a_segment() -> None:
    """A stop word that is not a conjunction, like "Beispiel", still heads."""
    document = DoclingDocument(name="fees")
    document.add_heading(text="Gebühren", level=1)
    document.add_heading(text="Beispiel", level=2)
    document.add_text(
        label=DocItemLabel.TEXT, text="Eine Überweisung kostet zwei Euro."
    )

    assert trails(document, "de")[0][1] == ["Gebühren", "Beispiel"]


@pytest.mark.nlp
def test_a_conjunction_in_capitals_stays_a_segment() -> None:
    """A technical manual heads a section "OR"; the layout's stray word is lower case."""
    document = DoclingDocument(name="gates")
    document.add_heading(text="Logic gates", level=1)
    document.add_heading(text="OR", level=2)
    document.add_text(
        label=DocItemLabel.TEXT, text="An OR gate outputs one if either input does."
    )

    assert trails(document, "en")[0][1] == ["Logic gates", "OR"]


def unfurnished() -> DoclingDocument:
    """Headings, paragraphs and a list, with no running head or foot."""
    document = paged(2)
    document.add_heading(text="Accounts", level=1, prov=on(1, 60))
    say(document, 1, "An account opens once the bank has checked the holder.")
    document.add_heading(text="Fees", level=2, prov=on(2, 60))
    say(document, 2, "For every transfer abroad:")
    group = document.add_list_group()
    for item in ("the bank charges a flat fee", "the payee pays nothing"):
        document.add_list_item(text=item, parent=group, prov=on(2, 140))
    return document


def plain(document: DoclingDocument) -> list:
    """The cut with no reading of furniture at all."""
    cutting = word_chunker(200)
    return [
        (chunk.text, chunk.meta.headings, [i.self_ref for i in chunk.meta.doc_items])
        for chunk in lead_ins_kept(list(cutting.chunk(document)), cutting, document)
    ]


def read(document: DoclingDocument) -> list:
    """The cut as the builder makes it."""
    return [
        (chunk.text, chunk.meta.headings, [i.self_ref for i in chunk.meta.doc_items])
        for chunk in cut(document)
    ]


def test_a_document_with_no_running_head_or_foot_is_cut_as_before() -> None:
    """No chapter, no prefix, no reset, and the document is not copied."""
    document = unfurnished()

    tidy, _ = chunks_of(document, word_chunker(200), None)

    assert tidy is document
    assert read(document) == plain(unfurnished())


def test_a_foot_holding_only_the_title_and_the_page_changes_nothing() -> None:
    """A page number changes on every page and is not a chapter."""
    document = unfurnished()
    for page in (1, 2):
        foot(document, page, f"{GUIDE} | Page {page} of 2")

    assert read(document) == plain(document)


def test_running_heads_that_alternate_change_nothing() -> None:
    """Chapter on the right-hand page, title on the left: neither is a chapter.

    Read as chapters, they would reset the heading trail on every page.
    """
    document = unfurnished()
    for page, printed in ((1, "Accounts"), (2, GUIDE), (3, "Accounts"), (4, GUIDE)):
        foot(document, page, printed)

    assert read(document) == plain(document)


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        (
            "Retail Banking Guide  2026 | Accounts",
            ["Retail Banking Guide  2026", "Accounts"],
        ),
        (
            "Retail Banking Guide 2026\tAccounts",
            ["Retail Banking Guide 2026", "Accounts"],
        ),
        (
            "Retail Banking Guide 2026   Accounts",
            ["Retail Banking Guide 2026", "Accounts"],
        ),
    ],
)
def test_a_running_head_splits_where_its_text_separates_fields(
    printed, expected
) -> None:
    """On its bars when it has them, else on tabs and runs of spaces."""
    assert fields(printed) == expected


def transfers(*heads: tuple[str, ...]) -> DoclingDocument:
    """One numbered section over as many pages as there are heads given."""
    document = paged(len(heads))
    for page, printed in enumerate(heads, 1):
        for text in printed:
            head(document, page, text)
    document.add_heading(text="2. Transfers", level=1, prov=on(1, 60))
    for page in range(1, len(heads) + 1):
        say(document, page, f"A transfer rule printed on page {page}.")
    return document


def test_a_head_printed_on_one_page_only_is_not_a_chapter() -> None:
    """A stray page header does not take the pages after it from their heading."""
    document = transfers((GUIDE,), (GUIDE, "Important notice"), (GUIDE,), (GUIDE,))

    assert read(document) == plain(document)
    assert {str(headings) for _, headings, _ in read(document)} == {"['2. Transfers']"}


def test_heads_that_differ_on_every_page_are_not_chapters() -> None:
    """A guide's guide words name the page, not a chapter, numerals or none."""
    document = transfers(("Abacus",), ("Balance",), ("Credit",), ("Deposit",))

    assert read(document) == plain(document)


def test_a_chapter_headed_on_one_page_is_not_filed_under_the_one_before() -> None:
    """Its single-page head names no chapter, so it carries none, not the last."""
    document = paged(4)
    for page, printed in ((1, "Accounts"), (2, "Accounts"), (3, "Cards")):
        foot(document, page, f"{GUIDE} | {printed}")
    foot(document, 4, GUIDE)
    document.add_heading(text="1. Opening an account", level=1, prov=on(1, 60))
    say(document, 1, "An account opens once the bank has checked the holder.")
    say(document, 2, "A joint account needs both holders to sign.")
    document.add_heading(text="1. Debit cards", level=1, prov=on(3, 60))
    say(document, 3, "A debit card draws on the current account.")
    say(document, 4, "A credit card carries a monthly limit.")

    assert [headings for _, headings in trails(document)] == [
        ["Accounts", "1. Opening an account"],
        ["1. Debit cards"],
    ]


def facing() -> DoclingDocument:
    """Left pages head their chapter, right pages a topic of their own."""
    document = paged(9)
    topics = {3: "Savings", 5: "Loans", 7: "Cards", 9: "Mortgages"}
    for page in range(2, 10):
        chapter = "Chapter A" if page < 6 else "Chapter B"
        head(document, page, topics.get(page, f"{GUIDE} | {chapter}"))
    document.add_heading(text="Overview", level=1, prov=on(2, 60))
    for page in range(2, 10):
        if page == 6:
            document.add_heading(text="Details", level=1, prov=on(6, 60))
        say(document, page, f"A rule the guide prints on page {page}.")
    return document


def test_a_facing_page_with_a_topic_of_its_own_stays_in_its_chapter() -> None:
    """Its chapter is printed either side of it, so its section is not cut short."""
    document = facing()

    tidy, chunks = chunks_of(document, word_chunker(200), None)

    on_four = [c for c in chunks if "page 4." in c.text or "page 5." in c.text]
    assert on_four and all("Overview" in (c.meta.headings or []) for c in on_four), [
        (c.text, c.meta.headings) for c in chunks
    ]
    inserted = [item.text for item in tidy.texts if item.label == DocItemLabel.TITLE]
    assert len(inserted) == 2, inserted
