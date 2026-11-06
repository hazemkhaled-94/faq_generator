"""A Stop that Dagster answers with an error is raised with Dagster's words.

Neither a whole-call error nor a per-run answer that is neither success nor
failure means the run stopped, and neither may be read as "already finished".
"""

from __future__ import annotations

import pytest

from api.orchestrator import Dagster, Refused


class Replied:
    """One parsed GraphQL body."""

    status_code = 200

    def __init__(self, body: dict) -> None:
        self._body = body

    def json(self) -> dict:
        """The parsed body."""
        return self._body


class Session:
    """Answers from a script and records what it was asked."""

    def __init__(self, *bodies: dict) -> None:
        self.bodies = list(bodies)
        self.sent: list[dict] = []

    def post(self, url: str, json: dict, timeout: float) -> Replied:
        """Answers the next scripted body."""
        self.sent.append(json)
        return Replied(self.bodies.pop(0))


def test_a_whole_call_error_is_raised_as_a_refusal() -> None:
    """Dagster could not run the mutation at all."""
    session = Session(
        {
            "data": {
                "terminateRuns": {
                    "__typename": "PythonError",
                    "message": "run storage is locked",
                }
            }
        }
    )

    with pytest.raises(Refused, match="run storage is locked"):
        Dagster("http://dagster:3000", session=session).terminate("run-7")
    assert len(session.sent) == 1


def test_a_per_run_answer_that_is_neither_success_nor_failure_is_a_refusal() -> None:
    """An unauthorised stop is not looked up as if the run had finished."""
    session = Session(
        {
            "data": {
                "terminateRuns": {
                    "__typename": "TerminateRunsResult",
                    "terminateRunResults": [
                        {
                            "__typename": "UnauthorizedError",
                            "message": "not permitted to terminate run-7",
                        }
                    ],
                }
            }
        }
    )

    with pytest.raises(Refused, match="not permitted to terminate run-7"):
        Dagster("http://dagster:3000", session=session).terminate("run-7")
    assert len(session.sent) == 1, "no status lookup, no forced cancel"
