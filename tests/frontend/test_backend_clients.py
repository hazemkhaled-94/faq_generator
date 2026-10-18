"""The HTTP mechanics every backend client shares, against a recorded session."""

from __future__ import annotations

import pytest
import requests

from lib.backend.base import refusal
from lib.backend.catalog import CatalogApi
from lib.backend.health import HealthApi
from lib.backend.pipeline import PipelineApi
from lib.backend.settings import SettingsApi
from lib.backend.upload import UploadApi


class Session:
    """Answers every request with one status and records what was sent."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.sent: list[tuple[str, str, float]] = []

    def request(self, method: str, url: str, *, timeout: float, **kwargs):
        """Records one request and answers it."""
        self.sent.append((method, url, timeout))
        status = self.status

        class Answered:
            status_code = status

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise requests.exceptions.HTTPError(response=self)  # type: ignore[arg-type]

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


@pytest.mark.parametrize(
    ("call", "sent"),
    [
        (
            lambda session: HealthApi("http://api", session).components(),
            ("GET", "http://api/status", 10.0),
        ),
        (
            lambda session: SettingsApi("http://api", session).change_settings(
                "questions", {"A_COUNT": "1"}, "v1"
            ),
            ("PATCH", "http://api/settings/questions", 30.0),
        ),
        (
            lambda session: CatalogApi("http://api", session).delete("a" * 64),
            ("DELETE", f"http://api/documents/{'a' * 64}", 60.0),
        ),
        (
            lambda session: UploadApi("http://api", session).add_document(
                "report.pdf", b"%PDF-1.4"
            ),
            ("POST", "http://api/documents", 60.0),
        ),
    ],
    ids=["GET", "PATCH", "DELETE", "POST"],
)
def test_each_verb_is_sent_with_its_own_timeout(call, sent) -> None:
    """A verb missing from the timeouts raised before anything was sent."""
    session = Session()

    call(session)

    assert session.sent == [sent]


def test_an_error_status_is_raised_rather_than_read() -> None:
    """The page renders the refusal; the client never hands back its body."""
    session = Session(status=500)

    with pytest.raises(requests.exceptions.HTTPError):
        SettingsApi("http://api", session).settings("questions")  # type: ignore[arg-type]

    assert session.sent == [("GET", "http://api/settings/questions", 10.0)]


def test_one_reader_reads_every_refusal() -> None:
    """The API's own sentence where it wrote one, and the failure where not.

    An HTTPError stringifies as its status line, which names nothing a
    person can act on; a timeout has no body to read a sentence from.
    """

    class Refused:
        @staticmethod
        def json() -> dict:
            return {"code": "unknown_topic", "detail": "no topic 17"}

    refused = requests.exceptions.HTTPError("404 Client Error")
    refused.response = Refused()  # type: ignore[assignment]
    late = requests.exceptions.ReadTimeout("read timed out")

    assert refusal(refused) == "no topic 17"
    assert refusal(late) == "read timed out"
