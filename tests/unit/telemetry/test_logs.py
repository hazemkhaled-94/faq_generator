"""The JSON line the log shipper reads.

An `@timestamp` Filebeat cannot parse is replaced with the time the line was
read, and an exception rendered without `error.stack_trace` reaches the
dashboard as a failure with no cause.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import threading
from datetime import datetime

import pytest

from telemetry.logs import JsonFormatter, _Bound, _file, bind, running_as


@pytest.fixture
def line() -> dict:
    """One formatted record: an error with a traceback and a caller's field."""
    record = logging.LogRecord(
        name="extraction.service",
        level=logging.ERROR,
        pathname="extraction/service.py",
        lineno=104,
        msg="failed passage %d",
        args=(41,),
        exc_info=None,
        func="process_next",
    )
    try:
        raise ValueError("the model would not answer")
    except ValueError:
        record.exc_info = sys.exc_info()
    # As telemetry.add_trace_fields puts them on: zeros outside a span.
    record.otelTraceID = "0" * 32
    record.otelSpanID = "0" * 16
    record.passage_id = 41  # a caller's own field, passed as extra=

    return json.loads(JsonFormatter("extraction").format(record))


def test_the_ecs_fields_are_named_and_filled(line: dict) -> None:
    """The level, the logger, the service, the message and the origin."""
    assert line["log.level"] == "error", line["log.level"]
    assert line["log.logger"] == "extraction.service", line["log.logger"]
    assert line["service.name"] == "extraction", line["service.name"]
    assert line["message"] == "failed passage 41", line["message"]
    assert line["log.origin.file.line"] == 104, line["log.origin.file.line"]
    assert line["trace.id"] == "0" * 32, line["trace.id"]


def test_the_run_is_on_every_line_a_run_writes(line: dict) -> None:
    """`run.id`, which is what reads one run's lines across five processes.

    The same value Phoenix names its project after, so a run found in one
    store is findable in the other.
    """
    record = logging.LogRecord(
        name="extraction.service",
        level=logging.INFO,
        pathname="extraction/service.py",
        lineno=1,
        msg="working",
        args=(),
        exc_info=None,
    )
    record.otelTraceID = "0" * 32
    record.otelSpanID = "0" * 16

    written = json.loads(JsonFormatter("extraction", "full-20260922").format(record))

    assert written["run.id"] == "full-20260922"
    # Present and empty for a process that is not a run, rather than absent:
    # one shape of line, and a panel filtering on it finds nothing to show.
    assert line["run.id"] == ""


def test_the_run_that_asked_outranks_the_process_that_worked(line: dict) -> None:
    """A claimed row names the run it belongs to, and the lines follow it.

    The worker is long-lived, so its own id names the container rather than
    the work. The row's `run_id` is this value, and a lineage page's link
    into Grafana joins on it - so a line stamped with the process instead
    would leave that link finding nothing.
    """
    record = logging.LogRecord(
        name="extraction.service",
        level=logging.INFO,
        pathname="extraction/service.py",
        lineno=1,
        msg="working",
        args=(),
        exc_info=None,
    )
    record.otelTraceID = "0" * 32
    record.otelSpanID = "0" * 16
    running_as("dagster-run-7")
    try:
        written = json.loads(JsonFormatter("extraction", "worker-uuid").format(record))
    finally:
        running_as(None)

    assert written["run.id"] == "dagster-run-7"


def test_a_callers_own_fields_survive(line: dict) -> None:
    """What was passed as extra= is carried beside the rest."""
    assert line["passage_id"] == 41


def test_the_whole_traceback_is_carried(line: dict) -> None:
    """The type, the message and the stack, not just the message."""
    assert line["error.type"] == "ValueError", line["error.type"]
    assert line["error.message"] == "the model would not answer"
    assert "Traceback" in line["error.stack_trace"], line["error.stack_trace"]
    assert "ValueError" in line["error.stack_trace"]


