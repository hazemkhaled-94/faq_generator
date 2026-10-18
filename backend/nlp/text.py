"""Mending a word a converter broke across two lines.

Shared by parsing, which mends every string it reads, and by the table and
page joins after it, which make new strings of two: the halves of a word
broken at a cell's wrap or at a page's foot meet only once those are joined.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import cache

from nlp.pipelines import languages

#: The words that complete a hanging hyphen, by ISO 639-1 code, as in "Zoll-
#: und Steuerrecht": the hyphen holds the place of a suffix the next word
#: shares, and the page broke nothing.
JOINING: dict[str, tuple[str, ...]] = {
    "de": (
        "und",
        "oder",
        "bzw",
        "sowie",
        "beziehungsweise",
        "als",
        "noch",
        "bis",
        "u",
        "resp",
        "vs",
        "versus",
        "statt",
        "wie",
    ),
    "en": ("and", "or", "nor", "to", "vs", "versus"),
}

#: A hyphen a word is printed with, between the letters either side of it:
#: "third-party", and each of "state-of-the-art".
_COMPOUND = re.compile(r"([^\W\d_]+)-(?=([^\W\d_]+))")

#: The letters a broken word's first half ends on, and its second starts on.
_FIRST_HALF = re.compile(r"[^\W\d_]+$")
_SECOND_HALF = re.compile(r"[^\W\d_]+")


@cache
def _broken_word() -> re.Pattern[str]:
    """A word the page broke across two lines with a real hyphen.

    A hyphen after a letter and before a lower-case continuation, unless a
    word in `JOINING` follows it. Read in every configured language at once,
    because a document is parsed before any of its passages has a language.

    ponytail: punctuation alone cannot separate a broken word from two
    ratings written side by side in one cell ("Mittel- niedrig"). Telling
    those apart needs a character language model or the geometry of the
    cells either side.
    """
    words = sorted({word for code in languages() for word in JOINING.get(code, ())})
    joined = rf"(?!(?:{'|'.join(words)})\b)" if words else ""
    return re.compile(
        rf"(?<=[A-Za-zÄÖÜäöüß])-\s+{joined}"
        r"(?=[a-zäöüß])"
    )


def printed(texts: Iterable[str]) -> frozenset[tuple[str, str]]:
    """The words a document prints whole around a hyphen, as their halves.

    Casefolded, so "Third-party" opening a sentence is "third-party".
    """
    return frozenset(
        (first.casefold(), second.casefold())
        for text in texts
        for first, second in _COMPOUND.findall(text)
    )


def rejoined(text: str, whole: frozenset[tuple[str, str]] = frozenset()) -> str:
    """The text with every word broken at a line hyphen made whole again.

    A word whose halves `whole` holds, one the document prints with its
    hyphen elsewhere, keeps it: "third- party" is "third-party" where the
    document prints that, and "thirdparty" only where it never does, since
    a broken word and a compound broken at its own hyphen look alike.
    Mending a string already mended changes nothing, so a join may mend the
    whole of what it made.

    Args:
        text: The string to mend.
        whole: What `printed` read off the document the string is from.
    """

    def mended(broken: re.Match[str]) -> str:
        first = _FIRST_HALF.search(text, 0, broken.start())
        second = _SECOND_HALF.match(text, broken.end())
        kept = (
            first is not None
            and second is not None
            and (first[0].casefold(), second[0].casefold()) in whole
        )
        return "-" if kept else ""

    return _broken_word().sub(mended, text)
