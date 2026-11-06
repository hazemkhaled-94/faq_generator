"""A bilingual chunk whose items cannot be found in its text is kept whole.

Splitting by language cuts the chunk's text where each run's first item is
found. Where the chunker re-spelled an item (a word rejoined, a space
dropped) it is not found, and a cut made by guessing would drop or misfile
text: the chunk stays as it was, every word in it.
"""

from __future__ import annotations

import pytest
from docling_core.transforms.chunker.doc_chunk import DocChunk, DocMeta
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from test_peers_language import PAIRS

from preprocessing.chunking.passages import _one_language

GERMAN = PAIRS[0][1]

#: The same notice after the German one, and the word the chunker re-spells.
SECOND = {
    "en": (PAIRS[0][2], "current account", "current-account"),
    "fr": (
        (
            "La banque facture des frais mensuels de 4,90 EUR pour la tenue du compte "
            "courant. Les frais sont supprimés si au moins 1 000 EUR sont versés."
        ),
        "compte courant",
        "compte-courant",
    ),
    "el": (
        (
            "Η τράπεζα χρεώνει μηνιαία χρέωση 4,90 EUR για την τήρηση του τρεχούμενου "
            "λογαριασμού. Η χρέωση δεν ισχύει αν κατατεθούν τουλάχιστον 1.000 EUR."
        ),
        "τρεχούμενου λογαριασμού",
        "τρεχούμενου-λογαριασμού",
    ),
}


def chunk_of(second: str, written: str) -> tuple[DocChunk, DoclingDocument]:
    """A German item then `second`, the chunk's text reading `written` for it."""
    document = DoclingDocument(name="t")
    items = [
        document.add_text(label=DocItemLabel.TEXT, text=GERMAN),
        document.add_text(label=DocItemLabel.TEXT, text=second),
    ]
    chunk = DocChunk(
        text=f"{GERMAN}\n\n{written}",
        meta=DocMeta(doc_items=items, headings=["Kontoführung"]),
    )
    return chunk, document


@pytest.mark.parametrize("language", sorted(SECOND))
def test_a_chunk_whose_second_item_is_not_found_in_its_text_stays_whole(
    language,
) -> None:
    """German then another language, re-spelled in the chunk's text."""
    second, word, respelled = SECOND[language]
    chunk, document = chunk_of(second, second.replace(word, respelled))

    assert [one.text for one in _one_language([chunk], document)] == [chunk.text]


def test_the_same_chunk_spelled_as_its_items_splits_in_two() -> None:
    """The control: found, German and English part."""
    second = SECOND["en"][0]
    chunk, document = chunk_of(second, second)

    assert [one.text for one in _one_language([chunk], document)] == [GERMAN, second]
