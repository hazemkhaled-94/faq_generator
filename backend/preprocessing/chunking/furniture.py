"""Reading a document's running heads and feet, and the debris on its pages.

A running head or foot names the chapter its page is in, which the
converter's heading tree does not when a chapter opens on a decorative title
it never takes as a heading: the last numbered heading of the chapter before
is then inherited by every passage of the next. The converter also reads a
running foot as body text now and then, and a glossary's index letter as a
paragraph; neither is passage text.

Nothing here names a word of any document: the chapter is whatever the
document's own running heads print that changes from page to page.
"""

from __future__ import annotations

import logging
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import ProvenanceItem, RefItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.node import DocItem, NodeItem
from docling_core.types.doc.items.text import SectionHeaderItem, TextItem, TitleItem
from docling_core.types.doc.labels import DocItemLabel

from nlp.text import printed, rejoined

log = logging.getLogger(__name__)

#: The labels the converter gives a running head or foot.
_RUNNING = frozenset({DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER})

#: The labels of a paragraph of body text.
_PROSE = frozenset({DocItemLabel.TEXT, DocItemLabel.PARAGRAPH})

#: What separates the fields of a running head with no bar in it: a tab or a
#: run of spaces.
_GAP = re.compile(r"\t+|\s{2,}")

#: A numeral: digits, or a word spelled only in the letters of a Roman one.
_NUMERAL = re.compile(r"\d+|\b[ivxlcdm]+\b", re.IGNORECASE)

_SPACE = re.compile(r"\s+")

#: Everything but letters and digits, which a repeated heading is compared on.
_PUNCTUATION = re.compile(r"[\W_]+")

#: A page number as a page prints one: a bare integer of up to four digits,
#: framed at most by dashes or brackets - `47`, `– 12 –`, `(3)`. A price, a
#: rate, a phone number, a date or a time carries more than that.
_PAGE_NUMBER = re.compile(r"[-–—(\[\s]*\d{1,4}[-–—)\]\s]*")

#: The labels of a heading the converter took as one.
_HEADINGS = frozenset({DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE})

#: The most body words one running field is matched against when its
#: spacing is read off the body.
_RESPACE_WORDS = 8

#: What a sentence or a lead-in ends on. A block ending in none of these
#: before a page or column break goes on in the next one.
_ENDS = (".", "!", "?", ":", ";")

#: The conjunctions that join two alternatives or two items, by ISO 639-1
#: code: printed alone between two blocks, the layout reads one as a heading.
_CONJUNCTIONS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {"und", "oder", "aber", "sondern", "sowie", "bzw", "beziehungsweise"}
    ),
    "en": frozenset({"and", "or", "but", "nor"}),
}


def fields(text: str) -> list[str]:
    """Splits a running head or foot into its fields, as its text separates them.

    On its bars when it has any, so a doubled space inside a field does not
    split it; otherwise on tabs and runs of spaces.
    """
    parts = text.split("|") if "|" in text else _GAP.split(text)
    return [part.strip() for part in parts if part.strip()]


def _key(field: str) -> str:
    """A field's identity, whatever spacing the converter read into it."""
    return _SPACE.sub("", field).casefold()


def _lettered(field: str) -> bool:
    """Reports whether a field holds a letter, which a page number does not."""
    return any(character.isalpha() for character in field)


@dataclass(frozen=True)
class Furniture:
    """What a document's running heads and feet say about its pages.

    Attributes:
        starts: The pages the chapter changes on, ascending.
        labels: The chapter from each of those pages on: its label's fields,
            as the first page printing them spelled them, or empty from a
            page that is in no chapter.
        running: Every running head and foot, as the keys of its fields,
            page numbers left out.
    """

    starts: tuple[int, ...] = ()
    labels: tuple[tuple[str, ...], ...] = ()
    running: frozenset[tuple[str, ...]] = frozenset()

    def chapter(self, page: int | None) -> tuple[str, ...]:
        """The chapter a page is in, empty when it is in none."""
        if page is None:
            return ()
        at = bisect_right(self.starts, page) - 1
        return self.labels[at] if at >= 0 else ()


