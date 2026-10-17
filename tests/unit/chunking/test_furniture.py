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


def test_a_chapter_printed_on_one_page_is_filed_under_its_own_foot() -> None:
    """A short chapter prints its foot on one page, laid out as every chapter's is.

    The foot has the shape of the ones that name the chapters before it, so
    it names this one, rather than leaving its rules under no chapter.
    """
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
        ["Cards", "1. Debit cards"],
    ]


def test_guide_words_inside_a_chaptered_guide_name_no_chapter() -> None:
    """A glossary whose foot names each page's first entry is still one glossary."""
    document = paged(6)
    for page, printed in (
        (1, "Accounts"),
        (2, "Accounts"),
        (3, "Abacus"),
        (4, "Balance"),
        (5, "Credit"),
        (6, "Fees"),
    ):
        foot(document, page, f"{GUIDE} | {printed}")
    document.add_heading(text="1. Opening an account", level=1, prov=on(1, 60))
    say(document, 1, "An account opens once the bank has checked the holder.")
    say(document, 2, "A joint account needs both holders to sign.")
    document.add_heading(text="Glossary", level=1, prov=on(3, 60))
    for page, entry in (
        (3, "Abacus: a counting frame."),
        (4, "Balance: money held."),
        (5, "Credit: money lent."),
    ):
        say(document, page, entry)

    glossary = [headings for text, headings in trails(document) if "Abacus" in text]

    assert glossary == [["Glossary"]]


def test_a_stray_foot_inside_a_chapter_changes_nothing() -> None:
    """One page printing a notice in its foot is still in the chapter around it."""
    document = paged(5)
    for page, printed in (
        (1, "Accounts"),
        (2, "Accounts"),
        (3, "Important notice"),
        (4, "Accounts"),
        (5, "Accounts"),
    ):
        foot(document, page, f"{GUIDE} | {printed}")
    document.add_heading(text="1. Opening an account", level=1, prov=on(1, 60))
    for page in range(1, 6):
        say(document, page, f"An account rule printed on page {page}.")

    assert {str(headings) for _, headings in trails(document)} == {
        "['Accounts', '1. Opening an account']"
    }


def test_a_label_printed_letter_spaced_is_spelled_as_the_body_spells_it() -> None:
    """A tracked font puts spaces inside the words of a running foot."""
    document = paged(4)
    for page in (1, 2):
        foot(document, page, f"{GUIDE} | Sav ings ac counts")
    for page in (3, 4):
        foot(document, page, f"{GUIDE} | Cards")
    document.add_heading(text="1. Interest", level=1, prov=on(1, 60))
    say(document, 1, "Savings accounts pay interest every month.")
    say(document, 2, "Interest on savings accounts is taxed.")
    document.add_heading(text="1. Debit cards", level=1, prov=on(3, 60))
    say(document, 3, "A debit card draws on the current account.")

    assert trails(document)[0][1] == ["Savings accounts", "1. Interest"]


def test_a_sentence_cut_by_a_page_break_is_read_whole() -> None:
    """The converter ends a block at the foot of a page, mid-sentence."""
    document = paged(2)
    say(document, 1, "A transfer is released once the payee")
    say(document, 2, "is verified by the bank.")

    texts = [text for text, _ in trails(document)]

    assert any(
        "A transfer is released once the payee is verified by the bank." in text
        for text in texts
    ), texts


@pytest.mark.parametrize(
    ("before", "after", "whole"),
    [
        (
            "Die monatliche Kontofüh-",
            "rungsgebühr beträgt fünf Euro.",
            "Die monatliche Kontoführungsgebühr beträgt fünf Euro.",
        ),
        (
            "Es gilt das Zoll-",
            "und Steuerrecht des Landes.",
            "Es gilt das Zoll- und Steuerrecht des Landes.",
        ),
    ],
    ids=["a broken word", "a shared suffix"],
)
def test_a_word_hyphenated_across_a_page_is_one_word(
    before: str, after: str, whole: str
) -> None:
    """The page broke the word; a hyphen a joining word completes stays."""
    document = paged(2)
    say(document, 1, before)
    say(document, 2, after)

    texts = [text for text, _ in trails(document)]

    assert texts == [whole], texts


def test_two_blocks_in_one_column_of_a_page_are_not_joined() -> None:
    """A break the page does not force is the document's own."""
    document = paged(1)
    say(document, 1, "Fees are listed in the annex")
    say(document, 1, "interest is paid monthly.")

    texts = [text for text, _ in trails(document)]

    assert not any("annex interest" in text for text in texts), texts


def test_a_paragraph_repeating_a_running_field_heads_what_follows() -> None:
    """A chapter title the converter read as body text says nothing of its own."""
    document = paged(2)
    for page in (1, 2):
        foot(document, page, f"{GUIDE} | Accounts")
    say(document, 1, "Accounts")
    say(document, 1, "An account opens once checked.")

    found = trails(document)

    assert [(text, headings[-1:]) for text, headings in found] == [
        ("An account opens once checked.", ["Accounts"])
    ], found


def test_a_paragraph_repeating_a_heading_heads_what_follows() -> None:
    """A heading printed again as a paragraph is a heading, not a passage."""
    document = paged(1)
    document.add_heading(text="4. Disciplinary action", level=1, prov=on(1, 60))
    say(document, 1, "A warning is recorded in writing.")
    document.add_heading(text="5. Appeals", level=1, prov=on(1, 300))
    say(document, 1, "4. Disciplinary action")
    say(document, 1, "An appeal is heard within 14 days.")

    found = trails(document)

    assert all(not text.startswith("4. Disciplinary") for text, _ in found), found


