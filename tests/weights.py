"""What a test does when the weights it needs are not cached.

On a laptop it skips: the weights are gigabytes and a contributor may not
have them. In the nightly job that exists to run those tests, a skip is the
failure it was built to catch, so `REQUIRE_MODELS=1` turns it into one.
"""

from __future__ import annotations

import os
from typing import NoReturn

import pytest


def unavailable(reason: str) -> NoReturn:
    """Skips the test, or fails it where `REQUIRE_MODELS=1` says the weights must be there."""
    if os.environ.get("REQUIRE_MODELS") == "1":
        pytest.fail(f"REQUIRE_MODELS=1 and {reason}", pytrace=False)
    pytest.skip(reason)


#: The files a load reads the weights from, one or the other.
WEIGHTS = ("model.safetensors", "pytorch_model.bin")


def cached(model: str, revision: str, cache_dir: str | None = None) -> bool:
    """Whether the Hugging Face cache holds the model's weights at `revision`.

    The weights, not config.json: the tokenizer caches that on its own, and a
    guard reading it downloads gigabytes instead of skipping. At the commit the
    loads pin, not at main: a fetch by commit, the nightly job's, writes no
    refs/main, so a guard asking for main finds nothing it fetched.
    """
    from huggingface_hub import try_to_load_from_cache

    return any(
        isinstance(
            try_to_load_from_cache(model, name, cache_dir=cache_dir, revision=revision),
            str,
        )
        for name in WEIGHTS
    )
