"""The flag, the judge and the two cost dials.

The flag is the one setting in this package with a behaviour of its own:
off, the command line says so and stops before it claims anything, which
is a different thing from finding an empty queue and has to read as one.
"""

from __future__ import annotations

import logging

import pytest

from assessment import run as cli
from assessment.config import Settings, judge_of, judged_kinds
from assessment.factory import judge_model
from llm.config import Settings as ModelSettings

#: A complete set of values, for the reader to vary one of.
VALUES = {
    "ASSESSMENT_ENABLED": "true",
    "ASSESSMENT_JUDGE_MODEL": "azure/gpt-5.4",
    "ASSESSMENT_KINDS": "fact,topic,question",
    "ASSESSMENT_SAMPLE": "200",
    "ASSESSMENT_STRATIFY": "false",
}


def settings(**changed: str) -> Settings:
    """The settings, read from VALUES with some values changed."""
    return Settings.load({**VALUES, **changed})


#: A self-hosted writer, which is what makes the judge below a
#: CROSS-PROVIDER override rather than a change of model.
_SHARED = {
    "LLM_MODEL": "ollama_chat/gemma4:31b",
    "LLM_BASE_URL": "http://localhost:11434",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "LLM_STRUCTURED_MODE": "JSON",
    "LLM_TEMPERATURE": "0",
    "LLM_TIMEOUT_SECONDS": "60",
    "LLM_MAX_ATTEMPTS": "3",
}


def model(**changed: str) -> ModelSettings:
    """The shared model settings, with whatever a test needs changed."""
    return ModelSettings.load({**_SHARED, **changed})


def test_the_flag_is_read() -> None:
    """Both ways, because off is the default and has to be reachable."""
    assert settings().enabled is True
    assert settings(ASSESSMENT_ENABLED="false").enabled is False


def test_a_sample_of_zero_means_every_artefact() -> None:
    """Which on a large corpus is a model call per fact, so it is opt-in."""
    from sqlalchemy.dialects import postgresql

    from assessment.repository import AssessmentQueue

    def enrols(sample: int) -> str:
        """The enrolment's SQL for one sample size."""
        built = AssessmentQueue()._enrolment("fact", sample)
        return str(built.compile(dialect=postgresql.dialect()))

    assert "LIMIT" not in enrols(0)
    assert "LIMIT" in enrols(3)


def test_the_kinds_are_checked_against_the_templates() -> None:
    """A kind with no template is a queue row nothing could judge."""
    assert judged_kinds(settings()) == ("fact", "topic", "question")

    with pytest.raises(ValueError, match="passage"):
        judged_kinds(settings(ASSESSMENT_KINDS="fact,passage"))


def test_the_judge_is_the_model_the_setting_names() -> None:
    """And is refused when it names nothing, rather than being the writer."""
    assert judge_model(settings(), model()).model == "azure/gpt-5.4"
    with pytest.raises(ValueError, match="ASSESSMENT_JUDGE_MODEL"):
        judge_model(settings(ASSESSMENT_JUDGE_MODEL=""), model())


def test_with_no_judge_named_the_command_line_judges_nothing(monkeypatch) -> None:
    """Refused before a claim, and not by `--status` or the queue verbs."""
    monkeypatch.setattr(
        "assessment.run.snapshot",
        lambda *_: ({**VALUES, **_SHARED, "ASSESSMENT_JUDGE_MODEL": ""}, "environment"),
    )
    monkeypatch.setattr(cli, "before_work", lambda asked: None)
    handed: dict = {}
    monkeypatch.setattr(cli, "queue_main", lambda **kwargs: handed.update(kwargs))

    cli.main([])

    assert handed["repository"]() is not None
    with pytest.raises(ValueError, match="ASSESSMENT_JUDGE_MODEL"):
        handed["preflight"]()


