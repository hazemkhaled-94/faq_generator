"""Mending a word a converter broke across two lines.

Shared by parsing, which mends every string it reads, and by the table and
page joins after it, which make new strings of two: the halves of a word
broken at a cell's wrap or at a page's foot meet only once those are joined.
The text checks of what a quote holds are here too, shared by the stages.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
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


#: Marks two readers print differently, folded before a quote is looked for.
_FOLDED = str.maketrans(
    {"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"', "–": "-", "—": "-"}
)


def _plain(text: str) -> str:
    """Text as a quote is compared: folded marks, single spaces, no case."""
    return " ".join(text.translate(_FOLDED).casefold().split())


#: A list item's marker at the start of a line: a dash or a bullet, or a
#: number or a letter closed by a full stop or a bracket.
_MARKER = re.compile(r"^\s*(?:[-–—•*·▪●◦]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s+")

#: Where a quote stitched from lines, cells, sentences or passages joins two
#: runs: a line break, an ellipsis, a cell bar, the [n] a passage was shown
#: under, a bullet inside a line, and a sentence's or a clause's end.
_JOINS = re.compile(r"\n+|…|\||\[\d{1,3}\]|\s[•▪●◦·]\s|(?<=[.!?;:])\s+")

#: What a piece is trimmed of at either end, once its marks are folded.
_EDGES = " -,;:.!?\"'()"

#: Words a piece needs to be evidence wherever it sits. A shorter one, a
#: heading's `Refunds:` or a cell's `Impact`, is in any number of passages,
#: so it counts only in a passage the longest piece is in.
_ALONE = 3


def _pieces(quote: str) -> list[str]:
    """A quote's runs, each as `_plain` reads it, without its list marker."""
    runs = (_MARKER.sub("", run) for run in _JOINS.split(quote.replace("...", "…")))
    return [piece for run in runs if (piece := _plain(run).strip(_EDGES))]


def _readings(passage: str) -> tuple[str, str]:
    """A passage as it reads, and with its list markers and cell bars folded out."""
    folded = " ".join(_MARKER.sub("", line) for line in passage.split("\n"))
    return _plain(passage), _plain(folded.replace("|", " "))


def _within(piece: str, text: str) -> bool:
    """Whether a text holds a piece as whole words, never inside a longer one."""
    start = r"(?<!\w)" if re.match(r"\w", piece) else ""
    end = r"(?!\w)" if re.match(r"\w", piece[-1]) else ""
    return re.search(start + re.escape(piece) + end, text) is not None


def held(quote: str, passages: Sequence[str]) -> bool:
    """Whether every piece of a quote is one unbroken run of one passage.

    A reply quoting two items of a list, two cells of a row or two passages
    stitches runs no passage carries unbroken, and the answer it settles a
    question with is still in what was shown.
    """
    pieces = _pieces(quote)
    readings = [_readings(passage) for passage in passages]
    where = [
        {
            n
            for n, both in enumerate(readings)
            if any(_within(piece, one) for one in both)
        }
        for piece in pieces
    ]
    if not pieces or not all(where):
        return False
    longest = where[max(range(len(pieces)), key=lambda n: len(pieces[n]))]
    return all(
        len(piece.split()) >= _ALONE or found & longest
        for piece, found in zip(pieces, where, strict=True)
    )


def holders(quote: str, passages: Sequence[str]) -> frozenset[int]:
    """The indices of the passages that hold the whole quote on their own."""
    return frozenset(
        at for at, passage in enumerate(passages) if held(quote, [passage])
    )
