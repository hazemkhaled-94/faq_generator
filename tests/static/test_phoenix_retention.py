"""Phoenix keeps customer text only as long as a policy says, set at `make up`."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_make_up_sets_the_retention_policy() -> None:
    """After the stack is up, and ignoring a failure so the stack still starts."""
    makefile = (ROOT / "Makefile").read_text()
    up = re.search(r"^up:.*?(?=^\S)", makefile, re.MULTILINE | re.DOTALL)

    assert up is not None
    assert "phoenix-retention" in up.group(0)
    assert re.search(
        r"^phoenix-retention:\n\t.*telemetry\.projects --retention",
        makefile,
        re.MULTILINE,
    )


def test_the_retention_is_a_deployment_value_with_a_reason() -> None:
    """Named in deployment.env, beside its reason: data retention for customer text."""
    env = (ROOT / "configs/env/deployment.env").read_text()

    assert re.search(r"^PHOENIX_TRACE_RETENTION_DAYS=\d+$", env, re.MULTILINE)
    assert "retention" in env.lower()
