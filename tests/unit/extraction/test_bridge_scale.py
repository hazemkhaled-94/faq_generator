"""What the bridge pass holds in memory and in what order it deletes.

Every passage of the corpus is read for it, vector and text, and a corpus
ten times this build's is 20,000 of them. Vectors were tuples of Python
floats, 32 KB each against the 4 KB they are, each passage was parsed twice,
and the bridges a pass replaces were deleted before the links that decide
what replaces them were dealt, so a pass that died in between left none.
"""

from __future__ import annotations

import tracemalloc
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from drivers import Catalogue, Model, passage

from extraction import links
from extraction import service as service_module
from extraction.extractors.bridge import BridgeExtractor
from extraction.links import linked
from extraction.repository import _passage
from extraction.service import bridge
from extraction.validation import FactChecker
from nlp import analysis

pytestmark = pytest.mark.nlp


def _row(ident: int, vector) -> SimpleNamespace:
    """A passage row as `by_topic` selects it."""
    return SimpleNamespace(
        id=ident,
        text=f"Item {ident} costs {ident} EUR.",
        section_path=f"Fees > Part {ident}",
        block_type=None,
        language="en",
        sentences=None,
        table_cells=None,
        doc_sha256="doc-a",
        embedding=vector,
    )


def test_a_passage_carries_its_vector_as_float32() -> None:
    """As the column returns it, not read out into Python floats."""
    vector = np.arange(1024, dtype=np.float32)

    read = _passage(_row(1, vector), "en", None)

    assert isinstance(read.embedding, np.ndarray)
    assert read.embedding.dtype == np.float32
    assert np.array_equal(read.embedding, vector)


def test_two_thousand_passages_are_held_in_the_space_of_their_vectors() -> None:
    """A tenth of the corpus in under 12 MB; tuples of floats were 65."""
    rng = np.random.default_rng(0)
    rows = [_row(i, rng.random(1024, dtype=np.float32)) for i in range(2_000)]

    tracemalloc.start()
    try:
        held = [_passage(row, "en", None) for row in rows]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(held) == 2_000
    assert peak < 12 * 1024 * 1024, peak


@pytest.mark.parametrize(
    ("language", "sentence"),
    [("en", "Item {0} costs {0} EUR."), ("de", "Artikel {0} kostet {0} EUR.")],
)
def test_each_passage_is_parsed_once(monkeypatch, language, sentence) -> None:
    """A heading that names a section, a term, or neither: one parse each."""
    parsed: list[str] = []

    def counting(real):
        def build(name):
            nlp = real(name)

            def parse(text, *args, **kwargs):
                parsed.append(text)
                return nlp(text, *args, **kwargs)

            return parse

        return build

    passages = [
        replace(
            passage(
                sentence.format(i),
                language=language,
                section_path=f"Section {i} > Part {i}",
                id=i + 1,
            ),
            doc_sha256="doc-a",
        )
        for i in range(150)
    ]

    # Built above, which parses each for its sentences: only what the link
    # pass reads is counted.
    monkeypatch.setattr(analysis, "pipeline", counting(analysis.pipeline))
    if hasattr(links, "pipeline"):
        monkeypatch.setattr(links, "pipeline", counting(links.pipeline))
    analysis._read.cache_clear()

    linked(passages, passages, {p.id: 1 for p in passages}, 5, 2)

    most = Counter(parsed).most_common(1)[0]
    assert most[1] == 1, most


class Ordered(Catalogue):
    """A catalogue that says when the bridges in scope are deleted."""

    def __init__(self, order: list[str], **topics) -> None:
        super().__init__(**topics)
        self._order = order

    def clear_bridges(self, within=None) -> int:
        """Notes the deletion."""
        self._order.append("clear")
        return super().clear_bridges(within)

    def bridged_pairs(self, within=None, replaced=False):
        """Notes the read of what stays."""
        self._order.append(f"held replaced={replaced}")
        return super().bridged_pairs(within, replaced)


def test_the_bridges_in_scope_are_deleted_only_after_the_links_are_dealt(
    monkeypatch,
) -> None:
    """Nothing is lost if the pass dies while it reads or deals."""
    order: list[str] = []
    real = service_module.linked

    def dealing(*args, **kwargs):
        order.append("linked")
        return real(*args, **kwargs)

    monkeypatch.setattr(service_module, "linked", dealing)
    first, second = (
        replace(
            passage(text, section_path=f"Support > {name}", id=ident),
            doc_sha256=f"doc-{ident}",
        )
        for ident, name, text in (
            (1, "Standard", "Standard requests are answered within 48 hours."),
            (2, "Urgent", "Urgent requests are answered within 4 hours."),
        )
    )
    catalog = Ordered(order, support=[first, second]).stating()
    answer = {
        "relation": "contrast",
        "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
        "statement": "Urgent requests are answered sooner than standard requests.",
        "question": "Which is answered sooner?",
        "answer": "an urgent request",
    }

    bridge(
        catalog,  # type: ignore[arg-type]
        BridgeExtractor(Model(answer)),  # type: ignore[arg-type]
        FactChecker(0.6),
        5,
        2,
    )

    assert order == ["held replaced=True", "linked", "clear"], order
