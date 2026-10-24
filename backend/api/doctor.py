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


def every_model() -> tuple[list[Settings], list[str]]:
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

    shared = Shared.load()

    def naming() -> list[Shared]:
        model = Topics.load().model
        return [model] if model else []

    def judging() -> list[Shared]:
        judge = Assessment.load()
        return [judge_model(judge, shared)] if judge.enabled else []

    stages = {
        "extraction": lambda: extraction_models(Extraction.load(), shared),
        "topics": naming,
        "questions": lambda: question_models(Questions.load(), shared),
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
    from llm.config import check_split, describe

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
    failed = 0
    try:
        check_split()
    except ValueError as refusal:
        log.error("%s", refusal)
        failed = 1
    models, refused = every_model()
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
