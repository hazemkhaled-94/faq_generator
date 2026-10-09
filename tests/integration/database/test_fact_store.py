"""What the facts repository writes and reads back.

Against a real Postgres, because what is under test is the SQL: which rows a
store replaces, which it leaves, and what the listing and the quality report
count when they are filtered the same way.
"""

from __future__ import annotations

from typing import Any

import pytest
from facts import FactStore, checked
from seed import digest
from sqlalchemy.exc import IntegrityError

from database.qa_generator import FactKind, Passage, Rejection, Status
from extraction.models import Citation

pytestmark = pytest.mark.integration

#: The bridge pass's extractor and checker, which a corpus with no topics
#: never reaches.
UNREAD: Any = None


@pytest.fixture
def store(engine, database) -> FactStore:
    """A driver on the empty, migrated database."""
    return FactStore(engine)


@pytest.fixture
def corpus(store) -> dict[str, list[int]]:
    """Two documents of two passages each."""
    return store.corpus(
        ("a", ["Standard requests are answered within 48 hours.", "Urgent: 4 hours."]),
        ("b", ["Requests may be raised by phone.", "The line opens at 08:00."]),
    )


class TestClaiming:
    """Taking the next passage off the queue."""

    def test_an_unqueued_corpus_offers_nothing(self, store, corpus) -> None:
        """A row arrives `new` and no worker looks at it until asked."""
        assert store.queue.claim() is None

    def test_a_queued_passage_comes_back_whole(self, store, corpus) -> None:
        """Its text, its sentences and its language."""
        first = corpus["a"][0]
        store.queued(first)

        claimed = store.queue.claim()
        assert claimed is not None
        assert claimed.id == first
        assert claimed.text.startswith("Standard requests")
        assert [one.index for one in claimed.sentences] == [0]
        assert claimed.language == "en"
        assert claimed.doc_sha256

    def test_a_passage_is_read_in_its_own_language(self, store, corpus) -> None:
        """One file carries a German report and its English summary.

        Chunking detects the language per passage and segments it under
        that one, so a document-wide label would judge the statement with
        one pipeline against sentence counts another produced.
        """
        first = corpus["a"][0]
        store.language_of(first, "de")
        store.queued(first)

        claimed = store.queue.claim()
        assert claimed is not None
        assert claimed.language == "de", "the passage's, not its document's"

    def test_a_passage_too_short_to_tell_falls_back_to_its_document(
        self, store, corpus
    ) -> None:
        """Which is what NULL in that column means."""
        first = corpus["a"][0]
        store.language_of(first, None)
        store.queued(first)

        claimed = store.queue.claim()
        assert claimed is not None
        assert claimed.language == "en"

    def test_claiming_marks_the_row_in_progress(self, store, corpus) -> None:
        """So a second worker takes the following row instead."""
        store.queued(*corpus["a"])
        first = store.queue.claim()
        second = store.queue.claim()

        assert first is not None and second is not None
        assert first.id != second.id
        assert store.queue.claim() is None


