"""A model that answers every passage with nothing must stop the drain.

Every row succeeds, so a count of failures cannot see it: the whole corpus
would be marked extracted with no fact under it.
"""

from __future__ import annotations

import os
import signal

import pytest
from drivers import Extraction, passage

from database.qa_generator import FactKind
from extraction.service import _EMPTY_STOP, _WINDOW
from stages.cli import STOPPED, exit_code

pytestmark = pytest.mark.nlp

NOTHING = {"facts": []}
ATOMIC = {"facts": [{"sentences": [0], "statement": "The device weighs 4 kg."}]}

#: One readable passage per language the corpus configures, and one the
#: configuration names none for, where the count must work all the same.
TEXTS = {
    "en": "The device weighs {n} kg. It runs for 12 hours.",
    "de": "Das Gerät wiegt {n} kg. Es läuft 12 Stunden lang.",
    "xx": "Lorem {n} ipsum dolor sit amet. Consectetur adipiscing elit sed do.",
}


def passages(language: str, count: int):
    """Numbered readable passages of one language."""
    return [
        passage(TEXTS[language].format(n=n), language=language, id=n)
        for n in range(1, count + 1)
    ]


@pytest.mark.parametrize("language", TEXTS)
def test_a_model_answering_nothing_for_every_passage_stops_within_the_window(
    language: str,
) -> None:
    """The passages it counted go back, and none is left marked read."""
    run = Extraction(*passages(language, 3 * _WINDOW), facts=NOTHING)

    run.run()

    assert run.service.stalled is not None
    assert exit_code(run.service) == STOPPED
    assert run.model.calls <= _WINDOW
    assert run.queue.stored == {}, "no passage is marked extracted"
    assert len(run.queue.released) >= _EMPTY_STOP


def test_one_passage_in_fifty_with_nothing_does_not_stop_it() -> None:
    """A page that asserts nothing exists, and is ordinary."""
    quiet = {n for n in range(1, 301, _WINDOW)}

    def answer(shown: str) -> dict:
        """Nothing for the numbered few, a fact for the rest."""
        return NOTHING if any(f"wiegt {n} kg" in shown for n in quiet) else ATOMIC

    run = Extraction(*passages("de", 300), facts=answer)

    assert run.run() == 300
    assert run.service.stalled is None
    assert exit_code(run.service) == 0
    assert len(run.queue.stored) == 300


def test_a_digest_does_not_make_a_silent_passage_look_answered() -> None:
    """The count is of what the passage reader found."""
    run = Extraction(
        *passages("en", 3 * _WINDOW),
        facts=NOTHING,
        digest={"summary": "The device weighs 4 kg.", "outline": ["Weighs 4 kg"]},
        kinds=(FactKind.SUMMARY,),
    )

    run.run()

    assert run.service.stalled is not None


def test_a_passage_nothing_could_read_is_not_counted() -> None:
    """A heading never reaches a model, so a run of them says nothing about it."""
    run = Extraction(
        *[passage("Risiko", language="de", id=n) for n in range(1, 3 * _WINDOW)],
        facts=NOTHING,
    )

    run.run()

    assert run.service.stalled is None
    assert run.model.calls == 0


@pytest.mark.parametrize("language", TEXTS)
def test_a_worker_after_the_silent_stop_asks_the_model_nothing_until_rebuilt(
    language: str, monkeypatch
) -> None:
    """The passages it gave back are not read again, and paid for, every poll."""
    from stages.worker import Shutdown, watch

    held = {one: signal.getsignal(one) for one in (signal.SIGTERM, signal.SIGINT)}
    run = Extraction(*passages(language, 3 * _WINDOW), facts=NOTHING)
    run.run()
    asked = run.model.calls
    assert run.service.stalled is not None
    # What the stop gave back is queued again, as the real queue has it.
    run.queue._pending.extend(passages(language, _WINDOW))

    waits: list[float] = []
    monkeypatch.setattr(Shutdown, "wait", lambda self, seconds: waits.append(seconds))
    polls: list[int] = []

    def drain(stopping) -> int:
        """One poll of a watching worker, which stops after three."""
        polls.append(run.service.drain(stopping))
        if len(polls) == 3:
            os.kill(os.getpid(), signal.SIGTERM)
        return polls[-1]

    try:
        watch(drain, 5.0)
    finally:
        for one, handler in held.items():
            signal.signal(one, handler)

    assert polls == [0, 0, 0], "a stopped drain works nothing"
    assert waits == [5.0, 5.0, 5.0], "and the worker waits its interval after each"
    assert run.model.calls == asked, "no further model call"
    assert exit_code(run.service) == STOPPED
