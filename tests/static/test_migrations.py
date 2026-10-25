"""The shape of the migration history.

Read through alembic's own script directory, so this sees what `alembic
upgrade` would. No database: whether the schema the revisions build matches
the models is a question for a live one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend/database/migrations/versions"

_REVISION = re.compile(r"^revision: str = [\"']([^\"']+)[\"']", re.MULTILINE)


@pytest.fixture(scope="module")
def scripts() -> ScriptDirectory:
    """The revisions, as alembic reads them."""
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))


def test_there_is_exactly_one_head(scripts: ScriptDirectory) -> None:
    """Two heads mean two people wrote a revision against the same parent."""
    heads = scripts.get_heads()

    assert len(heads) == 1, f"{len(heads)} heads: {heads}. Merge them."


def test_there_is_exactly_one_base(scripts: ScriptDirectory) -> None:
    """One history, starting once."""
    bases = scripts.get_bases()

    assert len(bases) == 1, f"{len(bases)} bases: {bases}"


def test_every_revision_file_is_reachable_from_the_head(
    scripts: ScriptDirectory,
) -> None:
    """A revision off the chain is one `upgrade head` never runs."""
    reachable = {revision.revision for revision in scripts.walk_revisions()}
    on_disk = {
        match.group(1)
        for path in VERSIONS.glob("*.py")
        if (match := _REVISION.search(path.read_text()))
    }

    assert on_disk, f"no revisions found in {VERSIONS}"
    assert on_disk == reachable, f"off the chain: {sorted(on_disk - reachable)}"


def test_every_parent_named_exists(scripts: ScriptDirectory) -> None:
    """A down_revision pointing at nothing breaks the whole upgrade."""
    reachable = {revision.revision for revision in scripts.walk_revisions()}

    for revision in scripts.walk_revisions():
        named = revision.down_revision
        parents = (named,) if isinstance(named, str) else tuple(named or ())
        missing = set(parents) - reachable
        assert not missing, f"{revision.revision} names {missing}, which is not here"


def test_every_revision_can_be_taken_back_out(scripts: ScriptDirectory) -> None:
    """An upgrade with no downgrade is a one-way door."""
    import ast

    for revision in scripts.walk_revisions():
        tree = ast.parse(Path(revision.path).read_text())
        downgrade = next(
            (
                one
                for one in tree.body
                if isinstance(one, ast.FunctionDef) and one.name == "downgrade"
            ),
            None,
        )
        assert downgrade is not None, revision.path
        assert not all(
            isinstance(one, ast.Pass)
            or (isinstance(one, ast.Expr) and isinstance(one.value, ast.Constant))
            for one in downgrade.body
        ), f"{Path(revision.path).name} has an empty downgrade"


#: Revisions up to here predate the rule below and are not read against it.
_BEFORE_THE_RULE = "20261021_0300"


def _blocking_check(source: str) -> bool:
    """Whether a revision adds a CHECK that scans the table under its lock.

    A CHECK added `NOT VALID` takes a short lock and is validated by a later
    revision; `op.create_check_constraint` has no such option.
    """
    if "create_check_constraint(" in source:
        return True
    adds = re.findall(
        r"ADD\s+CONSTRAINT[^;\"']*?\bCHECK\b[^;]*", source, re.IGNORECASE | re.DOTALL
    )
    return any("NOT VALID" not in one.upper() for one in adds)


@pytest.mark.parametrize(
    ("source", "blocks"),
    [
        ('op.create_check_constraint("c", "questions", "a > 0")', True),
        ('op.execute("ALTER TABLE questions ADD CONSTRAINT c CHECK (a > 0)")', True),
        (
            'op.execute("ALTER TABLE questions ADD CONSTRAINT c CHECK (a > 0) NOT VALID")',
            False,
        ),
        ('op.execute("ALTER TABLE rechnungen ADD CONSTRAINT c CHECK (b)")', True),
        ('op.add_column("orders", sa.Column("x", sa.Text()))', False),
    ],
)
def test_the_check_rule_reads_a_revision(source: str, blocks: bool) -> None:
    """In any table's name and in any language of its comments."""
    assert _blocking_check(source) is blocks


def test_no_revision_after_the_rule_adds_a_blocking_check() -> None:
    """A CHECK is added NOT VALID, and validated by a revision of its own."""
    later = [p for p in sorted(VERSIONS.glob("*.py")) if p.name > _BEFORE_THE_RULE]

    assert [p.name for p in later if _blocking_check(p.read_text())] == []
