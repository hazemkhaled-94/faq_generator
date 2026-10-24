"""The question generation command line.

Every flag is the same operation as a route under /questions. Most of them
are `stages.cli.queue_main`'s and are covered there; what is this stage's
own is the two operations no other stage has - the re-check and the release
draw.
"""

from __future__ import annotations

import os
from typing import ClassVar

import pytest


class Queue:
    """A question queue that records what was asked of it."""

    scopes: ClassVar[dict[str, None]] = {"topic": None}

    def __init__(self) -> None:
        """Starts with nothing asked of it."""
        self.calls: list[str] = []

    def counts_by_status(self, within=None) -> dict[str, int]:
        """The queue depth."""
        self.calls.append("counts")
        return {"new": 2}

    def never_asked(self):
        """What no accepted question reaches."""
        from question_generation.queue import NeverAsked

        self.calls.append("never_asked")
        return NeverAsked((("Terms of sale", 3),), 5)

    def start(self, within=None, *, trigger: str | None = None) -> int:
        """Queues what was never asked for."""
        self.calls.append("start")
        return 1

    def stop(self, within=None) -> int:
        """Takes back what has not begun."""
        self.calls.append("stop")
        return 1

    def retry(self, within=None, *, trigger: str | None = None) -> int:
        """Returns failed rows."""
        self.calls.append("retry")
        return 1

    def reset(self, within=None, *, trigger: str | None = None) -> int:
        """Queues every row again."""
        self.calls.append("rerun")
        return 1

    def narrowed(self, scope: str, value: str):
        """The condition one scope selects."""
        from stages.queue import Unnarrowable

        if scope != "topic":
            raise Unnarrowable("unknown_scope", "this stage narrows to topic")
        return f"{scope}={value}"


class Service:
    """A service that records each drain."""

    name = "stub"
    unit = "row"
    estimate = None
    failed = 0
    stalled = None

    def __init__(self) -> None:
        """Initialises with nothing drained."""
        self.drains = 0

    def drain(self, stopping=None) -> int:
        """Records one drain."""
        del stopping
        self.drains += 1
        return 0

    def give_back(self) -> bool:
        """Holds no row."""
        return False


class Driver:
    """The command line with its collaborators replaced."""

    def __init__(self, monkeypatch) -> None:
        """Points every collaborator at something that records."""
        from question_generation import run as module
        from stages import cli

        self.queue = Queue()
        self.service = Service()
        self.built = 0
        self.rechecked: list = []
        self.rescored: list = []
        self.balanced: list = []
        self.watched: list[float] = []
        #: The models the preflight was asked to prove, in order. Replaced
        #: because the real one calls them, and a unit test serves nothing.
        self.proved: list[str] = []

        def build():
            """Counts the builds and hands back the recording service."""
            self.built += 1
            return self.service

        # Model identity, which compose gives a worker and .env gives the
        # host. conftest loads configs/env/backend.env, which carries the
        # rest of the model settings and deliberately not this one.
        monkeypatch.setenv("LLM_MODEL", "ollama_chat/test-model")

        # The settings the command reads, without the database they are
        # stored in. Settings.load is still the real one.
        monkeypatch.setattr(
            module, "snapshot", lambda *_: (dict(os.environ), "test-settings")
        )
        monkeypatch.setattr(module, "QuestionQueue", lambda **kwargs: self.queue)
        monkeypatch.setattr(module, "QuestionCatalog", lambda: object())
        monkeypatch.setattr(module, "build_service", lambda *_: build())
        monkeypatch.setattr(
            module, "reverify", lambda catalog, settings, within: self._recheck(within)
        )
        monkeypatch.setattr(
            module,
            "balance",
            lambda catalog, settings, within, verifier=None: self._balance(
                within, verifier
            ),
        )
        #: The verifier each re-judge was handed, and what it was narrowed to.
        self.rejudged: list[tuple[str, object]] = []
        monkeypatch.setattr(
            module,
            "rejudge",
            lambda catalog, settings, verifier, within: self._rejudge(verifier, within),
        )
        monkeypatch.setattr(
            module,
            "rescore",
            lambda catalog, settings, within: self.rescored.append(within) or 2,
        )

        def proving(*models):
            """Records what was asked."""
            self.proved.extend(one.model for one in models)

        monkeypatch.setattr(module, "before_work", proving)
        # The real one writes the prompts into whatever DATABASE_URL names.
        monkeypatch.setattr(module, "record", lambda *_: 0)
        monkeypatch.setattr(cli.telemetry, "configure", lambda *_, **__: None)
        monkeypatch.setattr(cli.telemetry, "trace_engine", lambda *_: None)
        monkeypatch.setattr(cli, "engine", lambda: None)
        monkeypatch.setattr(module, "engine", lambda: None)
        monkeypatch.setattr(
            cli, "watch", lambda _, seconds, *__: self.watched.append(seconds)
        )
        self._main = module.main

    def _recheck(self, within) -> int:
        """Records one re-check and what it was narrowed to."""
        self.rechecked.append(within)
        return 3

    def _rejudge(self, verifier, within) -> int:
        """Records one re-judge, the model it asks and its narrowing."""
        self.rejudged.append((verifier.model, within))
        return 2

    def _balance(self, within, verifier=None) -> int:
        """Records one draw, what it was narrowed to and who judged its twins."""
        self.balanced.append(within)
        self.judged_by = verifier.model if verifier is not None else None
        return 7

    def run(self, *argv: str) -> int:
        """Runs the command line."""
        return self._main(list(argv))