class TestStoring:
    """Writing what one passage yielded."""

    def test_a_passage_is_finished_when_its_facts_are_written(
        self, store, corpus
    ) -> None:
        """Both happen in one transaction."""
        first = corpus["a"][0]
        store.queued(first)
        store.queue.claim()

        assert store.store(first, checked(first)) == 1
        assert store.statuses()[0] == Status.EXTRACTED
        assert store.count() == 1

    def test_a_second_reading_replaces_the_first(self, store, corpus) -> None:
        """Re-extracting a passage does not double its facts."""
        first = corpus["a"][0]
        store.store(first, checked(first, "One."), checked(first, "Two."))
        store.store(first, checked(first, "Three."))

        assert [row[0] for row in store.rows("statement")] == ["Three."]

    def test_a_duplicate_cites_its_passage_beside_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """The surviving fact then cites every document that states it."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")

        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                twin_id=survivor,
            ),
        )

        assert [
            (passage, position)
            for fact, passage, position in store.links()
            if fact == survivor
        ] == [(first, 0), (other, 1)]

    def test_reading_the_duplicate_again_keeps_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """The other document still states it, so it is not deleted."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")
        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                twin_id=survivor,
            ),
        )

        store.store(other)

        assert store.rows("id") == [(survivor,)]
        assert [(fact, passage) for fact, passage, _ in store.links()] == [
            (survivor, first)
        ]

    def test_a_duplicate_adds_its_evidence_to_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """evidence_text is every cited span, the added citation's included."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(
            first,
            checked(first, "Requests are answered in 48 hours.", evidence_text="A."),
        )
        ((survivor,),) = store.rows("id")

        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                twin_id=survivor,
                evidence_text="B.",
            ),
        )

        assert store.rows("evidence_text", where="id = :id", id=survivor) == [
            ("A.\nB.",)
        ]

    def test_reading_a_duplicate_again_does_not_repeat_its_evidence(
        self, store, corpus
    ) -> None:
        """The citation comes back on a re-read; its text is already there."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(
            first,
            checked(first, "Requests are answered in 48 hours.", evidence_text="A."),
        )
        ((survivor,),) = store.rows("id")
        duplicate = checked(
            other,
            "Requests are answered in 48 hours.",
            validated=False,
            rejection_code=Rejection.DUPLICATE,
            twin_id=survivor,
            evidence_text="B.",
        )
        store.store(other, duplicate)

        store.store(other, duplicate)

        assert store.rows("evidence_text", where="id = :id", id=survivor) == [
            ("A.\nB.",)
        ]

    def test_only_the_passage_read_is_replaced(self, store, corpus) -> None:
        """Two workers on one document do not delete each other's results."""
        first, second = corpus["a"]
        store.store(first, checked(first, "From the first."))
        store.store(second, checked(second, "From the second."))

        assert store.count() == 2

    def test_every_kind_is_written_with_its_own_value(self, store, corpus) -> None:
        """The kind decides which checks a re-judgement holds it to."""
        first = corpus["a"][0]
        store.store(
            first,
            checked(first, "A claim.", kind=FactKind.ATOMIC),
            checked(first, "A summary.", kind=FactKind.SUMMARY),
            checked(first, "- A point\n- Another", kind=FactKind.OUTLINE),
        )

        assert [row[0] for row in store.rows("kind")] == [
            FactKind.ATOMIC,
            FactKind.SUMMARY,
            FactKind.OUTLINE,
        ]

    def test_a_refused_fact_is_written_with_its_reason(self, store, corpus) -> None:
        """The share that failed is how extraction is judged."""
        first = corpus["a"][0]
        store.store(
            first,
            checked(
                first,
                "Invented.",
                validated=False,
                rejection_code=Rejection.UNSUPPORTED_ADDITION,
                validation_error="the statement asserts 9",
            ),
        )

        (row,) = store.rows("validated", "rejection_code", "validation_error")
        assert row == (False, Rejection.UNSUPPORTED_ADDITION, "the statement asserts 9")

    def test_a_passage_yielding_nothing_is_still_finished(self, store, corpus) -> None:
        """Nothing found is an answer, not an error."""
        first = corpus["a"][0]

        assert store.store(first) == 0
        assert store.statuses()[0] == Status.EXTRACTED