def furniture_of(document: DoclingDocument) -> Furniture:
    """Reads the chapters and running strings off a document's furniture.

    Each running head and foot is split into fields. A field that numbers
    pages is dropped, and so is one printed on every page that prints any:
    the title, the edition. What is left, printed on a run of pages and
    changing from one run to the next, is the chapter label. A page printing
    only the title is in the chapter of the page before, and so is one
    printing only some of that chapter's fields. So is a page printing only
    single-page fields, when the same label is printed either side of it.

    Otherwise a field printed on a single page names a chapter of one page
    when its running item is laid out as one naming a chapter of several -
    the same fields constant and varying, in the same places - and no page
    beside it prints a single-page field of its own. A short chapter prints
    its foot on one page; guide words, naming each page's first entry, print
    a different one on every page in a row, and a page between them is in
    no chapter. When one of the varying fields comes back after another has
    taken over, as on pages whose heads alternate between title and
    chapter, the heads do not name chapters and none is read.

    Args:
        document: The converted document.

    Returns:
        Its chapters and running strings; empty for a document with no
        running head or foot.
    """
    printed = [
        (item.prov[0].page_no, fields(item.text))
        for item in document.texts
        if item.label in _RUNNING and item.prov
    ]
    pages_of: dict[str, set[int]] = defaultdict(set)
    spelled: dict[str, str] = {}
    for page, found in printed:
        for one in found:
            pages_of[_key(one)].add(page)
            spelled.setdefault(_key(one), one)
    numbers = _numbers(pages_of, spelled)
    spelled = _respaced(spelled, document)
    running = frozenset(
        keys
        for _, found in printed
        if (
            keys := tuple(
                _key(one)
                for one in found
                if _lettered(one) and _key(one) not in numbers
            )
        )
    )

    by_page: dict[int, dict[str, None]] = defaultdict(dict)
    # Each running item's fields, by page, for the layout a chapter's has.
    items_on: dict[int, list[tuple[str, ...]]] = defaultdict(list)
    for page, found in printed:
        keys = tuple(_key(one) for one in found if _key(one) not in numbers)
        for key in keys:
            by_page[page][key] = None
        if keys:
            items_on[page].append(keys)
    furnished = set(by_page)
    constant = {key for key, pages in pages_of.items() if pages >= furnished}
    varying = {
        key
        for key, pages in pages_of.items()
        if key not in numbers and len(pages) > 1 and key not in constant
    }
    order = sorted(
        page for page, keys in by_page.items() if any(k in varying for k in keys)
    )
    position = {page: index for index, page in enumerate(order)}
    if not all(_contiguous(pages_of[key], position) for key in varying):
        log.info(
            "%s: its running heads come back out of order, so name no chapters",
            document.name,
        )
        return Furniture(running=running)

    def shape(keys: tuple[str, ...]) -> tuple[bool, ...]:
        """Which of an item's fields are constant, in the order it prints them."""
        return tuple(key in constant for key in keys)

    chaptered = {
        shape(keys)
        for items in items_on.values()
        for keys in items
        if any(key in varying for key in keys)
    }

    def single(page: int) -> tuple[str, ...]:
        """The lettered fields of a page that no other page prints."""
        return tuple(
            key
            for key in by_page.get(page, {})
            if key not in constant and key not in varying and _lettered(key)
        )

    def names_a_chapter(page: int, own: tuple[str, ...]) -> bool:
        """Whether a page's single-page fields name a chapter of one page."""
        if not any(
            shape(keys) in chaptered and any(key in own for key in keys)
            for keys in items_on[page]
        ):
            return False
        return not any(
            single(beside)
            and set(single(beside)) != set(own)
            and not any(key in varying for key in by_page.get(beside, {}))
            for beside in (page - 1, page + 1)
        )

    pages = sorted(by_page)
    printing = {
        page: tuple(spelled[key] for key in by_page[page] if key in varying)
        for page in pages
    }
    # The next label printed after each page, None after the last.
    following: dict[int, tuple[str, ...] | None] = {}
    upcoming: tuple[str, ...] | None = None
    for page in reversed(pages):
        following[page] = upcoming
        upcoming = printing[page] or upcoming

    starts: list[int] = []
    labels: list[tuple[str, ...]] = []
    for page in pages:
        label, before = printing[page], labels[-1] if labels else ()
        # A page printing only the title goes on in its chapter, and so does
        # one printing only fields of its own between two pages of the same
        # chapter, as a facing page's topic does. Between two chapters, or
        # after the last, it is in none rather than in the chapter before: a
        # chapter headed on a single page.
        if not label and (
            by_page[page].keys() <= constant or following[page] == before
        ):
            continue
        if not label and (own := single(page)) and names_a_chapter(page, own):
            label = tuple(spelled[key] for key in own)
        # A page printing only part of its chapter's label, its number
        # without its title, is still in it.
        if label and set(label) <= set(before):
            continue
        if label != before:
            starts.append(page)
            labels.append(label)
    return Furniture(tuple(starts), tuple(labels), running)