def test_with_no_judge_named_the_status_says_nothing_is_judged(
    monkeypatch, caplog
) -> None:
    """Beside the queue, naming the setting for the host and the containers."""
    monkeypatch.setattr(
        "assessment.run.snapshot",
        lambda *_: ({**VALUES, **_SHARED, "ASSESSMENT_JUDGE_MODEL": ""}, "environment"),
    )
    monkeypatch.setattr("stages.cli.telemetry.configure", lambda *_, **__: None)

    class _Queue:
        """A queue that reports one waiting row."""

        def __init__(self, **_) -> None:
            """Takes the kinds and the sample, and keeps neither."""

        def counts_by_status(self, within=None) -> dict[str, int]:
            """One row waiting."""
            return {"queued": 1}

    monkeypatch.setattr(cli, "AssessmentQueue", _Queue)

    with caplog.at_level("INFO"):
        assert cli.main(["--status"]) == 0

    assert "assessment queue: {'queued': 1}" in caplog.text
    assert "nothing is judged" in caplog.text
    assert "LLM_MODEL is not asked in its place" in caplog.text
    assert "Set ASSESSMENT_JUDGE_MODEL" in caplog.text
    assert "ASSESSMENT_JUDGE_CONTAINER_MODEL" in caplog.text


def test_the_plan_names_the_writer_when_it_is_the_judge() -> None:
    """The model the next run judges with, and whether that is the writer."""
    writer = {"LLM_MODEL": "ollama_chat/gemma4:31b"}

    assert judge_of(settings(), writer) == ("azure/gpt-5.4", False)
    assert judge_of(settings(ASSESSMENT_JUDGE_MODEL=""), writer) == (None, False)
    named = settings(ASSESSMENT_JUDGE_MODEL="ollama_chat/gemma4:31b")
    assert judge_of(named, writer)[1] is True


def test_a_hosted_judge_does_not_keep_the_local_runtime_address() -> None:
    """The deployment this is pointed at judges on Azure and writes locally.

    `overridden` drops a base URL it can prove belongs to the runtime being
    left, which is when it is the one OLLAMA_BASE_URL names. Kept, an Azure
    request would be sent to Ollama's port - which is the failure that
    argument exists to stop, in the other direction.
    """
    asked = judge_model(settings(), model())

    assert asked.model == "azure/gpt-5.4"
    assert asked.base_url is None, "litellm reads AZURE_API_BASE instead"
    assert asked.window is None, "a hosted provider sizes its own context"


def test_a_judge_on_the_writers_own_provider_keeps_the_address() -> None:
    """A same-provider judge is the one-thing change this always was.

    Naming another deployment of the provider already configured moves the
    model and nothing else.
    """
    asked = judge_model(
        settings(),
        model(
            LLM_MODEL="azure/gpt-4.1",
            LLM_BASE_URL="https://example.openai.azure.com",
            OLLAMA_BASE_URL="",
        ),
    )

    assert asked.model == "azure/gpt-5.4"
    assert asked.base_url == "https://example.openai.azure.com"


def test_the_command_line_stops_when_the_phase_is_off(monkeypatch, caplog) -> None:
    """Saying so, and without building a service or reaching a database.

    A deployment that has not turned this on and cannot tell "off" from
    "nothing to judge" will read the second as a bug in the first.
    """
    monkeypatch.setattr(
        "assessment.run.snapshot",
        lambda *_: ({**VALUES, "ASSESSMENT_ENABLED": "false"}, "environment"),
    )
    built = []
    monkeypatch.setattr(
        "assessment.run.build_service", lambda *a: built.append(a) or None
    )
    monkeypatch.setattr("assessment.run.telemetry.configure", lambda *a, **k: None)

    with caplog.at_level("INFO"):
        assert cli.main(["--status"]) == 0

    assert not built, "nothing is built when the phase is off"
    assert "ASSESSMENT_ENABLED" in caplog.text


