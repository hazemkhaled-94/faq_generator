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
from functools import cache
from itertools import pairwise

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import RefItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.node import DocItem, NodeItem
from docling_core.types.doc.items.text import TextItem
from docling_core.types.doc.labels import DocItemLabel

from nlp.pipelines import languages, pipeline

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

#: The most body words one running field is matched against when its
#: spacing is read off the body.
_RESPACE_WORDS = 8

#: The parts of speech of a conjunction, in spaCy's universal tag set.
_CONJUNCTIONS = frozenset({"CCONJ", "SCONJ"})


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
    document: DoclingDocument, furniture: Furniture
) -> tuple[DoclingDocument, dict[str, tuple[str, ...]]]:
    """Prepares a document for the chunker: debris out, a title at each chapter.

    A paragraph that starts with a running head or foot, field for field and
    with whitespace removed, is the converter reading furniture as body
    text. A paragraph of one letter, followed by entries under that letter,
    is a glossary's index divider, where the document holds two or more in
    ascending order. Both move to the furniture layer. Before
    the first block of each chapter goes a title naming it, which empties
    the heading trail the chunker would otherwise carry over from the
    chapter before.

    Args:
        document: The converted document, which is not modified.
        furniture: What its running heads and feet say.

    Returns:
        The document to cut, a copy when anything changed and `document`
        itself when nothing did; and every title put in, by its text, with
        the chapter label it stands for.
    """
    debris = _dividers(document) | {
        item.self_ref
        for item in document.texts
        if item.content_layer == ContentLayer.BODY
        and item.label in _PROSE
        and _repeats(item.text, furniture.running)
    }
    starts = _chapter_starts(document, furniture, debris)
    if not debris and not starts:
        return document, {}

    tidy = document.model_copy(deep=True)
    for reference in debris:
        _resolved(reference, tidy).content_layer = ContentLayer.FURNITURE
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
    """The paragraphs that are a glossary's index letters.

    One letter, and the next text in the body starts with it, in either
    case. A lone letter followed by anything else is content: an energy
    class, a part marker. And an index has two letters or more, each after
    the one before as its character code is, so a document whose letters are
    one, or come back or run backwards, is giving values - a class "A" over
    a line that happens to start with an A - and none is dropped.
    """
    texts = [
        item
        for item, _ in document.iterate_items()
        if isinstance(item, TextItem) and item.text.strip()
    ]
    found = [
        (item.self_ref, letter.casefold())
        for item, following in pairwise(texts)
        if item.label in _PROSE
        and len(letter := item.text.strip()) == 1
        and letter.isalpha()
        and following.text.strip()[0].casefold() == letter.casefold()
    ]
    letters = [letter for _, letter in found]
    if len(found) < 2 or any(a >= b for a, b in pairwise(letters)):
        return set()
    return {reference for reference, _ in found}


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
        language: The document's language, whose pipeline tells a
            conjunction; one with no pipeline is read for punctuation only.

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
    segment that is one token, a stop word tagged as a conjunction, is the
    layout reading the word between two headings as a heading of its own;
    not when it is written in capitals, as a manual heads its section on the
    OR gate. The second needs the language's pipeline; without one, only the
    first is read.
    """
    readable = language is not None and language in languages()

    @cache
    def junk(segment: str) -> bool:
        if not any(character.isalnum() for character in segment):
            return True
        if not readable or segment.isupper():
            return False
        tokens = pipeline(language)(segment)
        return (
            len(tokens) == 1 and tokens[0].is_stop and tokens[0].pos_ in _CONJUNCTIONS
        )

    return junk