@pytest.fixture
def cli(monkeypatch) -> Driver:
    """The command line, wired to recorders."""
    return Driver(monkeypatch)


def test_status_reports_the_queue_and_builds_no_service(cli, caplog) -> None:
    """The cheap flag: a read of the queue, and no model named."""
    caplog.set_level("INFO")

    assert cli.run("--status") == 0

    assert cli.queue.calls == ["counts", "never_asked"]
    assert cli.built == 0, "a status read loaded the writer"
    assert "1 document(s) with facts and no accepted question: Terms of sale (3)" in (
        caplog.text
    )
    assert "5 passage(s) with facts never asked" in caplog.text


@pytest.mark.parametrize("flag", ["start", "stop", "retry"])
def test_each_queue_verb_is_the_route_beside_it(cli, flag: str) -> None:
    """The same operation POST /questions/{flag} makes."""
    assert cli.run(f"--{flag}") == 0
    assert cli.queue.calls == [flag]
    assert cli.service.drains == 0


def test_no_flag_at_all_drains_what_is_already_queued(cli) -> None:
    """A bare run works the queue once and returns."""
    assert cli.run() == 0
    assert cli.service.drains == 1


def test_rerun_queues_everything_again_and_then_drains(cli) -> None:
    """Both, in that order."""
    assert cli.run("--rerun") == 0
    assert cli.queue.calls == ["rerun", "counts"], "then counted for the estimate"
    assert cli.service.drains == 1


def test_every_model_this_stage_calls_is_proved_before_anything_is_claimed(
    cli,
) -> None:
    """The verifier and the phrasing judge as well as the writer.

    A run whose verifier will not answer is a run of ungated questions,
    which is worse than no run at all. QUESTIONS_PHRASING_MODEL may name a
    model neither of the other two does, and an unreachable one abstains
    once per question instead of failing the start.
    """
    assert cli.run("--watch") == 0
    assert len(cli.proved) == 3, "the writer, the verifier and the phrasing judge"


# ── The two operations no other stage has ─────────────────────────────────


def test_reverify_puts_the_stored_questions_through_the_free_gates(cli) -> None:
    """No model is called, so a re-check costs a pass over the table."""
    assert cli.run("--reverify") == 0
    assert cli.rechecked == [None]
    assert cli.built == 0, "the re-check calls no model and needs no service"


def test_rescore_rewrites_the_stored_bands_without_building_a_service(cli) -> None:
    """The criteria are read off the citations, so no model is called."""
    assert cli.run("--rescore") == 0
    assert cli.rescored == [None]
    assert cli.built == 0


def test_balance_draws_a_release_without_building_a_service(cli) -> None:
    """The draw is a column on rows already there."""
    assert cli.run("--balance") == 0
    assert cli.balanced == [None]
    assert cli.built == 0


def test_balance_judges_twins_with_the_verifier_model_proved_first(
    cli, monkeypatch
) -> None:
    """Whether two released questions want one answer is the verifier's call."""
    monkeypatch.setenv("QUESTIONS_VERIFIER_MODEL", "ollama_chat/verifier")

    assert cli.run("--balance") == 0
    assert cli.proved == ["ollama_chat/verifier"]
    assert cli.judged_by == "ollama_chat/verifier"


def test_a_balance_is_traced_once_its_verifier_has_answered(cli, monkeypatch) -> None:
    """The draw and the verifier's calls are traced under this run.

    `queue_main` installs tracing only before a drain, so this stage's own
    operations ran without it and every line the draw wrote read trace 0.
    After the preflight, as a drain's is: a verifier that will not answer
    leaves no project behind.
    """
    import telemetry
    from question_generation import run as module

    happened: list[str] = []
    monkeypatch.setattr(
        telemetry,
        "configure",
        lambda *_, tracing=True, **__: happened.append(
            "traced" if tracing else "logged"
        ),
    )
    monkeypatch.setattr(module, "before_work", lambda *_: happened.append("proved"))
    monkeypatch.setattr(module, "balance", lambda *_: happened.append("drawn") or 7)

    assert cli.run("--balance") == 0
    assert happened == ["logged", "proved", "traced", "drawn"]


def test_a_narrowed_balance_is_refused_before_anything_is_drawn(cli) -> None:
    """The draw clears every release first, so a narrowed one keeps one topic's."""
    with pytest.raises(SystemExit, match="--only"):
        cli.run("--balance", "--only", "topic=7")
    assert cli.balanced == []


def test_a_re_check_can_be_narrowed_to_one_topic(cli) -> None:
    """`--only` reaches this stage's own operations too."""
    assert cli.run("--reverify", "--only", "topic=3") == 0
    assert cli.rechecked == ["topic=3"]


def test_the_only_scope_this_stage_takes_is_a_topic(cli) -> None:
    """A topic is already the smallest subject there is."""
    with pytest.raises(SystemExit, match="narrows to topic"):
        cli.run("--status", "--only", "document=abc")


def test_rejudge_asks_the_verifier_model_and_proves_it_first(cli, monkeypatch) -> None:
    """The one re-check that calls a model, so the model is the verifier's.

    Proved before the first question is asked, as a drain proves its models,
    and narrowed to a topic like the free re-check beside it.
    """
    monkeypatch.setenv("QUESTIONS_VERIFIER_MODEL", "ollama_chat/verifier")

    assert cli.run("--rejudge", "--only", "topic=4") == 0
    assert cli.proved == ["ollama_chat/verifier"]
    assert cli.rejudged == [("ollama_chat/verifier", "topic=4")]
    assert cli.built == 0, "a re-judge writes no question and needs no service"
