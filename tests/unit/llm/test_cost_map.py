"""litellm reads its price list from the installed package, never from the network.

LITELLM_LOCAL_MODEL_COST_MAP=true is committed in backend.env: litellm
otherwise fetches a list from GitHub when it is imported, so the price a call
is counted at, and which models it knows do not reason, would change with a
list nobody reviewed and fail to load where there is no network. The decision
the client takes from it must be the same one without the network.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PROBE = """
import socket
attempts = []
def refuse(*args, **kwargs):
    attempts.append(1)
    raise OSError("network blocked")
socket.socket.connect = refuse
socket.create_connection = refuse
import llm.config as config
print(config._cannot_reason("azure/gpt-4.1"), config._cannot_reason("azure/gpt-5.6-sol"), len(attempts))
"""


def test_backend_env_commits_the_local_cost_map() -> None:
    """Read by litellm at import, in the host and in every container."""
    live = dict(
        re.findall(
            r"^([A-Z][A-Z0-9_]*)=(.*)$",
            (ROOT / "configs/env/backend.env").read_text(),
            re.MULTILINE,
        )
    )

    assert live["LITELLM_LOCAL_MODEL_COST_MAP"] == "true"


def test_the_client_decides_the_same_with_the_network_blocked() -> None:
    """A model that does not reason is sent no effort; one that does is, and nothing is fetched."""
    committed = re.search(
        r"^LITELLM_LOCAL_MODEL_COST_MAP=(.*)$",
        (ROOT / "configs/env/backend.env").read_text(),
        re.MULTILINE,
    )
    ran = subprocess.run(
        [sys.executable, "-c", PROBE],
        env={
            **os.environ,
            # What a worker has after sourcing backend.env.
            "LITELLM_LOCAL_MODEL_COST_MAP": committed.group(1) if committed else "",
            "PYTHONPATH": str(ROOT / "backend"),
            "LITELLM_MODE": "PRODUCTION",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert ran.returncode == 0, ran.stderr[-600:]
    assert ran.stdout.split()[-3:] == ["True", "False", "0"], ran.stdout
