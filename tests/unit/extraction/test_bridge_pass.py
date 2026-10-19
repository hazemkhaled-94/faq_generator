"""The pass that reads a corpus's topics for claims spanning passages.

Not part of the passage queue: the unit of work is a group of passages the
topic model put together, so it runs on its own and replaces what it wrote
last time rather than adding to it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from drivers import DIGEST_SHARE, Catalogue, Model, group, passage

from database.qa_generator import FactKind
from extraction.extractors.bridge import BridgeExtractor
from extraction.service import bridge
from extraction.validation import FactChecker
from llm.client import ModelUnavailable

pytestmark = pytest.mark.nlp

ANSWER = {
    "relation": "contrast",
    "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
    "statement": "Urgent requests are answered sooner than standard requests.",
    "question": "Which is answered sooner, a standard or an urgent request?",
    "answer": "an urgent request",
}


OTHER = (
    "Parcels leave the warehouse within 2 days.",
    "Pallets leave the depot within 9 days.",
)


def pair(at: int = 0, parent: str = "Support", texts: tuple[str, str] | None = None):
    """Two sections under one heading, as one topic offers them.

    Args:
        at: Added to both passage ids, so two pairs in one corpus differ.
        parent: The heading both sections sit under.
        texts: What the two say, where another pair in the corpus must share
            no term with them.
    """
    first, second = group(
        *(
            texts
            or (
                "Standard requests are answered within 48 hours.",
                "Urgent requests are answered within 4 hours.",
            )
        )
    )
    return [
        replace(first, id=first.id + at, section_path=f"{parent} > Standard"),
        replace(second, id=second.id + at, section_path=f"{parent} > Urgent"),
    ]


def run(catalog: Catalogue, model: Model, wanted: int = 5, size: int = 2) -> int:
    """Runs the bridge pass over a catalogue with one scripted model."""
    if not hasattr(catalog, "atomic"):
        catalog.stating()
    return bridge(
        catalog,  # type: ignore[arg-type]
        BridgeExtractor(model),  # type: ignore[arg-type]
        FactChecker(DIGEST_SHARE),
        wanted,
        size,
    )


def test_a_topic_of_two_passages_yields_one_bridge() -> None:
    """One group, one call, one stored claim."""
    catalog, model = Catalogue(support=pair()), Model(ANSWER)

    assert run(catalog, model) == 1
    assert model.calls == 1
    assert catalog.kinds == [FactKind.BRIDGE]
    assert catalog.written[0].validated, catalog.written[0].validation_error


def test_the_previous_pass_is_replaced_rather_than_added_to() -> None:
    """Re-running twice must not double the bridges."""
    catalog = Catalogue(support=pair())
    run(catalog, Model(ANSWER))

    assert catalog.cleared == 1, "the clear happens once, before anything is read"


def test_every_topic_is_read() -> None:
    """A run covers the corpus, not one subject of it."""
    catalog, model = (
        Catalogue(support=pair(), delivery=pair(100, "Delivery", OTHER)),
        Model(ANSWER),
    )

    assert run(catalog, model) == 2
    assert model.calls == 2


def test_a_bridge_may_join_two_topics() -> None:
    """The documents' link decides, not the topic model."""
    first = replace(
        passage(
            "An account is dormant when its holder has made no payment for 24 "
            "months. Fees for dormant accounts are set out in Section 7.",
            section_path="Accounts > Dormant accounts",
            id=1,
        ),
        doc_sha256="doc-0",
    )
    second = replace(
        passage(
            "A dormant account is charged a yearly fee of 10 EUR.",
            section_path="Section 7 > Yearly fees",
            id=2,
        ),
        doc_sha256="doc-1",
    )
    catalog, model = Catalogue(accounts=[first], fees=[second]), Model(ANSWER)

    assert run(catalog, model) == 1
    assert model.calls == 1


def test_a_topic_too_small_to_group_is_skipped() -> None:
    """Nothing is asked of a topic that offers no pair."""
    catalog, model = Catalogue(support=pair()[:1]), Model(ANSWER)

    assert run(catalog, model) == 0
    assert model.calls == 0


def test_a_group_the_model_will_not_read_does_not_stop_the_rest() -> None:
    """One unreachable call is not a reason to abandon the corpus."""

    class Flaky(Model):
        """Refuses the first group and answers the second."""

        def answer(self, **kwargs):
            """Raises once, then answers."""
            if not self.asked:
                self.asked.append(kwargs)
                raise ModelUnavailable("Timeout: took too long")
            return super().answer(**kwargs)

    catalog = Catalogue(support=pair(), delivery=pair(100, "Delivery", OTHER))

    assert run(catalog, Flaky(ANSWER)) == 1, "the second group still wrote"


