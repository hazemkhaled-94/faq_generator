"""Every prompt this stage sends, for the record that resolves a version.

`facts.prompt_version` names a version; this is what says what that version
asked for. Three extractors, three versions, bumped separately: what counts
as a fact, what a digest condenses, and what a bridge may claim are three
decisions.

Read by `run.py` at start-up and by the api. Nothing here calls a model.
"""

from __future__ import annotations

from extraction.config import Settings
from extraction.extractors import bridge, digest, llm
from stages.prompts import Composed

#: What the stage records its prompts under.
SERVICE = "extraction"


def catalogue(
    cap: int | None = None, settings: Settings | None = None
) -> list[Composed]:
    """Every prompt this stage can send, composed as it would be sent.

    Both halves and the shape: the system prompt, the user message as its
    template, and the JSON schema the answer has to come back in.

    `cap` is what `EXTRACTION_MIN_OTHER_SHARE` works out to, as the
    factory resolved it, because the atomic extractor appends the cap
    instruction to its own prompt. The text recorded under it is what a
    passage stating no more sentences and list items than the cap is sent;
    a passage stating more is sent the same text with its own count, under
    the same version. Absent means the same thing it means there: no cap,
    and the paragraph is left off entirely rather than written as a
    limitless one.

    `settings` names the model each is sent to: EXTRACTION_MODEL reads and
    bridges, and EXTRACTION_DIGEST_MODEL condenses, the reader when absent.
    """
    reads = settings.model if settings else None
    condenses = (settings.digest_model or reads) if settings else None
    return [
        Composed(
            "atomic",
            llm.version(cap),
            llm.composed(cap),
            llm._USER,
            llm._Facts.model_json_schema(),
            reads,
        ),
        Composed(
            "digest",
            digest.PROMPT_VERSION,
            digest._SYSTEM,
            digest._USER,
            digest._Digest.model_json_schema(),
            condenses,
        ),
        Composed(
            "bridge",
            bridge.PROMPT_VERSION,
            bridge._SYSTEM,
            bridge._USER,
            bridge._Bridges.model_json_schema(),
            reads,
        ),
    ]
