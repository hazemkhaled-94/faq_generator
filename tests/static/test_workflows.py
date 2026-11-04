"""The CI workflows, read as the files they are.

A workflow only reports a mistake when it runs, and some mistakes are
quiet: a marker renamed here and not there deselects every test and the
job goes green having run nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))

#: Markers a workflow selects on, which must be markers pytest knows.
_SELECTOR = re.compile(r'-m\s+"([^"]+)"')


def loaded(path: Path) -> dict:
    """One workflow, parsed."""
    return yaml.safe_load(path.read_text())


def test_there_are_workflows_to_check() -> None:
    """A moved directory would otherwise pass as nothing to say."""
    assert WORKFLOWS, "no workflows in .github/workflows"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_a_workflow_parses_and_declares_jobs(path: Path) -> None:
    """Valid YAML, with jobs in it."""
    workflow = loaded(path)

    assert workflow.get("jobs"), path.name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_local_action_a_job_uses_exists(path: Path) -> None:
    """`uses: ./...` is a path, and a renamed one fails every job at once."""
    missing = []
    for job in loaded(path)["jobs"].values():
        for step in job.get("steps", []):
            used = step.get("uses", "")
            if used.startswith("./") and not (ROOT / used / "action.yml").exists():
                missing.append(used)

    assert not missing, sorted(missing)


@pytest.mark.parametrize(
    "path",
    [*WORKFLOWS, *sorted((ROOT / ".github/actions").glob("*/action.yml"))],
    ids=lambda p: p.relative_to(ROOT / ".github").as_posix(),
)
def test_every_action_from_elsewhere_is_pinned_to_a_commit(path: Path) -> None:
    """A tag can be moved to other code; a commit cannot."""
    used = re.findall(r"uses:\s*([^\s#]+)", path.read_text())
    loose = [
        one
        for one in used
        if not one.startswith("./") and not re.fullmatch(r"[^@]+@[0-9a-f]{40}", one)
    ]

    assert used, path.name
    assert not loose, loose


#: The first release of the smallest major of each action that runs on node24
#: (Node 20 actions are forced onto Node 24 and warn on every run).
NODE24_PINS = {
    "actions/checkout": "08c6903cd8c0fde910a37f88322edcfb5dd907a8",
    "actions/cache": "a7833574556fa59680c1b7cb190c1735db73ebf0",
    "actions/upload-artifact": "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
    "actions/download-artifact": "37930b1c2abaa49bbe596cd826c3c89aef350131",
    "actions/setup-python": "e797f83bcb11b83ae66e0230d6156d7c80228e7c",
}


@pytest.mark.parametrize(
    "path",
    [*WORKFLOWS, *sorted((ROOT / ".github/actions").glob("*/action.yml"))],
    ids=lambda p: p.relative_to(ROOT / ".github").as_posix(),
)
def test_every_github_action_is_pinned_to_its_node24_release(path: Path) -> None:
    """An older pin runs on Node 20 and warns on every run of every workflow."""
    used = re.findall(r"uses:\s*(actions/[^@\s]+)@([0-9a-f]{40})", path.read_text())
    stale = [name for name, sha in used if sha != NODE24_PINS.get(name)]

    assert not stale, stale


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_marker_a_workflow_selects_on_is_registered(path: Path) -> None:
    """A renamed marker would deselect everything and pass."""
    import tomllib

    declared = {
        line.split(":")[0]
        for line in tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"][
            "pytest"
        ]["ini_options"]["markers"]
    }

    selected = {
        word
        for expression in _SELECTOR.findall(path.read_text())
        for word in re.findall(r"[a-z_]+", expression)
        if word not in ("not", "and", "or")
    }

    assert selected, f"{path.name} selects on no marker at all"
    assert selected <= declared, sorted(selected - declared)


@pytest.mark.parametrize("marker", ["smoke", "eval", "integration"])
def test_the_fast_target_starts_no_container(marker: str) -> None:
    """`make test-fast` is the quick check, and a smoke test builds both images."""
    from collections import defaultdict

    makefile = (ROOT / "Makefile").read_text()
    recipe = re.search(r"^test-fast:\n\t(.+)$", makefile, re.MULTILINE)
    expression = _SELECTOR.search(recipe[1])[1]

    assert not eval(expression, {}, defaultdict(bool, {marker: True})), expression


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_a_job_running_the_smoke_layer_writes_a_dot_env_first(path: Path) -> None:
    """Without one, compose cannot resolve and every compose check skips."""
    for name, job in loaded(path)["jobs"].items():
        runs = [step.get("run", "") for step in job.get("steps", [])]
        smoke = [at for at, run in enumerate(runs) if _selects_smoke(run)]
        written = [at for at, run in enumerate(runs) if "cp .env.example .env" in run]

        assert not smoke or (written and written[0] < smoke[0]), name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_step_sets_a_tuning_value_of_its_own(path: Path) -> None:
    """The tests read backend.env, and a step's own value wins over it."""
    tuning = {
        line.partition("=")[0]
        for line in (ROOT / "configs/env/backend.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    }
    copied = [
        f"{name}: {setting}"
        for name, job in loaded(path)["jobs"].items()
        for step in job.get("steps", [])
        for setting in step.get("env", {})
        if setting in tuning
    ]

    assert not copied, copied


def _selects_smoke(run: str) -> bool:
    """Whether one step runs the smoke layer, by target or by marker.

    A bare `pytest` with no `-m` and no path is not seen.
    """
    from collections import defaultdict

    return "test-smoke" in run or any(
        eval(expression, {}, defaultdict(bool, {"smoke": True}))
        for expression in _SELECTOR.findall(run)
    )


def test_every_property_test_runs_the_profiles_example_count() -> None:
    """A `max_examples` written on a test overrides `HYPOTHESIS_PROFILE`."""
    import ast

    pinned = [
        f"{path.name}:{call.lineno}"
        for path in sorted((ROOT / "tests/property").glob("test_*.py"))
        for call in ast.walk(ast.parse(path.read_text()))
        if isinstance(call, ast.Call)
        and getattr(call.func, "id", None) == "settings"
        and any(keyword.arg == "max_examples" for keyword in call.keywords)
    ]

    assert not pinned, pinned


def test_the_gate_waits_for_every_other_job() -> None:
    """One job for a branch protection rule to require.

    So that adding a job above does not also mean editing the rule.
    """
    jobs = loaded(ROOT / ".github/workflows/ci.yml")["jobs"]
    gate = jobs["gate"]

    assert set(gate["needs"]) == set(jobs) - {"gate"}, gate["needs"]


def test_the_gate_names_every_job_it_waits_for_in_its_condition() -> None:
    """A job added to `needs` and not to the check passes unexamined."""
    jobs = loaded(ROOT / ".github/workflows/ci.yml")["jobs"]
    reported = " ".join(step.get("run", "") for step in jobs["gate"]["steps"])

    for needed in jobs["gate"]["needs"]:
        assert f"needs.{needed}.result" in reported, needed


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_that_sets_up_the_project_checks_out_first(path: Path) -> None:
    """The composite action is in the repository it is setting up."""
    for name, job in loaded(path)["jobs"].items():
        steps = [step.get("uses", "") for step in job.get("steps", [])]
        if "./.github/actions/setup" not in steps:
            continue
        assert any(one.startswith("actions/checkout") for one in steps), name
        assert steps.index("./.github/actions/setup") > next(
            index
            for index, one in enumerate(steps)
            if one.startswith("actions/checkout")
        ), name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_runs_on_a_named_runner_image(path: Path) -> None:
    """`ubuntu-latest` moves on its own, and the cached venv is keyed without the image."""
    runners = {job["runs-on"] for job in loaded(path)["jobs"].values()}

    assert runners == {"ubuntu-24.04"}, runners


def test_ci_installs_the_poetry_that_wrote_the_lock() -> None:
    """Another poetry can read the lock differently, and PyPI serves a new one unannounced."""
    written = re.search(
        r"generated by Poetry (\S+) ", (ROOT / "poetry.lock").read_text(), re.IGNORECASE
    )
    action = (ROOT / ".github/actions/setup/action.yml").read_text()

    assert written, "poetry.lock does not say which poetry wrote it"
    assert f"pipx install poetry=={written.group(1)}\n" in action


def test_the_nightly_fails_rather_than_skips_where_weights_are_missing() -> None:
    """Fetches the models, runs offline, and makes a skip on a weight an error."""
    job = loaded(ROOT / ".github/workflows/nightly.yml")["jobs"]["weights"]
    steps = {step["name"]: step for step in job["steps"] if "name" in step}
    fetch = steps["Fetch the models at their pinned revisions"]["run"]
    run = steps["Run what needs them"]

    assert "EMBEDDING_MODEL" in fetch and "NLI_MODEL" in fetch
    assert "snapshot_download" in fetch and "revision" in fetch
    assert run["env"]["REQUIRE_MODELS"] == "1"
    assert run["env"]["HF_HUB_OFFLINE"] == "1"
    for tests in ("test_embedding.py", "test_fact_refusals.py", "tests/golden"):
        assert tests in run["run"], tests


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_the_golden_conversion_runs_in_the_weights_job_alone(path: Path) -> None:
    """Every other selection leaves the slow layer out.

    It converts real PDFs from the cached weights against snapshots, which only
    the nightly weights job fetches; anywhere else it would download them on
    every run and compare against snapshots no runner of that kind recorded.
    """
    from collections import defaultdict

    selecting = [
        (name, expression)
        for name, job in loaded(path)["jobs"].items()
        if name != "weights"
        for step in job.get("steps", [])
        for expression in _SELECTOR.findall(step.get("run", ""))
    ]

    chosen = [
        f"{name}: {expression}"
        for name, expression in selecting
        if eval(expression, {}, defaultdict(bool, {"slow": True}))
    ]
    assert not chosen, chosen


def test_the_weights_job_caches_docling_by_its_version_and_keeps_a_failed_conversion() -> (
    None
):
    """Its cache holds Docling's weights, and a difference leaves a Linux refresh.

    Docling's weights land in the Hugging Face cache when DOCLING_ARTIFACTS_PATH
    is unset, at revisions its release pins, so the key carries that release: a
    key of the embedding model alone kept the first Docling's weights forever.
    A golden difference converts again into the snapshots and uploads them.
    """
    job = loaded(ROOT / ".github/workflows/nightly.yml")["jobs"]["weights"]
    steps = job["steps"]
    (cache,) = [one for one in steps if "actions/cache@" in one.get("uses", "")]
    read = [one for one in steps if one.get("id") == "docling"]
    refresh = [one for one in steps if "golden-refresh" in one.get("run", "")]
    kept = [one for one in steps if "actions/upload-artifact@" in one.get("uses", "")]

    assert "~/.cache/huggingface" in cache["with"]["path"]
    assert "steps.docling.outputs.version" in cache["with"]["key"]
    assert read and 'name = "docling"' in read[0]["run"]
    assert "poetry.lock" in read[0]["run"]
    assert refresh and refresh[0]["if"] == "failure()"
    assert kept and kept[0]["if"] == "failure()"
    assert kept[0]["with"]["path"] == "tests/golden/snapshots"
    assert steps.index(refresh[0]) < steps.index(kept[0])


def test_the_stack_job_starts_compose_yaml_alone_and_runs_the_orchestrator_smoke_tests() -> (
    None
):
    """C-104's CI half: images without mounts, then the queries against a live Dagster."""
    ci = loaded(ROOT / ".github/workflows/ci.yml")
    job = ci["jobs"]["stack"]
    commands = " ".join(step.get("run", "") for step in job["steps"])

    assert "compose.dev.yaml" not in commands
    assert "up -d --wait" in commands
    assert "tests/smoke/test_orchestrator_queries.py" in commands
    # The path end to end: two PDFs the golden tests hold, uploaded, then parsed
    # and chunked by the corpus job the api launches.
    assert "tests/golden/pdfs/shopping_de.pdf" in commands
    assert "tests/golden/pdfs/shopping_en.pdf" in commands
    # Launched the way the pages launch it, through the api, never by exec.
    assert "/pipeline/run" in commands and "/pipeline/stop" in commands
    assert "asset materialize" not in commands and " exec " not in commands
    assert "time.monotonic() < deadline" in commands
    assert "docling-weights" in commands
    assert (ROOT / "tests/golden/pdfs/shopping_de.pdf").exists()
    assert (ROOT / "tests/golden/pdfs/shopping_en.pdf").exists()
    assert job["if"] == "github.event_name != 'pull_request'"
    assert (ROOT / "tests/smoke/test_orchestrator_queries.py").exists()


def test_the_gate_tolerates_the_stack_job_being_skipped_on_a_pull_request() -> None:
    """Skipped is not a failure; anything else but success is."""
    gate = loaded(ROOT / ".github/workflows/ci.yml")["jobs"]["gate"]
    script = " ".join(step.get("run", "") for step in gate["steps"])

    assert "stack" in gate["needs"]
    assert 'needs.stack.result }}" = "skipped"' in script


def test_the_stack_job_runs_every_step_with_pipefail_and_starts_what_an_upload_needs() -> (
    None
):
    """GitHub's `shell: bash` is `bash -eo pipefail`; the volume servers are what a PUT is placed on."""
    job = loaded(ROOT / ".github/workflows/ci.yml")["jobs"]["stack"]
    commands = " ".join(step.get("run", "") for step in job["steps"])

    assert job["defaults"]["run"]["shell"] == "bash"
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    first = next(one for one in commands.split("$DC up -d --wait")[1:2])
    for service in ("seaweedfs-s3", "seaweedfs-volume", "seaweedfs-volume2"):
        assert service in first, service
    # Nothing depends on the volume servers, which is why they are named.
    assert not any(
        "seaweedfs-volume" in str(one.get("depends_on", "")) for one in compose.values()
    )


def test_the_model_quality_job_runs_only_for_a_named_model_with_its_provider_secrets() -> (
    None
):
    """Unset, it shows skipped rather than green; set, the step can authenticate.

    A job that runs with no model skips all of its tests and reports success,
    which reads as a quality measure that has been taken. The condition is on
    the job, so the run says skipped, and the provider's credentials reach the
    step from secrets, so a named model that does not answer fails.
    """
    job = loaded(ROOT / ".github/workflows/nightly.yml")["jobs"]["evaluate"]
    (step,) = [one for one in job["steps"] if "pytest -m eval" in one.get("run", "")]

    assert "vars.LLM_MODEL" in str(job.get("if", ""))
    for name in ("AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"):
        assert f"secrets.{name}" in step["env"][name], name


def test_a_mutation_run_that_cannot_start_fails_the_nightly() -> None:
    """The step that runs mutants is not allowed to fail quietly, nor to time out loudly.

    `continue-on-error` hid a harness that ran no mutant for as long as it was
    there. Only running out of time (the exit status of `timeout`, 124) ends
    the step as a pass, with a warning; every other status fails it. The
    survivors are put in the summary whatever the run did, and the summary
    step makes the link the survivors are read through, which `make mutation`
    removes when it ends.
    """
    job = loaded(ROOT / ".github/workflows/nightly.yml")["jobs"]["mutation"]
    (run,) = [one for one in job["steps"] if "make mutation" in one.get("run", "")]
    (summary,) = [
        one
        for one in job["steps"]
        if one.get("name", "").startswith("Put the survivors")
    ]

    assert "continue-on-error" not in run
    assert "timeout" in run["run"]
    assert 'exit "$status"' in run["run"]
    # Out of time passes only after a mutant was checked.
    assert "not checked" in run["run"]
    assert "::error::no mutant was checked" in run["run"]
    assert summary["if"] == "always()"
    assert summary["run"].index("ln -sfn backend src") < summary["run"].index(
        "mutmut results"
    )


def test_the_mutation_harness_copies_what_its_layers_read_and_selects_no_git_layer() -> (
    None
):
    """Mutmut runs the tests from a copy holding only the files it mutates.

    The layers it runs read configs/env/backend.env at import, the backend
    packages beside the mutated files and compose.yaml, so the copy takes them.
    The static layer reads the git checkout and is not selected: a layer that
    cannot run in the copy fails the whole run before a mutant is tried.
    """
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    copied = set(config["also_copy"])
    selected = config["pytest_add_cli_args_test_selection"]

    assert {"src", "backend", "configs", "compose.yaml"} <= copied
    assert selected
    # The files it mutates are named under src, which `make mutation` links to
    # backend, so mutmut's name for a function is the name the tests import.
    for path in config["source_paths"]:
        assert path.startswith("src/"), path
        assert (ROOT / "backend" / path.removeprefix("src/")).is_file(), path
    assert "ln -sfn backend src" in (ROOT / "Makefile").read_text()
    assert "backend" not in config["pytest_add_cli_args"][1].split()
    for path in selected:
        assert path.startswith(("tests/unit/", "tests/property")), path
        assert not path.startswith("tests/static"), path


def test_the_mutation_layers_name_their_cases_in_ascii() -> None:
    """Mutmut's clean run cannot find a case whose explicit id holds a non-ASCII letter.

    In the first Nightly of v0.5.3 it found none of the four cases named
    `außer Acht`, `30 Tage Rückgaberecht` and `die Karte der Überschrift ...`,
    pytest ran no test, and the shard of question_generation.gates stopped
    before its first mutant. Ids pytest makes from the values, letters
    included, ran in the same list.
    """
    import ast
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    found = []
    for layer in config["pytest_add_cli_args_test_selection"]:
        for path in sorted((ROOT / layer).rglob("test_*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "parametrize"
                ):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "ids" or not isinstance(
                        keyword.value, (ast.List, ast.Tuple)
                    ):
                        continue
                    found += [
                        f"{path.relative_to(ROOT)}:{one.lineno} {one.value}"
                        for one in keyword.value.elts
                        if isinstance(one, ast.Constant)
                        and isinstance(one.value, str)
                        and not one.value.isascii()
                    ]

    assert not found, found


def test_the_mutation_job_runs_one_shard_to_each_mutated_file() -> None:
    """The matrix lists exactly the files `[tool.mutmut]` mutates, one runner each.

    mutmut names a mutant after its file's path with `src.` stripped, and takes
    a glob of those names, so a shard is `make mutation MUTANTS=<module>.*` and
    runs nothing of another file. The job takes the largest file's share of the
    time, and a shard that checked nothing before its box ran out fails alone.
    """
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    mutated = [
        path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        for path in config["source_paths"]
    ]
    job = loaded(ROOT / ".github/workflows/nightly.yml")["jobs"]["mutation"]
    (run,) = [one for one in job["steps"] if "make mutation" in one.get("run", "")]

    assert job["strategy"]["matrix"]["module"] == mutated
    assert job["strategy"]["fail-fast"] is False
    assert 'MUTANTS="${{ matrix.module }}.*"' in run["run"]
    assert "matrix.module" in job["name"]
    makefile = (ROOT / "Makefile").read_text()
    assert 'mutmut run $(if $(MUTANTS),"$(MUTANTS)")' in makefile


#: Twice the longest recent green run, rounded up to the next 10 minutes
#: (read 2026-11-04), so a hung test ends its job in at most that long rather
#: than at GitHub's six hours. The stack job is the exception: its wait
#: allows itself 15 minutes after about 6 of setup, and a timed-out job is
#: cancelled before its `if: failure()` log step runs, so it gets 30.
_TIMEOUTS = {
    ("nightly.yml", "everything"): 110,
    ("nightly.yml", "weights"): 20,
    ("nightly.yml", "ceilings"): 120,
    ("ci.yml", "unit"): 60,
    ("ci.yml", "integration"): 30,
    ("ci.yml", "smoke"): 30,
    ("ci.yml", "stack"): 30,
}


@pytest.mark.parametrize(("name", "job"), _TIMEOUTS, ids=lambda v: str(v))
def test_a_long_job_stops_at_the_minutes_its_longest_green_run_earns(
    name: str, job: str
) -> None:
    """Too low fails a healthy run; missing or too high lets a hang run on."""
    minutes = loaded(ROOT / ".github/workflows" / name)["jobs"][job].get(
        "timeout-minutes"
    )

    assert minutes == _TIMEOUTS[name, job], f"{name}:{job} {minutes}"


def test_pytest_prints_the_stacks_of_a_test_that_hangs() -> None:
    """Without it a hung run says only which file came before the silence."""
    import tomllib

    options = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"][
        "ini_options"
    ]

    assert 0 < options.get("faulthandler_timeout", 0) <= 1800


def test_the_nightly_seed_reaches_its_step_through_env() -> None:
    """An input in a `run:` line is code the dispatcher writes."""
    workflow = loaded(ROOT / ".github/workflows/nightly.yml")
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    steps = workflow["jobs"]["everything"]["steps"]
    pytest_step = next(s for s in steps if "pytest" in s.get("run", ""))

    assert inputs["seed"]["type"] == "string"
    assert inputs["seed"]["required"] is False
    assert pytest_step["env"]["SEED"] == "${{ inputs.seed }}"
    assert "${{" not in pytest_step["run"]
    assert '${SEED:+-p randomly --randomly-seed="$SEED"}' in pytest_step["run"]