def test_a_watching_worker_waits_for_the_phase_rather_than_exiting(monkeypatch) -> None:
    """An exit is a restart under `restart: unless-stopped`, every few seconds.

    And the Assessment page switches the flag on without restarting the
    worker, so the worker has to notice it in place.
    """
    flags = iter(["false", "false"])
    monkeypatch.setattr(
        "assessment.run.snapshot",
        lambda *_: (
            {**VALUES, "ASSESSMENT_ENABLED": next(flags, "true")},
            "environment",
        ),
    )
    monkeypatch.setenv("WORKER_POLL_SECONDS", "5")
    slept: list[float] = []
    monkeypatch.setattr("assessment.run.time.sleep", slept.append)
    monkeypatch.setattr("assessment.run.telemetry.configure", lambda *a, **k: None)
    handed: dict = {}
    monkeypatch.setattr(cli, "queue_main", lambda **kwargs: handed.update(kwargs) or 0)

    assert cli.main(["--watch"]) == 0

    assert slept == [5]
    assert handed["argv"] == ["--watch"]


def test_the_phase_off_message_is_logged_once_logging_is_set_up(monkeypatch) -> None:
    """Logged before the handlers exist, it reached nobody on the host."""
    monkeypatch.setattr(
        "assessment.run.snapshot",
        lambda *_: ({**VALUES, "ASSESSMENT_ENABLED": "false"}, "environment"),
    )
    events: list[str] = []
    monkeypatch.setattr(
        "assessment.run.telemetry.configure",
        lambda *a, **k: events.append("configured"),
    )

    class Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            events.append("logged")

    logger = logging.getLogger("assessment.run")
    handler = Recorder()
    # setLevel, not the attribute: only setLevel clears the cache an earlier
    # test filled with "INFO is off" for this logger.
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        assert cli.main(["--status"]) == 0
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

    assert events == ["configured", "logged"]


def test_a_judge_named_as_the_writer_is_warned_about(caplog) -> None:
    """Naming the writer's own model is the same as naming none."""
    from assessment.factory import build_service

    writer = model()

    with caplog.at_level("WARNING"):
        build_service(settings(ASSESSMENT_JUDGE_MODEL=writer.model), writer)

    assert "judging the pipeline's own output" in caplog.text


#: The split a deployment names: seven roles, one of which may be the judge's.
_ROLES = {
    "LLM_MODEL": "azure/gpt-5.4",
    "QUESTIONS_MODEL": "azure/gpt-5.6-sol",
    "QUESTIONS_VERIFIER_MODEL": "azure/gpt-4.1",
    "QUESTIONS_PHRASING_MODEL": "azure/gpt-5.4",
    "EXTRACTION_MODEL": "azure/gpt-5.4",
    "EXTRACTION_DIGEST_MODEL": "azure/gpt-4o",
    "TOPIC_MODEL": "azure/gpt-4.1",
}


def test_a_judge_equal_to_the_digest_model_names_the_digest_role() -> None:
    """Every role whose output is judged, not only the shared model."""
    from assessment.config import judge_equals

    named = settings(ASSESSMENT_JUDGE_MODEL="azure/gpt-4o")

    assert judge_equals(named, _ROLES) == ["digest"]
    assert judge_of(named, _ROLES) == ("azure/gpt-4o", True)


def test_a_judge_equal_to_several_roles_names_each() -> None:
    """The verifier and the topic namer here."""
    from assessment.config import judge_equals

    assert judge_equals(settings(ASSESSMENT_JUDGE_MODEL="azure/gpt-4.1"), _ROLES) == [
        "verifier",
        "topics",
    ]


def test_a_judge_distinct_from_every_role_is_not_warned_about() -> None:
    """Nothing to say."""
    from assessment.config import judge_equals

    named = settings(ASSESSMENT_JUDGE_MODEL="azure/some-other-judge")

    assert judge_equals(named, _ROLES) == []
    assert judge_of(named, _ROLES)[1] is False


def test_a_judge_that_is_one_of_the_roles_is_warned_about_naming_it(
    caplog, monkeypatch
) -> None:
    """The log line says which role it is marking."""
    from assessment.factory import build_service

    for name, value in _ROLES.items():
        monkeypatch.setenv(name, value)

    with caplog.at_level("WARNING"):
        build_service(
            settings(ASSESSMENT_JUDGE_MODEL="azure/gpt-4o"),
            model(LLM_MODEL="azure/gpt-5.4"),
        )

    assert (
        "digest" in caplog.text and "judging the pipeline's own output" in caplog.text
    )
