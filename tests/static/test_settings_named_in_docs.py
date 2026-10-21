"""What the documentation says about the settings, against what the code reads.

`test_settings_documented` holds every setting the code reads by literal
name to a file that declares it. Three things it leaves out:

    a setting read through a module constant, `os.getenv(TRACE_DATABASE)`,
    which its scan cannot see and the telemetry README checks "by hand"
    a settings table that says which file declares a setting
    the list of settings whose absence reads a default in code, which the
    configuration guide and the settings README give as the only exceptions
    to "a missing variable stops the service"

Read as syntax, so nothing is imported but the scan.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from tests.static.settings_scan import read_by

ROOT = Path(__file__).resolve().parents[2]

#: Directories holding the code that runs on the host or in a container.
SOURCES = ("backend", "frontend", "telemetry", "orchestration", "review", "evaluation")

#: Every file a deployment edits, as test_env_files lists them.
ENV_FILES = (
    ".env.example",
    "configs/env/backend.env",
    "configs/env/deployment.env",
    "configs/env/elasticsearch.env",
    "configs/env/evaluation.env",
    "configs/env/orchestration.env",
    "configs/env/review.env",
    "configs/env/seaweedfs-filer.env",
    "configs/env/provider.env.example",
)

_DECLARED = re.compile(r"^[^\S\n]*#?[^\S\n]*([A-Z][A-Z0-9_]*)[^\S\n]*=", re.MULTILINE)

_ENVIRON_CALLS = {
    "os.getenv",
    "getenv",
    "os.environ.get",
    "environ.get",
}


def _modules() -> list[Path]:
    return [
        path
        for source in SOURCES
        for path in sorted((ROOT / source).glob("**/*.py"))
        if "__pycache__" not in path.parts
    ]


def _through_a_constant(source: str) -> set[str]:
    """Names read from the environment, a module constant resolved to its value."""
    tree = ast.parse(source)
    constants = {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def value(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return constants.get(node.id) if isinstance(node, ast.Name) else None

    found = set()
    for node in ast.walk(tree):
        named = None
        if isinstance(node, ast.Call) and node.args:
            if ast.unparse(node.func) in _ENVIRON_CALLS:
                named = value(node.args[0])
        elif isinstance(node, ast.Subscript) and "environ" in ast.unparse(node.value):
            named = value(node.slice)
        if named and re.fullmatch(r"[A-Z][A-Z0-9_]+", named):
            found.add(named)
    return found


def _read() -> dict[str, str]:
    """Every setting any module reads, and the first module that reads it."""
    read: dict[str, str] = {}
    for path in _modules():
        source = path.read_text()
        for name in read_by(source) | _through_a_constant(source):
            read.setdefault(name, str(path.relative_to(ROOT)))
    return read


READ = _read()


def _docs() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "docs/*.md", "*README.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [ROOT / one for one in listed if (ROOT / one).exists()]


DOCS = "\n".join(path.read_text() for path in _docs())


def test_the_rows_naming_a_file_are_found() -> None:
    """The llm, telemetry and evaluation READMEs each have such a table."""
    assert len(ROWS) > 20, len(ROWS)


def test_the_scan_sees_what_a_constant_names() -> None:
    """The settings the telemetry README says the literal scan cannot see."""
    assert {"TRACE_DATABASE", "LOG_DIR", "RUN_ID", "DATABASE_URL"} <= set(READ)
    assert len(READ) > 100, len(READ)


@pytest.mark.parametrize("name", sorted(READ))
def test_every_setting_the_code_reads_is_named_in_a_doc(name: str) -> None:
    """In backticks, in docs/ or a README: where an operator looks it up."""
    assert f"`{name}`" in DOCS, f"{name}, read in {READ[name]}, is in no doc"


def _declared_in() -> dict[str, set[str]]:
    where: dict[str, set[str]] = {}
    for relative in ENV_FILES:
        for name in _DECLARED.findall((ROOT / relative).read_text()):
            where.setdefault(name, set()).add(Path(relative).name)
    return where


DECLARED = _declared_in()


def _table_rows() -> list[tuple[str, int, str, str]]:
    """(doc, line, setting, second cell) for each row whose second cell names a file."""
    rows = []
    for path in _docs():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            found = re.match(r"^\| `([A-Z][A-Z0-9_]+)` \|([^|]*)\|", line)
            if found and re.search(r"\.env\b", found[2]) and found[1] in DECLARED:
                relative = str(path.relative_to(ROOT))
                rows.append((relative, number, found[1], found[2]))
    return rows


ROWS = _table_rows()


@pytest.mark.parametrize(
    ("doc", "line", "name", "cell"), ROWS, ids=[f"{r[0]}:{r[1]}" for r in ROWS]
)
def test_a_table_that_names_the_file_names_the_one_declaring_it(
    doc: str, line: int, name: str, cell: str
) -> None:
    """`| NAME | backend.env |` is where an operator goes to change it."""
    files = set(re.findall(r"([a-z][a-z-]*\.env(?:\.example)?)", cell))
    if "`.env`" in cell:
        files.add(".env.example")  # .env is not in git; the example stands in

    assert files & DECLARED[name], (
        f"{doc}:{line} says {name} is in {sorted(files)}; "
        f"it is declared in {sorted(DECLARED[name])}"
    )


def _defaulted_in_code() -> set[str]:
    """Settings an absent value of which is replaced by a value in code.

    `X if optional("NAME") else <value>` and `optional("NAME") or <value>`,
    where the value is not None or empty: absence then reads something.
    """

    def optional(node: ast.AST) -> str | None:
        if isinstance(node, ast.NamedExpr):
            node = node.value
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", None)) == "optional"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            return node.args[0].value
        return None

    def empty(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value in (None, "", ())

    found = set()
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.IfExp)
                and (name := optional(node.test))
                and not empty(node.orelse)
            ):
                found.add(name)
            if (
                isinstance(node, ast.BoolOp)
                and isinstance(node.op, ast.Or)
                and (name := optional(node.values[0]))
                and not empty(node.values[1])
            ):
                found.add(name)
    return found


DEFAULTED = sorted(_defaulted_in_code())


def test_the_defaults_in_code_are_found() -> None:
    """The two the docs already list, so a moved reader cannot pass vacuously."""
    assert {"QUESTIONS_MEETS_SHARE", "QUESTIONS_CATEGORIZATIONS"} <= set(DEFAULTED)


def _precedence() -> str:
    text = (ROOT / "docs/configuration.md").read_text()
    return text.split("\n## Precedence\n", 1)[1].split("\n## ", 1)[0]


def _settings_opening() -> str:
    text = (ROOT / "backend/settings/README.md").read_text()
    return text.split("\n## ", 1)[0]


@pytest.mark.xfail(
    strict=True,
    reason="QUESTIONS_KIND_MIX reads needs_both:5,compound:1 in code when absent, and neither the configuration guide nor the settings README lists it among the settings that read a default",
)
def test_every_default_in_code_is_one_the_docs_list() -> None:
    """Both pages give the exceptions to "a missing variable stops the service"."""
    unlisted = {
        page: [name for name in DEFAULTED if f"`{name}`" not in text]
        for page, text in (
            ("docs/configuration.md#precedence", _precedence()),
            ("backend/settings/README.md", _settings_opening()),
        )
    }

    assert unlisted == {page: [] for page in unlisted}, unlisted