class TestBridges:
    """Writing the claims that rest on more than one passage."""

    def test_a_bridge_records_every_passage_it_rests_on(self, store, corpus) -> None:
        """Anchor first, in the order the model was shown them."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor,
                "Both name a way in.",
                kind=FactKind.BRIDGE,
                passage_ids=[anchor, other],
            )
        )

        ((fact_id, *_),) = store.rows("id")
        assert store.links() == [(fact_id, anchor, 0), (fact_id, other, 1)]

    def test_a_bridge_records_where_in_each_passage_it_rests(
        self, store, corpus
    ) -> None:
        """The span, not just the passage: a citation has to be resolvable."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor,
                "Both name a way in.",
                kind=FactKind.BRIDGE,
                citations=[
                    Citation(passage_id=anchor, sentence_ids=[0], start=0, end=47),
                    Citation(passage_id=other, sentence_ids=[0], start=0, end=32),
                ],
            )
        )

        assert store.citations() == [
            (anchor, [0], 0, 47),
            (other, [0], 0, 32),
        ]

    def test_every_stored_citation_resolves_in_its_own_passage(
        self, store, corpus
    ) -> None:
        """The invariant a reader of fact_passages relies on."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor,
                "Both name a way in.",
                kind=FactKind.BRIDGE,
                citations=[
                    Citation(
                        passage_id=anchor,
                        sentence_ids=[0],
                        start=0,
                        end=len("Standard requests are answered within 48 hours."),
                    ),
                    Citation(
                        passage_id=other,
                        sentence_ids=[0],
                        start=0,
                        end=len("Requests may be raised by phone."),
                    ),
                ],
            )
        )

        assert store.cited_text() == [
            "Standard requests are answered within 48 hours.",
            "Requests may be raised by phone.",
        ]

    def test_a_citation_is_written_whole_or_not_at_all(self, store, corpus) -> None:
        """A span with no sentences behind it is a span nothing can resolve."""
        anchor, other = corpus["a"][0], corpus["b"][0]

        with pytest.raises(IntegrityError, match="fact_passages_citation_complete"):
            store.bridges(
                checked(
                    anchor,
                    "Both name a way in.",
                    kind=FactKind.BRIDGE,
                    citations=[
                        Citation(passage_id=anchor, sentence_ids=None, start=0, end=4),  # type: ignore[arg-type]
                        Citation(passage_id=other, sentence_ids=[0], start=0, end=4),
                    ],
                )
            )

    def test_a_citation_naming_sentences_carries_both_bounds(
        self, store, corpus
    ) -> None:
        """A NULL bound makes the comparison NULL, which a CHECK lets through."""
        anchor, other = corpus["a"][0], corpus["b"][0]

        with pytest.raises(IntegrityError, match="fact_passages_citation_complete"):
            store.bridges(
                checked(
                    anchor,
                    "Both name a way in.",
                    kind=FactKind.BRIDGE,
                    citations=[
                        Citation(passage_id=anchor, sentence_ids=[0]),
                        Citation(passage_id=other, sentence_ids=[0], start=0, end=4),
                    ],
                )
            )

    def test_every_other_kind_records_the_one_passage_it_rests_on(
        self, store, corpus
    ) -> None:
        """The link table is the only route to a passage, for every kind."""
        first = corpus["a"][0]
        store.store(first, checked(first, kind=FactKind.SUMMARY))

        ((fact_id, *_),) = store.rows("id")
        assert store.links() == [(fact_id, first, 0)]

    def test_re_reading_a_passage_leaves_its_bridges_alone(self, store, corpus) -> None:
        """They are the bridge pass's to write and to replace."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )
        store.store(anchor, checked(anchor, "A fresh claim."))

        assert sorted(row[0] for row in store.rows("kind")) == [
            FactKind.ATOMIC,
            FactKind.BRIDGE,
        ]

    def test_clearing_replaces_what_the_last_pass_wrote(self, store, corpus) -> None:
        """A second run must not double the bridges."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )
        store.store(anchor, checked(anchor, "An ordinary claim."))

        assert store.catalog.clear_bridges() == 1
        assert [row[0] for row in store.rows("kind")] == [FactKind.ATOMIC]
        assert [row[1] for row in store.links()] == [anchor], (
            "the bridge's links went with it, and the atomic fact kept its own"
        )

    def test_clearing_narrows_to_the_passages_a_scope_names(
        self, store, corpus
    ) -> None:
        """`--only document=…` replaces that document's bridges and no others."""
        from seed import digest

        a_anchor, b_anchor = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                a_anchor,
                "From a.",
                kind=FactKind.BRIDGE,
                passage_ids=[a_anchor, b_anchor],
            ),
            checked(
                b_anchor,
                "From b.",
                kind=FactKind.BRIDGE,
                passage_ids=[b_anchor, a_anchor],
            ),
        )

        # Both rest on a passage of a, so both go: a scope names the
        # passages a bridge rests on and not the one it opens with.
        removed = store.catalog.clear_bridges(Passage.doc_sha256 == digest("a"))
        assert removed == 2
        assert store.rows("statement") == []

    def test_a_narrowed_pass_clears_every_bridge_of_the_topics_it_reads(
        self, store, corpus
    ) -> None:
        """`by_topic` reads a touched topic whole, so it writes those again."""
        first, second = corpus["b"]
        store.topic("Support", corpus["a"][0], first, second)
        store.bridges(
            checked(
                first, "Within b.", kind=FactKind.BRIDGE, passage_ids=[first, second]
            )
        )

        assert store.catalog.clear_bridges(Passage.doc_sha256 == digest("a")) == 1

    def test_losing_a_passage_deletes_the_bridge_that_needed_it(
        self, store, corpus
    ) -> None:
        """Re-chunking one side would otherwise leave a claim bridging nothing."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        store.drop_passage(other)

        assert store.count() == 0, "the trigger took the fact with the link"
        assert store.links() == []

    def test_losing_the_anchor_deletes_the_bridge_too(self, store, corpus) -> None:
        """The trigger does this one too: the anchor is a citation like any other."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        store.drop_passage(anchor)

        assert store.count() == 0
        assert store.links() == []

    def test_writing_nothing_writes_nothing(self, store) -> None:
        """A topic that bridges nothing costs no statement."""
        assert store.bridges() == 0