def _respaced(spelled: dict[str, str], document: DoclingDocument) -> dict[str, str]:
    """Each field spelled with the spaces the body puts in its words.

    A running head set in a tracked font comes out of the converter
    letter-spaced, `Sav ings ac counts`, and the chapter would be labelled
    so. The body prints the same words: a run of up to `_RESPACE_WORDS` body
    words whose letters, case and spaces aside, are the field's gives the
    spaces - the run with the fewest, then the commonest. The field keeps
    its own characters and case and borrows only where the spaces go. A
    field the body never prints keeps its spelling.
    """
    seen: dict[str, Counter[str]] = defaultdict(Counter)
    for item in document.texts:
        if item.label in _RUNNING or not item.text:
            continue
        words = item.text.split()
        for start in range(len(words)):
            joined = ""
            for end in range(start, min(len(words), start + _RESPACE_WORDS)):
                joined += words[end]
                if joined.casefold() in spelled:
                    seen[joined.casefold()][" ".join(words[start : end + 1])] += 1
    respaced = dict(spelled)
    for key, runs in seen.items():
        best = min(runs.items(), key=lambda run: (run[0].count(" "), -run[1]))[0]
        own = [char for char in spelled[key] if not char.isspace()]
        if len(own) != len(best) - best.count(" "):
            continue
        letters = iter(own)
        respaced[key] = "".join(" " if char == " " else next(letters) for char in best)
    return respaced


def _numbers(pages_of: dict[str, set[int]], spelled: dict[str, str]) -> set[str]:
    """The keys of the fields that number pages.

    A field holding no letter, and every field of one shape, its numerals
    masked, that no two pages print alike: "Page 3 of 12" and "iv".
    """
    by_shape: dict[str, list[str]] = defaultdict(list)
    for key in pages_of:
        by_shape[_key(_NUMERAL.sub("#", spelled[key]))].append(key)
    found = {key for key in pages_of if not _lettered(key)}
    for shape, keys in by_shape.items():
        if (
            "#" in shape
            and len(keys) > 1
            and all(len(pages_of[key]) == 1 for key in keys)
        ):
            found.update(keys)
    return found


def _contiguous(pages: set[int], position: dict[int, int]) -> bool:
    """Reports whether a field is printed on one unbroken run of pages.

    Counted over the pages printing a field that varies, so a page whose
    foot carries only the title or a number breaks no run.
    """
    at = sorted(position[page] for page in pages if page in position)
    return not at or at[-1] - at[0] + 1 == len(at)


