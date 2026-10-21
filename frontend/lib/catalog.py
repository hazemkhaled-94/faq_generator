"""The search, the filters and the pager, in one panel.

The search box comes first and widest, the pager last. The pager's slot is
filled after the rows are fetched, once their total is known.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from lib import config, page

#: Width of each control, in the units a row is measured in.
_WORDS, _COLUMN, _FILTER, _PAGER = 3, 3, 2, 1.5

#: Width of one row of controls.
_ROW = 13.5


def label_for(document: dict) -> str:
    """Names a document the way a person would recognise it."""
    return document.get("filename") or f"{document['sha256'][:12]}…"


def find(
    key: str,
    fields: dict[str, str],
    choices: dict[str, tuple[str, Sequence[str], str]],
    documents: list[dict] | None = None,
) -> tuple[str, str, dict[str, str | None], DeltaGenerator]:
    """Draws the search and the filters, and reserves the pager's slot.

    `fields` maps the heading a column carries in the table to the name the
    route takes for it; the column picker is drawn only when there are two
    or more.

    `choices` maps the name the route takes to the heading, the values and
    the tooltip. Each returns the chosen value, or None for the `All` entry
    every picker carries first.

    The document picker is drawn even when the corpus is empty, disabled
    rather than absent.

    Returns:
        The words, the column they are looked in, the chosen filter values,
        and the slot `paged` draws the pager into.
    """
    slots = _slots(choices, documents)
    widths = [
        _WORDS,
        *([_COLUMN] if len(fields) > 1 else []),
        *[_FILTER] * len(slots),
        _PAGER,
    ]

    chosen: dict[str, str | None] = {}
    with page.panel("Search and filters"):
        cells = iter(_laid_out(widths))
        typed = next(cells).text_input(
            "Words",
            key=f"{key}-search",
            # Past it every listing route refuses the whole page with a 422.
            max_chars=config.SEARCH_MAX,
            placeholder="Contains…",
            help="A case-insensitive substring. Not a word search.",
        )
        heading = (
            next(cells).selectbox(
                "In column",
                list(fields),
                key=f"{key}-field",
                help="Where the words are looked for.",
            )
            if len(fields) > 1
            else next(iter(fields))
        )
        for name, label, options, named, explanation in slots:
            picked = next(cells).selectbox(
                label,
                options,
                key=f"{key}-{name}",
                disabled=len(options) == 1,
                help=explanation,
            )
            chosen[name] = (
                named.get(picked)
                if named is not None
                else picked
                if picked in options[1:]
                else None
            )
        pager = next(cells)

    # A new search starts on the first page: the one somebody was on is a
    # position among the old matches. Dropped rather than set to 1, which
    # Streamlit warns about on a widget drawn with a default.
    held = (typed, heading, tuple(chosen.items()))
    if st.session_state.get(f"{key}-filter", held) != held:
        st.session_state.pop(f"{key}-page", None)
    st.session_state[f"{key}-filter"] = held
    return typed, fields[heading], chosen, pager


def _slots(
    choices: dict[str, tuple[str, Sequence[str], str]],
    documents: list[dict] | None,
) -> list[tuple[str, str, list[str], dict | None, str]]:
    """Lists every picker: the document first, where there is one."""
    slots: list[tuple[str, str, list[str], dict | None, str]] = []
    if documents is not None:
        named = {
            f"{label_for(one)} ({one['sha256'][:8]})": one["sha256"]
            for one in documents
        }
        slots.append(
            ("document", "Document", ["All documents", *named], named, "One document.")
        )
    slots += [
        (name, heading, [f"All {heading.lower()}", *values], None, explanation)
        for name, (heading, values, explanation) in choices.items()
    ]
    return slots


def wrapped(widths: Sequence[float]) -> list[list[float]]:
    """Packs controls of these widths into rows, in order, none wider than one."""
    packed: list[list[float]] = [[]]
    for width in widths:
        if packed[-1] and sum(packed[-1]) + width > _ROW:
            packed.append([])
        packed[-1].append(width)
    return packed


def _laid_out(widths: Sequence[float]) -> list[DeltaGenerator]:
    """Draws one cell per control, each row padded out to the full width."""
    cells: list[DeltaGenerator] = []
    for row in wrapped(widths):
        spare = _ROW - sum(row)
        cells += st.columns([*row, spare] if spare else row)[: len(row)]
    return cells


def paged(
    key: str,
    into: DeltaGenerator,
    fetch: Callable[[int, int], dict[str, Any]],
    rows_key: str,
) -> tuple[int, list[Any]]:
    """Fetches one page, draws the pager into its slot, and returns both.

    The page number is read from session state rather than from the widget,
    which is drawn afterwards: asking the backend for the total first cost a
    second request, and its own count query, on every rerun.
    """
    size = config.PAGE_SIZE
    slot = f"{key}-page"
    number = int(st.session_state.get(slot, 1))

    answer = fetch(size, (number - 1) * size)
    total, rows = answer["total"], answer[rows_key]
    if not rows and total and number > 1:
        # The corpus shrank under a page somebody was already on.
        st.session_state[slot] = 1
        answer = fetch(size, 0)
        total, rows = answer["total"], answer[rows_key]

    pages = max(1, math.ceil(total / size))
    if int(st.session_state.get(slot, 1)) > pages:
        st.session_state[slot] = 1
    into.number_input(
        f"Page of {pages:,}",
        min_value=1,
        max_value=pages,
        value=1,
        step=1,
        key=slot,
        disabled=pages == 1,
        help="Which page of the rows that matched.",
    )
    return total, rows
