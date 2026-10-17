"""Mending a word a converter broke across two lines.

Shared by parsing, which mends every string it reads, and by the table and
page joins after it, which make new strings of two: the halves of a word
broken at a cell's wrap or at a page's foot meet only once those are joined.
"""

from __future__ import annotations

import re
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


def rejoined(text: str) -> str:
    """The text with every word broken at a line hyphen made whole again.

    Mending a string already mended changes nothing, so a join may mend the
    whole of what it made.
    """
    return _broken_word().sub("", text)
