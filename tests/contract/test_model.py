"""What every model adapter does, run against each one there is.

`Client` is today's: litellm and instructor, here with `litellm.completion`
answering from a script. `tests.drivers.Model` is the scripted double every
stage test uses, and it has to keep the port's promises too, or those tests
pass against something no adapter is. An Azure OpenAI or Foundry adapter joins
by being added to `RIGS`.
"""

from __future__ import annotations

import litellm
import pytest
from drivers import Model as Scripted
from pydantic import BaseModel

from llm import client as module
from llm.client import ModelRefused, ModelUnavailable


class Shape(BaseModel):
    """The shape a caller asks for."""

    value: str = ""


class LitellmRig:
    """`Client` over a scripted `litellm.completion`."""

    def __init__(self, monkeypatch) -> None:
        """Binds the script to litellm."""
        self.monkeypatch = monkeypatch
        self.script: object = '{"value": ""}'
        monkeypatch.setattr(litellm, "completion", self._completion)

    def _completion(self, *args, **kwargs):
        if isinstance(self.script, Exception):
            raise self.script
        return litellm.ModelResponse(
            model="azure/gpt-4.1",
            choices=[
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": self.script},
                }
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def build(self):
        """The adapter, one attempt."""
        from llm.config import Settings

        return module.build_model(
            Settings(
                model="azure/test",
                base_url=None,
                structured_mode="JSON_SCHEMA",
                temperature=0.2,
                timeout_seconds=1.0,
                max_attempts=1,
                num_ctx=None,
                reasoning_effort=None,
            )
        )

    def answers(self, value: str) -> None:
        """The next answer is this value."""
        self.script = f'{{"value": "{value}"}}'

    def refuses(self) -> None:
        """The provider filters the prompt."""
        self.script = litellm.exceptions.ContentPolicyViolationError(
            message="filtered by the content policy",
            model="azure/test",
            llm_provider="azure",
        )

    def is_unreachable(self) -> None:
        """The provider does not answer."""
        self.script = litellm.exceptions.Timeout(
            message="too slow", llm_provider="azure", model="azure/test"
        )


class ScriptedRig:
    """`tests.drivers.Model`, scripted the way the stage tests do."""

    def __init__(self, monkeypatch) -> None:
        """Starts with an empty answer."""
        self.script: dict | BaseException = {}

    def build(self):
        """The double, reading what the rig holds when it is asked."""
        rig = self
        double = Scripted(
            lambda _: (
                rig.script
                if isinstance(rig.script, dict)
                else (_ for _ in ()).throw(rig.script)
            )
        )
        return double

    def answers(self, value: str) -> None:
        """The next answer is this value."""
        self.script = {"value": value}

    def refuses(self) -> None:
        """The provider filters the prompt."""
        self.script = ModelRefused("filtered by the content policy")

    def is_unreachable(self) -> None:
        """The provider does not answer."""
        self.script = ModelUnavailable("too slow")


RIGS = {"litellm": LitellmRig, "scripted": ScriptedRig}


@pytest.fixture(params=RIGS)
def rig(request, monkeypatch):
    """Each adapter's rig in turn."""
    return RIGS[request.param](monkeypatch)


def ask(model):
    """One question, with a prompt version."""
    return model.answer(
        system="Antworte.",
        user="Wie hoch ist die Gebühr?",
        shape=Shape,
        prompt_version="3",
    )


def test_an_answer_is_the_shape_asked_for(rig) -> None:
    """Parsed, not text."""
    rig.answers("2,50 Euro")

    answer = ask(rig.build())

    assert isinstance(answer, BaseModel)
    assert answer.value == "2,50 Euro"  # type: ignore[attr-defined]


def test_the_model_names_itself_for_the_record(rig) -> None:
    """What every stage writes beside the answer."""
    model = rig.build()

    assert isinstance(model.model, str) and model.model
    assert isinstance(model.temperature, float)


def test_the_prompt_version_is_optional(rig) -> None:
    """A prompt never versioned says nothing."""
    rig.answers("ok")

    assert rig.build().answer(system="s", user="u", shape=Shape).value == "ok"


def test_a_refused_prompt_is_refused_and_still_unavailable(rig) -> None:
    """ModelRefused is a ModelUnavailable, so a caller that handles one handles both."""
    rig.refuses()

    with pytest.raises(ModelRefused):
        ask(rig.build())
    assert issubclass(ModelRefused, ModelUnavailable)


def test_an_unreachable_provider_is_unavailable_and_not_refused(rig) -> None:
    """Only the port's two errors ever leave an adapter."""
    rig.is_unreachable()

    with pytest.raises(ModelUnavailable) as raised:
        ask(rig.build())
    assert not isinstance(raised.value, ModelRefused)


def test_llm_client_names_the_adapter(monkeypatch) -> None:
    """`litellm` is the default; an unknown name is refused."""
    from llm.config import Settings

    settings = Settings(
        model="azure/test",
        base_url=None,
        structured_mode="JSON_SCHEMA",
        temperature=0.0,
        timeout_seconds=1.0,
        max_attempts=1,
        num_ctx=None,
        reasoning_effort=None,
    )
    monkeypatch.delenv("LLM_CLIENT", raising=False)
    assert isinstance(module.build_model(settings), module.Client)
    # compose hands an unset name over empty
    monkeypatch.setenv("LLM_CLIENT", "")
    assert isinstance(module.build_model(settings), module.Client)

    monkeypatch.setenv("LLM_CLIENT", "elsewhere")
    with pytest.raises(ValueError, match="LLM_CLIENT"):
        module.build_model(settings)
