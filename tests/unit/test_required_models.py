"""A test that needs weights fails, rather than skips, where they must be there."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import weights
from _pytest.outcomes import Failed, Skipped

ROOT = Path(__file__).resolve().parents[2]


def test_the_helper_skips_by_default_and_fails_when_required(monkeypatch) -> None:
    """The one switch every skip on a missing weight goes through."""
    monkeypatch.delenv("REQUIRE_MODELS", raising=False)
    with pytest.raises(Skipped):
        weights.unavailable("the weights are not in the cache")

    monkeypatch.setenv("REQUIRE_MODELS", "1")
    with pytest.raises(Failed, match="REQUIRE_MODELS=1"):
        weights.unavailable("the weights are not in the cache")


@pytest.mark.parametrize(
    ("required", "outcome"),
    [("", "1 skipped"), ("1", "1 error")],
    ids=["a laptop", "the nightly job"],
)
def test_the_real_embedding_test_with_an_empty_cache(
    tmp_path: Path, required: str, outcome: str
) -> None:
    """No cache at all: a skip for a contributor, an error in the fixture for the job."""
    env = {
        **os.environ,
        "HF_HOME": str(tmp_path),
        "HF_HUB_OFFLINE": "1",
        "REQUIRE_MODELS": required,
    }
    ran = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/nlp/test_embedding.py",
            "-k",
            "embeds_at_the_width",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert outcome in ran.stdout, ran.stdout[-800:]