class TestReplacingCitedBridges:
    """A second bridge pass, over bridges questions already cite."""

    @pytest.fixture
    def cited(self, store, corpus):
        """Cites the one bridge across both documents with a question of a status."""

        def cite(status: str) -> None:
            """Writes the bridge and a question of `status` resting on it."""
            anchor, other = corpus["a"][0], corpus["b"][0]
            store.bridges(
                checked(
                    anchor,
                    "A bridge.",
                    kind=FactKind.BRIDGE,
                    passage_ids=[anchor, other],
                )
            )
            ((fact_id,),) = store.rows("id")
            store.asked(fact_id, status)

        return cite

    def test_an_accepted_question_on_a_bridge_stops_the_pass(
        self, store, cited
    ) -> None:
        """Before anything is deleted, naming how many questions."""
        from extraction.service import CitedBridges, bridge

        cited("accepted")

        with pytest.raises(CitedBridges, match="1 accepted question"):
            bridge(store.catalog, UNREAD, UNREAD, 5, 2)

        assert store.count() == 1
        assert store.count("questions") == 1

    def test_forcing_it_replaces_the_bridge_anyway(self, store, cited) -> None:
        """And the question resting on that bridge alone goes with it."""
        from extraction.service import bridge

        cited("accepted")

        assert bridge(store.catalog, UNREAD, UNREAD, 5, 2, force=True) == 0
        assert store.count() == 0
        assert store.count("questions") == 0

    def test_a_question_nobody_accepted_does_not_stop_it(self, store, cited) -> None:
        """A draft is not the dataset."""
        from extraction.service import bridge

        cited("draft")

        assert bridge(store.catalog, UNREAD, UNREAD, 5, 2) == 0
        assert store.count() == 0


class TestGroups:
    """Which passages the bridge pass is offered."""

    def test_a_topic_hands_back_its_passages(self, store, corpus) -> None:
        """With their sentences rebuilt and the document they came from."""
        topic_id = store.topic("Support", corpus["a"][0], corpus["b"][0])
        group = store.group_of(topic_id)

        assert sorted(one.id for one in group) == [corpus["a"][0], corpus["b"][0]]
        assert all(one.sentences for one in group)
        assert len({one.doc_sha256 for one in group}) == 2, "two documents"

    def test_a_topic_is_ordered_by_document_then_reading_order(
        self, store, corpus
    ) -> None:
        """So one document's passages arrive together and in sequence."""
        topic_id = store.topic("Support", *corpus["a"], *corpus["b"])
        group = store.group_of(topic_id)

        documents = [one.doc_sha256 for one in group]
        assert documents == sorted(documents), "one document at a time"
        for sha in set(documents):
            within = [one.id for one in group if one.doc_sha256 == sha]
            assert within == sorted(within), "in reading order"

    def test_a_passage_belongs_to_the_topic_it_carries_most_strongly(
        self, store, corpus
    ) -> None:
        """Which is what puts two of them in the same group."""
        first = corpus["a"][0]
        weak = store.topic("Weak", first, weight=0.1)
        strong = store.topic("Strong", first, weight=0.8)

        assert store.group_of(strong) != []
        assert store.group_of(weak) == []

    def test_a_passage_in_no_topic_is_offered_to_nobody(self, store, corpus) -> None:
        """Topics are what group passages; without a fit there are no groups."""
        assert list(store.catalog.by_topic()) == []

    def test_every_topic_is_streamed_separately(self, store, corpus) -> None:
        """A group never spans two subjects."""
        store.topic("Support", *corpus["a"])
        store.topic("Access", *corpus["b"])

        found = {
            topic_id: [one.id for one in group]
            for topic_id, group in store.catalog.by_topic()
        }
        assert len(found) == 2
        assert sorted(one for group in found.values() for one in group) == sorted(
            corpus["a"] + corpus["b"]
        )

    def test_narrowing_to_one_document_reads_its_topics_whole(
        self, store, corpus
    ) -> None:
        """Both sides of a cross-document bridge, or it cannot be rewritten.

        `clear_bridges` deletes any bridge resting on a passage of the named
        document, and a bridge rests on two. Reading back only that
        document's passages would leave one side of each in hand, so a
        narrowed run would delete the cross-document bridges and be unable
        to write them again - and those are the ones worth having.
        """
        spanning = store.topic("Support", corpus["a"][0], corpus["b"][0])

        found = dict(
            store.catalog.by_topic(Passage.doc_sha256 == digest("a")),
        )
        assert list(found) == [spanning]
        assert sorted(one.id for one in found[spanning]) == sorted(
            [corpus["a"][0], corpus["b"][0]]
        ), "the passage in document b is the other half of the bridge"

    def test_a_topic_the_narrowing_does_not_touch_is_left_out(
        self, store, corpus
    ) -> None:
        """Reading topics whole is not reading the corpus."""
        store.topic("Support", corpus["a"][0])
        store.topic("Access", corpus["b"][0])

        found = dict(store.catalog.by_topic(Passage.doc_sha256 == digest("a")))
        assert [one.id for group in found.values() for one in group] == [corpus["a"][0]]


