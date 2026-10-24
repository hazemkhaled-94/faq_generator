"""Reading an NLI model's answer, under either head it may have.

No weights are loaded here. What is worth testing without them is the label
handling, because that is the part that fails SILENTLY: a checkpoint whose
labels are not an NLI model's scores every pair fluently and means nothing
by it, and a threshold will happily compare the numbers.

Read by NAME throughout. The transformers pipeline hands back the label
beside each score, so the order a checkpoint declares its outputs in - which
mDeBERTa-xnli and bart-mnli disagree about - cannot invert a verdict any
more. These cases stay because the labels still have to be understood.

The encoder against real weights is `tests/eval/`, which needs a model.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nlp.entailment import Entailment, verdict

pytestmark = pytest.mark.nlp

THREE_WAY = {"entailment": 0.7, "neutral": 0.2, "contradiction": 0.1}
REVERSED = {"contradiction": 0.7, "neutral": 0.2, "entailment": 0.1}
TWO_WAY = {"entailment": 0.8, "not_entailment": 0.2}


def test_a_three_way_head_is_read_by_name_not_by_position() -> None:
    """mDeBERTa-xnli and bart-mnli order them opposite ways round."""
    forward = verdict(THREE_WAY, "a/checkpoint")
    backward = verdict(REVERSED, "another/checkpoint")

    assert forward.entailment == pytest.approx(0.7)
    assert backward.entailment == pytest.approx(0.1)
    assert backward.contradiction == pytest.approx(0.7)


def test_a_label_is_read_whatever_case_the_checkpoint_wrote_it_in() -> None:
    """Some checkpoints shout them: ENTAILMENT, NEUTRAL, CONTRADICTION."""
    answered = verdict(
        {"ENTAILMENT": 0.6, "NEUTRAL": 0.3, "CONTRADICTION": 0.1}, "a/shouting-model"
    )

    assert answered.entailment == pytest.approx(0.6)
    assert answered.neutral == pytest.approx(0.3)
    assert answered.contradiction == pytest.approx(0.1)


def test_a_two_way_head_reports_what_it_did_not_split() -> None:
    """bge-m3-zeroshot-v2.0 names entailment and not_entailment only.

    It cannot tell "says something different" from "does not address it",
    and both are refusals here, so the mass goes to neutral and
    contradiction stays 0.0 rather than being invented.
    """
    answered = verdict(TWO_WAY, "a/zeroshot")

    assert answered.entailment == pytest.approx(0.8)
    assert answered.neutral == pytest.approx(0.2)
    assert answered.contradiction == 0.0


@pytest.mark.parametrize(
    "scores",
    [
        {"positive": 0.9, "negative": 0.1},
        {"neutral": 0.9, "contradiction": 0.1},
        {},
    ],
)
def test_a_head_that_is_not_an_nli_model_is_refused(scores: dict) -> None:
    """Scored anyway it would answer fluently and mean nothing."""
    with pytest.raises(ValueError, match="neither a three-way"):
        verdict(scores, "a/sentiment-model")


def test_the_refusal_names_what_the_checkpoint_did_say() -> None:
    """A deployment that named the wrong model has to be told which one."""
    with pytest.raises(ValueError, match="negative.*positive"):
        verdict({"positive": 0.9, "negative": 0.1}, "a/sentiment-model")


def test_nothing_to_judge_costs_no_forward_pass() -> None:
    """A gate with no passages must not load weights to say so.

    The model name is never resolved, so this also pins that construction
    alone downloads nothing.
    """
    assert Entailment("a/checkpoint-that-does-not-exist").judge_all([]) == []


def test_the_weights_are_loaded_in_full_precision(monkeypatch) -> None:
    """Whatever precision the checkpoint was saved in.

    A checkpoint saved in half precision loads in it unless asked otherwise,
    and on a CPU that runs many times slower for the same scores.
    """
    import torch
    import transformers.pipelines

    asked: dict = {}

    def pipeline(task, **options):
        asked.update(options)
        return type("Built", (), {"tokenizer": Tokenizer(512)})()

    # Where `from transformers import pipeline` finds it once the lazy
    # package has resolved the name.
    monkeypatch.setattr(transformers.pipelines, "pipeline", pipeline)

    Entailment("a/checkpoint")._loaded  # noqa: B018 - loading is the act

    assert asked["dtype"] is torch.float32


def test_only_the_premise_is_cut_to_fit_the_window() -> None:
    """The hypothesis is the answer being judged, so it is kept whole."""
    asked: dict = {}

    def classify(pairs, **options):
        asked.update(options)
        return [
            [
                {"label": "entailment", "score": 0.8},
                {"label": "neutral", "score": 0.1},
                {"label": "contradiction", "score": 0.1},
            ]
            for _ in pairs
        ]

    judge = Entailment("a/checkpoint")
    judge.__dict__["_loaded"] = classify

    judge.judge_all([("A long passage.", "An answer.")])

    assert asked["truncation"] == "only_first"


# ── The window one setting gives two encoders ─────────────────────────────


@dataclass
class Tokenizer:
    """The one field `window` reads."""

    model_max_length: int
    name_or_path: str = "a/checkpoint"


def test_a_model_is_held_to_its_own_window() -> None:
    """ENCODER_MAX_TOKENS is one ceiling over every encoder.

    A checkpoint whose tokenizer declares 512, as the shipped NLI model's
    does, reads 512 however high the setting is.
    """
    from nlp.windows import window

    assert window(Tokenizer(512), 8192) == 512


def test_a_window_the_model_allows_is_left_alone() -> None:
    """The setting is a ceiling, not an instruction."""
    from nlp.windows import window

    assert window(Tokenizer(8192), 512) == 512
    assert window(Tokenizer(8192), 8192) == 8192


def test_a_tokenizer_declaring_nothing_is_not_believed() -> None:
    """A checkpoint that declares no window is not taken at its word.

    `model_max_length` comes back as a near-1e30 sentinel when the
    checkpoint is silent, and truncating to that truncates nothing.
    """
    from nlp.windows import window

    assert window(Tokenizer(1_000_000_000_000_000_019_884_624_838_656), 512) == 512


# ── A premise longer than the window ──────────────────────────────────────


class _Words:
    """A tokenizer that counts words, as the one field a window is cut by."""

    model_max_length = 40
    name_or_path = "a/checkpoint"

    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": text.split()}


class _Reader:
    """A pipeline that entails a hypothesis exactly when its premise holds the answer."""

    tokenizer = _Words()

    def __init__(self) -> None:
        self.premises: list[str] = []

    def __call__(self, pairs, **options):
        out = []
        for pair in pairs:
            self.premises.append(pair["text"])
            held = pair["text_pair"].lower() in pair["text"].lower()
            yes = 0.9 if held else 0.05
            out.append(
                [
                    {"label": "entailment", "score": yes},
                    {"label": "neutral", "score": 1 - yes},
                    {"label": "contradiction", "score": 0.0},
                ]
            )
        return out


def _reading(reader: _Reader) -> Entailment:
    judge = Entailment("a/checkpoint", 40)
    judge.__dict__["_loaded"] = reader
    return judge


@pytest.mark.parametrize(
    ("filler", "answer"),
    [
        (
            "The customer may return the item and the shop will refund it. " * 6,
            "30 days",
        ),
        (
            "Der Kunde kann die Ware zurücksenden und der Händler erstattet sie. " * 6,
            "30 Tage",
        ),
        ("| Plan | Fee |\n| Basic | 5 EUR |\n" * 8, "Premium | 12 EUR"),
    ],
)
def test_an_answer_in_the_tail_of_a_premise_longer_than_the_window_is_entailed(
    filler, answer
) -> None:
    """The window is cut by sentence and each is judged, the best one kept."""
    reader = _Reader()
    premise = f"{filler}\nThe period is {answer}."
    assert len(reader.tokenizer(premise)["input_ids"]) > 40

    (read,) = _reading(reader).judge_all([(premise, answer)])

    assert read.entailment == pytest.approx(0.9)
    assert len(reader.premises) > 1
    assert all(len(p.split()) <= 40 for p in reader.premises)


def test_a_premise_that_fits_is_judged_in_one_window_as_before() -> None:
    """Nothing is split that did not need to be."""
    reader = _Reader()

    (read,) = _reading(reader).judge_all([("The period is 30 days.", "30 days")])

    assert read.entailment == pytest.approx(0.9)
    assert reader.premises == ["The period is 30 days."]


def test_a_premise_that_holds_no_answer_in_any_window_is_not_entailed() -> None:
    """The best window is still not an entailment."""
    reader = _Reader()
    premise = "The customer may return the item and the shop will refund it. " * 6

    (read,) = _reading(reader).judge_all([(premise, "30 days")])

    assert read.entailment == pytest.approx(0.05)
