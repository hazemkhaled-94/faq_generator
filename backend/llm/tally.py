"""What this process has spent on model calls.

Kept apart from `llm.client` because that loads litellm, and a drain's loop
reads this between rows in processes that must not: it is the figure
`SPEND_CAP` is held to, counted in process rather than parsed back out of the
logs, which carry the same numbers per call for people.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

_spent = {"usd": 0.0}
_unpriced: set[str] = set()
_lock = threading.Lock()

#: The run's ledger, once `carry` has named one, which every priced call
#: rewrites with the run's total.
_ledger: dict[str, Path | None] = {"path": None}


def spent_usd() -> float:
    """What every call this process has made has cost, as litellm priced it."""
    with _lock:
        return _spent["usd"]


def add(usd: float) -> None:
    """Counts what one answer cost, and writes the run's total to its ledger.

    After every priced call rather than when the process exits, so a drain
    killed by SIGKILL, the OOM killer or a supervisor that outwaited its grace
    leaves what it spent counted for the run's next drain.
    """
    with _lock:
        _spent["usd"] += usd
        if usd and (path := _ledger["path"]) is not None:
            _write(path, _spent["usd"])


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
    """Counts what earlier processes of this run spent, and keeps the run's total.

    The tally is per process and a corpus run is one process per drain, so a
    cap one drain met would start again at zero in the next. SPEND_LEDGER
    names a file of amounts, one per line: this process starts at their sum,
    and `add` replaces the file with the run's total, this process's spend
    included, after every call it pays for. The drains of a run follow one
    another, so one process writes it at a time. None is the development path
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
    with _lock:
        _spent["usd"] += carried
        _ledger["path"] = path


def _write(path: Path, total: float) -> None:
    """Replaces the ledger with the run's total, whole or not at all.

    A file beside it renamed over it, so a kill mid-write leaves the last
    total rather than half a number the next drain refuses to read.
    """
    part = path.with_name(f"{path.name}.part")
    part.write_text(f"{total:.6f}\n")
    os.replace(part, path)
