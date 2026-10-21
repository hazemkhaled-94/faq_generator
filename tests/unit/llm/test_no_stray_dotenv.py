"""An xdist worker must not read a .env above its working directory.

litellm calls `dotenv.load_dotenv()` when it is imported (LITELLM_MODE
defaults to DEV). python-dotenv searches from the working directory
upward whenever `__main__` has no `__file__`, which is how execnet starts
every xdist worker (`python -c "import sys;exec(...)"`). A worktree under
the main checkout therefore picks up the main checkout's `.env`: its
LLM_MODEL, base URL and verifier model, with no shell having sourced it.

The `.env` here is a fake one in a temporary directory, so no real
credential is read.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

STRAY = "LLM_MODEL=ollama_chat/shop-catalogue-writer\nQUESTIONS_VERIFIER_MODEL=azure/bank-statement-checker\n"

PROBE = """
import os
import llm.client  # imports litellm, as every model-calling test does
print(os.environ.get("LLM_MODEL"), os.environ.get("QUESTIONS_VERIFIER_MODEL"))
"""


def _layout(tmp_path: Path) -> Path:
    """A checkout holding a .env, and a worktree below it holding none."""
    (tmp_path / ".env").write_text(STRAY)
    worktree = tmp_path / ".claude" / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    return worktree


def _env() -> dict[str, str]:
    clean = {
        k: v
        for k, v in os.environ.items()
        if k not in ("LLM_MODEL", "QUESTIONS_VERIFIER_MODEL", "LITELLM_MODE")
    }
    clean["PYTHONPATH"] = f"{ROOT / 'backend'}:{ROOT}"
    clean["HF_HUB_OFFLINE"] = "1"
    return clean


def test_a_worker_started_as_xdist_starts_it_reads_no_env_file(tmp_path) -> None:
    """`python -c`, as execnet starts a worker: no .env may reach os.environ."""
    worktree = _layout(tmp_path)
    said = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=worktree,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.strip()
    assert said == "None None", f"the worker read the checkout's .env: {said}"


def test_an_xdist_run_reads_no_env_file(tmp_path) -> None:
    """The same through pytest -n 1: the eval fixtures' LLM_MODEL check sees it."""
    worktree = _layout(tmp_path)
    (worktree / "test_probe.py").write_text(
        "import os\n"
        "def test_probe():\n"
        "    import llm.client\n"
        "    assert os.environ.get('LLM_MODEL') is None, os.environ.get('LLM_MODEL')\n"
    )
    ran = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "1",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "test_probe.py",
        ],
        cwd=worktree,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert ran.returncode == 0, ran.stdout[-1500:]


def test_control_a_script_with_a_file_reads_none(tmp_path) -> None:
    """Control: a `__main__` with a file (pytest without -n) reads none.

    python-dotenv then searches from litellm's own directory, not the caller's.
    """
    worktree = _layout(tmp_path)
    script = worktree / "probe.py"
    script.write_text(PROBE)
    said = subprocess.run(
        [sys.executable, str(script)],
        cwd=worktree,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.strip()
    assert said == "None None"
