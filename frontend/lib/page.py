"""Shared layout for the view scripts.

Views are functions rather than classes: Streamlit re-runs the whole script
on every interaction, so nothing persists between calls except the HTTP
session, which lib.backend caches.

Every page is the same sequence of panels, top to bottom: the figures worth
seeing on arrival, the one service this page runs with its folds beside each
other, search and filters, the table of everything, and the row a person
picked. A view that follows that order needs no layout of its own.

A panel is what separates one section from the next, and `panel` is the only
way to draw one.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import streamlit as st

log = logging.getLogger(__name__)

#: What each queue status means, in one line. The same words appear on five
#: pages and on the system status panel.
STATUS_HELP = {
    "new": "Stored, never asked for.",
    "pending": "Queued, waiting for a worker.",
    "in_progress": "Held by a worker now.",
    "failed": "The worker could not finish it.",
    "parsed": "Converted into a structured document.",
    "chunked": "Split into passages.",
    "extracted": "Read for facts.",
    "modelled": "Fitted into the stored topic model.",
    "generated": "Questions have been written for it.",
    "assessed": "An LLM judge has answered about it.",
}


#: Left by an action, so the next table is drawn with nothing picked.
_ACTED = "page-acted"

#: Every ASCII punctuation mark, each of which Markdown draws as itself once
#: a backslash is put before it.
_MARKUP = re.compile(r"([!-/:-@\[-`{-~])")


def plain(text: str) -> str:
    """Stored text as Markdown that draws it as written.

    For a filename or an artefact's own text put into a Markdown renderer
    (a message, a spinner, a `st.table` cell), where `$4.99 ... $20` would
    read as math and `*Entwurf*` as italics.
    """
    return _MARKUP.sub(r"\\\1", text)


def share(part: int, whole: int) -> str:
    """Renders a count as itself and its share of a whole, in one string."""
    if not whole:
        return f"{part:,}"
    return f"{part:,} ({part / whole:.0%})"


def header(title: str) -> None:
    """Renders the page's title, with the product's name on the same line."""
    st.html(
        f"<div class='qa-header'><div class='qa-page-title'>"
        f"{html.escape(title, quote=False)}</div>"
        "<div class='qa-brand-title'>FAQ Generator</div></div>"
    )


@contextmanager
def panel(title: str) -> Iterator[None]:
    """Opens one bordered section, labelled.

    The label is drawn inside the border rather than above it, so a section
    and its heading cannot drift apart.
    """
    with st.container(border=True):
        # Escaped: a document's panel is headed by its filename.
        st.html(f"<div class='qa-panel-label'>{html.escape(title, quote=False)}</div>")
        yield


@contextmanager
def folds() -> Iterator[None]:
    """Opens one row for a service's folds, stacked once one is opened."""
    with st.container(horizontal=True, key="folds"):
        yield


def stats(values: Mapping[str, tuple[str, str]]) -> None:
    """Renders one row of figures, each with the line that says what it is.

    Keyed by label, valued by `(figure, what it counts)`, so a caller cannot
    add a figure without saying what it is.
    """
    for column, (label, (value, explanation)) in zip(
        st.columns(len(values)), values.items(), strict=True
    ):
        column.metric(label, value, help=explanation)


def attributes(rows: Mapping[str, Any]) -> None:
    """Renders everything held about one item, as a two-column table."""
    st.dataframe(
        {"Field": list(rows), "Value": [written(one) for one in rows.values()]},
        width="stretch",
        hide_index=True,
        column_config={
            "Field": st.column_config.TextColumn(width="small"),
            "Value": st.column_config.TextColumn(width="large"),
        },
    )


def written(value: Any) -> str:
    """Renders one value the way a table cell should read it.

    Everything becomes a string: a column mixing a number with a dash is not
    a column a table can draw, and `None` should read as an em dash rather
    than as the word None.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(one) for one in value) or "—"
    return str(value)


def acted() -> None:
    """Unpicks the table's row on the next run, as an action moved the rows."""
    st.session_state[_ACTED] = True


def table(
    rows: list[dict],
    key: str,
    column_config: dict | None = None,
    ids: list | None = None,
) -> int | None:
    """Draws the page's table and returns which row was picked, if any.

    Nothing below the table is drawn until a row is chosen, so this returns
    None on arrival and a position into `rows` afterwards.

    Streamlit hands the selection back as a position and keeps it under the
    table's key whatever rows the next run draws. So the pick is also
    remembered by the id of the row (`ids`, one per row; the position when
    not given): a page, filter or search change that no longer shows that row
    drops the pick, and a row that moved under it takes the pick along.
    After `acted` the pick is cleared as well.
    """
    ids = list(range(len(rows))) if ids is None else ids
    remembered = f"{key}-picked"
    if st.session_state.pop(_ACTED, False):
        st.session_state[key] = {"selection": {"rows": []}}
    chosen = (st.session_state.get(key) or {}).get("selection", {}).get("rows", [])
    held = st.session_state.get(remembered)
    if not chosen:
        st.session_state.pop(remembered, None)
    else:
        position = chosen[0]
        if held is not None and held[0] == position:
            # The same pick as the last run: follow its row, if it is still here.
            position = ids.index(held[1]) if held[1] in ids else None
            if position is None:
                st.caption("That row changed meanwhile.")
        elif position >= len(rows):
            position = None
        if position is None:
            st.session_state.pop(remembered, None)
        else:
            st.session_state[remembered] = (position, ids[position])
        if position != chosen[0]:
            st.session_state[key] = {
                "selection": {"rows": [] if position is None else [position]}
            }
    picked = st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config=column_config,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    chosen = picked["selection"]["rows"]
    return chosen[0] if chosen and chosen[0] < len(rows) else None


def queue_rows(
    unit: str, counts: Mapping[str, int], states: tuple[str, ...]
) -> list[dict[str, str]]:
    """Builds the findings rows describing one stage's queue.

    The same five columns every other check in the fold carries, so one
    table can hold the queue and the quality checks together. Only `failed`
    has a verdict: the rest are where work is, not whether it went well.
    """
    total = sum(counts.values())
    return [
        {
            "Check": f"{unit} {state.replace('_', ' ')}",
            "Value": share(counts.get(state, 0), total),
            "Should be": "0" if state == "failed" else "—",
            "State": ("Attention" if counts.get(state) else "OK")
            if state == "failed"
            else "—",
            "What it means": STATUS_HELP[state],
        }
        for state in states
    ]


def findings(rows: list[dict[str, str]]) -> None:
    """Renders what a stage's own numbers say about themselves, as a table.

    Every check is listed, the ones that passed included: a check missing
    from a list is indistinguishable from a check nobody wrote.
    """
    if not rows:
        return
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "Check": st.column_config.TextColumn(width="medium"),
            "What it means": st.column_config.TextColumn(width="large"),
        },
    )


def render(view: Callable[[], None]) -> None:
    """Runs one page, reporting a failure as a message not a traceback."""
    try:
        view()
    except Exception as exc:
        log.exception("page failed")
        st.error(f"Failed to load: {exc}")
