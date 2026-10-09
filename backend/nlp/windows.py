"""How long a pair one encoder may be given.

`ENCODER_MAX_TOKENS` is a CEILING a deployment asks for over every encoder,
and each model is held to the window its tokenizer declares as
`model_max_length`. Nothing here has to know which model is which.

Entailment reads at most its tokenizer's `model_max_length`, 512 for the
shipped `bge-m3-zeroshot-v2.0`, so `ENCODER_MAX_TOKENS` does not apply to it
unless set below that. `xlm-roberta-large-squad2` declares 512 as well.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: What the embedder puts in front of every text. e5 was trained on
#: prefixed inputs, and both sides of every comparison here are one kind of
#: text, so one prefix serves.
PREFIX = "query: "

#: Above this, a declared length is a sentinel rather than a window.
#: A tokenizer reports `model_max_length` as a number near 1e30 when the
#: checkpoint says nothing, and truncating to 1e30 truncates nothing.
_ABSURD = 1_000_000


def window(tokenizer, wanted: int) -> int:
    """The longest pair this checkpoint can be given, at or under `wanted`.

    Read off the tokenizer's `model_max_length` rather than off
    `max_position_embeddings`, and the two can disagree: `xlm-roberta`
    declares 514 embeddings and its tokenizer 512, `bge-m3-zeroshot-v2.0`
    8,194 and its tokenizer 512. The tokenizer's is the window used.

    Args:
        tokenizer: The loaded tokenizer.
        wanted: What the deployment asked for.

    Returns:
        `wanted`, or the model's own maximum where that is smaller.
    """
    declared = getattr(tokenizer, "model_max_length", None)
    if not isinstance(declared, int) or declared <= 0 or declared > _ABSURD:
        return wanted
    if declared < wanted:
        log.info(
            "%s reads %d tokens, so the %d asked for is capped at it",
            getattr(tokenizer, "name_or_path", "the model"),
            declared,
            wanted,
        )
    return min(wanted, declared)


def reserved(tokenizer) -> int:
    """The tokens the embedder adds to a text: `PREFIX` and the special tokens."""
    return len(tokenizer(PREFIX)["input_ids"])