def test_the_timestamp_is_parseable_offset_aware_and_utc(line: dict) -> None:
    """What Filebeat needs to keep it rather than substitute its own."""
    assert line["@timestamp"].endswith("Z"), line["@timestamp"]
    when = datetime.fromisoformat(line["@timestamp"])
    assert when.tzinfo is not None, line["@timestamp"]
    assert when.utcoffset().total_seconds() == 0, line["@timestamp"]


def test_a_record_renders_as_one_line() -> None:
    """The shipper reads one event per line."""
    record = logging.LogRecord(
        name="extraction.service",
        level=logging.ERROR,
        pathname="extraction/service.py",
        lineno=104,
        msg="failed passage %d",
        args=(41,),
        exc_info=None,
        func="process_next",
    )
    try:
        raise ValueError("the model would not answer")
    except ValueError:
        record.exc_info = sys.exc_info()

    assert "\n" not in JsonFormatter("extraction").format(record)


def test_no_log_dir_means_no_file_handler(monkeypatch) -> None:
    """A process given neither .env nor compose, which includes pytest."""
    monkeypatch.delenv("LOG_DIR", raising=False)
    assert _file("extraction") is None


def test_a_writable_log_dir_is_created_and_named_per_process(
    monkeypatch, tmp_path
) -> None:
    """Two writers over one directory must not share a file.

    A scaled stage is several containers over one volume, and `./logs` is
    one machine over many runs — so the host alone is not enough and the
    pid is what finishes the name. Two processes rotating one file take
    each other's lines with them.
    """
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "nested"))

    handler = _file("extraction")
    assert handler is not None, "a writable LOG_DIR must give a handler"
    assert handler.baseFilename.startswith(f"{tmp_path / 'nested'}/extraction-")
    assert handler.baseFilename.endswith(f"-{os.getpid()}.log"), handler.baseFilename
    handler.close()


def test_an_unwritable_log_dir_costs_the_shipped_copy_and_nothing_else(
    monkeypatch,
) -> None:
    """Raising here would stop a worker over a mounted volume."""
    monkeypatch.setenv("LOG_DIR", "/proc/nowhere/qa")
    assert _file("extraction") is None


@pytest.fixture
def shipped():
    """A logger writing JSON lines through the bound-field filter.

    Built here rather than through `configure`, which would replace the
    root handlers for the rest of the session.
    """
    written = io.StringIO()
    handler = logging.StreamHandler(written)
    handler.setFormatter(JsonFormatter("extraction"))
    handler.addFilter(_Bound())

    logger = logging.getLogger("test.bound")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    def lines() -> list[dict]:
        """Every record written so far, parsed."""
        return [json.loads(one) for one in written.getvalue().strip().splitlines()]

    yield logger, lines
    logger.handlers = []


def test_bound_fields_reach_the_line(shipped) -> None:
    """What a stage bound where it claimed, on a line logged beneath it."""
    logger, lines = shipped
    with bind({"stage": "parsing", "document.sha256": "abc"}):
        logger.info("parsed")

    assert lines()[0]["document.sha256"] == "abc"
    assert lines()[0]["stage"] == "parsing"


def test_binding_nests_and_unwinds(shipped) -> None:
    """An inner bind adds to the outer one, and only until it closes."""
    logger, lines = shipped
    with bind({"stage": "extraction"}):
        with bind({"passage.id": 41}):
            logger.info("inner")
        logger.info("outer")
    logger.info("unbound")

    inner, outer, unbound = lines()
    assert inner["passage.id"] == 41 and inner["stage"] == "extraction"
    assert "passage.id" not in outer and outer["stage"] == "extraction"
    assert "stage" not in unbound


def test_a_library_line_carries_the_binding_too(shipped) -> None:
    """The filter is on the handler, so a propagated record gets it.

    This is the point of binding rather than passing extra= everywhere:
    the line that says which connection failed is logged by botocore.
    """
    _, lines = shipped
    library = logging.getLogger("test.bound.botocore")
    with bind({"document.sha256": "abc"}):
        library.warning("could not reach the bucket")

    assert lines()[0]["document.sha256"] == "abc"


