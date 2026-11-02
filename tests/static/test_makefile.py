"""The Makefile, read through `make -n`, which prints a recipe and runs none.

The one command executed here is the worker guard on its own, against a
stand-in for compose.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

#: Every target that drains a stage's queue on the host, and the container
#: worker that drains the same queue.
DRAINS = {
    "parse": "parse-worker",
    "parse-rerun": "parse-worker",
    "chunk": "chunk-worker",
    "chunk-rerun": "chunk-worker",
    "extract": "extract-worker",
    "extract-rerun": "extract-worker",
    "topics": "topic-worker",
    "topics-discover": "topic-worker",
    "questions": "question-worker",
    "questions-rerun": "question-worker",
    "assess": "assess-worker",
    "assess-rerun": "assess-worker",
}

#: Every target that rewrites stored verdicts across the corpus on the host,
#: and the container worker writing verdicts beside it.
REWRITES = {
    "extract-dedup": "extract-worker",
    "extract-revalidate": "extract-worker",
    "extract-recap": "extract-worker",
}


def printed(*arguments: str, **environment: str) -> list[str]:
    """What `make -n` prints for the arguments, one command per line."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    return subprocess.run(
        ["make", "-n", "--no-print-directory", *arguments],
        cwd=ROOT,
        env={**inherited, **environment},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


@pytest.mark.parametrize(("target", "worker"), [*DRAINS.items(), *REWRITES.items()])
def test_a_host_drain_asks_whether_its_worker_runs_first(
    target: str, worker: str
) -> None:
    """The guard naming the stage's own worker comes before the drain or rewrite."""
    lines = printed(target)
    guards = [at for at, line in enumerate(lines) if f"ps -q {worker} " in line]
    drains = [at for at, line in enumerate(lines) if "python -m" in line]

    assert guards and drains, lines
    assert guards[0] < drains[0], lines