def tidied(
    document: DoclingDocument, furniture: Furniture, language: str | None
) -> tuple[DoclingDocument, dict[str, tuple[str, ...]]]:
    """Prepares a document for the chunker: debris out, a title at each chapter.

    A heading that is a lone conjunction, as `_junk` tells one, between two
    list items or two paragraphs, is the layout reading the word between two
    alternatives as a heading: it is read as the paragraph it is, so the
    alternatives stay in one passage with the word between them. A
    paragraph that starts with a running head or foot, field for field and
    with whitespace removed, is the converter reading furniture as body
    text. A paragraph of one letter, followed by
    entries under that letter, is a glossary's index divider, where the
    document holds two or more in ascending order. Both move to the
    furniture layer. A sentence the converter cut at a page or column break
    is joined back: a paragraph or list item ending in no `_ENDS` mark,
    followed on the next page or in the next column by a paragraph opening
    in lower case, takes that paragraph's text and its place on the page,
    and the paragraph moves to the furniture layer. A paragraph that is a
    page number read as body text moves there too; a price, a rate, a phone
    number or a date with no letter beside it stays, and so does an elision
    mark, `(…)`. A paragraph that only
    repeats a running field or a heading of the document - a chapter title
    the converter read as body text - is a heading, unless it or what it
    repeats is a lone conjunction: one is
    put before it, a level below the heading it follows, so it heads what
    comes next, and it moves to the furniture layer; where it repeats the
    heading right before it, it only moves. Before the first block of each
    chapter goes a title naming it, which empties the heading trail the
    chunker would otherwise carry over from the chapter before.

    Args:
        document: The converted document, which is not modified.
        furniture: What its running heads and feet say.
        language: The document's language, whose `_CONJUNCTIONS` tell a
            lone conjunction.

    Returns:
        The document to cut, a copy when anything changed and `document`
        itself when nothing did; and every title put in, by its text, with
        the chapter label it stands for.
    """
    junk = _junk(language)
    given, document = document, _demoted(document, junk)
    debris = _dividers(document) | {
        item.self_ref
        for item in document.texts
        if item.content_layer == ContentLayer.BODY
        and item.label in _PROSE
        and (_repeats(item.text, furniture.running) or _page_number(item.text))
    }
    restated = _restated(document, debris, junk)
    debris |= {reference for reference, level in restated if level is None}
    promoted = [(reference, level) for reference, level in restated if level]
    debris |= {reference for reference, _ in promoted}
    joins = _continued(document, debris)
    starts = _chapter_starts(document, furniture, debris)
    if not debris and not starts and not joins:
        return document, {}

    # A document a heading was demoted in is a copy already.
    tidy = document.model_copy(deep=True) if document is given else document
    for reference, level in promoted:
        node = _resolved(reference, tidy)
        if isinstance(node, TextItem):
            # Appended to the texts, so no reference the passages store moves.
            tidy.insert_heading(
                sibling=node,
                text=node.text.strip(),
                level=level,
                prov=node.prov[0] if node.prov else None,
                after=False,
            )
    for reference in debris:
        _resolved(reference, tidy).content_layer = ContentLayer.FURNITURE
    into: dict[str, str] = {}
    whole = printed(item.text for item in tidy.texts)
    for first, second in joins:
        target = into.get(first, first)
        joined, taken = _resolved(target, tidy), _resolved(second, tidy)
        if isinstance(joined, TextItem) and isinstance(taken, TextItem):
            # Mended after the join: a word the page broke meets its rest here.
            joined.text = rejoined(
                f"{joined.text.rstrip()} {taken.text.lstrip()}", whole
            )
            # And its place, so the passage cites the page the sentence ends on.
            joined.prov.extend(taken.prov)
            taken.content_layer = ContentLayer.FURNITURE
            into[second] = target
    titles: dict[str, tuple[str, ...]] = {}
    for reference, label in starts:
        text = " | ".join(label)
        titles[text] = label
        # Appended to the texts, so no reference the passages store moves.
        tidy.insert_title(sibling=_resolved(reference, tidy), text=text, after=False)
    return tidy, titles


def _resolved(reference: str, document: DoclingDocument) -> NodeItem:
    """The node a reference names in a document."""
    return RefItem.model_validate({"$ref": reference}).resolve(document)


def _dividers(document: DoclingDocument) -> set[str]:
    """The paragraphs and headings that are a glossary's index letters.

    One letter, and the next text in the body starts with it, in either
    case. The converter takes some index letters as headings and some as
    text, so both are read. A lone letter followed by anything else is
    content: an energy class, a part marker. And an index has two letters or
    more, each after the one before as its character code is: the longest
    such run is the index, and a letter outside it - a stray one the page
    hides, a class "A" over a line that happens to start with an A - is
    left. A document whose letters never run is giving values, and none is
    dropped.
    """
    texts = [
        item
        for item, _ in document.iterate_items()
        if isinstance(item, TextItem) and item.text.strip()
    ]
    found = [
        (item.self_ref, letter.casefold())
        for item, following in pairwise(texts)
        if (item.label in _PROSE or item.label == DocItemLabel.SECTION_HEADER)
        and len(letter := item.text.strip()) == 1
        and letter.isalpha()
        and following.text.strip()[0].casefold() == letter.casefold()
    ]
    # The longest run of letters each after the one before, by its references.
    runs: list[list[str]] = []
    for index, (reference, letter) in enumerate(found):
        before = [runs[at] for at in range(index) if found[at][1] < letter]
        runs.append([*max(before, key=len, default=[]), reference])
    longest = max(runs, key=len, default=[])
    return set(longest) if len(longest) >= 2 else set()


