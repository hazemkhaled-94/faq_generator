"""One name, one file, and nothing sensitive in git.

`test_settings_documented` checks that a setting the CODE reads is declared
somewhere. Nothing checked the files against each other, or against the one
consumer that reads none of them through a Python reader: compose, which
interpolates `${...}` and whose misses are a blank string and a warning.

Four rules, which together are what "a single source of truth" means here:

    a name is assigned in exactly one file
    every `${...}` compose interpolates is declared in one of them
    .env.example declares the same names as the files a clone will need
    .env.example holds placeholders, because it is the file that is in git
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

#: The files a deployment edits. `.env` itself is not here: it is gitignored
#: and personal, and `.env.example` is what stands in for it.
ENV_FILES = (
    ".env.example",
    "configs/env/backend.env",
    "configs/env/deployment.env",
    "configs/env/elasticsearch.env",
    "configs/env/evaluation.env",
    "configs/env/orchestration.env",
    "configs/env/review.env",
    "configs/env/seaweedfs-filer.env",
)

#: An assignment that is live, not one commented out to document an optional
#: setting. `[^\S\n]` rather than `\s`, which would swallow the newline after
#: a bare `#` and read the next line as commented.
_ASSIGNED = re.compile(r"^[^\S\n]*([A-Z][A-Z0-9_]*)[^\S\n]*=", re.MULTILINE)

#: The same, commented out. Declaring an optional setting without setting it.
_COMMENTED = re.compile(r"^[^\S\n]*#[^\S\n]*([A-Z][A-Z0-9_]*)[^\S\n]*=", re.MULTILINE)

#: `${NAME}`, `${NAME:-default}`, `${NAME?message}`. The name only.
_INTERPOLATED = re.compile(r"\$\{([A-Z][A-Z0-9_]*)")


def _compose() -> str:
    """compose.yaml without its comments.

    The comments discuss interpolation - `naming them here as ${VAR:-} would
    set them empty` - and a scan that read those would ask for a variable
    called VAR.
    """
    lines = (ROOT / "compose.yaml").read_text().splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


#: Names compose interpolates that no env file declares, each because
#: something else supplies it.
SUPPLIED_ELSEWHERE = {
    # Derived from NLP_MODELS in backend.env by the Makefile, which exports
    # it so that `compose build` bakes what the workers will load. Declaring
    # it would be the copy this whole file exists to refuse.
    "SPACY_MODELS",
}


def _assigned(path: str) -> set[str]:
    """The names one file sets."""
    text = (ROOT / path).read_text()
    return set(_ASSIGNED.findall(text)) - set(_COMMENTED.findall(text))


def _declared(path: str) -> set[str]:
    """The names one file sets or documents as optional."""
    text = (ROOT / path).read_text()
    return set(_ASSIGNED.findall(text)) | set(_COMMENTED.findall(text))


def test_no_name_is_assigned_in_two_files() -> None:
    """Two files setting one name is two values free to disagree.

    Which one wins is then the order the Makefile happens to source them in,
    which is not a thing anybody should have to know.
    """
    where: dict[str, list[str]] = {}
    for path in ENV_FILES:
        for name in _assigned(path):
            where.setdefault(name, []).append(path)

    twice = {name: files for name, files in where.items() if len(files) > 1}

    assert not twice, "\n".join(
        f"{name} is set in {' and '.join(files)}"
        for name, files in sorted(twice.items())
    )


def test_every_name_compose_interpolates_is_declared() -> None:
    """A miss is a blank string and a warning, and the stack comes up wrong.

    This is the check that was missing when `LLM_CONTAINER_MODEL` was
    required by compose and only commented in `.env.example`, so a fresh
    clone could not start.
    """
    wanted = set(_INTERPOLATED.findall(_compose()))
    declared = {name for path in ENV_FILES for name in _declared(path)}

    undeclared = wanted - declared - SUPPLIED_ELSEWHERE

    assert not undeclared, (
        f"compose.yaml interpolates {', '.join(sorted(undeclared))}, which no "
        f"env file declares. A name only compose knows about can be found "
        f"only by reading compose.yaml."
    )


def test_a_required_interpolation_is_actually_set() -> None:
    """An interpolation with no fallback needs a value, not a comment.

    `${NAME:-x}` and `${NAME-x}` carry their own, so declaring those as a
    comment is how an optional setting is documented. `${NAME}` and
    `${NAME:?...}` do not: the first renders a blank string and a warning -
    a port binding of `:8000`, a password of nothing - and the second
    refuses to start. Both need the name actually set somewhere.
    """
    required = {
        name
        for name, tail in re.findall(r"\$\{([A-Z][A-Z0-9_]*)([^}]*)\}", _compose())
        if not tail.startswith(("-", ":-"))
    }
    assigned = {name for path in ENV_FILES for name in _assigned(path)}

    missing = required - assigned - SUPPLIED_ELSEWHERE

    assert not missing, (
        f"compose interpolates {', '.join(sorted(missing))} with no fallback, "
        f"so a commented declaration leaves it blank or stops the stack. Set "
        f"it in configs/env/deployment.env, or in .env.example if it is a "
        f"secret."
    )


def test_the_example_is_the_only_file_holding_a_secret() -> None:
    """`.env.example` stands in for the one file that is not in git.

    So every value in it is a placeholder. A real value here is one
    committed, and a name that is not a secret belongs in a file a
    deployment can review in a diff.
    """
    allowed = {
        # Which model this deployment calls, and where. A decision rather
        # than a credential, kept beside the credential that reaches it.
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_CONTAINER_MODEL",
        "OLLAMA_BASE_URL",
        "OLLAMA_CONTAINER_URL",
        "ASSESSMENT_ENABLED",
        "ASSESSMENT_JUDGE_MODEL",
        # The bearer header, whose value is PHOENIX_ADMIN_SECRET expanded.
        "OTEL_EXPORTER_OTLP_HEADERS",
    }

    text = (ROOT / ".env.example").read_text()
    real = []
    for line in text.splitlines():
        found = _ASSIGNED.match(line)
        if not found or _COMMENTED.match(line):
            continue
        name = found.group(1)
        value = line.split("=", 1)[1].strip()
        if name in allowed or value.startswith("change_me"):
            continue
        real.append(f"{name}={value}")

    assert not real, (
        "every value in .env.example is a change_me_* placeholder, because "
        "the file is in git and stands in for the one that is not. These are "
        "not: " + ", ".join(real)
    )


@pytest.mark.parametrize("path", ENV_FILES)
def test_a_value_carries_no_shell_expansion(path: str) -> None:
    """Bash sources these and compose parses them, and only one expands.

    A `${...}` therefore means one thing to a host command and another to a
    container. The exception is the OTLP header, which is only ever sourced.
    """
    for line in (ROOT / path).read_text().splitlines():
        found = _ASSIGNED.match(line)
        if not found or _COMMENTED.match(line):
            continue
        if found.group(1) == "OTEL_EXPORTER_OTLP_HEADERS":
            continue
        assert "${" not in line, f"{path}: {line}"


def _spacy_pipelines() -> list[str]:
    """The spaCy pipelines NLP_MODELS names, which is the only source.

    `de:de_core_news_md,en:en_core_web_md` -> the two model names.
    """
    line = next(
        value
        for name, value in (
            one.split("=", 1)
            for one in (ROOT / "configs/env/backend.env").read_text().splitlines()
            if "=" in one and not one.lstrip().startswith("#")
        )
        if name.strip() == "NLP_MODELS"
    )
    return [one.split(":", 1)[1] for one in line.split(",")]


def test_the_image_bakes_the_pipelines_the_workers_load() -> None:
    """Both fallbacks for SPACY_MODELS, against the list that decides.

    The Makefile derives SPACY_MODELS from NLP_MODELS and exports it, so
    `make` builds the right image whatever these say. They are what a bare
    `podman compose build` or `docker build` uses, and a pipeline missing
    from the image is a worker that starts and then cannot read a language.
    """
    wanted = _spacy_pipelines()

    dockerfile = (ROOT / "backend/api/Dockerfile").read_text()
    arg = re.search(r'^ARG SPACY_MODELS="([^"]*)"', dockerfile, re.MULTILINE)
    assert arg, "backend/api/Dockerfile declares no SPACY_MODELS ARG"
    assert arg.group(1).split() == wanted, (
        f"the Dockerfile bakes {arg.group(1)!r} and NLP_MODELS asks the "
        f"workers to load {' '.join(wanted)}"
    )

    for default in set(re.findall(r"\$\{SPACY_MODELS:-([^}]*)\}", _compose())):
        assert default.split() == wanted, (
            f"compose.yaml falls back to {default!r} and NLP_MODELS asks the "
            f"workers to load {' '.join(wanted)}"
        )


def test_the_checks_of_the_baked_pipelines_name_the_ones_the_workers_load() -> None:
    """CI's environment check and the smoke test each name them by hand."""
    wanted = _spacy_pipelines()
    action = (ROOT / ".github/actions/setup/action.yml").read_text()
    smoke = (ROOT / "tests/smoke/test_images.py").read_text()

    imported = re.search(r'python -c "import (\w+_core_[\w, ]+)"', action)
    loaded = re.search(r"for m in \(([^)]*)\)", smoke)

    assert imported, "action.yml imports no spaCy pipeline"
    assert loaded, "test_images.py loads no spaCy pipeline"
    assert imported[1].split(", ") == wanted, imported[1]
    assert re.findall(r"'(\w+)'", loaded[1]) == wanted, loaded[1]


