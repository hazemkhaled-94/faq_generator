"""What the frontend's static Streamlit configuration lets in."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_accepts_only_loopback_hosts() -> None:
    """An empty allow-list is Streamlit's way of saying any Host at all.

    Which lets a page on another site rebind its own name to 127.0.0.1 and
    open the app's WebSocket from the operator's browser. The port is
    published on the loopback and read at localhost, so those two names are
    all it is ever reached by.
    """
    config = tomllib.loads((ROOT / "frontend/.streamlit/config.toml").read_text())
    hosts = config["server"].get("allowedHosts", [])

    assert hosts, "server.allowedHosts is empty, which Streamlit reads as any host"
    assert set(hosts) <= {"localhost", "127.0.0.1"}, hosts