def _restated(
    document: DoclingDocument, skipped: set[str], junk: Callable[[str], bool]
) -> list[tuple[str, int | None]]:
    """The paragraphs that only repeat a running field or a heading.

    Compared with spaces, punctuation and case set aside, on the whole text,
    so `See Section 5 for the diagrams.` is not `5. Diagrams`. Each comes
    with the level a heading put before it takes - one below the heading it
    follows - or None where it repeats that heading itself and so heads
    nothing new. A paragraph `junk` flags is none, and neither is one that
    repeats a name it flags: a lone `oder` between two alternatives is text
    wherever else the layout took one for a heading.
    """
    names = {
        _plain(name)
        for item in document.texts
        if item.label in _RUNNING
        for name in (item.text, *fields(item.text))
        if not junk(name)
    } | {
        _plain(item.text)
        for item in document.texts
        if item.label in _HEADINGS and not junk(item.text)
    }
    names.discard("")
    found: list[tuple[str, int | None]] = []
    level, last = 0, ""
    for item, _ in document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            level, last = item.level, _plain(item.text)
        elif isinstance(item, TitleItem):
            level, last = 0, _plain(item.text)
        elif (
            isinstance(item, TextItem)
            and item.label in _PROSE
            and item.content_layer == ContentLayer.BODY
            and item.self_ref not in skipped
            and not junk(item.text)
            and (plain := _plain(item.text)) in names
        ):
            found.append(
                (item.self_ref, None if plain == last else min(level + 1, 100))
            )
    return found


def _demoted(document: DoclingDocument, junk: Callable[[str], bool]) -> DoclingDocument:
    """The document with each lone conjunction between alternatives a paragraph.

    A heading that is one, between two list items or two paragraphs - a
    picture between aside - is the word joining them. Anywhere else it
    stays a heading, which `headed` leaves out of the trail: the word
    between two headed sections belongs to neither. So does one holding no
    letter or digit, which names nothing.

    Returns:
        `document` itself when no heading is one, otherwise a copy.
    """
    blocks = [
        item
        for item, _ in document.iterate_items()
        if isinstance(item, DocItem) and item.label != DocItemLabel.PICTURE
    ]
    between = {
        item.self_ref
        for before, item, after in zip(blocks, blocks[1:], blocks[2:], strict=False)
        if isinstance(item, SectionHeaderItem)
        and any(character.isalnum() for character in item.text)
        and junk(item.text)
        and (
            before.label == after.label == DocItemLabel.LIST_ITEM
            or {before.label, after.label} <= _PROSE
        )
    }
    found = [
        index for index, item in enumerate(document.texts) if item.self_ref in between
    ]
    if not found:
        return document
    demoted = document.model_copy(deep=True)
    for index in found:
        heading = demoted.texts[index]
        # In its place in the texts, so every reference to it still holds.
        demoted.texts[index] = TextItem(
            **{
                name: getattr(heading, name)
                for name in TextItem.model_fields
                if name != "label"
            },
            label=DocItemLabel.TEXT,
        )
    return demoted


def _page_number(text: str) -> bool:
    """Whether a paragraph is a page number and nothing else.

    A bare integer alone in its paragraph is read as one, so a value printed
    under its label as one, `30` under `Return period (days):`, goes with it.
    """
    return _PAGE_NUMBER.fullmatch(text.strip()) is not None


def _plain(text: str) -> str:
    """Text with spaces, punctuation and case set aside."""
    return _PUNCTUATION.sub("", text).casefold()


def _continued(document: DoclingDocument, skipped: set[str]) -> list[tuple[str, str]]:
    """The pairs of blocks a page or column break cut one sentence between.

    The converter ends a block where a page or a column does, mid-sentence,
    and opens the next as a paragraph of its own. Read off the punctuation
    and the case, which a page's layout does not set: a block that ends on
    no sentence mark and a next one that opens in lower case are one
    sentence. A script without case opens nothing in lower case, so it is
    never joined.
    """
    texts = [
        item
        for item, _ in document.iterate_items()
        if isinstance(item, TextItem)
        and item.content_layer == ContentLayer.BODY
        and item.self_ref not in skipped
        and item.prov
        and item.text.strip()
    ]
    return [
        (first.self_ref, second.self_ref)
        for first, second in pairwise(texts)
        if first.label in _PROSE | {DocItemLabel.LIST_ITEM}
        and second.label in _PROSE
        and not first.text.rstrip().endswith(_ENDS)
        and second.text.lstrip()[0].islower()
        and _broken(first.prov[-1], second.prov[0])
    ]


