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
