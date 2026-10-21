"""The Makefile, read through `make -n`, which prints a recipe and runs none.

The one command executed here is the worker guard on its own, against a
stand-in for compose.
"""

from __future__ import annotations

import os
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


def test_the_corpus_reports_the_topics_and_never_fits_them() -> None:
    """`topics-discover` is the refit, asked for on its own."""
    topics = [line for line in printed("corpus") if "topic_modelling.run" in line]

    assert topics, "the corpus says nothing about the topics"
    assert all(line.endswith("topic_modelling.run --status") for line in topics), topics


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
def test_the_audit_keeps_pip_audits_exit_status(
    tmp_path: Path, advised: str, refused: bool
) -> None:
    """An advisory in any of the three locks fails it, and all are still read."""
    calls = tmp_path / "calls"
    poetry = tmp_path / "poetry"
    # `poetry run python` runs the test's own interpreter; pip-audit is only recorded.
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'echo "$*" >> {calls}\n'
        + (f'case "$*" in *{advised}*) exit 1;; esac\n' if advised else "")
    )
    poetry.chmod(0o755)

    ran = made("audit", path=tmp_path)

    assert (ran.returncode != 0) is refused, ran
    assert len(calls.read_text().splitlines()) == 3, calls.read_text()


def test_the_audit_reads_the_host_lock_without_the_torch_it_cannot_resolve(
    tmp_path: Path,
) -> None:
    """poetry.lock is what CI and the host install; torch is a +cpu build there too."""
    seen = tmp_path / "seen"
    poetry = tmp_path / "poetry"
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'for f in "$@"; do case "$f" in *poetry.lock) cp "$f" {seen};; esac; done\n'
    )
    poetry.chmod(0o755)

    assert made("audit", path=tmp_path).returncode == 0
    pins = seen.read_text().splitlines()

    assert any(pin.startswith("aiohttp==") for pin in pins), pins[:5]
    assert not [pin for pin in pins if pin.startswith(("torch==", "torchvision=="))]


def test_the_audit_reads_every_lock_against_osv(tmp_path: Path) -> None:
    """pip-audit's default, PyPI's own feed, missed three advisories OSV lists.

    On Pillow 12.3.0 it listed 18 of OSV's 21, a critical one left out.
    """
    calls = tmp_path / "calls"
    poetry = tmp_path / "poetry"
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'echo "$*" >> {calls}\n'
    )
    poetry.chmod(0o755)

    assert made("audit", path=tmp_path).returncode == 0
    audited = calls.read_text().splitlines()

    assert len(audited) == 3, audited
    assert all("--vulnerability-service osv" in call for call in audited), audited


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
    on_volume = command("logs-wipe", "/var/log/qa")
    assert "-delete" not in on_volume and "truncate -s 0" in on_volume, on_volume
    log = tmp_path / "logs" / "api-host-1.log"
    log.parent.mkdir()

    with log.open("a") as writer:
        writer.write("before\n")
        writer.flush()
        subprocess.run(
            ["bash", "-c", command("logs-wipe", "find logs")],
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
    assert not [line for line in lines if "python -m" in line or "alembic" in line]


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
