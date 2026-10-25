"""The embedding behind the dedup gate, against the real model.

Skipped unless EMBEDDING_MODEL is already in the Hugging Face cache. Nothing
here downloads it: it is 2.2 GB, and a test suite that fetches that on a cold
machine is a test suite nobody runs twice. `make dev` warms the cache the
first time the chunk worker or the question worker starts.
"""

from __future__ import annotations

import pytest
import weights

from nlp.embedding import WIDTH, Embedder, cosine

MODEL = "intfloat/multilingual-e5-large"

#: Everything taking `embedder` loads 2.2 GB of weights, which is what the
#: marker is for: `make test-fast` is `-m "not nlp"` and used to spend its
#: time here. On the tests rather than on the module, because `cosine` is
#: arithmetic over two lists and belongs in the layer that runs every time.
loads_the_model = pytest.mark.nlp


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    """The real embedder, or a skip when its weights are not here."""
    from huggingface_hub import try_to_load_from_cache

    # The weights, not config.json: the tokenizer caches that on its own,
    # and a guard reading it downloads 2.2 GB instead of skipping.
    if not any(
        isinstance(try_to_load_from_cache(MODEL, name), str)
        for name in ("model.safetensors", "pytorch_model.bin")
    ):
        weights.unavailable(f"{MODEL}'s weights are not in the cache")
    return Embedder(MODEL, max_tokens=512)


@loads_the_model
def test_a_question_embeds_at_the_width_the_column_holds(embedder) -> None:
    """questions.embedding is vector(1024); a mismatch fails at insert."""
    assert len(embedder.embed("What does the device weigh?")) == WIDTH


@loads_the_model
def test_an_embedding_is_a_unit_vector(embedder) -> None:
    """Which is what lets the gates compare by dot product."""
    vector = embedder.embed("What does the device weigh?")

    assert cosine(vector, vector) == pytest.approx(1.0, abs=1e-5)


@loads_the_model
def test_a_paraphrase_scores_above_an_unrelated_question(embedder) -> None:
    """The whole basis of the dedup gate, in one comparison."""
    asked = embedder.embed("What does the device weigh?")
    same = embedder.embed("How heavy is the device?")
    other = embedder.embed("Who is responsible for the quarterly risk report?")

    assert cosine(asked, same) > cosine(asked, other)


@loads_the_model
def test_the_same_question_in_two_languages_is_close(embedder) -> None:
    """The model is multilingual because this corpus is."""
    english = embedder.embed("Who must produce the risk report?")
    german = embedder.embed("Wer muss den Risikobericht erstellen?")
    unrelated = embedder.embed("What does the device weigh?")

    assert cosine(english, german) > cosine(english, unrelated)


@loads_the_model
def test_the_model_is_as_wide_as_the_column_that_holds_it(embedder) -> None:
    """The guard in the constructor, seen from the other side.

    Not tested against a model of the wrong width: that would mean
    downloading a second one to watch a four-line `if` fire.
    """
    assert len(embedder.embed("anything at all")) == WIDTH


def test_cosine_needs_two_vectors_of_the_same_width() -> None:
    """A silent zip would compare the first half of one with all of another."""
    with pytest.raises(ValueError):
        cosine([1.0, 0.0], [1.0, 0.0, 0.0])


@loads_the_model
def test_a_passage_cut_to_the_chunk_budget_fits_the_embedder() -> None:
    """The prefix and the special tokens are reserved out of the budget."""
    from transformers import AutoTokenizer

    from nlp.windows import PREFIX
    from preprocessing.chunking.passages import PassageBuilder

    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    except Exception as exc:  # noqa: BLE001 - any failure is the same answer
        weights.unavailable(f"{MODEL} is not in the cache: {exc}")
    budget = PassageBuilder(
        embedding_model=MODEL, max_tokens=512, merge_peers=True
    )._max_tokens

    assert len(tokenizer(PREFIX + "word " * budget)["input_ids"]) <= 512


def test_a_text_past_the_window_is_counted_in_the_log(caplog) -> None:
    """The embedding is the head of it, and the log says how many were cut."""
    import logging

    from nlp.embedding import Embedder

    class Words:
        def __call__(self, text, add_special_tokens=True):
            return {"input_ids": text.split()}

    class Model:
        tokenizer = Words()
        max_seq_length = 5

        def encode(self, texts, **options):
            import numpy

            return numpy.ones((len(texts), 2))

    embedder = Embedder.__new__(Embedder)
    embedder._model = Model()  # type: ignore[assignment]
    caplog.set_level(logging.INFO, logger="nlp.embedding")

    embedder.embed_all(["short", "one two three four five six seven"])

    assert any(
        "1 of 2 texts run past the 5-token window" in r.getMessage()
        for r in caplog.records
    )
