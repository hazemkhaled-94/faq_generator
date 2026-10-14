"""Entailment, in this process, from an encoder rather than a served model.

Importing this loads torch and a model's weights. Nothing outside a worker
should name it, which `tests/static/test_api_stays_light.py` pins, and it
sits beside `nlp.embedding` for the same reason: loading a model is this
package's, and a service may not import another service to reach one.

One pair answers ONE question. An NLI model is given a premise and a
hypothesis and returns three probabilities over them, and that is the whole
of what it knows. `judge_all` takes several pairs and judges each on its
own - the thing being replaced is a prompt that asked for four at once and
confused them, which is the failure this shape exists to prevent.

The model is named by a setting rather than written here. Which encoder reads
German best is a deployment's measurement to make and to re-make, and this
module has no opinion beyond the labels it reads off the model's own answer.

The forward pass and the softmax used to be written out, and the output read
by INDEX against a table built from `id2label`. `transformers`' own
text-classification pipeline hands back the label names, so there are no
indices to get the wrong way round; what is left here is the one thing the
pipeline does not do, which is insist that the labels name an NLI head.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import Any, cast

from nlp.windows import window

log = logging.getLogger(__name__)

#: The three things an NLI model can say about a premise and a hypothesis.
ENTAILMENT = "entailment"
NEUTRAL = "neutral"
CONTRADICTION = "contradiction"

#: What a two-way head calls everything that is not entailment. A model
#: trained this way cannot tell "says something different" from "does not
#: address it", and both are refusals here, so the distinction costs this
#: caller nothing - see `Verdict.contradiction`.
NOT_ENTAILMENT = "not_entailment"


@dataclass(frozen=True)
class Verdict:
    """What one premise says about one hypothesis.

    Attributes:
        entailment: Probability the premise supports the hypothesis.
        neutral: Probability it neither supports nor contradicts it.
        contradiction: Probability it says the opposite. Always 0.0 from a
            two-way head, which cannot tell this from neutral. Nothing here
            reads it - `entailment` is the whole of what a gate asks - and it
            is kept because a three-way model knows it and a reader
            debugging a refusal wants to see it.
    """

    entailment: float
    neutral: float
    contradiction: float


def verdict(scores: Mapping[str, float], model_name: str) -> Verdict:
    """One pair's probabilities, under whichever head produced them.

    Two heads are accepted and both are wanted. A three-way NLI model names
    all of entailment/neutral/contradiction; a zero-shot head - such as
    bge-m3-zeroshot-v2.0 - names entailment and not_entailment only. Either
    is enough, because the only thing a gate asks is how sure the model is
    of entailment.

    Args:
        scores: One probability per label, as the model named them.
        model_name: What to call the checkpoint when refusing it.

    Returns:
        The verdict. A two-way head reports everything that is not
        entailment as neutral rather than splitting it, because the model
        did not split it.

    Raises:
        ValueError: If the labels name neither head, which means it is not
            an NLI model. Worth raising rather than scoring: a sentiment
            checkpoint answers every pair fluently and means nothing by it.
    """
    at = {str(label).lower(): float(score) for label, score in scores.items()}
    if ENTAILMENT not in at or not ({NEUTRAL, NOT_ENTAILMENT} & set(at)):
        raise ValueError(
            f"{model_name!r} labels its outputs {sorted(at)}, which "
            f"names neither a three-way NLI head "
            f"({ENTAILMENT}/{NEUTRAL}/{CONTRADICTION}) nor a two-way one "
            f"({ENTAILMENT}/{NOT_ENTAILMENT}). This asks one about a premise "
            f"and a hypothesis."
        )
    if NEUTRAL in at:
        return Verdict(
            entailment=at[ENTAILMENT],
            neutral=at[NEUTRAL],
            contradiction=at.get(CONTRADICTION, 0.0),
        )
    return Verdict(
        entailment=at[ENTAILMENT],
        neutral=at[NOT_ENTAILMENT],
        contradiction=0.0,
    )


class Entailment:
    """One NLI model, asked about one premise and one hypothesis at a time."""

    def __init__(self, model_name: str, max_tokens: int = 512) -> None:
        """Names the model to load. Nothing is loaded until it is asked.

        Deferred, so building a service that may never reach this gate costs
        nothing: a worker draining a queue of questions that are all refused
        structurally should not pay for weights it never uses.
        """
        self._model_name = model_name
        self._max_tokens = max_tokens

    @cached_property
    def _loaded(self):
        """The classification pipeline, held to its tokenizer's window.

        A pair is cut to the tokenizer's `model_max_length`, 512 for the
        shipped model; `ENCODER_MAX_TOKENS` does not apply unless set below
        that.

        The weights load in full precision whatever the checkpoint was saved
        in: one saved in half precision would otherwise load in it, and on a
        CPU that runs many times slower for the same scores.
        """
        import torch
        from transformers import pipeline

        log.info("loading %s", self._model_name)
        built = pipeline(
            "text-classification",
            model=self._model_name,
            top_k=None,
            function_to_apply="softmax",
            dtype=torch.float32,
        )
        self._max_tokens = window(built.tokenizer, self._max_tokens)
        return built

    def judge_all(self, pairs: list[tuple[str, str]]) -> list[Verdict]:
        """The same, over several pairs in one forward pass.

        Args:
            pairs: One (premise, hypothesis) per judgement wanted.

        Returns:
            One verdict per pair, in the order given.
        """
        if not pairs:
            return []
        judged = self._loaded(
            [
                {"text": premise, "text_pair": hypothesis}
                for premise, hypothesis in pairs
            ],
            # The premise only: the hypothesis is the answer being judged.
            truncation="only_first",
            max_length=self._max_tokens,
            batch_size=len(pairs),
        )
        # The pipeline is annotated loosely - it returns a different shape
        # per task - so the rows are read through `dict` rather than
        # indexed straight into a comprehension a checker cannot follow.
        read: list[Verdict] = []
        for scored in judged:
            rows = cast("list[dict[str, Any]]", scored)
            read.append(
                verdict(
                    {str(one["label"]): float(one["score"]) for one in rows},
                    self._model_name,
                )
            )
        return read
