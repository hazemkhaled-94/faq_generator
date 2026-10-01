"""The HTTP mechanics every backend client shares, against a recorded session."""

from __future__ import annotations

from lib.backend.pipeline import PipelineApi


class Session:
    """Answers every request with 200 and records what was sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, float]] = []

    def request(self, method: str, url: str, *, timeout: float, **kwargs):
        """Records one request and answers it."""
        self.sent.append((method, url, timeout))

        class Answered:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {}

        return Answered()


def test_the_automation_switches_are_saved_with_a_put() -> None:
    """The one PUT the frontend sends had no timeout and raised KeyError."""
    session = Session()

    saved, said = PipelineApi("http://api", session).automate(on_arrival=True)  # type: ignore[arg-type]

    assert (saved, said) == (True, "Saved.")
    assert session.sent[0][:2] == ("PUT", "http://api/pipeline/automation")