def test_a_callers_extra_beats_the_binding(shipped) -> None:
    """The more specific of the two wins, and neither raises.

    Setting a bound field in the record factory instead would make this
    a KeyError out of logging.makeRecord, losing the line and its event.
    """
    logger, lines = shipped
    with bind({"passage.id": 41}):
        logger.info("re-reading", extra={"passage.id": 99})

    assert lines()[0]["passage.id"] == 99


def test_a_binding_does_not_leak_between_threads(shipped) -> None:
    """Two passages worked at once must not label each other's lines."""
    logger, lines = shipped

    def elsewhere() -> None:
        """Logs from a thread that bound nothing."""
        logger.info("elsewhere")

    with bind({"passage.id": 41}):
        thread = threading.Thread(target=elsewhere)
        thread.start()
        thread.join()

    assert "passage.id" not in lines()[0]


@pytest.fixture
def root():
    """The root logger put back as it was, since `configure` replaces its handlers."""
    from telemetry import logs

    root = logging.getLogger()
    held, level = list(root.handlers), root.level
    logs.add_trace_fields()
    yield root
    for handler in root.handlers:
        if handler not in held:
            handler.close()
    root.handlers[:] = held
    root.setLevel(level)


def test_an_unwritable_log_dir_is_a_record_on_stdout_with_the_usual_fields(
    root, tmp_path, monkeypatch, capsys
) -> None:
    """Said on the stream handler the docstring promises, not on a bare stderr line."""
    from telemetry.logs import configure

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("LOG_DIR", str(blocker / "logs"))
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    configure("probe")

    shown = capsys.readouterr()
    assert "is not writable" in shown.out, (shown.out, shown.err)
    assert "WARNING" in shown.out and "[trace=" in shown.out
    assert shown.err == ""


def test_the_warning_is_the_json_record_when_stdout_is_json(
    root, tmp_path, monkeypatch, capsys
) -> None:
    """The same failure, as one object with the file's ECS fields."""
    from telemetry.logs import configure

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("LOG_DIR", str(blocker / "logs"))
    monkeypatch.setenv("LOG_FORMAT", "json")

    configure("probe")

    (record,) = [json.loads(one) for one in capsys.readouterr().out.splitlines()]
    assert record["log.level"] == "warning"
    assert record["service.name"] == "probe"
    assert "is not writable" in record["message"]


@pytest.mark.parametrize(
    "message",
    [
        "Überweisung 12,50 €",
        "Virement de 12,50 EUR",
        "Przelew 12,50 zł",
        "Έμβασμα 12,50 €",
    ],
)
def test_json_on_stdout_is_one_object_per_record_with_the_fields_of_the_file(
    root, tmp_path, monkeypatch, capsys, message
) -> None:
    """One record is one line, whatever script it is in, and the file holds the same fields."""
    from telemetry.logs import configure

    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    configure("probe")
    logging.getLogger("probe.test").info(message, extra={"passage_id": 7})
    for handler in logging.getLogger().handlers:
        handler.flush()

    (on_stdout,) = [json.loads(one) for one in capsys.readouterr().out.splitlines()]
    (shipped,) = [
        json.loads(one)
        for f in tmp_path.glob("probe-*.log")
        for one in f.read_text().splitlines()
    ]
    assert on_stdout["message"] == message
    assert on_stdout["passage_id"] == 7
    assert set(on_stdout) == set(shipped)


def test_no_file_is_written_without_a_log_dir(
    root, tmp_path, monkeypatch, capsys
) -> None:
    """Stdout alone is enough, as on a platform that collects it."""
    from telemetry.logs import configure

    monkeypatch.delenv("LOG_DIR", raising=False)
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.chdir(tmp_path)

    configure("probe")
    logging.getLogger("probe.test").info("hello")

    assert [type(h).__name__ for h in logging.getLogger().handlers] == ["StreamHandler"]
    assert list(tmp_path.iterdir()) == []


def test_an_unknown_log_format_is_refused(root, monkeypatch) -> None:
    """`text` or `json`, and nothing quiet in between."""
    from telemetry.logs import configure

    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValueError, match="LOG_FORMAT"):
        configure("probe")
