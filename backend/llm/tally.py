"""What this process has spent on model calls.

Kept apart from `llm.client` because that loads litellm, and a drain's loop
reads this between rows in processes that must not: it is the figure
`SPEND_CAP` is held to, counted in process rather than parsed back out of the
logs, which carry the same numbers per call for people.
"""

from __future__ import annotations

import threading

_spent = {"usd": 0.0}
_unpriced: set[str] = set()
_lock = threading.Lock()


def spent_usd() -> float:
    """What every call this process has made has cost, as litellm priced it."""
    with _lock:
        return _spent["usd"]


def add(usd: float) -> None:
    """Counts what one answer cost."""
    with _lock:
        _spent["usd"] += usd


def unpriced_models() -> frozenset[str]:
    """The models this process called that litellm has no price for."""
    with _lock:
        return frozenset(_unpriced)


def note_unpriced(model: str) -> bool:
    """Records a model litellm could not price; True the first time it is."""
    with _lock:
        first = model not in _unpriced
        _unpriced.add(model)
    return first
