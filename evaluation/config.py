"""Where Phoenix is, as the experiment runner reaches it.

Runs on the host, so this is the published port rather than the compose
service name - the same distinction OTEL_EXPORTER_OTLP_ENDPOINT, which the
Makefile derives, and OTEL_CONTAINER_ENDPOINT, in configs/env/deployment.env,
already make.
"""

from __future__ import annotations

from dataclasses import dataclass

from settings import optional, required


@dataclass(frozen=True)
class Settings:
    """How to reach Phoenix, and what to call what is recorded there."""

    base_url: str
    #: Phoenix compares a bearer token against PHOENIX_ADMIN_SECRET
    #: directly, so there is no key to create and none to rotate.
    api_key: str
    #: What to name this run in Phoenix, so two are comparable by more than
    #: their timestamps. Optional: unset, the run is named after its set and
    #: model.
    run_name: str | None

    @classmethod
    def load(cls) -> Settings:
        """Reads settings from the environment."""
        return cls(
            base_url=required("PHOENIX_BASE_URL"),
            api_key=required("PHOENIX_ADMIN_SECRET"),
            run_name=optional("EVAL_RUN_NAME"),
        )