class TestListing:
    """What the API serves back."""

    @pytest.fixture
    def written(self, store, corpus):
        """One fact of each kind, across two documents."""
        a_first, b_first = corpus["a"][0], corpus["b"][0]
        store.store(
            a_first,
            checked(
                a_first,
                "The device weighs 4 kg.",
                kind=FactKind.ATOMIC,
                evidence_text="Its mass is 4 kg.",
            ),
            checked(a_first, "A short summary.", kind=FactKind.SUMMARY),
        )
        store.store(
            b_first,
            checked(
                b_first,
                "Phone lines exist.",
                kind=FactKind.ATOMIC,
                extraction_method="deterministic",
                validated=False,
                rejection_code=Rejection.COPIED,
            ),
        )
        return corpus

    def test_everything_written_is_listed(self, store, written) -> None:
        """Rejected facts included: the share that failed is the signal."""
        total, rows = store.catalog.page()

        assert total == 3
        assert len(rows) == 3
        assert {row.validated for row in rows} == {True, False}

    def test_the_listing_narrows_to_one_kind(self, store, written) -> None:
        """Each reading is looked at on its own."""
        total, rows = store.catalog.page(kind=FactKind.SUMMARY)

        assert total == 1
        assert [row.kind for row in rows] == [FactKind.SUMMARY]

    def test_the_listing_narrows_to_one_document(self, store, written) -> None:
        """Through the passage, which is the only route there is."""
        from seed import digest

        total, _ = store.catalog.page(document=digest("a"))
        assert total == 2

    def test_the_listing_narrows_to_one_method(self, store, written) -> None:
        """A deterministic reading is judged apart from a written one."""
        total, rows = store.catalog.page(method="deterministic")

        assert total == 1
        assert [row.statement for row in rows] == ["Phone lines exist."]

    @pytest.mark.parametrize(
        ("field", "term", "found"),
        [
            ("statement", "weighs", 1),
            ("evidence", "weighs", 0),
            ("evidence", "mass", 1),
            ("statement", "mass", 0),
            ("both", "mass", 1),
            ("both", "weighs", 1),
        ],
    )
    def test_the_search_looks_only_in_the_column_it_was_given(
        self, store, written, field, term, found
    ) -> None:
        """Nothing outside the chosen column is searched."""
        total, _ = store.catalog.page(search=term, field=field)
        assert total == found

    def test_the_page_and_its_count_agree_about_the_filter(
        self, store, written
    ) -> None:
        """One filter, applied in one place, to both queries."""
        total, rows = store.catalog.page(kind=FactKind.ATOMIC, limit=1)

        assert total == 2, "the total counts the filter, not the page"
        assert len(rows) == 1

    def test_a_page_beyond_the_end_is_empty_and_still_counted(
        self, store, written
    ) -> None:
        """The pager reads the total rather than discovering the end."""
        total, rows = store.catalog.page(offset=100)

        assert total == 3
        assert rows == []

    def test_a_bridge_is_listed_once_with_every_passage_it_rests_on(
        self, store, corpus
    ) -> None:
        """One row, naming both passages a reader can open."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        total, (row,) = store.catalog.page()
        assert total == 1, "a bridge is not multiplied by its passages"
        assert [one.passage_id for one in row.passages] == [anchor, other]
        assert [one.position for one in row.passages] == [0, 1]
        assert row.kind == FactKind.BRIDGE

    def test_a_bridge_is_listed_under_either_of_its_documents(
        self, store, corpus
    ) -> None:
        """A reader filtering to the second wants the facts its passages hold."""
        from seed import digest

        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        assert store.catalog.page(document=digest("a"))[0] == 1
        assert store.catalog.page(document=digest("b"))[0] == 1

    def test_the_passages_of_a_bridge_are_read_back_in_order(
        self, store, corpus
    ) -> None:
        """Which is what the detail page shows beside the anchor's evidence."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )
        ((fact_id,),) = store.rows("id")

        assert store.catalog.passages_of(fact_id) == [anchor, other]

    def test_another_kind_names_the_one_passage_it_rests_on(
        self, store, corpus
    ) -> None:
        """The same route as a bridge's, with one row rather than two."""
        first = corpus["a"][0]
        store.store(first, checked(first))
        ((fact_id,),) = store.rows("id")

        assert store.catalog.passages_of(fact_id) == [first]


