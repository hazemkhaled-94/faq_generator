"""What opens a line of a list, in any script.

Pattern text for the readers of lists to build on, kept apart from `text` and
`analysis` because the api reads a passage's list items and must not load a
pipeline to do it.
"""

from __future__ import annotations

#: A dash or a bullet.
BULLET = r"[-–—•*+·▪●◦]"

#: A number, a letter or a roman numeral, in brackets or not, closed by a full
#: stop or a bracket: `3.`, `a)`, `α)`, `(ii)`.
ENUMERATION = r"\(?(?:\d{1,3}|[^\W\d_]|[ivxIVX]{1,4})[.)]"

#: Either, as the mark a list line opens with.
LIST_MARKER = rf"(?:{BULLET}|{ENUMERATION})"
