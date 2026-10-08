"""Which settings a change may name."""

from __future__ import annotations

import pytest

from settings import changes


class Untouched:
    """A store holding no override."""

    def resolved(self) -> dict[str, str]:
        """No stored value."""
        return {}

    def version(self) -> str:
        """The version of an empty store."""
        return "environment"


@pytest.mark.parametrize("name", ["LLM_BASE_URL", "OLLAMA_BASE_URL"])
def test_a_change_naming_where_a_model_is_served_is_refused(name: str) -> None:
    """The address is the deployment's."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply("platform", {name: "http://elsewhere:11434"}, store=Untouched())

    assert refused.value.code == "fixed_setting"


def test_which_model_is_called_may_still_be_changed() -> None:
    """The name is the pipeline's."""
    assert changes.owned("platform", ["LLM_MODEL"])["LLM_MODEL"].fixed is False
