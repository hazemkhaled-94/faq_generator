"""What this process has spent on model calls.

Kept apart from `llm.client` because that loads litellm, and a drain's loop
reads this between rows in processes that must not: it is the figure
`SPEND_CAP` is held to, counted in process rather than parsed back out of the
logs, which carry the same numbers per call for people.
"""

from __future__ import annotations

import atexit
import threading
from pathlib import Path

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


def carry(ledger: str | None) -> None:
    """Counts what earlier processes of this run spent, and adds this one's at exit.

    The tally is per process and a corpus run is one process per drain, so a
    cap one drain met would start again at zero in the next. SPEND_LEDGER
    names a file of one amount per line: this process starts at their sum, and
    appends what it spent itself when it exits. None is the development path
    and carries nothing.

    Raises:
        ValueError: If the ledger holds something that is not a number, since
            a cap nobody can count against is no cap.
    """
    if not ledger:
        return
    path = Path(ledger)
    try:
        carried = sum(float(line) for line in path.read_text().split())
    except FileNotFoundError:
        carried = 0.0
    except ValueError:
        raise ValueError(
            f"SPEND_LEDGER {ledger} holds something that is not an amount; "
            "delete it to start the run's count again"
        ) from None
    add(carried)
    atexit.register(_append, path, carried)


def _append(path: Path, carried: float) -> None:
    """Writes what this process spent beyond what it carried, if anything."""
    spent = spent_usd() - carried
    if spent > 0:
        with path.open("a") as ledger:
            ledger.write(f"{spent:.6f}\n")
