"""A password reaches SQL and a URL as the one it is, whatever characters it holds."""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

import pytest

from api.doctor import _URL_PASSWORDS

ROOT = Path(__file__).resolve().parents[2]

#: A psql that only records the SQL it is given and its arguments.
FAKE_PSQL = """#!/bin/bash
cat >> "$SQL_LOG"
for a in "$@"; do printf 'ARG %s\\n' "$a" >> "$SQL_LOG"; done
exit 0
"""


@pytest.mark.parametrize(
    "chosen",
    ["Winter's-2026", "back\\slash'quote", "Passwort-für-Konto's", "κωδικός'1"],
)
def test_init_sh_hands_the_password_to_psql_as_a_variable(
    tmp_path: Path, chosen: str
) -> None:
    """A quote in it broke the first boot's SQL, and the SQL held it as written."""
    fake = tmp_path / "psql"
    fake.write_text(FAKE_PSQL)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "sql.log"
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "SQL_LOG": str(log),
        "POSTGRES_USER": "postgres",
        "POSTGRES_DB": "qa_generator",
        "APP_DB_USER": "qa_generator",
        "APP_DB_PASSWORD": chosen,
    }
    for role in ("SEAWEEDFS", "PHOENIX", "DAGSTER", "ARGILLA", "GRAFANA"):
        env[f"{role}_DB_USER"] = role.lower()
        env[f"{role}_DB_PASSWORD"] = "hex0123456789abcdef1"
    subprocess.run(
        ["bash", str(ROOT / "configs/postgres/init.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    recorded = log.read_text()
    assert f"ARG pw={chosen}" in recorded
    assert "ALTER ROLE qa_generator LOGIN PASSWORD :'pw';" in recorded
    sql = "\n".join(
        line for line in recorded.splitlines() if not line.startswith("ARG ")
    )
    assert chosen not in sql, "the password is in the SQL text"


def test_the_doctor_reads_every_password_compose_puts_in_a_url() -> None:
    """Read back out of compose.yaml, so a new URL with a password is caught."""
    compose = (ROOT / "compose.yaml").read_text()
    in_urls = set(re.findall(r"://[^\s:]*:\$\{([A-Z_]+PASSWORD)[^}]*\}@", compose))

    assert in_urls <= set(_URL_PASSWORDS), sorted(in_urls - set(_URL_PASSWORDS))
