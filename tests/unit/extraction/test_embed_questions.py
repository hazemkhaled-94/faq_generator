"""The embed pass also gives a question the vector a restore left out."""

from __future__ import annotations

import pytest

from extraction.service import embed

QUESTIONS = {
    "de": "Wie lange dauert eine Überweisung?",
    "en": "How long does a refund take?",
    "fr": "Quel est le délai de remboursement ?",
    "el": "Πόσο διαρκεί μια μεταφορά χρημάτων;",
}


class Embedder:
    """Records the texts it is given and answers a vector for each."""

    def __init__(self) -> None:
        """Starts with nothing seen."""
        self.seen: list[str] = []

    def embed_all(self, texts: list[str]) -> list[list[float]]:
        """One vector per text."""
        self.seen += texts
        return [[1.0, 0.0] for _ in texts]


class Catalog:
    """Questions of which some carry a vector already, and no passage or fact waits."""

    def __init__(
        self, held: dict[int, list[float] | None], texts: dict[int, str]
    ) -> None:
        """Holds each question's vector, or None, and its text."""
        self.held = held
        self.texts = texts

    def unembedded_passages(self, limit: int, within=None) -> list:
        """None."""
        del limit, within
        return []

    def embed_passages(self, vectors: list) -> int:
        """None."""
        return len(vectors)

    def unembedded(self, limit: int, within=None) -> list:
        """None."""
        del limit, within
        return []

    def embed_facts(self, vectors: list) -> int:
        """None."""
        return len(vectors)

    def unembedded_questions(self, limit: int, within=None) -> list:
        """The questions with no vector, as the repository reads them."""
        del within
        return [(i, self.texts[i]) for i, v in sorted(self.held.items()) if v is None][
            :limit
        ]

    def embed_questions(self, vectors: list) -> int:
        """Stores each vector."""
        for row, vector in vectors:
            self.held[row] = vector
        return len(vectors)


@pytest.mark.parametrize("language", sorted(QUESTIONS))
def test_a_question_with_no_vector_gets_one_and_one_with_a_vector_is_left(
    language: str,
) -> None:
    """The text is embedded as written, as the checker embeds a candidate."""
    kept = [0.5, 0.5]
    catalog = Catalog(
        {1: None, 2: kept}, {1: QUESTIONS[language], 2: "Already embedded?"}
    )
    embedder = Embedder()

    done = embed(catalog, embedder)  # type: ignore[arg-type]

    assert done == 1
    assert embedder.seen == [QUESTIONS[language]]
    assert catalog.held[1] == [1.0, 0.0]
    assert catalog.held[2] == kept
