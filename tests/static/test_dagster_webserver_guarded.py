"""Every start of Dagster's webserver goes through `orchestration.serve`.

Dagster's own webserver answers a GraphQL mutation sent as a GET and takes
a write from any page the operator has open, so a web page could launch or stop
a pipeline run with the token the stack's code location holds. `serve.py`
refuses those. `make dagster-dev` ran plain `dagster dev`, which starts the
unguarded webserver on the host, and nothing checked that the next recipe, compose
command, image command or script did not do the same.

The guard denies by default. Backslash-continued lines are joined, and every
occurrence of a start word in the Makefile, every script, every YAML file, every
image file (Dockerfile*, *.dockerfile, Containerfile*) and the workflows is a
failure, unless its context is one of a short list that is not a start: the line
runs `orchestration.serve`; the word is a compose service's own key or a
container name; it names the service after a compose verb; it is an address, a
probe name, a list of service names or the argument of a make macro that names a
service; or it is only printed. Commands and entrypoints in YAML (lists or
strings, anywhere) and the CMD and ENTRYPOINT of images are read as words too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKIPPED = {".git", "node_modules", ".venv", "venv", "__pycache__", "tests", "docs"}

#: The program or module, by its basename, wherever it stands on a line.
WORD = re.compile(r"(?<![\w.-])(?:dagster-webserver|dagster_webserver)(?![\w-])")
#: `dagster dev` and `dg dev`, quoted or comma-separated, and the make macro
#: that runs `dagster $(1)` in the container.
DEV = re.compile(
    r"(?<![\w-])(?:dagster|dg)[\"']*[\s,]+[\"']*dev\b|\$\(call DAGSTER,\s*dev\b"
)

#: A compose verb that takes service names, and the ones that take a command.
LISTING = ("logs", "build", "up", "restart", "stop", "start", "ps")
COMMANDING = ("exec", "run")


#: What puts a compose verb in a command: compose or a container engine, or a
#: variable that holds one (`$(COMPOSE_CMD)`, `$DC`). A bare `run` or `exec` is
#: the shell's, and what follows it is a program.
ENGINE = r"(?:compose|docker|podman|COMPOSE\w*|\bDC\b)"


def _tokens(before: str, verb: str) -> list[str]:
    """The words between a verb and a start word."""
    return re.split(rf"(?<![\w-]){verb}(?![\w-])", before)[-1].split()


def _after_verb(line: str, found: re.Match[str]) -> bool:
    """Whether the word names the service of a compose verb, not a program."""
    if "--entrypoint" in line:
        return False
    segment = re.split(r"&&|;|\|\||\||\$\(|\(|\{|`|>", line[: found.start()])[-1]
    for verb in LISTING:
        if re.search(rf"{ENGINE}.*(?<![\w-]){verb}(?![\w-])", segment):
            between = _tokens(segment, verb)
            if not any(WORD.fullmatch(one) for one in between):
                return True
    for verb in COMMANDING:
        if re.search(rf"{ENGINE}.*(?<![\w-]){verb}(?![\w-])", segment):
            # The first positional word is the service; later ones are the command.
            between = _tokens(segment, verb)
            if all(one.startswith("-") or "=" in one for one in between):
                return True
    return False


def _printed(line: str, found: re.Match[str]) -> bool:
    segment = re.split(r"&&|;|\|\||\||\$\(|\(|\{|`", line[: found.start()])[-1]
    return re.match(r"\s*[@-]*\s*(?:echo|printf)\b", segment) is not None


def _allowed(lines: list[str], index: int, found: re.Match[str]) -> bool:
    """Whether this occurrence has one of the contexts that are not a start."""
    line = lines[index]
    word = found.group(0)
    if "orchestration.serve" in line:
        return True
    if re.fullmatch(rf"\s*(?:container_name:\s*)?{word}:?\s*(?:#.*)?", line):
        return "container_name" in line or line.rstrip().endswith(":") or ":" in line
    if re.fullmatch(rf"\s*-\s*{word}\s*", line):
        # A service named in a list: only under depends_on.
        indent = len(line) - len(line.lstrip())
        for above in reversed(lines[:index]):
            if above.strip() and len(above) - len(above.lstrip()) < indent:
                return above.strip() == "depends_on:"
        return False
    around = line[max(0, found.start() - 4) : found.end() + 8]
    if re.search(rf"://{word}|{word}(?::\d|:\$\{{|=)", around):
        return True  # an address, or a probe's `name=` before its address
    if re.fullmatch(
        r"[A-Z_][A-Z0-9_]*\s*[:?+]?=\s*[a-z][\w-]*(?:\s+[a-z][\w-]*)*\s*", line
    ):
        return True  # a make variable holding service names
    if re.search(rf"\$\(call (?:WIPE_STEP|STORE_DOWN|RUNNING),{word}[,)]", line):
        return True
    return _printed(line, found) or _after_verb(line, found)


def starts(text: str) -> list[str]:
    """The lines of a script, recipe or YAML file that start the webserver."""
    joined = re.sub(r"\\\n", " ", text)
    lines = joined.splitlines()
    found = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if DEV.search(line):
            found.append(line.strip())
        for word in WORD.finditer(line):
            if not _allowed(lines, index, word):
                found.append(line.strip())
    return found


def _commands(value: object) -> list[str | list[str]]:
    """Every command, entrypoint, args or run value in a YAML document."""
    found: list[str | list[str]] = []
    if isinstance(value, dict):
        for name, inner in value.items():
            if name in ("command", "entrypoint", "args", "run", "cmd"):
                if isinstance(inner, list):
                    found.append([str(one) for one in inner])
                elif isinstance(inner, str):
                    found.append(inner)
            found += _commands(inner)
    elif isinstance(value, list):
        for inner in value:
            found += _commands(inner)
    return found


def command_starts(text: str) -> list[str]:
    """Commands in a YAML document, as lists or strings, that start the webserver.

    A string is read as a script is. A list is words: there, a start word is
    the program, whatever else is in it.
    """
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return []
    found = []
    for document in documents:
        for one in _commands(document):
            if isinstance(one, str):
                found += starts(one)
                continue
            joined = " ".join(one)
            if (
                DEV.search(joined)
                or WORD.search(joined)
                and "orchestration.serve" not in joined
            ):
                found.append(joined)
    return found


def image_starts(text: str) -> list[str]:
    """The CMD and ENTRYPOINT instructions of an image file that start it."""
    found = []
    for line in re.sub(r"\\\n", " ", text).splitlines():
        match = re.match(r"\s*(CMD|ENTRYPOINT)\s+(.*)", line, re.IGNORECASE)
        if not match:
            continue
        body = match.group(2).strip()
        if body.startswith("["):
            try:
                body = " ".join(json.loads(body))
            except ValueError:
                pass
        if DEV.search(body) or WORD.search(body) and "orchestration.serve" not in body:
            found.append(f"{match.group(1)}: {body}")
    return found


def _is_image(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(("dockerfile", "containerfile")) or name.endswith(
        ".dockerfile"
    )


def _files(root: Path = ROOT) -> list[Path]:
    return sorted(
        one
        for one in root.rglob("*")
        if one.is_file()
        and not SKIPPED & set(one.relative_to(root).parts)
        and (
            one.name == "Makefile"
            or one.suffix in (".sh", ".mk", ".yml", ".yaml")
            or _is_image(one)
        )
    )


def scan(path: Path, text: str) -> list[str]:
    """Everything in one file that starts the webserver, however it is written."""
    found = starts(text)
    if path.suffix in (".yml", ".yaml"):
        found += command_starts(text)
    if _is_image(path):
        found += image_starts(text)
    return found


#: The forms reviewers planted, each of which a start.
PLANTED = [
    "dagster-webserver &",
    "cd /app && dagster-webserver &",
    "nohup dagster-webserver > web.log 2>&1 &",
    "DAGSTER_HOME=/x dagster-webserver",
    "env DAGSTER_HOME=/x dagster-webserver",
    "dagster-webserver $DAGSTER_ARGS",
    "timeout 600 dagster-webserver",
    "\tpoetry run dagster \\\n\tdev",
    "poetry run dagster \\\n  dev",
    "\tpoetry run dg dev",
    "\t.venv/bin/dagster dev",
    "/usr/local/bin/dagster-webserver -h 0.0.0.0 -p 3000",
    'poetry run dagster "dev"',
    "$(DC) run --rm --entrypoint dagster-webserver orchestrator -h 0.0.0.0",
    "docker run --entrypoint=dagster-webserver img",
    "poetry run dagster-webserver -h 0.0.0.0",
    "python -m dagster_webserver.cli",
    "exec -T svc dagster-webserver -h 0.0.0.0",
    "\t$(call DAGSTER,dev)",
    "run: nohup dagster-webserver > web.log 2>&1 &",
    "        run: |\n          dagster-webserver &",
    "cd configs/dagster && dagster-webserver &",
    "exec dagster-webserver -h 0.0.0.0 -p 3000",
]

#: Lines that only name the service, and the serve module.
ORDINARY = [
    "$(COMPOSE_CMD) exec -T dagster-webserver dagster run list --limit 1",
    '$(COMPOSE_CMD) exec -T -e APP_DB_NAME="$$APP_DB_NAME" dagster-webserver python -m x',
    "$(COMPOSE_CMD) logs -f dagster-webserver dagster-daemon",
    "run: $DC build api dagster-webserver",
    "run: $DC up -d --wait api parse-worker dagster-webserver dagster-daemon",
    "$(COMPOSE_CMD) run --rm dagster-webserver dagster run list",
    "  dagster-webserver:",
    "    container_name: dagster-webserver",
    "      DAGSTER_URL: ${DAGSTER_URL:-http://dagster-webserver:3000}",
    "        dagster-webserver=http://localhost:${DAGSTER_WEBSERVER_PORT},",
    "OFF_PROFILE = extract-worker dagster-webserver dagster-daemon",
    "\t@$(call WIPE_STEP,dagster-webserver,dagster-wipe)",
    "\tif $(call RUNNING,dagster-webserver); then",
    '\t{ echo "REFUSED: dagster-webserver did not answer" >&2; }',
    "python -m orchestration.serve -h 127.0.0.1 -p 3000",
]


@pytest.mark.parametrize("text", PLANTED)
def test_a_start_of_the_webserver_is_found(text: str) -> None:
    """Every form a reviewer planted fails the guard."""
    assert starts(text), text


@pytest.mark.parametrize("text", ORDINARY)
def test_a_line_that_only_names_the_service_is_not_one(text: str) -> None:
    """The service, the container and the serve module are not starts."""
    assert starts(text) == [], text


def test_a_service_listed_under_depends_on_is_not_a_start() -> None:
    """A list item is allowed there and nowhere else."""
    ok = "services:\n  api:\n    depends_on:\n      - dagster-webserver\n"
    bad = "services:\n  api:\n    command:\n      - dagster-webserver\n"
    assert starts(ok) == []
    assert starts(bad) == ["- dagster-webserver"]


@pytest.mark.parametrize(
    "command",
    [
        'command: ["dagster-webserver", "-w", "w.yaml"]',
        'command: ["dagster", "dev"]',
        "command: dagster-webserver -w w.yaml",
        'entrypoint: ["python", "-m", "dagster_webserver"]',
        'command: ["sh", "-c", "exec dagster-webserver -h 0.0.0.0"]',
        'command: ["dg", "dev"]',
        'command: ["/usr/local/bin/dagster-webserver", "-h", "0.0.0.0"]',
        "command:\n      - dagster-webserver\n      - -h",
        "command:\n      - dagster\n      - dev",
    ],
)
def test_a_yaml_command_in_list_block_or_string_form_is_found(command: str) -> None:
    """Any YAML, whatever its name, and any key called command or entrypoint."""
    assert command_starts(f"services:\n  web:\n    {command}\n")


@pytest.mark.parametrize(
    "instruction",
    [
        'CMD ["dagster-webserver", "-h", "0.0.0.0"]',
        'ENTRYPOINT ["dagster", "dev"]',
        "CMD dagster-webserver -h 0.0.0.0",
        'CMD ["python", "-m", "dagster_webserver"]',
        "CMD sh -c 'cd /app && \\\n  dagster-webserver -p 3000'",
        'CMD ["/usr/local/bin/dagster-webserver", "-h", "0.0.0.0"]',
        'ENTRYPOINT ["/app/.venv/bin/dagster", "dev"]',
        'CMD ["dg", "dev"]',
    ],
)
def test_an_image_command_in_json_or_shell_form_is_found(instruction: str) -> None:
    """Both forms of an image's CMD or ENTRYPOINT."""
    assert image_starts(f"FROM scratch\n{instruction}\n")


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("Makefile", "ui:\n\tnohup dagster-webserver > web.log 2>&1 &\n"),
        ("Makefile", "ui:\n\tDAGSTER_HOME=$$PWD poetry run dagster \\\n\t  dev\n"),
        ("configs/x/entrypoint.sh", "dagster-webserver &\n"),
        (
            ".github/workflows/ui.yml",
            "jobs:\n  a:\n    steps:\n      - run: |\n          dagster-webserver &\n",
        ),
        (
            "orchestration/Dockerfile.dev",
            'CMD ["dagster-webserver", "-h", "0.0.0.0"]\n',
        ),
        ("orchestration/Containerfile", 'CMD ["dagster-webserver"]\n'),
        ("orchestration/ui.dockerfile", 'ENTRYPOINT ["dagster", "dev"]\n'),
        (
            "configs/dev/docker-compose.yml",
            "services:\n  ui:\n    command:\n      - dagster-webserver\n",
        ),
    ],
)
def test_a_planted_file_fails_the_whole_repository_scan(
    name: str, text: str, tmp_path: Path
) -> None:
    """A start planted in any kind of file the repository holds is found."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)

    found = [one for one in _files(tmp_path) if one == path]

    assert found == [path], "the file kind is not scanned"
    assert scan(path, text), "the start in it is not found"


def test_no_script_recipe_workflow_compose_command_or_image_starts_it() -> None:
    """Every start there is goes through `orchestration.serve`."""
    unguarded = [
        f"{path.relative_to(ROOT)}: {one}"
        for path in _files()
        for one in scan(path, path.read_text())
    ]

    assert unguarded == []


def test_the_webserver_service_runs_serve() -> None:
    """The one start there is: the compose service's command."""
    command = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"][
        "dagster-webserver"
    ]["command"]

    assert "orchestration.serve" in " ".join(command)