def _broken(before: ProvenanceItem, after: ProvenanceItem) -> bool:
    """Whether a page or a column break lies between two blocks."""
    if after.page_no != before.page_no:
        return after.page_no == before.page_no + 1
    return after.bbox.l >= before.bbox.r


def _repeats(text: str, running: frozenset[tuple[str, ...]]) -> bool:
    """Reports whether a paragraph starts with a running head or foot.

    Field for field, so a sentence that merely begins with the title is
    not one.
    """
    keys = tuple(_key(one) for one in fields(text) if _lettered(one))
    return any(keys[: len(run)] == run for run in running)


def _chapter_starts(
    document: DoclingDocument, furniture: Furniture, skipped: set[str]
) -> list[tuple[str, tuple[str, ...]]]:
    """The top-level block each chapter opens on, with the chapter's label."""
    if not furniture.labels:
        return []
    found = []
    current: tuple[str, ...] = ()
    for child in document.body.children:
        node = child.resolve(document)
        if node.content_layer != ContentLayer.BODY or node.self_ref in skipped:
            continue
        page = _first_page(node, document)
        if page is None:
            continue
        label = furniture.chapter(page)
        if label and label != current:
            found.append((node.self_ref, label))
        current = label
    return found


def _first_page(node: NodeItem, document: DoclingDocument) -> int | None:
    """The page a block starts on, read off its first item that has one."""
    for item, _ in document.iterate_items(root=node):
        if isinstance(item, DocItem) and item.prov:
            return item.prov[0].page_no
    return None


def headed(
    chunks: list[DocChunk],
    furniture: Furniture,
    titles: dict[str, tuple[str, ...]],
    language: str | None,
) -> list[DocChunk]:
    """Writes each chunk's heading trail as its passage will carry it.

    The chapter label of the chunk's first page leads, as its fields, unless
    the trail already starts with them; the title `tidied` put in is
    replaced by it. A segment that is
    a lone conjunction or holds no word at all is dropped.

    Args:
        chunks: What the chunker cut from the tidied document.
        furniture: What the document's running heads and feet say.
        titles: The titles `tidied` put in, with their labels.
        language: The document's language, whose `_CONJUNCTIONS` tell a
            lone conjunction; one missing from them is read for punctuation
            only.

    Returns:
        The chunks, each with its heading trail rewritten.
    """
    junk = _junk(language)
    written = []
    for chunk in chunks:
        trail = list(chunk.meta.headings or [])
        marked = titles.get(trail[0]) if trail else None
        if marked is not None:
            trail = trail[1:]
        # The page decides: a title of the document's own may have taken the
        # chapter's place, and a page in no chapter keeps the trail it had.
        page = _page_of(chunk)
        label = furniture.chapter(page) if page is not None else marked or ()
        if label:
            named = {_key(one) for one in label}
            while trail and _key(trail[0]) in named:
                trail = trail[1:]
            trail = [*label, *trail]
        trail = [segment for segment in trail if not junk(segment)]
        if trail != (chunk.meta.headings or []):
            chunk = chunk.model_copy(
                update={
                    "meta": chunk.meta.model_copy(update={"headings": trail or None})
                }
            )
        written.append(chunk)
    return written


def _page_of(chunk: DocChunk) -> int | None:
    """The page a chunk starts on."""
    return next(
        (item.prov[0].page_no for item in chunk.meta.doc_items if item.prov), None
    )


def _junk(language: str | None) -> Callable[[str], bool]:
    """Tells a heading segment that names nothing, in one language.

    A segment holding no letter or digit is an ellipsis or a stray mark. A
    segment that is only one of the language's `_CONJUNCTIONS` is the layout
    reading the word between two alternatives as a heading of its own; not
    when it is written in capitals, as a manual heads its section on the OR
    gate. Read off a table rather than a tagger: a word alone gives a tagger
    no context, and it tags a heading `When` a conjunction too. A language
    missing from the table is read for the first only.
    """
    conjunctions = _CONJUNCTIONS.get(language or "", frozenset())

    def junk(segment: str) -> bool:
        if not any(character.isalnum() for character in segment):
            return True
        return not segment.isupper() and _plain(segment) in conjunctions

    return junk
