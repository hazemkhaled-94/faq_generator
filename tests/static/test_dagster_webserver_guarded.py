"""Every start of Dagster's webserver goes through `orchestration.serve`.

Dagster's own webserver answers a GraphQL mutation sent as a GET and takes
a write from any page the operator has open, so a web page could launch or stop
a pipeline run with the token the stack's code location holds. `serve.py`
refuses those. `make dagster-dev` ran plain `dagster dev`, which starts the
unguarded webserver on the host, and nothing checked that the next recipe, compose
command or image command did not do the same.

Three readings of a start: the words of a shell or Makefile line, the command
and entrypoint of each compose service (a list or a string), and the CMD and
ENTRYPOINT of each image (JSON or shell form), so an exec form is not missed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKIPPED = {".git", "node_modules", ".venv", "venv", "__pycache__", "tests"}

#: `dagster dev`, the webserver's module, or the `dagster-webserver` program
#: given an option or a module path: starts, wherever they stand.
ALWAYS = (
    r"(?<![\w./-])dagster\s+dev\b",
    r"\bdagster_webserver\b",
    r"(?<![\w./=:-])dagster-webserver(?=\s+(?:-|\w+\.))",
)
#: `dagster-webserver` as the program word of a command: after the start of a
#: line, `&&`, `;`, `|`, `exec`, `run`, `(`, `[` or a quote, and before a quote,
#: a comma, a backslash, a space or the end. A service NAMED dagster-webserver
#: (`build api dagster-webserver`, `exec -T dagster-webserver dagster ...`)
#: follows other words and is not one.
PROGRAM = r"(?:^|&&|;|\||\bexec|\brun|\(|\[|[\"'])\s*dagster-webserver(?![\w=:.-])(?=\s*(?:$|[\"',\\]))"
STARTS = re.compile("|".join((*ALWAYS, PROGRAM)))

#: Words, for a command read from a list or a Dockerfile instruction: there,
#: a bare `dagster-webserver` is the program.
WORDS = re.compile("|".join((*ALWAYS, r"(?<![\w./=:-])dagster-webserver(?![\w=:.-])")))


def _walk(suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(
        one
        for one in ROOT.rglob("*")
        if one.is_file()
        and one.suffix in suffixes
        and not SKIPPED & set(one.relative_to(ROOT).parts)
    )


def _line_files() -> list[Path]:
    found = [ROOT / "Makefile", *_walk((".sh", ".yml", ".yaml", ".mk"))]
    found += [one for one in _walk(("",)) if one.name.startswith("Dockerfile")]
    return sorted(set(found))


def _code(text: str) -> list[tuple[int, str]]:
    """The lines that are not whole-line comments."""
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), 1)
        if not line.lstrip().startswith("#")
    ]


def _command_text(value: object) -> str:
    """A compose command or entrypoint, list or string, as one string."""
    if value is None:
        return ""
    return " ".join(value) if isinstance(value, list) else str(value)


def compose_starts(text: str) -> list[str]:
    """The services of a compose file whose command or entrypoint starts it."""
    found = []
    for name, service in (yaml.safe_load(text).get("services") or {}).items():
        for field in ("command", "entrypoint"):
            if WORDS.search(_command_text(service.get(field))):
                found.append(f"{name}.{field}")
    return found


def image_starts(text: str) -> list[str]:
    """The CMD and ENTRYPOINT instructions of an image file that start it."""
    found = []
    joined = re.sub(r"\\\n", " ", text)
    for _number, line in _code(joined):
        match = re.match(r"\s*(CMD|ENTRYPOINT)\s+(.*)", line, re.IGNORECASE)
        if not match:
            continue
        body = match.group(2).strip()
        if body.startswith("["):
            try:
                body = " ".join(json.loads(body))
            except ValueError:
                pass
        if WORDS.search(body):
            found.append(f"{match.group(1)}: {body}")
    return found


PLANTED_LINES = [
    "poetry run dagster dev",
    "exec dagster-webserver -h 0.0.0.0 -p 3000",
    "python -m dagster_webserver.cli",
    "cd x && dagster-webserver \\",
    "sh -c 'dagster-webserver'",
    "\tdagster-webserver",
    '  command: ["dagster-webserver", "-w", "w.yaml"]',
]
ORDINARY_LINES = [
    "exec -T dagster-webserver dagster run list",
    "$DC build api dagster-webserver",
    "up -d --wait api dagster-webserver dagster-daemon",
    "dagster-webserver=dagster-webserver:3000",
    "python -m orchestration.serve -h 127.0.0.1 -p 3000",
    "logs -f dagster-webserver dagster-daemon",
]


@pytest.mark.parametrize("line", PLANTED_LINES)
def test_a_line_that_starts_the_webserver_is_found(line: str) -> None:
    """A guard that matches nothing guards nothing."""
    assert STARTS.search(line), line


@pytest.mark.parametrize("line", ORDINARY_LINES)
def test_a_line_that_only_names_the_service_is_not_one(line: str) -> None:
    """The service, the container and the serve module are not starts."""
    assert not STARTS.search(line), line


@pytest.mark.parametrize(
    "command",
    [
        'command: ["dagster-webserver", "-w", "w.yaml"]',
        'command: ["dagster", "dev"]',
        "command: dagster-webserver -w w.yaml",
        'entrypoint: ["python", "-m", "dagster_webserver"]',
        'command: ["sh", "-c", "exec dagster-webserver -h 0.0.0.0"]',
    ],
)
def test_a_compose_command_in_exec_or_string_form_is_found(command: str) -> None:
    """Both forms of a service's command or entrypoint."""
    assert compose_starts(f"services:\n  web:\n    {command}\n")


def test_the_serve_command_is_not_a_start() -> None:
    """What the service runs now."""
    shipped = (ROOT / "compose.yaml").read_text()
    assert compose_starts(shipped) == []
    assert (
        compose_starts(
            'services:\n  web:\n    command: ["python", "-m", "orchestration.serve"]\n'
        )
        == []
    )


@pytest.mark.parametrize(
    "instruction",
    [
        'CMD ["dagster-webserver", "-h", "0.0.0.0"]',
        'ENTRYPOINT ["dagster", "dev"]',
        "CMD dagster-webserver -h 0.0.0.0",
        'CMD ["python", "-m", "dagster_webserver"]',
        "CMD sh -c 'cd /app && \\\n  dagster-webserver -p 3000'",
    ],
)
def test_an_image_command_in_json_or_shell_form_is_found(instruction: str) -> None:
    """Both forms of an image's CMD or ENTRYPOINT."""
    assert image_starts(f"FROM scratch\n{instruction}\n")


def test_no_recipe_script_workflow_compose_command_or_image_starts_it() -> None:
    """Every start there is goes through `orchestration.serve`, which is not matched."""
    unguarded = []
    for path in _line_files():
        text = path.read_text()
        unguarded += [
            f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
            for number, line in _code(text)
            if STARTS.search(line)
        ]
        if path.name.startswith("compose") and path.suffix in (".yaml", ".yml"):
            unguarded += [f"{path.name}: {one}" for one in compose_starts(text)]
        if path.name.startswith("Dockerfile"):
            unguarded += [
                f"{path.relative_to(ROOT)}: {one}" for one in image_starts(text)
            ]

    assert unguarded == []


def test_the_webserver_service_runs_serve() -> None:
    """The one start there is: the compose service's command."""
    command = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"][
        "dagster-webserver"
    ]["command"]

    assert "orchestration.serve" in _command_text(command)
