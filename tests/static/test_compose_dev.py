"""compose.yaml runs from its images; compose.dev.yaml is the only place source is mounted.

An image that needs the checkout beside it cannot be started anywhere the
checkout is not: a container platform pulls an image and runs it. So the
deployment file mounts none of it, and the development override adds the mounts
a developer wants.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FIRST_PARTY = (
    "backend/api/Dockerfile",
    "frontend/Dockerfile",
    "orchestration/Dockerfile",
)


def _services(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())["services"]


def _ours(service: dict) -> bool:
    return str(service.get("build", {}).get("dockerfile", "")) in FIRST_PARTY


BASE = _services("compose.yaml")
OURS = sorted(name for name, one in BASE.items() if _ours(one))


def _bind_sources(service: dict) -> list[str]:
    return [
        str(one).split(":")[0]
        for one in service.get("volumes", [])
        if str(one).startswith((".", "/"))
    ]


def test_the_scan_finds_the_first_party_services() -> None:
    """The api, the workers, the page and Dagster: not a vacuous list."""
    assert {
        "api",
        "parse-worker",
        "extract-worker",
        "streamlit",
        "dagster-daemon",
    } <= set(OURS)


@pytest.mark.parametrize("name", OURS)
def test_compose_yaml_mounts_no_checkout_path_into_a_first_party_image(
    name: str,
) -> None:
    """Named volumes and nothing of the working tree."""
    assert _bind_sources(BASE[name]) == [], name


def test_the_development_override_names_only_first_party_services_and_mounts_real_paths() -> (
    None
):
    """Every source is in the checkout, and every service it names is one of ours."""
    over = _services("compose.dev.yaml")

    assert set(over) <= set(OURS), sorted(set(over) - set(OURS))
    for name, service in over.items():
        for source in _bind_sources(service):
            assert (ROOT / source).exists(), (name, source)


def test_every_first_party_service_with_source_in_its_image_is_mounted_in_development() -> (
    None
):
    """A service left out of the override runs the image's copy while its siblings run the tree's."""
    assert set(_services("compose.dev.yaml")) == set(OURS)


def test_every_service_has_a_health_check() -> None:
    """A platform restarts and routes by it: a worker's is that PID 1 is the worker."""
    assert [name for name, one in BASE.items() if "healthcheck" not in one] == []


def test_a_worker_is_healthy_when_python_is_pid_1() -> None:
    """Not while the lock check is waiting out a stale lock, where `sh` is."""
    check = BASE["parse-worker"]["healthcheck"]["test"]

    assert check[:3] == ["CMD", "python", "-c"]
    assert "/proc/1/cmdline" in check[3] and "endswith(b'python')" in check[3]


def test_the_orchestration_image_carries_its_config_and_copies_it_where_dagster_reads_it() -> (
    None
):
    """Instance and workspace are baked, and copied to DAGSTER_HOME by the command."""
    dockerfile = (ROOT / "orchestration/Dockerfile").read_text()
    assert (
        "configs/dagster/dagster.yaml" in dockerfile
        and "configs/dagster/workspace.yaml" in dockerfile
    )
    assert "/opt/dagster/config/" in dockerfile

    for name in ("dagster-webserver", "dagster-daemon"):
        command = " ".join(BASE[name]["command"])
        assert (
            "cp /opt/dagster/config/dagster.yaml /opt/dagster/config/workspace.yaml"
            in command
        ), name


def test_the_makefile_names_the_override_on_the_development_profile_only() -> None:
    """The go-live branch starts compose.yaml alone."""
    text = (ROOT / "Makefile").read_text()
    up = re.search(r"^UP = .*?(?=\n\n)", text, re.MULTILINE | re.DOTALL)
    assert up, "the UP macro moved"
    macro = up.group(0)
    go_live, development = macro.split("else", 1)

    assert "compose.dev.yaml" not in go_live
    assert "-f compose.yaml -f compose.dev.yaml" in development


@pytest.mark.parametrize("name", ["dagster-webserver", "dagster-daemon"])
def test_a_dagster_container_starts_over_a_volume_holding_root_owned_config(
    name: str, tmp_path: Path
) -> None:
    """An old dagster_home holds the two files from the bind mounts, not writable by the app user.

    Overwriting such a file fails, unlinking it does not (the directory is the
    app user's), so the start removes before it copies. Run here against a
    read-only file standing in for the root-owned one.
    """
    import subprocess

    script = BASE[name]["command"][2].replace("$$", "$")
    copy = script.split(" && exec ", 1)[0]
    config, home = tmp_path / "config", tmp_path / "home"
    config.mkdir()
    home.mkdir()
    (config / "dagster.yaml").write_text("new instance\n")
    (config / "workspace.yaml").write_text("new workspace\n")
    for held in ("dagster.yaml", "workspace.yaml"):
        (home / held).write_text("left by a mount\n")
        (home / held).chmod(0o444)
    copy = copy.replace("/opt/dagster/config", str(config))

    ran = subprocess.run(
        ["sh", "-c", copy],
        env={"DAGSTER_HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert (home / "dagster.yaml").read_text() == "new instance\n"
    assert (home / "workspace.yaml").read_text() == "new workspace\n"


def test_the_health_checks_that_need_a_shell_have_one() -> None:
    """Phoenix is distroless and so uses the exec form; filebeat's reads its config as its command does."""
    phoenix = BASE["phoenix"]["healthcheck"]["test"]
    assert phoenix[0] == "CMD" and phoenix[1].startswith("/")
    assert "--strict.perms=false" in BASE["filebeat"]["healthcheck"]["test"][1]
