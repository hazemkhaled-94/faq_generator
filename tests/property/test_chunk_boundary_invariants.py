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


# ── A list's depth and a heading's number, wherever the page sets them ────

#: One rule a list item states, by language: a bank's, a shop's, an office's.
ITEMS = {
    "de": [
        "Kontoführung monatlich",
        "Ersatzkarte auf Antrag",
        "Rücksendung binnen 14 Tagen",
        "Antrag beim Bürgeramt",
    ],
    "en": [
        "Account kept monthly",
        "Replacement card on request",
        "Returns within 14 days",
        "Application at the office",
    ],
    "fr": [
        "Tenue de compte mensuelle",
        "Carte de remplacement",
        "Retour sous 14 jours",
        "Demande à la mairie",
    ],
    "pl": [
        "Prowadzenie konta co miesiąc",
        "Karta zastępcza na wniosek",
        "Zwrot w ciągu 14 dni",
        "Wniosek w urzędzie",
    ],
    "el": [
        "Τήρηση λογαριασμού μηνιαία",
        "Κάρτα αντικατάστασης",
        "Επιστροφή εντός 14 ημερών",
        "Αίτηση στην υπηρεσία",
    ],
}

#: How far right one level of a list is set: more than half a line.
INDENT = 18.0


@st.composite
def nestings(draw) -> tuple[str, list[int]]:
    """A language and the depth of each item of one list: from 0, one deeper at most each step."""
    language = draw(st.sampled_from(sorted(ITEMS)))
    depths = [0]
    for _ in range(draw(st.integers(1, 7))):
        depths.append(draw(st.integers(0, depths[-1] + 1)))
    return language, depths


def listed_lines(
    language: str, depths: list[int], margin: float, turn: int | None = None
) -> list[str]:
    """The lines one list cuts to, set at `margin`, each item a line 200 wide.

    On one page, or from item `turn` on at the top of a second page.
    """
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    group = document.add_list_group()
    for at, depth in enumerate(depths):
        left = margin + INDENT * depth
        page, row = (2, at - turn) if turn is not None and at >= turn else (1, at)
        top = (60 if page == 2 else 100 if turn is None else 700 - 14 * turn) + 14 * row
        document.add_list_item(
            text=f"{ITEMS[language][at % 4]} {at + 1}",
            parent=group,
            prov=ProvenanceItem(
                page_no=page,
                bbox=BoundingBox(
                    l=left,
                    t=top,
                    r=left + 200,
                    b=top + 10,
                    coord_origin=CoordOrigin.TOPLEFT,
                ),
                charspan=(0, 1),
            ),
        )
    _, chunks = chunks_of(document, word_chunker(200), language)
    return [line for chunk in chunks for line in chunk.text.splitlines()]


@given(case=nestings(), margin=st.floats(20, 300))
def test_a_list_items_depth_is_its_indent_wherever_the_page_margin_lies(
    case, margin
) -> None:
    """Each item nests as deep as it is set in, from the list's own edge, not the page's."""
    language, depths = case

    lines = listed_lines(language, depths, margin)

    assert [len(line) - len(line.lstrip()) for line in lines] == [
        4 * depth for depth in depths
    ], lines


@given(case=nestings(), margin=st.floats(20, 300), turn=st.data())
def test_a_list_going_on_over_a_page_keeps_each_items_depth(case, margin, turn) -> None:
    """Sub-items at the top of the next page stay as deep as they are set in.

    No level opens across the break, as `nested` says: the first item of the
    page is drawn no deeper than the last of the page before. Both pages set
    the list at one margin: a facing page's other margin is N-101's.
    """
    language, depths = case
    at = turn.draw(st.integers(1, len(depths) - 1))
    depths[at] = min(depths[at], depths[at - 1])
    for i in range(at + 1, len(depths)):
        depths[i] = min(depths[i], depths[i - 1] + 1)

    lines = listed_lines(language, depths, margin, at)

    assert [len(line) - len(line.lstrip()) for line in lines] == [
        4 * depth for depth in depths
    ], (lines, at)


#: A numbered heading of each language, as a label, a number and its words.
HEADINGS = {
    "de": ("Artikel", "Haftung des Kontoinhabers bei Missbrauch der Karte"),
    "en": ("Article", "Liability of the account holder for misuse of the card"),
    "fr": ("Article", "Responsabilité du titulaire en cas d'abus de la carte"),
    "pl": ("Artykuł", "Odpowiedzialność posiadacza rachunku za użycie karty"),
    "el": ("Άρθρο", "Ευθύνη του δικαιούχου για κατάχρηση της κάρτας"),
}

#: The paragraph each heading is over.
BODIES = {
    "de": "Die Bank haftet nicht für Schäden durch eine verschuldete Weitergabe.",
    "en": "The bank is not liable for losses caused by the customer passing on a code.",
    "fr": "La banque ne répond pas des pertes dues à la transmission d'un code.",
    "pl": "Bank nie odpowiada za szkody wynikłe z przekazania kodu przez klienta.",
    "el": "Η τράπεζα δεν ευθύνεται για ζημίες από τη μετάδοση κωδικού.",
}


@st.composite
def justified(draw) -> tuple[str, str, list[tuple[str, float, float]]]:
    """A language, its whole heading, and the heading cut into fragments set side by side on one line.

    A justified line's gaps: wider than a space, narrower than eight line heights.
    """
    language = draw(st.sampled_from(sorted(HEADINGS)))
    label, rest = HEADINGS[language]
    number = ".".join(
        map(str, draw(st.lists(st.integers(1, 19), min_size=1, max_size=3)))
    )
    words = [f"{label} {number}", *rest.split()]
    cuts = sorted(draw(st.sets(st.integers(1, len(words) - 1), min_size=1, max_size=4)))
    pieces = [
        " ".join(words[a:b])
        for a, b in zip([0, *cuts], [*cuts, len(words)], strict=True)
    ]
    placed, left = [], 30.0
    for piece in pieces:
        placed.append((piece, left, 100.0))
        left += 4 * len(piece) + draw(st.floats(3, 40))
    return language, " ".join(words), placed


@given(case=justified())
def test_a_numbered_heading_cut_into_fragments_on_its_line_heads_its_passage_whole(
    case,
) -> None:
    """The trail holds the heading whole, label and number first, however the converter cut it."""
    language, whole, placed = case
    document = DoclingDocument(name="terms")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    for text, left, top in placed:
        document.add_heading(
            text=text,
            level=2,
            prov=ProvenanceItem(
                page_no=1,
                bbox=BoundingBox(
                    l=left,
                    t=top,
                    r=left + 4 * len(text),
                    b=top + 12,
                    coord_origin=CoordOrigin.TOPLEFT,
                ),
                charspan=(0, 1),
            ),
        )
    document.add_text(label=DocItemLabel.TEXT, text=BODIES[language], prov=on(1, 300))

    _, chunks = chunks_of(document, word_chunker(80), language)

    assert [chunk.meta.headings for chunk in chunks] == [[whole]], placed
