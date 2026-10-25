"""`make doctor` lists every name the secrets file sets over a committed file.

`.env` is read after `configs/env/backend.env` and `configs/env/deployment.env`,
so a name it sets again wins. That is how a second stack moves its ports, and
it is also how a value set twice by mistake goes unseen: the doctor names each
one with the file it wins over.
"""

from __future__ import annotations

from pathlib import Path

from api.doctor import overridden


def _files(tmp_path: Path, env: str) -> tuple[Path, list[Path]]:
    backend = tmp_path / "backend.env"
    backend.write_text("EXTRACTION_DUPLICATE_COSINE=0.985\nLOG_LEVEL=INFO\n")
    deployment = tmp_path / "deployment.env"
    deployment.write_text(
        "# Where this deployment put things.\nPOSTGRES_PORT=5432\nS3_PORT=8333\n"
    )
    secrets = tmp_path / ".env"
    secrets.write_text(env)
    return secrets, [backend, deployment]


def test_a_port_the_secrets_file_sets_again_is_listed_with_its_file(
    tmp_path: Path,
) -> None:
    """The second stack's case: one port moved, nothing else."""
    secrets, committed = _files(
        tmp_path, "APP_DB_PASSWORD=9f3c1e7a2b\nPOSTGRES_PORT=25432\n"
    )

    assert overridden(secrets, committed) == [("POSTGRES_PORT", committed[1])]


def test_a_name_only_the_secrets_file_sets_is_no_override(tmp_path: Path) -> None:
    """Its passwords and model names are what it is for."""
    secrets, committed = _files(tmp_path, "APP_DB_PASSWORD=9f3c1e7a2b\n")

    assert overridden(secrets, committed) == []


def test_a_commented_line_overrides_nothing(tmp_path: Path) -> None:
    """Neither in the secrets file nor in a committed one."""
    secrets, committed = _files(tmp_path, "# POSTGRES_PORT=25432\n")
    committed[0].write_text("# S3_PORT=1\n")

    assert overridden(secrets, committed) == []


def test_each_committed_file_is_named_for_its_own_names(tmp_path: Path) -> None:
    """In the order the files are read, every name once."""
    secrets, committed = _files(
        tmp_path, "S3_PORT=28333\nLOG_LEVEL=DEBUG\nPOSTGRES_PORT=25432\n"
    )

    assert overridden(secrets, committed) == [
        ("LOG_LEVEL", committed[0]),
        ("POSTGRES_PORT", committed[1]),
        ("S3_PORT", committed[1]),
    ]


def test_a_missing_file_overrides_nothing(tmp_path: Path) -> None:
    """`make doctor` says so on its own line before it gets here."""
    _, committed = _files(tmp_path, "")

    assert overridden(tmp_path / "absent.env", committed) == []