@pytest.mark.parametrize(
    ("compose", "refused"),
    [
        ("echo 4f1c2a9e", True),
        ("true", False),
        ("echo 'cannot connect to the engine' >&2; exit 125", False),
        (None, False),
    ],
    ids=["worker-running", "stack-down", "engine-not-answering", "no-engine"],
)
def test_the_guard_refuses_only_while_the_worker_runs(
    tmp_path: Path, compose: str | None, refused: bool
) -> None:
    """And names the command that stops it, with the env files compose needs."""
    engine = tmp_path / "compose"
    if compose is not None:
        engine.write_text(f"#!/bin/sh\n{compose}\n")
        engine.chmod(0o755)
    (guard,) = [
        line
        for line in printed("extract", COMPOSE=str(engine))
        if f"{engine} --env-file" in line
    ]
    assert "python -m" not in guard and "poetry" not in guard, guard

    ran = subprocess.run(
        ["bash", "-c", guard], cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert (ran.returncode != 0) is refused, ran
    if refused:
        assert (
            f"{engine} --env-file configs/env/deployment.env --env-file .env "
            "stop extract-worker"
        ) in ran.stdout + ran.stderr


@pytest.mark.parametrize(("given", "forced"), [((), False), (("FORCE=1",), True)])
def test_the_bridge_pass_is_forced_only_when_asked(
    given: tuple[str, ...], forced: bool
) -> None:
    """`FORCE=1` reaches it as `--force`."""
    (bridging,) = [
        line for line in printed("extract-bridge", *given) if "--bridge" in line
    ]

    assert ("--force" in bridging) is forced, bridging


@pytest.mark.parametrize("target", ["delete", "delete-derived"])
def test_a_deletion_is_followed_by_the_dedup_replay_over_the_whole_corpus(
    target: str,
) -> None:
    """A refusal whose twin went with the document is in another document.

    The dedup alone: it re-judges and re-caps the passages of what it gives
    back itself, and nothing else in the corpus is touched.
    """
    ran = [
        line.split("python -m ", 1)[1].strip()
        for line in printed(target, "SHA=abc")
        if "python -m" in line
    ]

    assert ran == [f"ingestion.run --{target} abc", "extraction.run --dedup"], ran


@pytest.mark.parametrize("target", ["delete", "delete-derived"])
def test_a_deletion_refuses_before_it_deletes(target: str) -> None:
    """The extract worker's guard came with the replay, after the document was gone.

    A refusal then left a deletion whose duplicates were never given back.
    """
    lines = printed(target, "SHA=abc")
    guards = [at for at, line in enumerate(lines) if "ps -q extract-worker " in line]
    deleting = [at for at, line in enumerate(lines) if "ingestion.run" in line]

    assert guards and deleting, lines
    assert guards[0] < deleting[0], lines


@pytest.mark.parametrize(
    ("given", "guarded"),
    [((), True), (("TOPIC=7",), False)],
    ids=["whole-queue", "narrowed"],
)
@pytest.mark.parametrize(
    ("target", "worker"),
    [("questions-reclaim", "question-worker"), ("assess-reclaim", "assess-worker")],
)
def test_a_whole_queue_reclaim_asks_whether_its_worker_runs(
    target: str, worker: str, given: tuple[str, ...], guarded: bool
) -> None:
    """Over the whole stage it would hand a live worker's rows to another.

    Narrowed, it is what a person does to one row they know is dead, worker up
    or not.
    """
    lines = printed(target, *given)
    guards = [at for at, line in enumerate(lines) if f"ps -q {worker} " in line]
    reclaims = [at for at, line in enumerate(lines) if "--reclaim" in line]

    assert reclaims, lines
    assert bool(guards) is guarded, lines
    if guarded:
        assert guards[0] < reclaims[0], lines


def test_the_corpus_fits_the_topics_only_when_they_are_not_live() -> None:
    """`topics-discover` is the refit, asked for on its own.

    The corpus passes --ensure, which fits only a language with passages and
    no topic, or whose topics are stale, and fails if one still has none.
    """
    topics = [line for line in printed("corpus") if "topic_modelling.run" in line]

    assert topics, "the corpus says nothing about the topics"
    assert all(
        line.endswith(("topic_modelling.run --status", "run --discover --ensure"))
        for line in topics
    ), topics


def test_the_topics_are_fitted_after_extraction_and_before_a_bridge_needs_them() -> (
    None
):
    """When a language holds passages and no live fit; `--ensure` is that check."""
    lines = printed("corpus")
    digests = next(
        at for at, line in enumerate(lines) if "extraction.run --digests" in line
    )
    fit = next(
        at
        for at, line in enumerate(lines)
        if line.endswith("topic_modelling.run --discover --ensure")
    )
    bridge = next(
        at for at, line in enumerate(lines) if "extraction.run --bridge" in line
    )

    assert digests < fit < bridge


def test_the_corpus_writes_the_bridges_its_topics_are_missing() -> None:
    """After the topics are known and before a question is written from them.

    For the topics holding none only, so a second run over a corpus whose
    questions already cite its bridges neither deletes them nor stops.
    """
    lines = printed("corpus")
    bridged = [at for at, line in enumerate(lines) if "extraction.run --bridge" in line]
    topics = [
        at for at, line in enumerate(lines) if "topic_modelling.run --status" in line
    ]
    questions = [
        at for at, line in enumerate(lines) if "question_generation.run" in line
    ]

    assert bridged, "the corpus never writes a bridge"
    assert topics[0] < bridged[0] < questions[0]
    assert "--missing" in lines[bridged[0]]


def test_a_command_line_value_is_named_for_the_store_to_give_way_to() -> None:
    """A stored row for a name given on the command line is not applied."""
    lines = printed("topics-discover", "TOPIC_PASSES=20")

    assert any('QA_COMMAND_LINE="TOPIC_PASSES"' in line for line in lines), lines


@pytest.mark.parametrize(
    ("given", "address"),
    [
        ("BACKEND_PORT=9999", "http://localhost:9999"),
        ("BACKEND_URL=http://elsewhere:1", "http://elsewhere:1"),
    ],
    ids=["what-an-address-is-built-of", "the-address-itself"],
)
@pytest.mark.parametrize(
    "target",
    [("settings", "SERVICE=platform"), ("review-status",)],
    ids=["LOADENV", "WITH"],
)
def test_a_command_line_value_is_exported_before_the_derived_addresses(
    tmp_path: Path, target: tuple[str, ...], given: str, address: str
) -> None:
    """A port given on the command line reaches the address built from it.

    Applied only after the addresses were built, it reached the process
    while the address beside it still named the file's port.
    """
    for name, text in {
        "configs/env/backend.env": "",
        "configs/env/deployment.env": "BACKEND_PORT=8000\n",
        "configs/env/review.env": "",
        ".env": "",
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    (tmp_path / "poetry").write_text('#!/bin/sh\necho "$BACKEND_URL"\n')
    (tmp_path / "poetry").chmod(0o755)
    (line,) = [one for one in printed(*target, given) if "poetry run" in one]

    ran = subprocess.run(
        ["bash", "-c", line],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert ran.stdout.strip() == address, ran


def command(target: str, holding: str, **environment: str) -> str:
    """The one command `make -n` prints for a target that holds `holding`.

    A recipe line continued with a backslash is printed over several lines;
    they are joined back into the one command the shell is given.
    """
    joined = "\n".join(printed(target, **environment)).replace("\\\n", "")
    (found,) = [line for line in joined.splitlines() if holding in line]
    return found


def stand_in(tmp_path: Path, script: str) -> Path:
    """A compose that runs nothing and answers what `script` prints."""
    engine = tmp_path / "compose"
    engine.write_text(f"#!/bin/sh\n{script}\n")
    engine.chmod(0o755)
    return engine


def made(
    target: str, *arguments: str, path: Path | None = None
) -> subprocess.CompletedProcess:
    """`make` run for real, for a target that reaches no service.

    `path` goes first on PATH, so a stand-in there answers for a tool.
    """
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    if path is not None:
        inherited["PATH"] = f"{path}:{inherited['PATH']}"
    return subprocess.run(
        ["make", "--no-print-directory", target, *arguments],
        cwd=ROOT,
        env=inherited,
        capture_output=True,
        text=True,
        check=False,
    )


def _auditing(tmp_path: Path, advised: str = "", extra: str = "") -> Path:
    """A poetry whose `run python` is the test's interpreter, and a pip-audit.

    The pip-audit is recorded and writes an empty report where `--output`
    says, or one advisory on the lock `advised` names, exiting 1 as pip-audit
    does on a finding.
    """
    calls = tmp_path / "calls"
    poetry = tmp_path / "poetry"
    finding = (
        '{"dependencies": [{"name": "pillow", "version": "12.3.0", "vulns": '
        '[{"id": "GHSA-new", "fix_versions": ["13.0.0"], "aliases": []}]}], '
        '"fixes": []}'
    )
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'echo "$*" >> {calls}\n{extra}'
        'out=""; while [ $# -gt 0 ]; do [ "$1" = --output ] && out=$2; shift; done\n'
        'echo \'{"dependencies": [], "fixes": []}\' > "$out"\n'
        + (
            f'case "$(cat {calls} | tail -1)" in *{advised}*) '
            f"echo '{finding}' > \"$out\"; exit 1;; esac\n"
            if advised
            else ""
        )
    )
    poetry.chmod(0o755)
    return calls


@pytest.mark.parametrize(
    ("advised", "refused"),
    [
        ("api.lock", True),
        ("frontend/requirements.lock", True),
        ("poetry.lock", True),
        ("", False),
    ],
    ids=["backend-advisory", "frontend-advisory", "host-advisory", "none"],
)
def test_the_audit_fails_on_an_advisory_in_any_lock(
    tmp_path: Path, advised: str, refused: bool
) -> None:
    """An advisory in any of the three locks fails it, and all are still read."""
    calls = _auditing(tmp_path, advised)

    ran = made("audit", "AUDIT_ACCEPTED=/dev/null", path=tmp_path)

    assert (ran.returncode != 0) is refused, ran
    assert len(calls.read_text().splitlines()) == 3, calls.read_text()


def test_the_audit_reads_the_host_lock_without_the_torch_it_cannot_resolve(
    tmp_path: Path,
) -> None:
    """poetry.lock is what CI and the host install; torch is a +cpu build there too."""
    seen = tmp_path / "seen"
    _auditing(
        tmp_path,
        extra=f'for f in "$@"; do case "$f" in *poetry.lock) cp "$f" {seen};; esac; done\n',
    )

    assert made("audit", "AUDIT_ACCEPTED=/dev/null", path=tmp_path).returncode == 0
    pins = seen.read_text().splitlines()

    assert any(pin.startswith("aiohttp==") for pin in pins), pins[:5]
    assert not [pin for pin in pins if pin.startswith(("torch==", "torchvision=="))]


def test_the_audit_reads_every_lock_against_osv(tmp_path: Path) -> None:
    """pip-audit's default, PyPI's own feed, missed three advisories OSV lists.

    On Pillow 12.3.0 it listed 18 of OSV's 21, a critical one left out.
    """
    calls = _auditing(tmp_path)

    assert made("audit", "AUDIT_ACCEPTED=/dev/null", path=tmp_path).returncode == 0
    audited = calls.read_text().splitlines()

    assert len(audited) == 3, audited
    assert all("--vulnerability-service osv" in call for call in audited), audited


def test_the_audit_reads_each_lock_as_pinned_without_pip(tmp_path: Path) -> None:
    """The pinned list read as it is, never installed through pip.

    --no-deps alone still installs it through pip, which a pin with no wheel
    for this platform fails: pywin32 on Linux, a CUDA wheel on a Mac.
    """
    calls = _auditing(tmp_path)

    assert made("audit", "AUDIT_ACCEPTED=/dev/null", path=tmp_path).returncode == 0
    audited = calls.read_text().splitlines()

    assert len(audited) == 3, audited
    assert all("--no-deps" in call and "--disable-pip" in call for call in audited), (
        audited
    )


@pytest.mark.parametrize("target", ["audit", "lock"])
def test_the_scratch_files_of_a_target_stay_out_of_the_source_tree(target: str) -> None:
    """An interrupted run would leave them untracked among the sources."""
    recipe = "\n".join(printed(target))

    assert "backend/api/requirements.lock." not in recipe, recipe
    assert "mktemp" in recipe and "trap" in recipe, recipe


@pytest.mark.parametrize(
    ("held", "failing", "refused", "generated"),
    [
        ((), "req", True, ["genrsa", "req"]),
        (("ca.key",), "", False, ["genrsa", "req", "genrsa", "req", "x509"]),
        (("ca.key", "elasticsearch.crt"), "", False, []),
    ],
    ids=["failed-step", "half-made", "made"],
)
def test_certs_stops_on_a_failed_step(
    tmp_path: Path, held: tuple[str, ...], failing: str, refused: bool, generated: list
) -> None:
    """And a certs/ a failed run left half-made is made again, not skipped.

    It ran every step whatever the one before did, printed that it wrote the
    certificates and passed, and the next run saw ca.key and skipped.
    """
    (tmp_path / "certs").mkdir()
    for name in held:
        (tmp_path / "certs" / name).write_text("")
    calls = tmp_path / "calls"
    (tmp_path / "openssl").write_text(
        f'#!/bin/sh\necho "$1" >> {calls}\n[ "$1" != "{failing}" ]\n'
    )
    (tmp_path / "openssl").chmod(0o755)
    generate = command("certs", "openssl genrsa")

    ran = subprocess.run(
        ["bash", "-c", generate],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran
    assert (calls.read_text().split() if calls.exists() else []) == generated, ran


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("printf '/var/log/qa/api-1.log\\n/var/log/qa/api-2.log\\n'", False),
        ("echo 'no container named api' >&2; exit 125", True),
    ],
    ids=["pruned", "stack-down"],
)
def test_logs_prune_fails_when_its_exec_fails(
    tmp_path: Path, answer: str, refused: bool
) -> None:
    """A stopped api counted as "0 file(s) deleted" and passed."""
    engine = stand_in(tmp_path, answer)
    prune = command("logs-prune", "exec -T api", COMPOSE=str(engine))

    ran = subprocess.run(
        ["bash", "-c", prune],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran
    if not refused:
        assert ran.stdout.startswith("2 file(s)"), ran


def test_both_spend_targets_agree_and_count_failed_calls(tmp_path: Path) -> None:
    """A call that failed after it was billed is spend too.

    `spend` read only lines that began with their timestamp and
    `spend-by-shape` read them anywhere, so the two totals of one log
    differed, and neither read a failed call's price.
    """
    import re

    log = tmp_path / "run.log"
    log.write_text(
        "2026-10-17T17:23:12 INFO    llm.client [trace=1 span=2] azure/gpt-4.1 "
        "answered _Facts in 0.4s (1,000 in, 100 out, $0.0028)\n"
        "2026-10-17T17:23:13 ERROR   llm.client [trace=1 span=3] azure/gpt-4.1 "
        "did not answer _Facts in 0.1s (3,000 in, 300 out, $0.0084)\n"
    )

    spend = made("spend", f"LOG={log}").stdout
    (total,) = [
        line.split()[1:]
        for line in made("spend-by-shape", f"LOG={log}").stdout.splitlines()
        if line.split()[:1] == ["TOTAL"]
    ]

    assert re.search(r"^calls\s+2$", spend, re.MULTILINE), spend
    assert re.search(r"^tokens\s+4000 in, 400 out$", spend, re.MULTILINE), spend
    assert re.search(r"^cost\s+\$0\.0112\b", spend, re.MULTILINE), spend
    assert total == ["2", "4000", "400", "0.0112"], total


def test_the_log_wipe_empties_files_rather_than_unlinking_them(tmp_path: Path) -> None:
    """A service's open handler goes on writing into the file Filebeat reads.

    Unlinked, the file vanished from under its writer, which went on
    appending to a name nothing could open until a restart or a rotation.
    """
    on_volume = command("logs-wipe", "/var/log/qa", ALL_DATABASES="1")
    assert "-delete" not in on_volume and "truncate -s 0" in on_volume, on_volume
    log = tmp_path / "logs" / "api-host-1.log"
    log.parent.mkdir()

    with log.open("a") as writer:
        writer.write("before\n")
        writer.flush()
        subprocess.run(
            ["bash", "-c", command("logs-wipe", "find logs", ALL_DATABASES="1")],
            cwd=tmp_path,
            check=True,
        )
        writer.write("after\n")
        writer.flush()

        assert log.read_text() == "after\n"


def test_the_log_wipe_takes_every_stream_grafana_reads() -> None:
    """The dated streams an earlier filebeat.yml wrote are `qa-logs*` too."""
    assert "_data_stream/qa-logs*" in command("logs-wipe", "_data_stream")


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("""echo '{"acknowledged":true}'""", False),
        ("""echo '{"error":{"type":"index_not_found_exception"}}'""", False),
        ("""echo '{"error":{"type":"security_exception"}}'""", True),
        ("echo 'no container named elasticsearch' >&2; exit 125", True),
    ],
    ids=["deleted", "nothing-there", "refused", "stack-down"],
)
def test_the_log_wipe_fails_unless_elasticsearch_deleted_or_had_nothing(
    tmp_path: Path, answer: str, refused: bool
) -> None:
    """A refusal or a stopped container is not "deleted"."""
    sandbox(tmp_path)
    engine = stand_in(tmp_path, answer)
    delete = command("logs-wipe", "_data_stream", COMPOSE=str(engine))

    ran = subprocess.run(
        ["bash", "-c", delete],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("echo 'Started sensor arrivals'; echo 'Stopped sensor arrivals'", False),
        ("echo 'Error: Could not find sensor arrivals'", True),
        ("echo 'Error: no container with name dagster-webserver' >&2; exit 125", True),
        ("true", True),
    ],
    ids=["switched", "dagster-refused", "stack-down", "said-nothing"],
)
@pytest.mark.parametrize("target", ["auto", "manual"])
def test_handing_over_fails_unless_dagster_switched_the_sensor(
    tmp_path: Path, target: str, answer: str, refused: bool
) -> None:
    """A failed switch used to print the same success as a real one."""
    engine = stand_in(tmp_path, answer)
    switch = command(target, "sensor ", COMPOSE=str(engine))

    ran = subprocess.run(
        ["bash", "-c", switch],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran


def test_all_brings_the_stack_up_waits_for_dagster_then_launches_the_corpus() -> None:
    """No host drain and no schema step: the container workers drain."""
    lines = printed("all")
    up = [at for at, line in enumerate(lines) if line.endswith(" up -d")]
    wait = [at for at, line in enumerate(lines) if "job list" in line]
    launch = [at for at, line in enumerate(lines) if "job launch -j corpus" in line]

    assert up and wait and launch, lines
    assert up[0] < wait[0] < launch[0], lines
    # `up` also sets Phoenix's retention, which is a call to Phoenix and not a drain.
    assert not [
        line
        for line in lines
        if ("python -m" in line and "telemetry.projects --retention" not in line)
        or "alembic" in line
    ]


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("echo 'Job: corpus'", False),
        ("echo 'Job: other'", True),
        ("echo 'Error: no container with name dagster-webserver' >&2; exit 125", True),
    ],
    ids=["listed", "not-listed", "stack-down"],
)
def test_all_waits_a_bounded_time_for_the_corpus_job(
    tmp_path: Path, answer: str, refused: bool
) -> None:
    """With `sleep` a no-op the wait ends at once, listed or not."""
    engine = stand_in(tmp_path, answer)
    (tmp_path / "sleep").write_text("#!/bin/sh\n")
    (tmp_path / "sleep").chmod(0o755)
    wait = command("all", "job list", COMPOSE=str(engine))

    ran = subprocess.run(
        ["bash", "-c", wait],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (ran.returncode != 0) is refused, ran


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("echo 'code server started'", False),
        ("echo 'DagsterInvariantViolationError: no job corpus'; exit 1", True),
        ("echo 'Error: no container with name dagster-webserver' >&2; exit 125", True),
    ],
    ids=["launched", "dagster-refused", "stack-down"],
)
def test_the_pipeline_fails_exactly_when_the_launch_fails(
    tmp_path: Path, answer: str, refused: bool
) -> None:
    """`dagster job launch` prints nothing on success; its exit status is the answer."""
    engine = stand_in(tmp_path, answer)
    launch = command("pipeline", "job launch", COMPOSE=str(engine))

    ran = subprocess.run(
        ["bash", "-c", launch],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran


def test_every_target_is_declared_phony() -> None:
    """A file of a target's name would otherwise make make skip it quietly."""
    import re

    makefile = (ROOT / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):(?!=)", makefile, re.MULTILINE))
    declared = re.search(r"^\.PHONY:((?:.*\\\n)*.*)$", makefile, re.MULTILINE)
    phony = set(declared[1].replace("\\\n", " ").split())

    assert len(targets) > 100, len(targets)
    assert not targets - phony, sorted(targets - phony)


def test_doctor_checks_the_served_catalog() -> None:
    """The api runs the image it was built from, and a checkout moves on."""
    assert any("python -m settings.drift" in line for line in printed("doctor"))


def test_the_balance_is_drawn_over_every_topic_whatever_narrows_it() -> None:
    """A draw narrowed to one topic replaced the release for all of them."""
    (drawing,) = [
        line for line in printed("questions-balance", "TOPIC=7") if "--balance" in line
    ]

    assert "--only" not in drawing, drawing


def test_the_rejudge_is_the_question_command_narrowed_like_the_reverify() -> None:
    """The one re-check that calls a model, wired as the free one is."""
    (judging,) = [
        line for line in printed("questions-rejudge", "TOPIC=7") if "--rejudge" in line
    ]

    assert "question_generation.run" in judging, judging
    assert "--only topic=7" in judging, judging


#: The Phoenix tables the run dashboard queries.
DASHBOARD_TABLES = ("projects", "traces", "spans", "span_costs", "span_annotations")


@pytest.mark.parametrize("target", ["up", "dev"])
def test_bringing_the_stack_up_grants_grafana_the_dashboards_phoenix_tables(
    target: str,
) -> None:
    """Phoenix makes its tables after the database's first boot."""
    granted = " ".join(printed(target))

    assert "GRANT SELECT ON " + ", ".join(DASHBOARD_TABLES) in granted, granted


def test_the_first_boot_grants_grafana_no_phoenix_table() -> None:
    """Everything it may read is granted by name, once the tables exist."""
    phoenix = (
        (ROOT / "configs/postgres/init.sh").read_text().split("Phoenix database")[1]
    )
    phoenix = phoenix.split("Dagster database")[0]

    assert "ON ALL TABLES" not in phoenix
    assert "DEFAULT PRIVILEGES" not in phoenix


def test_install_fetches_doclings_weights_where_the_hub_is_reachable() -> None:
    """parse-worker reads them offline, so a fresh volume failed every document.

    The fetch runs in a service that mounts parse-worker's cache volume and
    sits on no internal network.
    """
    (fetch,) = [line for line in printed("install") if "parsing.weights" in line]
    service = fetch.split(" run --rm --no-deps ")[1].split()[0]
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    internal = {
        name for name, network in compose["networks"].items() if network.get("internal")
    }
    fetcher, parser = compose["services"][service], compose["services"]["parse-worker"]
    cache = [volume for volume in parser["volumes"] if volume.startswith("models:")]

    assert cache and cache[0] in fetcher["volumes"], fetcher["volumes"]
    assert not internal & set(fetcher["networks"]), fetcher["networks"]


def test_ci_installs_without_the_container_engine() -> None:
    """A runner has no .env for compose to read, and its jobs need no volume."""
    action = yaml.safe_load((ROOT / ".github/actions/setup/action.yml").read_text())
    (step,) = [
        step
        for step in action["runs"]["steps"]
        if step.get("name") == "Install dependencies"
    ]
    lines = printed(step["run"].removeprefix("make "))

    assert any("poetry install" in line for line in lines), lines
    assert not [line for line in lines if "compose" in line], lines


@pytest.mark.parametrize(
    ("answer", "refused"),
    [("exit 0", False), ("exit 2", True)],
    ids=["ready", "never-ready"],
)
def test_dev_waits_a_bounded_time_for_postgres(
    tmp_path: Path, answer: str, refused: bool
) -> None:
    """With `sleep` a no-op the wait ends at once, and a database that never answers fails it."""
    engine = stand_in(tmp_path, answer)
    (tmp_path / "sleep").write_text("#!/bin/sh\n")
    (tmp_path / "sleep").chmod(0o755)
    wait = command("dev", "pg_isready", COMPOSE=str(engine))
    wait = wait.split("set +a && ", 1)[1]  # past the environment the recipe loads

    ran = subprocess.run(
        ["bash", "-c", wait],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (ran.returncode != 0) is refused, ran


#: Every target that destroys data in a database, as the arguments that make
#: it unnarrowed, and what it says it is refusing.
DESTRUCTIVE = {
    "schema-down": (),
    "schema-reset": (),
    "wipe": (),
    "wipe-all": (),
    "delete": ("SHA=abc",),
    "delete-derived": ("SHA=abc",),
    "topics-delete": (),
    "parse-rerun": (),
    "chunk-rerun": (),
    "extract-rerun": (),
    "questions-rerun": (),
    "assess-rerun": (),
    "archive-purge": ("ALL=1",),
    "restore-backup": ("DIR=/backups/x",),
    "phoenix-purge": (),
    "review-delete": (),
    "logs-wipe": (),
    "dagster-wipe": (),
}


#: What only the CONFIRM guard prints, as `REFUSED:` is also what the check that
#: the two database names agree prints, and every line that loads the settings
#: carries that.
GUARD = "Run it again with CONFIRM="


def sandbox(tmp_path: Path, name: str = "qa_generator") -> Path:
    """Env files naming a database, for a recipe line to be run against."""
    for path, text in {
        "configs/env/backend.env": "",
        "configs/env/deployment.env": f"APP_DB_NAME={name}\nPOSTGRES_PORT=5432\n",
        ".env": "",
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    return tmp_path


def refusal(line: str, tmp_path: Path, **environment: str):
    """Runs one recipe line in the sandbox."""
    return subprocess.run(
        ["bash", "-c", line],
        cwd=tmp_path,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("target", DESTRUCTIVE)
def test_a_destructive_target_refuses_unless_confirm_names_the_database(
    tmp_path: Path, target: str
) -> None:
    """The first line to act is the guard, and it names database and port."""
    sandbox(tmp_path)
    given = DESTRUCTIVE[target]
    lines = printed(target, *given)
    at = next((i for i, line in enumerate(lines) if GUARD in line), None)
    assert at is not None, lines
    acting = [
        i
        for i, line in enumerate(lines)
        if any(word in line for word in ("python -m", "alembic", "dagster run"))
    ]
    assert not acting or at < acting[0], lines

    ran = refusal(lines[at], tmp_path)
    assert ran.returncode == 2, ran
    assert "database qa_generator on localhost:5432" in ran.stderr, ran
    assert "CONFIRM=qa_generator" in ran.stderr, ran

    wrong = refusal(printed(target, *given, "CONFIRM=other")[at], tmp_path)
    assert wrong.returncode == 2, wrong

    right = refusal(printed(target, *given, "CONFIRM=qa_generator")[at], tmp_path)
    assert right.returncode == 0, right


@pytest.mark.parametrize(
    ("target", "given"),
    [
        ("chunk-rerun", "SHA=abc"),
        ("extract-rerun", "PASSAGE=7"),
        ("parse-rerun", "SHA=abc"),
        ("questions-rerun", "TOPIC=3"),
        ("assess-rerun", "TOPIC=3"),
    ],
)
def test_a_narrowed_rerun_needs_no_confirmation(target: str, given: str) -> None:
    """Only the unnarrowed one reaches the whole corpus."""
    assert not any(GUARD in line for line in printed(target, given))


@pytest.mark.parametrize("target", [*DRAINS, *REWRITES])
def test_a_drain_names_its_database_and_port(tmp_path: Path, target: str) -> None:
    """Printed before the drain starts, from the settings the drain will read."""
    sandbox(tmp_path, "qa_scratch")
    lines = printed(target)
    banner = next(
        i for i, line in enumerate(lines) if "on database $db on $host" in line
    )
    assert banner < next(i for i, line in enumerate(lines) if "python -m" in line)
    ran = refusal(lines[banner], tmp_path)
    assert "on database qa_scratch on localhost:5432" in ran.stderr, ran


@pytest.mark.parametrize(
    "target", [("settings", "SERVICE=platform"), ("review-status",)]
)
def test_an_exported_database_name_is_honoured_not_replaced(
    tmp_path: Path, target: tuple[str, ...]
) -> None:
    """deployment.env says qa_generator; a shell that exported another meant it."""
    sandbox(tmp_path)
    (tmp_path / "configs/env/review.env").write_text("")
    (tmp_path / "poetry").write_text('#!/bin/sh\necho "$APP_DB_NAME $DATABASE_URL"\n')
    (tmp_path / "poetry").chmod(0o755)
    (line,) = [
        one for one in printed(*target, APP_DB_NAME="qa_fx_copy") if "poetry run" in one
    ]

    ran = refusal(
        line,
        tmp_path,
        APP_DB_NAME="qa_fx_copy",
        APP_DB_USER="u",
        APP_DB_PASSWORD="p",
        PATH=f"{tmp_path}:{os.environ['PATH']}",
    )
    assert ran.stdout.split()[0] == "qa_fx_copy", ran
    assert ran.stdout.strip().endswith("/qa_fx_copy"), ran

    (bare,) = [one for one in printed(*target) if "poetry run" in one]
    unset = refusal(
        bare,
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        APP_DB_USER="u",
        APP_DB_PASSWORD="p",
    )
    assert unset.stdout.split()[0] == "qa_generator", unset


def test_the_log_wipe_deletes_by_database_unless_every_database_is_meant() -> None:
    """One data stream serves every database: a wipe deletes its own lines."""
    own = command("logs-wipe", "_data_stream")
    assert '-e WIPE_DB="$db"' in own and "WIPE_ALL=1" not in own, own
    assert "_delete_by_query" in own and '\\"db\\":\\"$WIPE_DB' in own, own

    every = command("logs-wipe", "_data_stream", ALL_DATABASES="1")
    assert "-e WIPE_ALL=1" in every and "-e WIPE_DB" not in every, every


def test_the_shared_log_files_are_left_unless_every_database_is_meant() -> None:
    """Emptied, they would take the other databases' unshipped lines."""
    left = command("logs-wipe", "find logs")
    assert '[ "" = 1 ]' in left, left
    assert '[ "1" = 1 ]' in command("logs-wipe", "find logs", ALL_DATABASES="1")


def test_the_dagster_wipe_takes_only_the_runs_tagged_with_the_database() -> None:
    """`dagster run wipe` takes the instance's whole history: ALL_DATABASES only."""
    own = command("dagster-wipe", "dagster-webserver")
    assert "python -m orchestration.wipe" in own and "run wipe" not in own, own
    assert '-e APP_DB_NAME="$APP_DB_NAME"' in own, own
    assert "run wipe --force" in command(
        "dagster-wipe", "dagster-webserver", ALL_DATABASES="1"
    )


@pytest.mark.parametrize("target", ["phoenix-purge", "phoenix-prune"])
def test_the_phoenix_purge_takes_only_this_databases_projects(target: str) -> None:
    """The other databases' traces are on the same Phoenix."""
    (own,) = [one for one in printed(target) if "telemetry.projects" in one][:1]
    assert "--all-databases" not in own, own
    (every,) = [
        one for one in printed(target, "ALL_DATABASES=1") if "telemetry.projects" in one
    ][:1]
    assert "--all-databases" in every, every


#: The five databases a backup dumps, by the settings that name them.
DATABASES = (
    "APP_DB_NAME",
    "SEAWEEDFS_DB_NAME",
    "PHOENIX_DB_NAME",
    "DAGSTER_DB_NAME",
    "ARGILLA_DB_NAME",
)


@pytest.mark.parametrize("target", ["backup", "restore-backup", "restore-backup-stack"])
def test_a_backup_target_names_a_directory(target: str) -> None:
    """Without one it says how to call it and does nothing."""
    first = printed(target)[0]
    assert "usage: make" in first and "exit 2" in first, first


def test_a_backup_dumps_the_five_databases_and_copies_no_secret() -> None:
    """pg_dump of each, the objects and a manifest: never .env, provider.env or a key."""
    lines = printed("backup", "DIR=/backups/x", "ARGILLA=1")
    text = "\n".join(lines)
    for name in DATABASES:
        assert f"${name}" in text, name
    assert "pg_dump -Fc" in text and "archive.backup --backup" in text, text
    for forbidden in (" cp ", "rsync", "tar ", 'provider.env"', "certs/", ".key"):
        assert forbidden not in text.replace(". ./.env", "").replace(
            "./configs/env/provider.env", ""
        ), forbidden


def test_a_restore_refuses_while_a_worker_runs_and_checks_the_manifest() -> None:
    """The workers first, CONFIRM second, pg_restore of the five, the manifest last."""
    lines = printed("restore-backup-stack", "DIR=/backups/x", "CONFIRM=stack")
    text = "\n".join(lines)
    at = {
        part: text.index(part)
        for part in (
            "ps -q parse-worker",
            "ps -q assess-worker",
            "Run it again with CONFIRM=stack",
            "pg_restore --clean",
            "archive.backup --restore",
        )
    }
    assert list(at.values()) == sorted(at.values()), at
    for name in DATABASES:
        assert f"${name}" in text, name


def test_a_wipe_checks_every_store_before_it_deletes_anything() -> None:
    """A wrong key found after the third deletion leaves a corpus half gone."""
    lines = printed("wipe", CONFIRM="x")
    asked = [at for at, line in enumerate(lines) if "telemetry.projects --list" in line]
    deletes = [
        at
        for at, line in enumerate(lines)
        if "--delete-all" in line or "--delete" in line
    ]

    assert asked and deletes, lines
    assert asked[0] < deletes[0], lines


@pytest.mark.parametrize(
    "asked",
    [
        "telemetry.projects --list",
        "review.run --check",
        "_cluster/health",
        "dagster run list",
    ],
)
def test_the_wipe_preflight_asks_each_store_only_while_its_service_runs(
    asked: str,
) -> None:
    """A store whose profile is down is skipped with a note, not failed."""
    joined = "\n".join(printed("wipe-preflight")).replace("\\\n", "")
    (guarded,) = [one for one in joined.split("; fi") if asked in one]
    assert "ps -q" in guarded, guarded


def test_the_wipe_preflight_refuses_naming_the_store_that_did_not_answer(
    tmp_path: Path,
) -> None:
    """Everything runs, Elasticsearch refuses: one actionable line, exit non-zero."""
    engine = stand_in(
        tmp_path,
        'case "$*" in *"ps -q"*) echo 4f1c2a9e;; *_cluster/health*) exit 22;; *) ;; esac',
    )
    done = made("wipe-preflight", f"COMPOSE={engine}")
    assert done.returncode != 0, done
    assert "elasticsearch" in done.stderr.lower(), done.stderr


def test_the_wipe_preflight_passes_when_no_store_runs(tmp_path: Path) -> None:
    """A stack that is down has nothing to authenticate to, and says so."""
    engine = stand_in(tmp_path, "exit 0")
    done = made("wipe-preflight", f"COMPOSE={engine}")
    assert done.returncode == 0, done
    assert "not running" in done.stdout, done.stdout


#: The wipe's four steps beyond the database, by the service each one reaches.
WIPE_STEPS = {
    "phoenix": "phoenix-purge",
    "argilla": "review-delete",
    "elasticsearch": "logs-wipe",
    "dagster-webserver": "dagster-wipe",
}


@pytest.mark.parametrize(("service", "step"), WIPE_STEPS.items())
def test_a_store_that_is_down_is_skipped_by_the_preflight_and_by_the_wipe(
    service: str, step: str, tmp_path: Path
) -> None:
    """The preflight must not pass a store whose step the wipe then runs and fails on."""
    engine = stand_in(tmp_path, "exit 0")
    note = made("wipe-preflight", f"COMPOSE={engine}").stdout
    (said,) = [line for line in note.splitlines() if line.startswith(f"{service} ")]
    assert step in said, said

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "make").write_text('#!/bin/sh\necho "RAN $*"\n')
    (fake / "make").chmod(0o755)

    def wiped(compose: Path) -> str:
        """What the wipe's line for this step prints when it is run, with a stand-in make."""
        lines = printed("wipe", f"COMPOSE={compose}", f"MAKE={fake}/make", CONFIRM="x")
        (guarded,) = [line for line in lines if f"/make {step}" in line]
        ran = subprocess.run(
            ["bash", "-c", guarded],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert ran.returncode == 0, ran
        return ran.stdout

    assert "RAN" not in wiped(engine) and said in wiped(engine)
    up = stand_in(tmp_path, 'case "$*" in *"ps -q"*) echo 4f1c2a9e;; esac')
    assert f"RAN {step}" in wiped(up)


def test_doctor_prints_what_the_archive_holds() -> None:
    """The archive grows with every rerun; nobody looks unless doctor does."""
    assert any("archive.run --size" in line for line in printed("doctor"))


def test_a_restore_of_one_database_restores_that_database_alone() -> None:
    """Phoenix, Dagster, Argilla and the SeaweedFS filer are shared by every database: not rolled back."""
    text = "\n".join(
        printed("restore-backup", "DIR=/backups/x", "CONFIRM=qa_generator")
    )
    assert "pg_restore --clean" in text and "$APP_DB_NAME" in text, text
    for shared in (
        "SEAWEEDFS_DB_NAME",
        "PHOENIX_DB_NAME",
        "DAGSTER_DB_NAME",
        "ARGILLA_DB_NAME",
    ):
        assert shared not in text, shared
    assert "--stack" not in text, text


def test_the_stack_restore_names_what_it_rolls_back_and_refuses_beside_other_databases() -> (
    None
):
    """CONFIRM=stack, and more than one application database refuses unless ALL_DATABASES=1."""
    first = printed("restore-backup-stack")[0]
    assert "usage: make" in first and "exit 2" in first, first
    text = "\n".join(printed("restore-backup-stack", "DIR=/backups/x", "CONFIRM=stack"))
    for name in DATABASES:
        assert f"${name}" in text, name
    assert "archive.backup --restore" in text and "--stack" in text, text
    assert "ALL_DATABASES" in text and "pg_database" in text, text
    assert "rolls back" in text, text


def test_a_backup_leaves_out_the_argilla_dump_unless_asked() -> None:
    """Argilla's database holds the owner's API key in clear: no secret in a backup by default."""
    own = "\n".join(printed("backup", "DIR=/backups/x"))
    assert "$$ARGILLA_DB_NAME" not in own and "$ARGILLA_DB_NAME" not in own, own
    asked = "\n".join(printed("backup", "DIR=/backups/x", "ARGILLA=1"))
    assert "$ARGILLA_DB_NAME" in asked, asked
    for name in DATABASES[:-1]:
        assert f"${name}" in own, name


def test_the_stack_restore_skips_a_dump_the_backup_did_not_take() -> None:
    """A backup without Argilla's dump restores without it."""
    text = "\n".join(printed("restore-backup-stack", "DIR=/backups/x", "CONFIRM=stack"))
    assert "continue" in text and "ARGILLA_DB_NAME" in text, text


def test_a_purge_of_one_tables_archive_needs_confirmation_like_the_others(
    tmp_path: Path,
) -> None:
    """TABLE= is as irreversible as DAYS= and ALL=1: it is the second deletion of a whole table."""
    sandbox(tmp_path)
    (line,) = [
        one for one in printed("archive-purge", "TABLE=questions") if GUARD in one
    ]
    assert refusal(line, tmp_path).returncode == 2
    with_confirm = printed("archive-purge", "TABLE=questions", "CONFIRM=qa_generator")
    (line,) = [one for one in with_confirm if GUARD in one]
    assert refusal(line, tmp_path).returncode == 0


def test_no_text_still_says_a_rerun_deletes_questions_it_now_rejects() -> None:
    """A re-chunk, a bridge replacement and a lost fact reject as source_changed and keep the question."""
    stale = "rejected or deleted"
    for path in (
        "Makefile",
        "docs/operations.md",
        "docs/make.md",
        "backend/extraction/README.md",
        "backend/extraction/service.py",
    ):
        assert stale not in (ROOT / path).read_text(), path


def test_restore_documents_lists_transactions_not_minutes() -> None:
    """Without SINCE it lists the newest deleting transactions."""
    assert "20 newest minutes" not in (ROOT / "docs/make.md").read_text()


def test_a_wipe_of_one_database_takes_only_its_phoenix_datasets() -> None:
    """The golden datasets and their experiments are on the Phoenix every database shares."""
    own = [
        one
        for one in printed("phoenix-purge")
        if "--purge-datasets" in one and "telemetry.projects" in one
    ]
    every = [
        one
        for one in printed("phoenix-purge", "ALL_DATABASES=1")
        if "--purge-datasets" in one and "telemetry.projects" in one
    ]
    assert own and every
    assert all("--all-databases" not in one for one in own), own
    assert all("--all-databases" in one for one in every), every


def test_a_backup_says_before_it_dumps_that_running_workers_make_it_inconsistent() -> (
    None
):
    """The dumps, the objects and the row counts are three moments while a worker writes."""
    lines = printed("backup", "DIR=/backups/x")
    said = next(
        (at for at, one in enumerate(lines) if "different moments" in one), None
    )
    dumped = next(at for at, one in enumerate(lines) if "pg_dump" in one)
    assert said is not None and said < dumped, lines


@pytest.mark.parametrize(
    ("target", "given"),
    [
        ("restore-backup", ("CONFIRM=qa_generator",)),
        ("restore-backup-stack", ("CONFIRM=stack",)),
    ],
)
def test_a_restore_keeps_the_owners_the_dump_carries(target: str, given) -> None:
    """--no-owner as the superuser makes it own every table and leaves the application role none."""
    text = "\n".join(printed(target, "DIR=/backups/x", *given))
    assert "pg_restore --clean --if-exists --single-transaction -U" in text, text
    assert "--no-owner" not in text, text


@pytest.mark.parametrize("target", ["wipe", "schema-reset", "topics-delete"])
def test_a_confirm_exported_in_the_shell_does_not_satisfy_the_guard(
    tmp_path: Path, target: str
) -> None:
    """Only a CONFIRM typed on the command line counts: an exported one confirms every later target."""
    sandbox(tmp_path)
    lines = printed(target, CONFIRM="qa_generator")
    at = next(i for i, line in enumerate(lines) if GUARD in line)

    ran = refusal(lines[at], tmp_path, CONFIRM="qa_generator")

    assert ran.returncode == 2, ran


@pytest.mark.parametrize(
    "target", ["extract-bridge", "questions-reverify", "questions-rejudge"]
)
def test_a_rewriting_host_command_names_the_database_it_acts_on(target: str) -> None:
    """The banner comes before the command that rewrites rows."""
    lines = printed(target)
    banner = next((at for at, one in enumerate(lines) if "on database" in one), None)
    acting = next(at for at, one in enumerate(lines) if "python -m" in one)
    assert banner is not None and banner < acting, lines


def test_a_backup_is_written_readable_by_its_owner_alone() -> None:
    """Every line that writes under DIR does it under umask 077.

    The dumps hold every row and the Argilla dump the owner's API key in
    clear; the objects are every customer document. Each recipe line is a
    shell of its own, so one line's umask covers no other.
    """
    lines = printed("backup", "DIR=/backups/x", "ARGILLA=1")
    commands = "\n".join(lines).replace("\\\n", " ").splitlines()
    writing = [
        one
        for one in commands
        if any(verb in one for verb in ("mkdir", "pg_dump", "archive.backup --backup"))
    ]

    assert any("mkdir" in one for one in writing), lines
    assert any("pg_dump" in one for one in writing), lines
    assert any("archive.backup --backup" in one for one in writing), lines
    for one in writing:
        assert "umask 077" in one, one
    assert any('chmod 700 "/backups/x"' in one for one in writing), lines


def test_the_stack_restore_says_what_it_rolls_back_and_what_it_does_not() -> None:
    """The other databases keep their rows; their objects go back to the backup's."""
    text = "\n".join(printed("restore-backup-stack", "DIR=/backups/x"))
    assert "keep their rows" in text and "objects" in text, text
    assert "rolls back all of them" not in text, text


@pytest.mark.parametrize("target", ["restore-backup", "restore-backup-stack"])
def test_a_restore_is_one_transaction(target: str) -> None:
    """An error part-way must not leave the database half restored."""
    given = (
        ("CONFIRM=qa_generator",) if target == "restore-backup" else ("CONFIRM=stack",)
    )
    text = "\n".join(printed(target, "DIR=/backups/x", *given))
    assert "--single-transaction" in text, text


def test_logs_wipe_deletes_by_an_exact_term_on_the_db_field() -> None:
    """match_phrase on the analysed field matched qa-fx-2's lines for qa-fx."""
    text = "\n".join(printed("logs-wipe", "CONFIRM=qa_generator")).replace("\\", "")
    assert "match_phrase" not in text, text
    assert '"term":{"db":' in text and '"db.keyword"' in text, text


@pytest.mark.parametrize(
    ("path", "stale"),
    [
        ("docs/operations.md", "questions resting on it go into the archive"),
        ("docs/operations.md", "and the questions on them."),
        ("docs/operations.md", "questions resting on it go with it, into the archive"),
        ("docs/make.md", "restore-documents SINCE=<time>` puts them back"),
        ("docs/make.md", "and every dataset. What `make wipe` runs"),
        ("Makefile", "so it warns and waits first"),
        ("Makefile", "Every project this database filed AND every dataset"),
        ("review/service.py", "already says what it is about to do and waits"),
    ],
)
def test_no_text_keeps_a_claim_the_branch_made_false(path: str, stale: str) -> None:
    """Questions are rejected and kept, an unnarrowed rerun refuses without CONFIRM, a purge is this database's."""
    assert stale not in (ROOT / path).read_text(), path


def run_for_real(
    tmp_path: Path, *arguments: str
) -> tuple[subprocess.CompletedProcess, str]:
    """A target run in a copy of the Makefile with a compose and a poetry that only log their arguments."""
    sandbox(tmp_path)
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text())
    log = tmp_path / "log"
    log.write_text("")
    for name in ("compose", "poetry"):
        stand = tmp_path / name
        stand.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit 0\n')
        stand.chmod(0o755)
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    environment["PATH"] = f"{tmp_path}:{environment['PATH']}"
    ran = subprocess.run(
        [
            "make",
            "--no-print-directory",
            f"COMPOSE={tmp_path}/compose",
            *arguments,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return ran, log.read_text()


def test_dagster_wipe_leaves_the_runs_when_keep_names_them(tmp_path: Path) -> None:
    """The line read as (SPARED || set -a) && ... and deleted what it said it left."""
    ran, log = run_for_real(
        tmp_path, "dagster-wipe", "CONFIRM=qa_generator", "KEEP=runs"
    )
    assert ran.returncode == 0, ran
    assert "leaving the Dagster run history" in ran.stdout, ran
    assert "orchestration.wipe" not in log, log

    ran, log = run_for_real(tmp_path, "dagster-wipe", "CONFIRM=qa_generator")
    assert "orchestration.wipe" in log, (ran, log)


def test_a_stack_restore_confirmed_in_the_shell_is_refused(tmp_path: Path) -> None:
    """CONFIRM=stack counts only from the command line, as it does for every other guard."""
    sandbox(tmp_path)
    lines = printed("restore-backup-stack", "DIR=/backups/x", CONFIRM="stack")
    (line,) = [one for one in lines if "Run it again with CONFIRM=stack" in one]

    assert refusal(line, tmp_path, CONFIRM="stack").returncode == 2


def test_down_volumes_refuses_without_confirm_all_volumes() -> None:
    """It deletes every database's volumes, so a five-second pause is not a guard."""
    lines = printed("down-volumes")
    assert any("REFUSED:" in one and "all-volumes" in one for one in lines), lines
    assert not any("sleep 5" in one for one in lines), lines
    ran = [
        one
        for one in printed("down-volumes", "CONFIRM=all-volumes")
        if "down -v" in one
    ]
    assert ran, "the command is still there once confirmed"


def probe(
    tmp_path: Path, recipe: str, *given: str, env_text: str = "", **environment: str
):
    """Runs `recipe` through the repository's own LOADENV and CONFIRMED, in a scratch makefile.

    Nothing destructive runs: the recipe only echoes. ENV_FILE is a scratch file
    that holds `env_text`, as an operator's secrets file would.
    """
    env_file = tmp_path / "scratch.env"
    env_file.write_text("APP_DB_PASSWORD=x\n" + env_text)
    scratch = tmp_path / "probe.mk"
    scratch.write_text(f"include {ROOT}/Makefile\nprobe:\n\t@{recipe}\n")
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE")
        and name not in {"MFLAGS", "APP_DB_NAME", "CONFIRM"}
    }
    return subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            str(scratch),
            "probe",
            f"ENV_FILE={env_file}",
            *given,
        ],
        cwd=ROOT,
        env={**inherited, **environment},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


GUARDED = "$(call CONFIRMED,probe) && echo went-on"


def test_the_guard_refuses_without_confirm_and_goes_on_with_it(tmp_path: Path) -> None:
    """The control: a named database still needs its name typed."""
    assert probe(tmp_path, GUARDED).returncode == 2
    done = probe(tmp_path, GUARDED, "CONFIRM=qa_generator")
    assert done.returncode == 0 and "went-on" in done.stdout, done


@pytest.mark.parametrize("given", [("APP_DB_NAME=",), ("APP_DB_NAME=", "CONFIRM=")])
def test_an_empty_database_name_is_refused_with_or_without_confirm(
    tmp_path: Path, given: tuple[str, ...]
) -> None:
    """Both sides of the comparison were empty, so it passed and libpq took the user's namesake."""
    done = probe(tmp_path, GUARDED, *given)
    assert done.returncode == 2 and "REFUSED" in done.stderr, done
    assert "went-on" not in done.stdout, done


@pytest.mark.parametrize(
    ("url", "confirm", "goes_on"),
    [
        ("postgresql+psycopg://u:p@bank.example.net:5432/ledger", "ledger", True),
        (
            "postgresql+psycopg://u:p@bank.example.net:5432/ledger?sslmode=require",
            "ledger",
            True,
        ),
        (
            "postgresql+psycopg://u:p@bank.example.net:5432/ledger",
            "qa_generator",
            False,
        ),
        ("postgresql+psycopg://u:p@bank.example.net:5432/", "", False),
        ("postgresql+psycopg://u:p@bank.example.net:5432/?sslmode=require", "", False),
    ],
)
def test_the_guard_compares_confirm_with_the_database_the_url_names(
    tmp_path: Path, url: str, confirm: str, goes_on: bool
) -> None:
    """APP_DB_NAME alone said nothing about a DATABASE_URL the env file brought."""
    named = url.split("/", 3)[3].split("?")[0]
    done = probe(
        tmp_path,
        GUARDED,
        f"CONFIRM={confirm}",
        f"APP_DB_NAME={named}",
        env_text=f"DATABASE_URL={url}\n",
    )
    assert ("went-on" in done.stdout) is goes_on, done
    assert done.returncode == (0 if goes_on else 2), done


def test_the_refusal_names_the_database_the_url_names(tmp_path: Path) -> None:
    """The operator is told which name to type."""
    done = probe(
        tmp_path,
        GUARDED,
        "APP_DB_NAME=orders",
        env_text="DATABASE_URL=postgresql+psycopg://u:p@shop.example.net/orders\n",
    )
    assert "orders" in done.stderr and "CONFIRM=orders" in done.stderr, done


REMOTE = {
    "DATABASE_URL": "postgresql+psycopg://u:p@pg.example.net:5432/ledger?sslmode=require",
    "S3_ENDPOINT": "https://s3.eu-central-1.example.net",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.net:4317",
    "PHOENIX_BASE_URL": "https://phoenix.example.net",
    "BACKEND_URL": "https://api.example.net",
    "ARGILLA_API_URL": "https://review.example.net",
}


@pytest.mark.parametrize("name", sorted(REMOTE))
def test_a_host_command_keeps_the_address_the_env_file_names(
    tmp_path: Path, name: str
) -> None:
    """The address was rebuilt from localhost after the env file was read, so no remote service was reachable."""
    done = probe(
        tmp_path,
        f'$(LOADENV) && echo "$${name}"',
        "APP_DB_NAME=ledger",
        env_text=f"{name}={REMOTE[name]}\n",
    )
    assert done.stdout.strip() == REMOTE[name], done


def test_an_address_the_env_file_leaves_out_is_still_built_from_the_port(
    tmp_path: Path,
) -> None:
    """Only the addresses the env file names are kept."""
    done = probe(
        tmp_path,
        '$(LOADENV) && echo "$$S3_ENDPOINT $$BACKEND_URL $$DATABASE_URL"',
        env_text=f"S3_ENDPOINT={REMOTE['S3_ENDPOINT']}\nBACKEND_PORT=8123\nPOSTGRES_PORT=5999\n",
    )
    s3, backend, database = done.stdout.split()
    assert s3 == REMOTE["S3_ENDPOINT"], done
    assert backend == "http://localhost:8123", done
    assert database.endswith("@localhost:5999/qa_generator"), done


FAKE_COMPOSE = """#!/bin/bash
args=("$@"); wipe=; every=; script=
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    -e) kv="${args[$((i+1))]}"
        case "$kv" in WIPE_DB=*) wipe="${kv#WIPE_DB=}";; WIPE_ALL=*) every="${kv#WIPE_ALL=}";; esac ;;
    -c) script="${args[$((i+1))]}" ;;
  esac
done
WIPE_DB="$wipe" WIPE_ALL="$every" ELASTIC_PASSWORD=x PATH="$FAKE_BIN:$PATH" sh -c "$script"
"""

FAKE_CURL = """#!/bin/bash
printf '%s\\n' "$*" >> "$CURL_LOG"
echo '{"acknowledged":true}'
"""


def asked_of_logs_wipe(tmp_path: Path, *given: str, env_text: str = "") -> str:
    """What curl was asked when logs-wipe runs against a compose and a curl that only record."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("compose", FAKE_COMPOSE), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    env_file = tmp_path / "scratch.env"
    env_file.write_text("APP_DB_PASSWORD=x\n" + env_text)
    log = tmp_path / "curl.log"
    log.unlink(missing_ok=True)
    subprocess.run(
        [
            "make",
            "--no-print-directory",
            "logs-wipe",
            f"COMPOSE={bin_dir / 'compose'}",
            f"ENV_FILE={env_file}",
            *given,
        ],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "FAKE_BIN": str(bin_dir),
            "CURL_LOG": str(log),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return log.read_text() if log.exists() else ""


def test_logs_wipe_deletes_the_lines_of_the_database_the_url_names(
    tmp_path: Path,
) -> None:
    """The lines of the database DATABASE_URL names, not of APP_DB_NAME."""
    asked = asked_of_logs_wipe(
        tmp_path,
        "APP_DB_NAME=ledger",
        "CONFIRM=ledger",
        env_text="DATABASE_URL=postgresql+psycopg://u:p@pg.example.net/ledger\n",
    )
    assert "_delete_by_query" in asked and '"ledger"' in asked, asked
    assert "_data_stream" not in asked, asked


def test_logs_wipe_with_an_empty_database_name_asks_for_nothing(tmp_path: Path) -> None:
    """It read an empty name as every database's stream."""
    assert asked_of_logs_wipe(tmp_path, "APP_DB_NAME=") == ""
    assert asked_of_logs_wipe(tmp_path, "APP_DB_NAME=", "CONFIRM=") == ""


def test_logs_wipe_takes_every_stream_only_when_asked_to(tmp_path: Path) -> None:
    """ALL_DATABASES=1 is the one way to the every-database stream."""
    every = asked_of_logs_wipe(tmp_path, "CONFIRM=qa_generator", "ALL_DATABASES=1")
    assert "-X DELETE" in every and "_data_stream/qa-logs*" in every, every
    (tmp_path / "again").mkdir()
    named = asked_of_logs_wipe(tmp_path / "again", "CONFIRM=qa_generator")
    assert "_data_stream" not in named, named


@pytest.mark.parametrize("written", [".env", "configs/env/provider.env"])
@pytest.mark.parametrize("umask", ["022", "002"])
def test_setup_writes_secrets_for_the_owner_alone(
    tmp_path: Path, written: str, umask: str
) -> None:
    """Every password, the token and the provider's key were readable by every local account."""
    for one in (
        "Makefile",
        ".env.example",
        "configs/env/provider.env.example",
        "configs/env/backend.env",
        "configs/env/deployment.env",
    ):
        (tmp_path / one).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / one, tmp_path / one)
    done = subprocess.run(
        ["bash", "-c", f"umask {umask} && make --no-print-directory setup"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
    )

    assert done.returncode == 0, done.stderr
    mode = stat.S_IMODE((tmp_path / written).stat().st_mode)
    assert not mode & 0o077, f"make setup left {written} at {oct(mode)}"


def test_doctor_warns_about_a_secrets_file_other_accounts_can_read() -> None:
    """The check names the file and the fix."""
    recipe = "\n".join(printed("doctor"))

    assert "readable by other accounts" in recipe
    assert "chmod 600" in recipe


ADDRESSES = [
    "DATABASE_URL",
    "BACKEND_URL",
    "S3_ENDPOINT",
    "PHOENIX_BASE_URL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "ARGILLA_API_URL",
]


def test_doctor_says_where_each_address_came_from(tmp_path: Path) -> None:
    """One line each: the env file, the environment, the command line, or the ports."""
    done = probe(
        tmp_path,
        "$(ORIGINS)",
        "BACKEND_URL=https://api.example.net",
        env_text="DATABASE_URL=postgresql+psycopg://u:p@pg.example.net/ledger\n",
        S3_ENDPOINT="https://s3.example.net",
    )

    said = dict(line.split(": ", 1) for line in done.stdout.strip().splitlines())
    assert list(said) == ADDRESSES, done
    assert said["DATABASE_URL"] == "scratch.env", done
    assert said["S3_ENDPOINT"] == "the environment", done
    assert said["BACKEND_URL"] == "the command line", done
    for name in ADDRESSES[3:]:
        assert said[name] == "built from the ports", done


def test_the_origin_lines_never_print_an_address(tmp_path: Path) -> None:
    """An address may carry a password."""
    done = probe(
        tmp_path,
        "$(ORIGINS)",
        env_text="DATABASE_URL=postgresql+psycopg://u:hunter2@pg.example.net/ledger\n",
    )

    assert len(done.stdout.splitlines()) == len(ADDRESSES), done
    assert "hunter2" not in done.stdout and "pg.example.net" not in done.stdout


def test_doctor_prints_the_origins() -> None:
    """The recipe runs them."""
    assert "built from the ports" in "\n".join(printed("doctor"))


#: A compose that only records its arguments, and answers `ps` empty.
RECORDING_COMPOSE = """#!/bin/bash
printf '%s\\n' "$*" >> "$COMPOSE_LOG"
for a in "$@"; do [ "$a" = ps ] && exit 0; done
for a in "$@"; do [ "$a" = postgres ] && exit 1; done
exit 0
"""

#: A managed database an operator names in ENV_FILE or the shell, beside the stack's own.
MANAGED = "postgresql+psycopg://u:p@managed.example.net:5432/faq_prod"


def run_target(
    tmp_path: Path, target: str, *given: str, env_text: str = "", **environment: str
):
    """Runs one target against a compose that records; returns (result, its arguments)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "compose").write_text(RECORDING_COMPOSE)
    (bin_dir / "compose").chmod(0o755)
    env_file = tmp_path / "scratch.env"
    env_file.write_text("APP_DB_PASSWORD=x\n" + env_text)
    log = tmp_path / "compose.log"
    log.unlink(missing_ok=True)
    done = subprocess.run(
        [
            "make",
            "--no-print-directory",
            target,
            f"COMPOSE={bin_dir / 'compose'}",
            f"ENV_FILE={env_file}",
            *given,
        ],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "COMPOSE_LOG": str(log),
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return done, (log.read_text() if log.exists() else "")


def backup_directory(tmp_path: Path) -> Path:
    """A directory `make restore-backup` accepts, holding a dump of each database."""
    directory = tmp_path / "bk"
    (directory / "db").mkdir(parents=True)
    (directory / "manifest.json").write_text("{}")
    for name in ("qa_generator", "faq_prod", "qa_scratch"):
        (directory / "db" / f"{name}.dump").write_text("")
    return directory


def given_url(where: str) -> dict:
    """DATABASE_URL named in ENV_FILE, or in the environment."""
    return (
        {"env_text": f"DATABASE_URL={MANAGED}\n"}
        if where == "env_file"
        else {"DATABASE_URL": MANAGED}
    )


@pytest.mark.parametrize("where", ["env_file", "environment"])
@pytest.mark.parametrize(
    "target",
    [
        "restore-backup",
        "dagster-wipe",
        "backup",
        "schema",
        "topics-discover",
        "review-pull-facts",
        "eval-score",
    ],
)
def test_a_url_naming_another_database_than_app_db_name_is_refused(
    tmp_path: Path, where: str, target: str
) -> None:
    """Both names must be one, or a target confirms one database and acts on the other."""
    directory = backup_directory(tmp_path)
    if target == "backup":
        directory = tmp_path / "fresh"
    arguments = [f"DIR={directory}", "CONFIRM=faq_prod"]
    done, asked = run_target(tmp_path, target, *arguments, **given_url(where))

    assert done.returncode == 2, done
    assert "DATABASE_URL names faq_prod but APP_DB_NAME is qa_generator" in done.stderr
    assert "APP_DB_NAME=faq_prod" in done.stderr
    assert "pg_restore" not in asked and "orchestration.wipe" not in asked, asked


@pytest.mark.parametrize("where", ["env_file", "environment", "command_line"])
@pytest.mark.parametrize("target", ["backup", "restore-backup", "restore-backup-stack"])
def test_a_target_run_inside_the_stacks_postgres_refuses_another_host(
    tmp_path: Path, where: str, target: str
) -> None:
    """pg_dump and pg_restore run in the container, so a managed URL is not theirs to act on."""
    directory = backup_directory(tmp_path)
    if target == "backup":
        directory = tmp_path / "fresh"
    arguments = [
        f"DIR={directory}",
        "CONFIRM=stack" if target.endswith("stack") else "CONFIRM=faq_prod",
        "APP_DB_NAME=faq_prod",
    ]
    extra = {"env_text": f"DATABASE_URL={MANAGED}\n"}
    if where == "environment":
        extra = {"DATABASE_URL": MANAGED}
    if where == "command_line":
        arguments.append(f"DATABASE_URL={MANAGED}")
        extra = {}
    done, asked = run_target(tmp_path, target, *arguments, **extra)

    assert done.returncode == 2, done
    assert f"REFUSED: {target} dumps and restores" in done.stderr, done.stderr
    assert "managed.example.net:5432" in done.stderr and "localhost:5432" in done.stderr
    assert "pg_restore" not in asked and "pg_dump" not in asked, asked


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_restore_backup_restores_the_database_both_names_say_on_the_stack(
    tmp_path: Path, host: str
) -> None:
    """With the two names equal and the stack's own host, pg_restore acts on that one."""
    done, asked = run_target(
        tmp_path,
        "restore-backup",
        f"DIR={backup_directory(tmp_path)}",
        "CONFIRM=faq_prod",
        "APP_DB_NAME=faq_prod",
        env_text=f"DATABASE_URL=postgresql+psycopg://u:p@{host}:5432/faq_prod\n",
    )

    restore = [line for line in asked.splitlines() if "pg_restore" in line]
    assert restore and "-d faq_prod" in restore[0], (done.stderr, asked)


@pytest.mark.parametrize("where", ["env_file", "environment"])
def test_dagster_wipe_deletes_the_runs_of_the_database_both_names_say(
    tmp_path: Path, where: str
) -> None:
    """With the two names equal, the runs tagged with that database go."""
    done, asked = run_target(
        tmp_path,
        "dagster-wipe",
        "CONFIRM=faq_prod",
        "APP_DB_NAME=faq_prod",
        **given_url(where),
    )

    wipe = [line for line in asked.splitlines() if "orchestration.wipe" in line]
    assert wipe and "APP_DB_NAME=faq_prod" in wipe[0], (done.stderr, asked)


def test_a_command_line_database_is_not_beaten_by_an_exported_url(
    tmp_path: Path,
) -> None:
    """`make X APP_DB_NAME=qa_scratch` with another database's URL exported is refused, not run there."""
    done, _ = run_target(
        tmp_path,
        "schema",
        "APP_DB_NAME=qa_scratch",
        DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/qa_generator",
    )

    assert done.returncode == 2, done
    assert (
        "DATABASE_URL names qa_generator but APP_DB_NAME is qa_scratch" in done.stderr
    )


def test_the_refusal_and_the_banner_name_the_host_the_url_names(tmp_path: Path) -> None:
    """Not localhost and not APP_DB_NAME."""
    refused, _ = run_target(
        tmp_path,
        "schema-reset",
        "APP_DB_NAME=faq_prod",
        env_text=f"DATABASE_URL={MANAGED}\n",
    )
    assert "faq_prod on managed.example.net:5432" in refused.stderr, refused.stderr

    probe_file = tmp_path / "banner.mk"
    probe_file.write_text(f"include {ROOT}/Makefile\nprobe:\n\t@$(BANNER)\n")
    env_file = tmp_path / "banner.env"
    env_file.write_text(
        f"APP_DB_PASSWORD=x\nAPP_DB_NAME=faq_prod\nDATABASE_URL={MANAGED}\n"
    )
    shown = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            str(probe_file),
            "probe",
            f"ENV_FILE={env_file}",
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert "on database faq_prod on managed.example.net:5432" in shown.stderr, (
        shown.stderr
    )


@pytest.mark.parametrize(
    ("url", "host", "database"),
    [
        (
            "postgresql+psycopg://app:s3cr?t@db.example.net:5432/ledger",
            "db.example.net:5432",
            "ledger",
        ),
        (
            "postgresql+psycopg://app:s3/cr@db.example.net/ledger",
            "db.example.net",
            "ledger",
        ),
        (
            "postgresql+psycopg://u:hunter7@h@x:5432/db?sslmode=require",
            "h@x:5432",
            "db",
        ),
        (
            "postgresql+psycopg://bank:Passwort-für-Konto@kasse.example.net:6432/konten",
            "kasse.example.net:6432",
            "konten",
        ),
        (
            "postgresql+psycopg://shop:κωδικός@db.example.gr/παραγγελίες",
            "db.example.gr",
            "παραγγελίες",
        ),
    ],
)
def test_the_url_is_split_as_sqlalchemy_splits_it_and_the_password_is_never_printed(
    tmp_path: Path, url: str, host: str, database: str
) -> None:
    """A `?` or a `/` in a password is the password's, not the end of the authority."""
    done = probe(
        tmp_path,
        '$(LOADENV) && $(RESOLVED_DB) && echo "$$db|$$host"',
        f"APP_DB_NAME={database}",
        env_text=f"DATABASE_URL={url}\n",
    )
    secret = url.split("//", 1)[1].split("@")[0].split(":", 1)[1]

    assert done.stdout.strip() == f"{database}|{host}", done
    assert secret not in done.stdout + done.stderr

    refused = probe(
        tmp_path, GUARDED, f"APP_DB_NAME={database}", env_text=f"DATABASE_URL={url}\n"
    )
    assert secret not in refused.stdout + refused.stderr


@pytest.mark.parametrize(
    "key", ["dbname", "host", "hostaddr", "port", "service", "db%6Eame", "ho%73t"]
)
def test_a_url_naming_its_database_or_host_in_the_query_is_refused(
    tmp_path: Path, key: str
) -> None:
    """The query overrides the path, so the guard would read one database and the engine another.

    Percent-encoded, the key is one the engine decodes and the guard does not.
    """
    url = f"postgresql+psycopg://u:p@localhost:5432/qa_scratch?{key}=qa_generator"
    done = probe(
        tmp_path,
        GUARDED,
        "APP_DB_NAME=qa_scratch",
        "CONFIRM=qa_scratch",
        env_text=f"DATABASE_URL={url}\n",
    )

    assert done.returncode == 2 and "REFUSED" in done.stderr, done
    assert "went-on" not in done.stdout


def test_a_harmless_query_is_kept(tmp_path: Path) -> None:
    """`sslmode` and the like are the connection's own options."""
    url = "postgresql+psycopg://u:p@localhost:5432/qa_scratch?sslmode=require&application_name=faq"
    done = probe(
        tmp_path,
        GUARDED,
        "APP_DB_NAME=qa_scratch",
        "CONFIRM=qa_scratch",
        env_text=f"DATABASE_URL={url}\n",
    )

    assert "went-on" in done.stdout, done


def test_the_doctor_reports_a_name_disagreement_and_goes_on(tmp_path: Path) -> None:
    """Where every other target exits, the doctor wants the whole list."""
    recipe = (
        'say() { echo "$$1 $$2"; }; fail=0; $(LOADED) && set +a; $(AGREEMENT); '
        'echo "went-on fail=$$fail"'
    )
    done = probe(
        tmp_path,
        recipe,
        "APP_DB_NAME=qa_scratch",
        env_text="DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/qa_generator\n",
    )
    assert done.returncode == 0, done
    assert (
        "FAIL DATABASE_URL names qa_generator but APP_DB_NAME is qa_scratch"
        in done.stdout
    )
    assert "went-on fail=1" in done.stdout

    agreed = probe(tmp_path, recipe, "APP_DB_NAME=qa_scratch")
    assert "FAIL" not in agreed.stdout and "went-on fail=0" in agreed.stdout, agreed


def test_a_failed_settings_load_stops_the_recipe_line(tmp_path: Path) -> None:
    """A missing ENV_FILE ran the rest of the line and advised an APP_DB_NAME."""
    done = probe(
        tmp_path,
        "$(LOADENV) && echo ran",
        f"ENV_FILE={tmp_path}/missing.env",
    )

    assert done.returncode != 0, done
    assert "ran" not in done.stdout, done
    assert "APP_DB_NAME=" not in done.stderr, done


def test_a_percent_encoded_database_name_is_refused_and_a_password_escape_is_not(
    tmp_path: Path,
) -> None:
    """The engine decodes the name and the guard reads it raw; a password's escapes are the password's."""
    encoded = probe(
        tmp_path,
        GUARDED,
        "APP_DB_NAME=qa%5Fscratch",
        "CONFIRM=qa%5Fscratch",
        env_text="DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/qa%5Fscratch\n",
    )
    assert encoded.returncode == 2 and "unencoded" in encoded.stderr, encoded

    escaped = probe(
        tmp_path,
        GUARDED,
        "APP_DB_NAME=qa_scratch",
        "CONFIRM=qa_scratch",
        env_text="DATABASE_URL=postgresql+psycopg://u:p%40ss@localhost:5432/qa_scratch\n",
    )
    assert "went-on" in escaped.stdout, escaped
