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