class TestQuality:
    """The figures that say whether the facts are facts."""

    @pytest.fixture
    def written(self, store, corpus):
        """Two atomic facts, one refused, and one summary."""
        first = corpus["a"][0]
        store.store(
            first,
            checked(
                first,
                "A claim.",
                evidence_text="A claim and another.",
                statement_predicates=1,
                evidence_predicates=2,
            ),
            checked(
                first,
                "Invented.",
                validated=False,
                rejection_code=Rejection.UNSUPPORTED_ADDITION,
                statement_predicates=1,
                evidence_predicates=2,
            ),
            checked(
                first,
                "A summary.",
                kind=FactKind.SUMMARY,
                statement_predicates=2,
                evidence_predicates=2,
            ),
        )
        return corpus

    def test_the_totals_count_what_the_filter_selects(self, store, written) -> None:
        """Refused facts included, which is the point."""
        quality = store.catalog.quality()

        assert quality.total == 3
        assert quality.validated == 2

    def test_the_rejections_group_on_the_code(self, store, written) -> None:
        """A message carrying a measurement would give one bucket per fact."""
        assert store.catalog.quality().rejected == {Rejection.UNSUPPORTED_ADDITION: 1}

    def test_each_reading_is_counted_separately(self, store, written) -> None:
        """So a page can say how much of the corpus each one covers."""
        assert store.catalog.quality().kinds == {
            FactKind.ATOMIC: 2,
            FactKind.SUMMARY: 1,
        }

    def test_the_figures_narrow_with_the_listing(self, store, written) -> None:
        """One filter, so the report and the rows cannot disagree."""
        quality = store.catalog.quality(kind=FactKind.ATOMIC)

        assert quality.total == 2
        assert quality.kinds == {FactKind.ATOMIC: 2}

    def test_the_means_are_read_off_the_rows(self, store, written) -> None:
        """Decomposition is the evidence's claims against the statement's."""
        quality = store.catalog.quality(kind=FactKind.ATOMIC)

        assert quality.mean_statement_predicates == 1.0
        assert quality.mean_evidence_predicates == 2.0
        assert quality.facts_per_passage == 2.0

    def test_the_means_leave_out_the_facts_that_failed(self, store, corpus) -> None:
        """They say what the model does, not how often it fails.

        The counts above are the failure rate. A fact refused as
        `evidence_absent` cites nothing, so it enters the evidence means as
        a zero and drags the ratio towards a number about the refusals.
        """
        first = corpus["a"][0]
        store.store(
            first,
            checked(
                first,
                "A claim.",
                evidence_text="A claim and another.",
                statement_predicates=1,
                evidence_predicates=2,
            ),
            checked(
                first,
                "Cites nothing.",
                evidence_text="",
                validated=False,
                rejection_code=Rejection.EVIDENCE_ABSENT,
                statement_predicates=0,
                evidence_predicates=0,
            ),
        )
        quality = store.catalog.quality()

        assert quality.total == 2, "the refusal is still counted"
        assert quality.validated == 1
        assert quality.mean_evidence_predicates == 2.0, "not 1.0"
        assert quality.mean_evidence_chars == 20.0, "not 10.0"

    def test_an_empty_corpus_reports_zeroes_rather_than_dividing_by_one(
        self, store
    ) -> None:
        """Nothing extracted yet is a state the page has to render."""
        quality = store.catalog.quality()

        assert quality.total == 0
        assert quality.facts_per_passage == 0.0
        assert quality.mean_statement_chars == 0.0
        assert quality.rejected == {} and quality.kinds == {}