@pytest.mark.parametrize("number", ["47", "– 12 –", "(3)"])
def test_a_paragraph_with_no_letter_is_not_passage_text(number: str) -> None:
    """A page number the converter read as body text."""
    document = paged(1)
    say(document, 1, "An account opens once checked.")
    say(document, 1, number)

    texts = [text for text, _ in trails(document)]

    assert texts == ["An account opens once checked."], texts


@pytest.mark.parametrize(
    "value",
    [
        "4,90 €",
        "3,5 %",
        "0800 123 4567",
        "§ 12",
        "01.01.2026",
        "10:00 – 18:00",
        "-5,00 EUR",
    ],
)
def test_a_value_with_no_letter_stays_in_the_body(value: str) -> None:
    """A price, a rate, a phone number or a date is no page number."""
    document = paged(1)
    say(document, 1, "Die monatliche Gebühr beträgt:")
    say(document, 1, value)

    texts = [text for text, _ in trails(document)]

    assert any(value in text for text in texts), texts


@pytest.mark.parametrize(
    "line", ["See Section 5 for the diagrams.", "Promptly, in writing."]
)
def test_a_short_line_of_content_stays_passage_text(line: str) -> None:
    """Short and verbless is not the same as a heading."""
    document = paged(2)
    for page in (1, 2):
        foot(document, page, f"{GUIDE} | Accounts")
    document.add_heading(text="5. Diagrams", level=1, prov=on(1, 60))
    say(document, 1, line)

    assert any(line in text for text, _ in trails(document))


def test_an_elision_mark_stays_passage_text() -> None:
    """`(…)` says a quotation left something out; later readings rely on it."""
    document = paged(1)
    say(document, 1, "(…)")
    say(document, 1, "Except as outlined above, the fee is waived.")

    assert any("(…)" in text for text, _ in trails(document))


def test_a_running_head_read_as_body_text_on_its_own_page_is_dropped() -> None:
    """The head printed on the page, read twice, heads nothing; a list item stays."""
    document = paged(2)
    for page in (1, 2):
        head(document, page, "Accounts")
    say(document, 2, "Accounts")
    say(document, 2, "A joint account needs both holders to sign.")
    group = document.add_list_group()
    document.add_list_item(text="Accounts", parent=group, prov=on(2, 200))

    texts = [text for text, _ in trails(document)]

    assert texts == ["A joint account needs both holders to sign.\n- Accounts"], texts


def test_index_letters_read_as_headings_and_as_text_are_all_dividers() -> None:
    """The converter takes some index letters as headings and some as text."""
    document = DoclingDocument(name="glossary")
    document.add_heading(text="Glossary", level=1)
    for kind, text in (
        ("heading", "A"),
        ("text", "Abacus: a counting frame."),
        ("text", "B"),
        ("text", "Balance: money held."),
        ("heading", "C"),
        ("text", "Credit: money lent."),
    ):
        if kind == "heading":
            document.add_heading(text=text, level=2)
        else:
            document.add_text(label=DocItemLabel.TEXT, text=text)

    found = trails(document)

    assert all(len(segment) > 1 for _, trail in found for segment in trail), found
    assert all("\nB\n" not in f"\n{text}\n" for text, _ in found), found


def test_a_letter_out_of_an_index_run_does_not_hide_the_index() -> None:
    """One stray letter among the dividers leaves the rest of the run read."""
    document = DoclingDocument(name="glossary")
    document.add_heading(text="Glossary", level=1)
    for text in (
        "A",
        "Abacus: a counting frame.",
        "K",
        "Kiosk: a small shop.",
        "C",
        "Credit: money lent.",
        "D",
        "Debit: money taken.",
    ):
        document.add_text(label=DocItemLabel.TEXT, text=text)

    texts = "\n".join(text for text, _ in trails(document))

    assert "\nA\n" not in f"\n{texts}\n" and "\nC\n" not in f"\n{texts}\n", texts


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


def test_a_page_printing_part_of_its_chapter_s_label_stays_in_the_chapter() -> None:
    """A page heading only its chapter's number opens no chapter of its own."""
    full, cards = f"{GUIDE} | Chapter 3 | Fees", f"{GUIDE} | Chapter 4 | Cards"
    document = paged(5)
    for page, printed in enumerate(
        (full, full, f"{GUIDE} | Chapter 3", cards, cards), 1
    ):
        head(document, page, printed)
    document.add_heading(text="3.1 Account fees", level=1, prov=on(1, 60))
    for page in (1, 2, 3):
        say(document, page, f"A fee rule printed on page {page}.")
    document.add_heading(text="4.1 Debit cards", level=1, prov=on(4, 60))
    for page in (4, 5):
        say(document, page, f"A card rule printed on page {page}.")

    tidy, chunks = chunks_of(document, word_chunker(200), None)

    inserted = [item.text for item in tidy.texts if item.label == DocItemLabel.TITLE]
    assert inserted == ["Chapter 3 | Fees", "Chapter 4 | Cards"], inserted
    (third,) = [chunk for chunk in chunks if "page 3." in chunk.text]
    assert third.meta.headings == ["Chapter 3", "Fees", "3.1 Account fees"]
