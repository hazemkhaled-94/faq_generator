"""What names a configuration, and what it leaves out."""

from __future__ import annotations

import pytest

from settings import catalog
from settings.store import version

#: A setting that stales a stage, and one the deployment owns that stales none.
STALING = "EXTRACTION_DIGEST_MIN_CHARS"
PLATFORM = ("SPEND_CAP", "WORKER_POLL_SECONDS", "DATABASE_POOL_SIZE", "LLM_MODEL")


@pytest.mark.parametrize("name", PLATFORM)
def test_a_fixed_platform_setting_that_stales_nothing_is_not_in_the_version(
    name: str,
) -> None:
    """Moving it must not make every stored row read as made under another one."""
    setting = catalog.BY_NAME[name]
    assert setting.fixed and setting.service == "platform" and not setting.invalidates

    assert version({name: "1"}) == version({name: "9"}) == version({})


@pytest.mark.parametrize(
    "name", [STALING, "TOPIC_PASSES", "NLP_MODELS", "EXTRACTION_MODEL"]
)
def test_a_setting_that_changes_what_a_stage_writes_is_in_the_version(
    name: str,
) -> None:
    """A stage's own, a fixed one that stales stages, and a model of its own."""
    assert version({name: "1"}) != version({name: "9"})