class TestRejudging:
    """Reading every stored fact back to judge it again."""

    def test_a_fact_comes_back_with_its_passage_and_its_kind(
        self, store, corpus
    ) -> None:
        """Everything a second judgement needs, and no model call."""
        first = corpus["a"][0]
        store.store(first, checked(first, "A claim.", kind=FactKind.SUMMARY))

        ((_, passages, candidate, method),) = store.catalog.judged()
        assert passages[0].id == first
        assert passages[0].language == "en"
        assert candidate.statement == "A claim."
        assert candidate.kind == FactKind.SUMMARY
        assert method == "llm"

    def test_a_bridge_comes_back_with_its_whole_group(self, store, corpus) -> None:
        """Not only its anchor, which is what it would be judged against."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        ((_, passages, candidate, _),) = store.catalog.judged()
        assert [one.id for one in passages] == [anchor, other]
        assert [(one.position, one.sentences) for one in candidate.passages] == [
            (0, (0,)),
            (1, (0,)),
        ]

    def test_a_narrowed_read_still_hands_back_a_whole_group(
        self, store, corpus
    ) -> None:
        """A narrowing on the fact must not drop the other half of its group."""
        from seed import digest

        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )

        ((_, passages, _, _),) = store.catalog.judged(Passage.doc_sha256 == digest("a"))
        assert [one.id for one in passages] == [anchor, other]

    def test_a_verdict_is_written_back_without_touching_the_statement(
        self, store, corpus
    ) -> None:
        """What the model wrote is the record of one extraction."""
        first = corpus["a"][0]
        store.store(first, checked(first, "A claim."))
        ((fact_id, _, _, _),) = store.catalog.judged()

        store.catalog.rejudge(
            [
                (
                    fact_id,
                    checked(
                        first,
                        "REWRITTEN",
                        validated=False,
                        rejection_code=Rejection.COPIED,
                        validation_error="restated",
                    ),
                )
            ]
        )

        ((statement, validated, code),) = store.rows(
            "statement", "validated", "rejection_code"
        )
        assert statement == "A claim.", "the statement is never rewritten"
        assert (validated, code) == (False, Rejection.COPIED)

    def test_a_citation_the_verdict_does_not_name_keeps_its_span(
        self, store, corpus
    ) -> None:
        """An atomic verdict cites its first passage; a twin's citation stays."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")
        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                twin_id=survivor,
            ),
        )
        before = store.citations()

        store.catalog.rejudge(
            [(survivor, checked(first, "Requests are answered in 48 hours."))]
        )

        assert store.citations() == before

    def test_writing_no_verdicts_writes_nothing(self, store) -> None:
        """An empty batch is not a statement worth sending."""
        assert store.catalog.rejudge([]) == 0


def test_the_service_counts_what_it_owns(store, corpus) -> None:
    """What the status panel renders without knowing the names."""
    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "A claim."),
        checked(first, "Refused.", validated=False, rejection_code=Rejection.COPIED),
    )

    counts = store.queue.counts()
    assert counts["facts"] == 2
    assert counts["validated"] == 1
    assert counts[Status.EXTRACTED] == 1


def test_a_re_judgement_never_reaches_a_fact_the_cap_refused(engine, database) -> None:
    """`over_cap` is the one verdict no check can reach.

    It says the passage had no room left, which is a fact about that
    passage's budget rather than about this claim. The checks make nothing
    of it, so a re-judgement would hand the row back validated and quietly
    undo EXTRACTION_MIN_OTHER_SHARE across the corpus. `make extract-recap`
    is what re-applies it.
    """
    from seed import digest, document, fact, passage
    from sqlalchemy.orm import Session

    from extraction.repository import FactCatalog

    with Session(engine) as session:
        sha = digest("c")
        session.add(document(sha))
        at = passage(sha, ordinal=1, text="The device weighs 4 kg.", language="en")
        session.add(at)
        session.flush()
        kept = fact(at.id)
        refused = fact(at.id)
        refused.validated = False
        refused.rejection_code = Rejection.OVER_CAP
        session.add_all([kept, refused])
        session.commit()

    offered = list(FactCatalog().judged())

    assert len(offered) == 1, "the capped fact was offered for re-judgement"


def test_a_re_judgement_never_reaches_a_fact_refused_as_a_duplicate(
    engine, database
) -> None:
    """The checks cannot reproduce what the dedup probe decided either."""
    from seed import digest, document, fact, passage
    from sqlalchemy.orm import Session

    from extraction.repository import FactCatalog

    with Session(engine) as session:
        sha = digest("c")
        session.add(document(sha))
        at = passage(sha, ordinal=1, text="The device weighs 4 kg.", language="en")
        session.add(at)
        session.flush()
        kept = fact(at.id)
        refused = fact(at.id)
        refused.validated = False
        refused.rejection_code = Rejection.DUPLICATE
        session.add_all([kept, refused])
        session.commit()

    offered = list(FactCatalog().judged())

    assert len(offered) == 1, "the duplicate was offered for re-judgement"


def test_a_raised_cap_gives_back_the_facts_a_lower_one_refused(store, corpus) -> None:
    """`make extract-recap` moves a verdict both ways, as a cap moves."""
    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "One claim."),
        checked(first, "Two claims."),
        checked(first, "Three claims."),
    )

    assert store.catalog.recap(1, "over the cap") == 2
    store.catalog.recap(3, "over the cap")

    assert [row[0] for row in store.rows("validated")] == [True, True, True]
    assert store.rows("rejection_code", where="rejection_code IS NOT NULL") == []


