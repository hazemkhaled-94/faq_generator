"""`make doctor`'s model check: every model a stage run from here calls, asked once.

It sits in the api package because it imports every stage's settings and
model factory to resolve the models they call, and the api is the one layer
the import contract lets reach every stage. Every import is inside a function,
so the api process loads none of it.

    python -m api.doctor       # which is what `make doctor` runs
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.config import Settings

log = logging.getLogger(__name__)


#: Folders a sync client copies to a vendor's servers and to every device signed
#: in, by the name each vendor gives its folder: a component that starts with
#: one of the first group, or is one of the second. A path check, so it needs no
#: client installed and asks no vendor.
_SYNC_PREFIXES = ("onedrive", "icloud", "googledrive", "google drive")
_SYNC_NAMES = ("dropbox", "cloudstorage", "mobile documents")


def synced(path: Path) -> str | None:
    """The folder of this path a sync client watches, or None.

    A secret in a watched folder leaves the machine, whatever the file is
    called, so `make doctor` warns about the checkout and the secrets file.
    """
    for part in path.parts:
        folded = part.lower()
        if folded.startswith(_SYNC_PREFIXES) or folded in _SYNC_NAMES:
            return part
    return None


#: The repositories Docling's converter reads from the Hugging Face cache when
#: DOCLING_ARTIFACTS_PATH is unset, at the version the lock pins: the layout
#: model and the table model. A converter upgrade that reads others is a
#: change here.
_DOCLING_REPOS = (
    "docling-project/docling-layout-heron",
    "docling-project/docling-models",
)

#: The encoders a stage loads by hub id, as (the setting naming the model, the
#: setting pinning its commit). The embedding model is also the tokenizer
#: chunking sizes a passage with.
_ENCODERS = (
    ("EMBEDDING_MODEL", "EMBEDDING_MODEL_REVISION"),
    ("NLI_MODEL", "NLI_MODEL_REVISION"),
    ("QA_MODEL", "QA_MODEL_REVISION"),
)


def _hub_cache(source: Mapping[str, str]) -> Path:
    """Where the Hugging Face client keeps what it downloaded."""
    if source.get("HF_HUB_CACHE"):
        return Path(source["HF_HUB_CACHE"])
    home = source.get("HF_HOME") or "~/.cache/huggingface"
    return Path(home).expanduser() / "hub"


def _snapshot(cache: Path, repo: str, revision: str | None) -> bool:
    """Whether one commit of a repository is in the cache.

    A branch name is read through `refs`, the way the client does; no revision
    asks for `main`.
    """
    folder = cache / f"models--{repo.replace('/', '--')}"
    wanted = revision or "main"
    pointer = folder / "refs" / wanted
    commit = pointer.read_text().strip() if pointer.is_file() else wanted
    return (folder / "snapshots" / commit).is_dir()


def _holds_any(cache: Path, repo: str) -> bool:
    """Whether the cache holds any snapshot of a repository.

    For the repositories whose revision is not ours to pin: Docling asks for the
    one its release names, a tag more often than `main`.
    """
    snapshots = cache / f"models--{repo.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


def cache_problems(source: Mapping[str, str] | None = None) -> list[str]:
    """What a run with the Hub switched off would fail to find, by name.

    With HF_HUB_OFFLINE=1 a model not in the cache is not downloaded: the first
    passage fails. Every encoder the settings name is checked at its pinned
    commit, and the converter's weights where DOCLING_ARTIFACTS_PATH names
    them or, unset, in the cache. With the Hub reachable nothing is checked,
    because a missing model is then fetched at its first call, as it always
    was.

    Args:
        source: Where to read the settings, or None for the environment.
    """
    source = os.environ if source is None else source
    if (source.get("HF_HUB_OFFLINE") or "").lower() not in ("1", "true", "yes", "on"):
        return []
    cache = _hub_cache(source)
    found = []
    for model, pin in _ENCODERS:
        repo = (source.get(model) or "").strip()
        if not repo:
            continue
        revision = (source.get(pin) or "").strip() or None
        if not _snapshot(cache, repo, revision):
            found.append(
                f"{model} {repo} at {revision or 'main'} is not in the cache "
                f"{cache} and the Hub is off (HF_HUB_OFFLINE=1): fetch it once "
                "where the Hub is reachable"
            )
    artifacts = (source.get("DOCLING_ARTIFACTS_PATH") or "").strip()
    if artifacts:
        folder = Path(artifacts).expanduser()
        if not folder.is_dir() or not any(folder.iterdir()):
            found.append(
                f"DOCLING_ARTIFACTS_PATH {artifacts} is not a folder holding the "
                "converter's weights: run make docling-weights where the Hub is "
                "reachable"
            )
    else:
        found += [
            f"Docling's {repo} is not in the cache {cache} and the Hub is off: "
            "run make docling-weights where the Hub is reachable"
            for repo in _DOCLING_REPOS
            if not _holds_any(cache, repo)
        ]
    return found


def stored_source() -> Mapping[str, str]:
    """The settings the stages read: the environment, and what the store overrides it with.

    A value written through the Configuration page or `make settings-set` is the
    one a worker uses, so it is the one the doctor asks with, and the one it says
    came from the store. A store that cannot be read is said once, and the
    environment alone is asked with.
    """
    from settings.store import StoredRefused, snapshot

    try:
        source, _ = snapshot()
    except StoredRefused:
        raise
    except Exception as error:  # noqa: BLE001 - the doctor reports, it does not stop
        log.warning(
            "could not read the stored settings (%s); asking with the environment",
            error,
        )
        return os.environ
    for name in sorted(source):
        if source[name] != os.environ.get(name):
            log.info("%s comes from the store: %s", name, source[name])
    return source


#: What a URL reads as structure. APP_DB_PASSWORD goes into the connection string
#: as written, by the Makefile and by compose, neither of which percent-encodes.
_URL_CHARACTERS = "@/:#?%"


def password_problem(source: Mapping[str, str] | None = None) -> str | None:
    """Why APP_DB_PASSWORD cannot go into a connection string as written, or None.

    A password holding one of `@ / : # ? %` makes the URL name another host or
    none, and the failure names the database and never the password.
    """
    source = os.environ if source is None else source
    password = source.get("APP_DB_PASSWORD") or ""
    found = sorted({one for one in password if one in _URL_CHARACTERS})
    if not found:
        return None
    return (
        f"APP_DB_PASSWORD holds {' '.join(found)}, which a connection string reads "
        "as structure and nothing here percent-encodes: set one of letters, "
        "digits, `-`, `_` and `.` (make setup generates one)"
    )


def preflight() -> int:
    """What the host runner proves before it starts: the split and the password.

    Returns:
        0 if both hold, else 1, with each reason logged.
    """
    from llm.config import check_split

    failed = 0
    try:
        check_split()
    except ValueError as refusal:
        log.error("%s", refusal)
        failed = 1
    if problem := password_problem():
        log.error("%s", problem)
        failed = 1
    return failed


def every_model(
    source: Mapping[str, str] | None = None,
) -> tuple[list[Settings], list[str]]:
    """Every model a stage run from this environment calls, and the stages that will not load.

    LLM_MODEL and each stage's own: backend.env names some of those, so
    LLM_MODEL alone is not what a run calls. The judge only while the
    evaluation phase is on, as its worker asks it. A stage whose settings
    will not load is named rather than raised, so the others are still asked.
    """
    # Inside the function, as every import here: the api process imports
    # none of the stages' working halves, and tests/static/test_api_stays_light.py
    # reads only the imports a module makes when it loads.
    from assessment.config import Settings as Assessment
    from assessment.factory import judge_model
    from extraction.config import Settings as Extraction
    from extraction.factory import models as extraction_models
    from llm.config import Settings as Shared
    from question_generation.config import Settings as Questions
    from question_generation.factory import models as question_models
    from topic_modelling.config import Settings as Topics

    shared = Shared.load(source)

    def naming() -> list[Shared]:
        model = Topics.load(source).model
        return [model] if model else []

    def judging() -> list[Shared]:
        judge = Assessment.load(source)
        return [judge_model(judge, shared)] if judge.enabled else []

    stages = {
        "extraction": lambda: extraction_models(Extraction.load(source), shared),
        "topics": naming,
        "questions": lambda: question_models(Questions.load(source), shared),
        "assessment": judging,
    }
    asked, refused = [shared], []
    for stage, models in stages.items():
        try:
            asked += models()
        except Exception as error:  # noqa: BLE001 - the doctor reports every stage
            refused.append(f"{stage}: {error}")
    return list({(m.model, m.base_url): m for m in asked}.values()), refused


def behind_lines() -> list[str]:
    """What each stage stored under another configuration than the current one.

    A settings change reaches no stored row, so this is where a person finds
    out which are still made under the old one. Never raises: a database that
    will not answer is said once, and does not fail the model check.
    """
    from settings.run import behind
    from settings.store import Settings

    try:
        version = Settings().version()
        return [
            line
            for stage in ("extraction", "topics", "questions")
            for line in behind(stage, version)
        ]
    except Exception as error:  # noqa: BLE001 - the doctor reports, it does not stop
        return [f"could not read what is stored: {error}"]


def main() -> int:
    """Asks every configured model one question, and says what happened.

    Returns:
        The process exit code: 0 if every model answered in shape.
    """
    import telemetry
    from llm.check import Unreachable, reachable
    from llm.config import describe
    from settings.store import StoredRefused

    telemetry.configure("doctor")

    for what, where in (
        ("the checkout", Path.cwd().resolve()),
        ("ENV_FILE", Path(os.environ.get("ENV_FILE") or ".env").resolve()),
    ):
        if folder := synced(where):
            log.warning(
                "%s is %s, under %s, which a sync client copies off this machine; "
                "move it out and rotate every key it held "
                "(docs/operations.md, Go-live host)",
                what,
                where,
                folder,
            )
    log.info("%s", describe())
    failed = preflight()
    for problem in cache_problems():
        log.error("%s", problem)
        failed = 1
    try:
        source = stored_source()
    except StoredRefused as refusal:
        # What every service build says of the same row.
        log.error("stored settings: %s", refusal)
        failed = 1
        source = os.environ
    models, refused = every_model(source)
    for stage in refused:
        log.error("settings will not load: %s", stage)
    failed = int(bool(refused) or bool(failed))
    for settings in models:
        log.info("model    %s", settings.model)
        log.info("address  %s", settings.base_url or "(the provider's own)")
        log.info("mode     %s", settings.structured_mode)
        try:
            reachable(settings)
        except Unreachable as refusal:
            log.error("%s", refusal)
            failed = 1
            continue
        log.info("the model answered in shape")
    for line in behind_lines():
        log.info("%s", line)
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
