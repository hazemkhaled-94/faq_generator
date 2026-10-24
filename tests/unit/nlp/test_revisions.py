"""Every Hugging Face load names the revision its setting pins.

A repository id alone resolves to whatever its default branch holds on the day
a worker first downloads it, so a push to the repository would change passages
and scores under the same settings. The loaders are stood in for, and what is
under test is the revision each is called with.
"""

from __future__ import annotations

import pytest

from nlp.embedding import Embedder
from nlp.entailment import Entailment
from nlp.qa import Extractive

PINS = {
    "EMBEDDING_MODEL_REVISION": "e5pin0000000000000000000000000000000000",
    "NLI_MODEL_REVISION": "nlipin000000000000000000000000000000000",
    "QA_MODEL_REVISION": "qapin0000000000000000000000000000000000",
}


class Stop(Exception):
    """Raised by a stand-in once it has seen what it was called with."""


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    """The three revisions a deployment would pin."""
    for name, value in PINS.items():
        monkeypatch.setenv(name, value)


def test_the_embedder_loads_the_pinned_revision(monkeypatch) -> None:
    """SentenceTransformer, with the embedding model's revision."""
    seen: dict = {}

    def stand_in(name, **kwargs):
        seen.update(kwargs, name=name)
        raise Stop

    monkeypatch.setattr("nlp.embedding.SentenceTransformer", stand_in)

    with pytest.raises(Stop):
        Embedder("any/embedder", max_tokens=512)

    assert seen["revision"] == PINS["EMBEDDING_MODEL_REVISION"]


def test_the_entailment_pipeline_loads_the_pinned_revision(monkeypatch) -> None:
    """The transformers pipeline, with the NLI model's revision."""
    seen: dict = {}

    def stand_in(task, **kwargs):
        seen.update(kwargs)
        raise Stop

    # Both names: the package caches what it resolved first, so a stand-in on one
    # alone is missed by whichever test runs second.
    monkeypatch.setattr("transformers.pipelines.pipeline", stand_in)
    monkeypatch.setattr("transformers.pipeline", stand_in)

    with pytest.raises(Stop):
        _ = Entailment("any/nli", max_tokens=512)._loaded

    assert seen["revision"] == PINS["NLI_MODEL_REVISION"]


def test_the_qa_head_and_its_tokenizer_load_the_pinned_revision(monkeypatch) -> None:
    """Both halves of the checkpoint are the one commit."""
    seen: list[dict] = []

    class Loader:
        @staticmethod
        def from_pretrained(name, **kwargs):
            seen.append(kwargs)
            if len(seen) == 2:
                raise Stop
            return object()

    monkeypatch.setattr("nlp.qa.AutoTokenizer", Loader)
    monkeypatch.setattr("nlp.qa.AutoModelForQuestionAnswering", Loader)

    with pytest.raises(Stop):
        _ = Extractive("any/qa", max_tokens=512)._loaded

    assert [one["revision"] for one in seen] == [PINS["QA_MODEL_REVISION"]] * 2


def test_a_qa_model_with_no_revision_is_refused_naming_the_setting(
    monkeypatch,
) -> None:
    """Not read as the default branch."""
    monkeypatch.setenv("QA_MODEL_REVISION", "")

    with pytest.raises(KeyError, match="QA_MODEL_REVISION"):
        _ = Extractive("any/qa", max_tokens=512)._loaded


def test_the_chunking_tokenizer_loads_the_embedding_models_revision(
    monkeypatch,
) -> None:
    """The tokenizer sizes a passage for the model that embeds it."""
    from preprocessing.chunking.passages import PassageBuilder

    seen: dict = {}

    def stand_in(**kwargs):
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(
        "preprocessing.chunking.passages.HuggingFaceTokenizer.from_pretrained",
        stand_in,
    )

    with pytest.raises(Stop):
        PassageBuilder(embedding_model="any/embedder", max_tokens=512, merge_peers=True)

    assert seen["revision"] == PINS["EMBEDDING_MODEL_REVISION"]