def test_the_tests_start_the_images_compose_runs() -> None:
    """The fixtures' images, and the ones CI pulls for them, are compose's."""
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    composed = {one["image"] for one in services.values() if "image" in one}
    fixtures = re.findall(
        r'^[A-Z_]+_IMAGE = "([^"]+)"',
        (ROOT / "tests/conftest.py").read_text(),
        re.MULTILINE,
    )
    pulled = re.findall(
        r"docker pull (\S+)", (ROOT / ".github/workflows/ci.yml").read_text()
    )

    strays = sorted(set(fixtures + pulled) - composed)

    assert fixtures and pulled, (fixtures, pulled)
    assert not strays, strays


def test_the_frontend_rejects_an_upload_at_the_same_size_the_api_does() -> None:
    """One limit, written in two files, because Streamlit reads no env var.

    `server.maxUploadSize` is a static TOML the frontend reads at start-up,
    so raising MAX_FILE_SIZE_MB - in backend.env, or through the
    Configuration panel, which needs no restart - does nothing at all on its
    own: Streamlit refuses the file before the API ever sees it, and the
    person uploading is told the wrong limit.
    """
    backend = next(
        int(value)
        for name, value in (
            one.split("=", 1)
            for one in (ROOT / "configs/env/backend.env").read_text().splitlines()
            if "=" in one and not one.lstrip().startswith("#")
        )
        if name.strip() == "MAX_FILE_SIZE_MB"
    )
    config = (ROOT / "frontend/.streamlit/config.toml").read_text()
    found = re.search(r"^maxUploadSize\s*=\s*(\d+)", config, re.MULTILINE)

    assert found, "frontend/.streamlit/config.toml sets no maxUploadSize"
    assert int(found.group(1)) == backend, (
        f"MAX_FILE_SIZE_MB is {backend} and Streamlit's maxUploadSize is "
        f"{found.group(1)}; the smaller one is the real limit and the other "
        f"is what the person is told"
    )