def test_no_cap_gives_back_every_fact_a_cap_refused(store, corpus) -> None:
    """EXTRACTION_MIN_OTHER_SHARE set to cap nothing."""
    first = corpus["a"][0]
    store.store(first, checked(first, "One claim."), checked(first, "Two claims."))
    store.catalog.recap(1, "over the cap")

    store.catalog.recap(None, "over the cap")

    assert [row[0] for row in store.rows("validated")] == [True, True]


def test_a_recap_keeps_the_fact_asserting_a_value_and_leaves_a_grid_alone(
    store, corpus
) -> None:
    """Ranked as the cap ranks a passage in flight, over written facts only."""
    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "One claim."),
        checked(first, "Two claims."),
        checked(first, "It weighs 4 kg.", units_statement=["4 kg"]),
        checked(first, "A row of the grid.", extraction_method="deterministic"),
    )

    assert store.catalog.recap(1, "over the cap") == 2
    assert store.rows("statement", "validated") == [
        ("One claim.", False),
        ("Two claims.", False),
        ("It weighs 4 kg.", True),
        ("A row of the grid.", True),
    ]


def test_a_recap_records_the_settings_that_moved_each_verdict(store, corpus) -> None:
    """Refused and given back alike, as a re-judgement records them."""
    from extraction.repository import FactCatalog

    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "One claim."),
        checked(first, "Two claims."),
        checked(first, "Three claims."),
    )

    FactCatalog(version="lower").recap(1, "over the cap")
    FactCatalog(version="raised").recap(2, "over the cap")

    assert store.rows("statement", "settings_version") == [
        ("One claim.", None),
        ("Two claims.", "raised"),
        ("Three claims.", "lower"),
    ]


class TestTheEmbeddingBackfill:
    """`make extract-embed`, against the database it writes to.

    Here rather than only in a unit test because the failure this exists to
    catch was not in the logic: the bulk update named the mapped class, which
    SQLAlchemy reads as an ORM update by primary key and refuses a WHERE of
    its own. Nothing without a real session could have seen it, and the first
    run against the corpus is where it surfaced.
    """

    @pytest.fixture
    def embedder(self):
        """One axis per text, so a vector needs no weights to produce."""

        class Axes:
            def __init__(self) -> None:
                self.seen: list[str] = []

            def embed_all(self, texts: list[str]) -> list[list[float]]:
                for text in texts:
                    if text not in self.seen:
                        self.seen.append(text)
                return [
                    [1.0 if i == self.seen.index(one) else 0.0 for i in range(1024)]
                    for one in texts
                ]

        return Axes()

    def test_every_passage_and_fact_is_given_a_vector(
        self, store, corpus, embedder
    ) -> None:
        """Both tables, in one pass, with no model called."""
        from extraction.service import embed

        for passage_id in corpus["a"]:
            store.store(passage_id, checked(passage_id, "A claim about it."))

        done = embed(store.catalog, embedder)

        assert done == 4 + 2, "four passages and the two facts written"
        assert store.rows("id", where="embedding IS NULL") == []

    def test_a_row_that_already_carries_one_is_left_alone(
        self, store, corpus, embedder
    ) -> None:
        """The backfill is resumable: it reads only what is still NULL."""
        from extraction.service import embed

        store.store(corpus["a"][0], checked(corpus["a"][0], "A claim about it."))
        embed(store.catalog, embedder)
        first = len(embedder.seen)

        again = embed(store.catalog, embedder)

        assert again == 0
        assert len(embedder.seen) == first, "nothing was embedded twice"

    def test_the_vectors_are_what_a_probe_reads_back(
        self, store, corpus, embedder
    ) -> None:
        """Written as vectors rather than as text, so pgvector can order by them."""
        from extraction.service import embed

        store.store(corpus["a"][0], checked(corpus["a"][0], "A claim about it."))
        embed(store.catalog, embedder)

        twin = store.queue.nearest_fact([1.0] + [0.0] * 1023)

        assert twin is not None
        assert twin.statement == "A claim about it."

    def test_a_passage_read_again_is_not_its_own_twin(
        self, store, corpus, embedder
    ) -> None:
        """Its old facts are about to be replaced, so they refuse nothing."""
        from extraction.service import embed

        first = corpus["a"][0]
        store.store(first, checked(first, "A claim about it."))
        embed(store.catalog, embedder)

        assert store.queue.nearest_fact([1.0] + [0.0] * 1023, excluding=first) is None

    def test_a_bridge_is_no_twin(self, store, corpus, embedder) -> None:
        """A passage fact refused as its duplicate would cite into the bridge."""
        from extraction.service import embed

        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )
        embed(store.catalog, embedder)

        assert store.queue.nearest_fact([1.0] + [0.0] * 1023) is None
