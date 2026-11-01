"""An image carries no weights: they come from the cache a path names, offline.

The weights live in the `models` volume at HF_HOME (an Azure Files share on
Azure), never in the image and never fetched at run time. Loading an encoder
from a scratch, empty cache with the Hub off must fail at once and name what is
missing, which is what a platform operator needs; `api.doctor` says the same
beforehand, tested in `tests/unit/api/test_doctor_cache.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.nlp

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "intfloat/multilingual-e5-large"


def test_an_encoder_loaded_offline_from_an_empty_cache_fails_naming_the_repository(
    tmp_path,
) -> None:
    """No download is attempted, and the failure is quick."""
    scratch = tmp_path / "hf"
    scratch.mkdir()
    code = f"from nlp.embedding import Embedder; Embedder({REPOSITORY!r}, 512)"
    started = time.monotonic()
    ran = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "PYTHONPATH": f"{ROOT}/backend:{ROOT}",
            "HF_HOME": str(scratch),
            "HF_HUB_OFFLINE": "1",
            "EMBEDDING_MODEL_REVISION": "0" * 40,
        },
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )

    assert ran.returncode != 0
    assert "multilingual-e5-large" in ran.stderr, ran.stderr[-600:]
    assert not list(scratch.rglob("*.safetensors")), "something was fetched"
    assert time.monotonic() - started < 120