def test_a_refused_bridge_is_stored_with_its_reason() -> None:
    """The share that failed is how the pass is judged, as everywhere else."""
    alone = {**ANSWER, "facts": [{"excerpt": 0, "fact": 0}]}
    catalog = Catalogue(support=pair())

    assert run(catalog, Model(alone)) == 1
    assert not catalog.written[0].validated
    assert catalog.written[0].rejection_code == "not_bridging"


def test_a_topic_that_bridges_nothing_writes_nothing() -> None:
    """Returning no facts is a correct answer."""
    catalog = Catalogue(support=pair())

    assert run(catalog, Model({"relation": "none"})) == 0
    assert catalog.written == []


class TestThePassageGate:
    """The same gate the per-passage stage applies, applied here too.

    `by_topic` asks only that a passage was segmented, so without this a
    group is spent on a table of contents or a bare heading - which is what
    `skipped` exists to refuse.
    """

    def test_navigation_is_not_offered_to_the_model(self) -> None:
        """A group of two, one of which is a contents page, is not a group."""
        listing = replace(pair()[1], block_type="document_index", doc_sha256="doc-1")
        catalog, model = Catalogue(support=[pair()[0], listing]), Model(ANSWER)

        assert run(catalog, model) == 0
        assert model.calls == 0, "one readable passage is not a pair"

    def test_a_heading_is_not_offered_either(self) -> None:
        """It asserts nothing, so there is nothing for it to bridge."""
        heading = passage(
            "Response times",
            section_path="Support > Response times",
            id=22,
            doc_sha256="doc-1",
        )
        catalog, model = Catalogue(support=[pair()[0], heading]), Model(ANSWER)

        assert run(catalog, model) == 0
        assert model.calls == 0

    def test_the_readable_passages_of_a_topic_still_group(self) -> None:
        """The gate takes the junk out, it does not refuse the topic."""
        listing = replace(pair()[1], block_type="document_index", doc_sha256="doc-9")
        catalog = Catalogue(support=[*pair(), listing])

        assert run(catalog, Model(ANSWER)) == 1


def test_the_narrowing_reaches_both_the_clear_and_the_read() -> None:
    """`--only` selects the same passages for each half of the pass."""
    catalog = Catalogue(support=pair()).stating()
    bridge(
        catalog,  # type: ignore[arg-type]
        BridgeExtractor(Model(ANSWER)),  # type: ignore[arg-type]
        FactChecker(DIGEST_SHARE),
        5,
        2,
        "a-condition",
    )

    assert catalog.narrowed == ["a-condition", None], (
        "the heads are read narrowed, their partners whole"
    )


def test_a_pass_for_the_missing_reads_only_the_topics_holding_no_bridge() -> None:
    """What a whole-corpus run asks for: nothing replaced, nothing a question cites lost."""
    catalog = (
        Catalogue(support=pair(), billing=pair(100, "Billing", OTHER))
        .holding_bridges(1)
        .stating()
    )
    model = Model(ANSWER)

    written = bridge(
        catalog,  # type: ignore[arg-type]
        BridgeExtractor(model),  # type: ignore[arg-type]
        FactChecker(DIGEST_SHARE),
        5,
        2,
        missing=True,
    )

    assert written == 1
    assert model.calls == 1, "a bridged topic was read again"
    assert catalog.cleared == 0, "a pass for the missing deleted bridges"


def test_the_pass_reads_each_passages_validated_facts_once() -> None:
    """One query for the corpus, and the facts reach the extractor."""
    catalog, model = Catalogue(support=pair()), Model(ANSWER)

    assert run(catalog, model) == 1
    assert catalog.read_facts == [{11, 22}]
    assert "[F0] Standard requests are answered within 48 hours." in model.sent["user"]


def test_a_link_with_a_passage_that_states_nothing_is_not_read() -> None:
    """There is nothing to compose from, so the call is not made."""
    catalog, model = Catalogue(support=pair()), Model(ANSWER)
    catalog.atomic = {
        11: [(911, "Standard requests are answered within 48 hours.", (0,))]
    }

    assert run(catalog, model) == 0
    assert model.calls == 0
