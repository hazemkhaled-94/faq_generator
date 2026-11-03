"""The container probe in tests/conftest.py must not leak the docker client's socket.

`docker.from_env().ping()` was never closed. With no container runtime the
socket was dropped open, CPython warned from `socket.__del__`, and the
`filterwarnings = error` setting turned the warning into a failure of whichever
unrelated test was running when the collector reached it.
"""

from __future__ import annotations

import gc
import warnings

from tests.conftest import _runtime_ready


def test_the_probe_closes_its_client(monkeypatch) -> None:
    """No ResourceWarning follows the probe when there is no runtime to reach."""
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/container.sock")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        refused = _runtime_ready()
        for _ in range(3):
            gc.collect()

    leaked = [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)]
    assert not leaked, (refused, leaked)
