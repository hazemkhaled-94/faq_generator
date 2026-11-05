"""A 429 whose Retry-After is not a number of seconds backs off.

A provider may send an HTTP-date, or no Retry-After at all. Neither is a
wait to honour, and neither may stop the call: it backs off and asks again.
"""

from __future__ import annotations

import httpx
import litellm
import pytest
from pydantic import BaseModel

from llm.client import Client
from llm.config import Settings


class Shape(BaseModel):
    """The shape a caller asks for."""

    value: str = "answered"


def settings() -> Settings:
    """Settings for a model nothing actually calls."""
    return Settings(
        model="ollama/test-model",
        base_url=None,
        structured_mode="JSON_SCHEMA",
        temperature=0.0,
        timeout_seconds=1.0,
        max_attempts=2,
        num_ctx=None,
        reasoning_effort=None,
    )


@pytest.mark.parametrize(
    "headers", [{"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, {}]
)
def test_a_retry_after_that_is_a_date_or_absent_backs_off(monkeypatch, headers) -> None:
    """One short backoff, then the answer."""
    waited: list[float] = []
    attempts: list[str] = []

    def limited(self, system, user, shape):
        attempts.append(user)
        if len(attempts) == 1:
            raise litellm.exceptions.RateLimitError(
                message="slow down",
                llm_provider="azure",
                model="test-model",
                response=httpx.Response(
                    429,
                    headers=headers,
                    request=httpx.Request("POST", "https://provider.invalid"),
                ),
            )
        return shape(), None

    monkeypatch.setattr(Client, "_ask", limited)
    monkeypatch.setattr("tenacity.nap.time.sleep", waited.append)

    answer = Client(settings()).answer(system="s", user="u", shape=Shape)

    assert answer.value == "answered"
    assert len(waited) == 1
    assert 0 < waited[0] <= 10
