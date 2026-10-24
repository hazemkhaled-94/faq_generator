"""A container whose image was built from another lock than the checkout holds refuses to start.

The lock is bind-mounted read-only from the checkout and its hash is baked at
build, so a lock changed without `compose build` is told apart at the start of
every container, not at the first import the old image cannot satisfy.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "telemetry/lockcheck.sh"

#: Each image, the file it installs from, where a container sees the
#: checkout's copy of it, and the Dockerfile that bakes its hash.
IMAGES = {
    "backend": ("backend/api/requirements.lock", "/app/api", "backend/api/Dockerfile"),
    "frontend": ("frontend/requirements.lock", "/app", "frontend/Dockerfile"),
    "orchestration": (
        "orchestration/requirements.txt",
        "/opt/dagster/app/orchestration",
        "orchestration/Dockerfile",
    ),
}


def _run(tmp_path: Path, baked: str, live: str, *command: str):
    sha = tmp_path / "lock-sha"
    sha.write_text(hashlib.sha256(baked.encode()).hexdigest() + "\n")
    lock = tmp_path / "requirements.lock"
    lock.write_text(live)
    return subprocess.run(
        ["sh", str(CHECK), *command],
        env={
            "PATH": os.environ["PATH"],
            "LOCK_SHA": str(sha),
            "LOCK_FILE": str(lock),
            "LOCKCHECK_WAIT": "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_lock_that_matches_what_was_built_starts_the_command(tmp_path: Path) -> None:
    """The check is invisible when nothing moved."""
    ran = _run(tmp_path, "torch==2.9\n", "torch==2.9\n", "echo", "started")

    assert ran.returncode == 0 and ran.stdout.strip() == "started", ran


def test_a_lock_changed_since_the_build_refuses_naming_the_fix(tmp_path: Path) -> None:
    """Exits non-zero without starting the command, and says what to run."""
    ran = _run(tmp_path, "torch==2.9\n", "torch==3.0\n", "echo", "started")

    assert ran.returncode != 0
    assert "started" not in ran.stdout
    assert "compose build" in ran.stderr


def test_a_missing_baked_hash_refuses(tmp_path: Path) -> None:
    """An image built before the check carries none, and is not trusted."""
    (tmp_path / "requirements.lock").write_text("x\n")
    ran = subprocess.run(
        ["sh", str(CHECK), "true"],
        env={
            "PATH": os.environ["PATH"],
            "LOCK_SHA": str(tmp_path / "none"),
            "LOCK_FILE": str(tmp_path / "requirements.lock"),
            "LOCKCHECK_WAIT": "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode != 0 and "compose build" in ran.stderr


def test_a_refusal_waits_before_it_exits_so_a_restart_policy_does_not_spin(
    tmp_path: Path,
) -> None:
    """`unless-stopped` restarts every exit, whatever the code: the wait is the brake."""
    text = CHECK.read_text()

    assert "sleep" in text and "LOCKCHECK_WAIT" in text


@pytest.mark.parametrize("image", sorted(IMAGES))
def test_each_dockerfile_bakes_the_hash_and_starts_through_the_check(
    image: str,
) -> None:
    """At build, and as the entrypoint, so every command is behind it."""
    _, _, dockerfile = IMAGES[image]
    text = (ROOT / dockerfile).read_text()

    assert "sha256sum" in text and "LOCK_SHA" in text and "LOCK_FILE" in text
    assert 'ENTRYPOINT ["sh", "/shared/telemetry/lockcheck.sh"]' in text


def _services() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]


def _image_of(service: dict) -> str:
    image = service.get("image", "")
    if "orchestration" in image:
        return "orchestration"
    if "backend" in image:
        return "backend"
    return "frontend" if "frontend" in str(service.get("build", {})) else ""


OURS = sorted(name for name, one in _services().items() if _image_of(one))


def test_the_scan_finds_the_containers_of_our_images() -> None:
    """The api, the workers, the page and Dagster: not a vacuous list."""
    assert {"api", "extract-worker", "streamlit", "dagster-daemon"} <= set(OURS)


@pytest.mark.parametrize("name", OURS)
def test_every_container_of_our_images_sees_the_checkouts_lock_read_only(
    name: str,
) -> None:
    """The mount the check reads, which none may drop."""
    service = _services()[name]
    image = _image_of(service)
    _, target, _ = IMAGES[image]
    mounts = [str(one) for one in service.get("volumes", [])]

    assert any(one.endswith(f":{target}:ro") for one in mounts), (name, mounts)