def test_every_published_port_listens_on_the_loopback_only() -> None:
    """A port published without a host address listens on every interface.

    That makes the API, the stores and every UI reachable from the LAN.
    """
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    open_to_all = [
        f"{name}: {port}"
        for name, service in services.items()
        for port in service.get("ports", [])
        if not str(port).startswith("127.0.0.1:")
    ]

    assert not open_to_all, "\n".join(open_to_all)


def test_the_log_shipper_listens_on_nothing() -> None:
    """It reads files. A listener takes lines from anyone who can reach it."""
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    shipper = yaml.safe_load((ROOT / "configs/filebeat/filebeat.yml").read_text())

    assert not services["filebeat"].get("ports"), services["filebeat"]["ports"]
    assert {one["type"] for one in shipper["filebeat.inputs"]} == {"filestream"}


def test_the_object_store_is_published_through_its_s3_gateway_only() -> None:
    """The master, filer and volume servers answer without credentials."""
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    published = sorted(
        name
        for name, service in services.items()
        if name.startswith("seaweedfs") and service.get("ports")
    )

    assert published == ["seaweedfs-s3"]


def test_no_container_is_given_the_ca_key() -> None:
    """Whoever holds the CA's key can mint a certificate every client trusts.

    So each container is given the certificate files it reads, one at a
    time, and never the directory that holds the key beside them.
    """
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    given = [
        f"{name}: {volume}"
        for name, service in services.items()
        for volume in service.get("volumes", [])
        if str(volume).split(":")[0].rstrip("/") == "./certs" or "ca.key" in str(volume)
    ]

    assert not given, "\n".join(given)


def test_the_api_and_the_frontend_hold_no_phoenix_admin_secret() -> None:
    """Neither exports a span nor posts a verdict, so neither needs it."""
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    holding = [
        f"{name}: {key}"
        for name in ("api", "streamlit")
        for key, value in services[name].get("environment", {}).items()
        if "PHOENIX_ADMIN_SECRET" in str(value)
    ]

    assert not holding, "\n".join(holding)


def test_every_image_built_here_runs_with_no_capability_and_no_way_to_gain_one() -> (
    None
):
    """Each runs as `app`, binds a port above 1024 and needs no capability."""
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    built = {name: one for name, one in services.items() if "build" in one}
    loose = [
        name
        for name, service in built.items()
        if "no-new-privileges:true" not in service.get("security_opt", [])
        or service.get("cap_drop") != ["ALL"]
    ]

    assert len(built) == 10, sorted(built)
    assert not loose, sorted(loose)


def test_the_parser_reaches_only_the_services_it_writes_to() -> None:
    """It reads untrusted uploads, so its one network is internal."""
    declared = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = declared["services"]
    (network,) = services["parse-worker"]["networks"]
    beside = sorted(
        name
        for name, service in services.items()
        if network in service.get("networks", []) and name != "parse-worker"
    )

    assert declared["networks"][network].get("internal") is True, network
    assert beside == ["phoenix", "postgres", "seaweedfs-s3"], beside
    assert services["parse-worker"]["environment"]["HF_HUB_OFFLINE"] == "1"


def test_every_service_has_exactly_one_network_with_a_way_out() -> None:
    """A second one gives it two default routes, and it loses outbound."""
    declared = yaml.safe_load((ROOT / "compose.yaml").read_text())
    internal = {
        name
        for name, one in declared["networks"].items()
        if (one or {}).get("internal")
    }
    wrong = sorted(
        name
        for name, service in declared["services"].items()
        if len(set(service.get("networks", [])) - internal) > 1
        or (service.get("ports") and not set(service.get("networks", [])) - internal)
    )

    assert not wrong, wrong
