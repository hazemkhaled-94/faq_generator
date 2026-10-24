"""What the facts repository writes and reads back.

Against a real Postgres, because what is under test is the SQL: which rows a
store replaces, which it leaves, and what the listing and the quality report
count when they are filtered the same way.
"""

from __future__ import annotations

from typing import Any, ClassVar

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

    def test_a_duplicate_adds_no_citation_to_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """The refusal names its twin, and the twin rests on its own passage alone.

        A citation added there counts the duplicate's passage towards every
        question the twin is asked in, and a candidate the gate reads as a
        twin may state another rule.
        """
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
        ] == [(first, 0)]

    def test_reading_the_duplicate_again_keeps_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """The twin rests on its own passage, which was not read again."""
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

    def test_a_duplicate_adds_no_evidence_to_the_fact_it_repeats(
        self, store, corpus
    ) -> None:
        """evidence_text stays the twin's own span, however often it is refused."""
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

        assert store.rows("evidence_text", where="id = :id", id=survivor) == [("A.",)]

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

    def test_clearing_narrows_to_the_bridges_a_scope_opens(self, store, corpus) -> None:
        """`--only document=…` replaces the bridges opening in that document.

        A bridge opening elsewhere stays even where it rests on a passage of
        the scope: the narrowed pass reads only the heads of the scope, so
        it could not write that bridge again.
        """
        from seed import digest

        a_anchor, b_anchor = corpus["a"][0], corpus["b"][0]
        store.topic("Support", a_anchor)
        store.topic("Access", b_anchor)
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

        removed = store.catalog.clear_bridges(Passage.doc_sha256 == digest("a"))
        assert removed == 1
        assert [row[0] for row in store.rows("statement")] == ["From b."]

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

    def test_the_validated_atomic_facts_of_a_passage_are_read_with_their_sentences(
        self, store, corpus
    ) -> None:
        """What a bridge is composed from: checked claims and where they cite."""
        first, second = corpus["a"]
        store.store(
            first,
            checked(
                first, "Requests are answered in 48 hours.", evidence_sentence_ids=[0]
            ),
            checked(
                first, "Refused.", validated=False, rejection_code=Rejection.NOT_ATOMIC
            ),
        )
        store.bridges(
            checked(
                first, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[first, second]
            )
        )

        found = store.catalog.atomic_of({first, second})

        assert list(found) == [first], "a passage with none is absent"
        ((_, statement, sentences),) = found[first]
        assert (statement, sentences) == ("Requests are answered in 48 hours.", (0,))

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

    def test_a_pass_for_the_missing_leaves_a_cited_bridge_and_its_question(
        self, store, corpus, cited
    ) -> None:
        """What `make corpus` runs: a topic already bridged is not read again."""
        from extraction.service import bridge

        topic_id = store.topic("Support", corpus["a"][0], corpus["b"][0])
        cited("accepted")

        assert store.catalog.bridged_topics() == frozenset({topic_id})
        assert bridge(store.catalog, UNREAD, UNREAD, 5, 2, missing=True) == 0
        assert store.count() == 1
        assert store.count("questions") == 1

    def test_a_bridge_counts_only_the_topic_of_its_first_passage_as_bridged(
        self, store, corpus
    ) -> None:
        """Its partner may sit in any topic, and that topic is not read for it."""
        first, partner = corpus["a"][0], corpus["b"][0]
        home = store.topic("Support", first)
        store.topic("Billing", partner)
        store.bridges(
            checked(
                first, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[first, partner]
            )
        )

        assert store.catalog.bridged_topics() == frozenset({home})


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

        `clear_bridges` deletes any bridge opening on a passage of the topics
        of the named document, and a bridge rests on two. Reading back only that
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
        _, (row,) = store.catalog.page()
        assert [one.passage_id for one in row.passages] == [first], (
            "and the listing carries it, so the page need not ask"
        )


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
        """An atomic verdict cites its first passage; a folded citation stays."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")
        store.folded(survivor, other)
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


def test_a_recap_never_counts_a_repaired_fact_against_the_cap(store, corpus) -> None:
    """The repair call's pieces stand in for a refused statement."""
    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "One claim."),
        checked(first, "Piece one.", prompt_version="repair-1"),
        checked(first, "Piece two.", prompt_version="repair-1"),
    )

    assert store.catalog.recap(1, "over the cap") == 0
    assert [row[0] for row in store.rows("validated")] == [True, True, True]


def test_a_recap_gives_back_a_repaired_fact_an_earlier_cap_refused(
    store, corpus
) -> None:
    """Moved to a bigger room, a piece is no longer left refused."""
    first = corpus["a"][0]
    store.store(
        first,
        checked(first, "One claim."),
        checked(
            first,
            "Piece one.",
            validated=False,
            rejection_code=Rejection.OVER_CAP,
            prompt_version="repair-1",
        ),
    )

    assert store.catalog.recap(1, "over the cap") == 1
    assert store.rows("statement", "validated") == [
        ("One claim.", True),
        ("Piece one.", True),
    ]


def test_a_recap_never_caps_a_passage_below_its_claims_and_items(store) -> None:
    """A list of three under a cap of one keeps all three."""
    (listed,) = store.corpus(
        ("c", ["Fees apply to:\n- cards\n- transfers\n- letters"])
    )["c"]
    store.store(
        listed,
        checked(listed, "Fees apply to cards."),
        checked(listed, "Fees apply to transfers."),
        checked(listed, "Fees apply to letters."),
    )

    assert store.catalog.recap(1, "over the cap") == 0
    assert [row[0] for row in store.rows("validated")] == [True, True, True]


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

    def test_a_fact_in_another_language_is_no_twin(
        self, store, corpus, embedder
    ) -> None:
        """No dedup across languages: a translation is its language's own fact."""
        from extraction.service import embed

        first = corpus["a"][0]
        store.store(first, checked(first, "A claim about it."))
        embed(store.catalog, embedder)
        probe = [1.0] + [0.0] * 1023

        assert store.queue.nearest_fact(probe, language="de") is None
        assert store.queue.nearest_fact(probe, language="en") is not None

    def test_a_passage_too_short_to_tell_is_probed_in_its_document_s_language(
        self, store, corpus, embedder
    ) -> None:
        """The language its candidates were read in, which is the document's."""
        from extraction.service import embed

        first = corpus["a"][0]
        store.language_of(first, None)
        store.store(first, checked(first, "A claim about it."))
        embed(store.catalog, embedder)

        assert store.queue.nearest_fact([1.0] + [0.0] * 1023, language="en")

    def test_a_fact_of_another_kind_is_no_twin(self, store, corpus, embedder) -> None:
        """A summary repeating an atomic fact is caught inside its passage only."""
        from extraction.service import embed

        first = corpus["a"][0]
        store.store(first, checked(first, "A summary of it.", kind=FactKind.SUMMARY))
        embed(store.catalog, embedder)
        probe = [1.0] + [0.0] * 1023

        assert store.queue.nearest_fact(probe, kind=FactKind.ATOMIC) is None
        assert store.queue.nearest_fact(probe, kind=FactKind.SUMMARY) is not None

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


def _axis(at: int) -> list[float]:
    """A unit vector along one axis of the column's width."""
    return [1.0 if i == at else 0.0 for i in range(1024)]


def _tilted(towards: int, angle: float) -> list[float]:
    """A unit vector `angle` radians off the first axis, towards another."""
    import math

    vector = _axis(0)
    vector[0], vector[towards] = math.cos(angle), math.sin(angle)
    return vector


def _nearer_names_another_number(store, corpus) -> int:
    """Two stored fees near "25 EUR": the nearer says 10 EUR, the other 25 Euro.

    Returns:
        The id of the one naming 25.
    """
    first, other = corpus["a"]
    store.store(first, checked(first, "The fee is 10 EUR.", embedding=_tilted(1, 0.03)))
    store.store(other, checked(other, "The fee is 25 Euro.", embedding=_tilted(2, 0.1)))
    ((named,),) = store.rows("id", where="statement = 'The fee is 25 Euro.'")
    return named


def test_the_probe_reads_past_a_nearer_fact_naming_other_numbers(store, corpus) -> None:
    """The number guard chooses among the nearest few, not from the nearest one."""
    from extraction.service import _counted_alike

    named = _nearer_names_another_number(store, corpus)

    twin = store.queue.nearest_fact(
        _axis(0),
        alike=lambda one: _counted_alike("The fee is 25 EUR.", one.statement, "en"),
    )

    assert twin is not None
    assert (twin.fact_id, twin.statement) == (named, "The fee is 25 Euro.")
    assert twin.similarity > 0.99


def _indexed() -> None:
    """Makes every connection the repository opens read through the HNSW index.

    A table this small is read by a scan and sorted, which is exact, so
    without this the index's own limit never shows. The engine is released
    after the test, and the listener with it.
    """
    from sqlalchemy import event

    from database.qa_generator.engine import engine as connect

    @event.listens_for(connect(), "connect")
    def off(dbapi_connection, _record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET enable_seqscan = off")
            cursor.execute("SET enable_sort = off")
        dbapi_connection.commit()


#: More facts than one index scan hands back, which is `hnsw.ef_search`.
_CROWD = 45


@pytest.mark.parametrize("crowd", ["language", "kind"])
def test_the_probe_finds_a_twin_behind_more_facts_than_one_scan_holds(
    store, crowd: str
) -> None:
    """The language and kind filters run over the index scan, which keeps scanning.

    Every one of the crowd is nearer the probe than the twin, and of another
    language or another kind than the one asked for. Indexed before the
    first write, because the repository's pool keeps the connection it
    writes on and the probe reads on it.
    """
    _indexed()
    (written,) = store.corpus(
        ("a", [f"Claim {at}." for at in range(_CROWD + 1)])
    ).values()
    *crowded, own = written
    for at, passage_id in enumerate(crowded, 1):
        if crowd == "language":
            store.language_of(passage_id, "de")
        store.store(
            passage_id,
            checked(
                passage_id,
                f"Claim {at}.",
                kind=FactKind.SUMMARY if crowd == "kind" else FactKind.ATOMIC,
                embedding=_tilted(1, 0.001 * at),
            ),
        )
    store.store(own, checked(own, "The fee is 25 EUR.", embedding=_tilted(1, 0.5)))

    twin = store.queue.nearest_fact(_axis(0), language="en", kind=FactKind.ATOMIC)

    assert twin is not None and twin.statement == "The fee is 25 EUR."


class TestTheDedupReplay:
    """`make extract-dedup`, against the database it writes to."""

    def test_a_fold_is_taken_out_and_the_evidence_rebuilt(self, store, corpus) -> None:
        """The fact rests on its own passage again, citing its own text alone."""
        from extraction.validation import _cited_text

        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")
        store.folded(survivor, other, "Requests may be raised by phone.")

        assert store.catalog.unfold(_cited_text) == (1, 0)
        assert store.links() == [(survivor, first, 0)]
        assert store.rows("evidence_text") == [
            ("Standard requests are answered within 48 hours.",)
        ]

    def test_a_bridge_keeps_every_passage_it_rests_on(self, store, corpus) -> None:
        """A bridge's later positions are what it rests on, not folds."""
        from extraction.validation import _cited_text

        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor, "A bridge.", kind=FactKind.BRIDGE, passage_ids=[anchor, other]
            )
        )
        before = store.links()

        assert store.catalog.unfold(_cited_text) == (0, 0)
        assert store.links() == before

    def test_a_fact_whose_own_citation_is_gone_keeps_its_folds(
        self, store, corpus
    ) -> None:
        """Taking the rest out would delete it, and the questions on it."""
        from extraction.validation import _cited_text

        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "Requests are answered in 48 hours."))
        ((survivor,),) = store.rows("id")
        store.folded(survivor, other)
        store.store(first)

        assert store.catalog.unfold(_cited_text) == (0, 1)
        assert store.rows("id") == [(survivor,)]

    def test_a_refusal_comes_back_with_its_passage_language_and_vector(
        self, store, corpus
    ) -> None:
        """Everything the probe is asked again with."""
        from extraction.models import Refused

        other = corpus["b"][0]
        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                validation_error="says what fact 1 already says",
                embedding=_axis(0),
            ),
        )
        ((refused,),) = store.rows("id")

        assert store.catalog.duplicates() == [
            Refused(
                fact_id=refused,
                passage_id=other,
                language="en",
                kind=FactKind.ATOMIC,
                statement="Requests are answered in 48 hours.",
                embedding=_axis(0),
            )
        ]

    def test_a_refusal_given_back_is_validated_under_this_configuration(
        self, store, corpus
    ) -> None:
        """Stamped with the settings it moved under, as a recap stamps one."""
        from extraction.repository import FactCatalog

        other = corpus["b"][0]
        store.store(
            other,
            checked(
                other,
                "Requests are answered in 48 hours.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                validation_error="says what fact 1 already says",
            ),
        )
        ((refused,),) = store.rows("id")

        reading = [{"gate": "duplicate", "value": 0.97, "threshold": 0.985}]

        assert FactCatalog(version="deduped").give_back(refused, reading, 0.064) == 1
        assert store.rows(
            "validated",
            "rejection_code",
            "validation_error",
            "settings_version",
            "gate_scores",
            "confidence",
        ) == [(True, None, None, "deduped", reading, 0.064)]

    def test_what_a_passage_keeps_is_read_with_its_kinds(self, store, corpus) -> None:
        """The facts it validated, and not the ones it refused."""
        first = corpus["a"][0]
        store.store(
            first,
            checked(first, "A claim.", embedding=_axis(0)),
            checked(first, "A summary.", kind=FactKind.SUMMARY, embedding=_axis(1)),
            checked(
                first,
                "Refused.",
                validated=False,
                rejection_code=Rejection.COPIED,
                embedding=_axis(2),
            ),
        )

        assert store.catalog.kept(first) == [
            ("A claim.", FactKind.ATOMIC, _axis(0)),
            ("A summary.", FactKind.SUMMARY, _axis(1)),
        ]

    def test_the_replay_gives_back_a_different_rule_and_keeps_a_restatement(
        self, store, corpus
    ) -> None:
        """Another number is another claim; the same one stays refused."""
        from extraction.service import dedup

        first, other, third = corpus["a"][0], corpus["b"][0], corpus["b"][1]
        store.store(
            first, checked(first, "The device weighs 7 kg.", embedding=_axis(0))
        )
        for passage_id, statement in (
            (other, "The device weighs 4 kg."),
            (third, "The device weighs 7 kg."),
        ):
            store.store(
                passage_id,
                checked(
                    passage_id,
                    statement,
                    validated=False,
                    rejection_code=Rejection.DUPLICATE,
                    validation_error="says what fact 1 already says",
                    embedding=_axis(0),
                    gate_scores=[{"gate": "duplicate", "value": 1.0, "margin": 0.0}],
                    confidence=0.0,
                ),
            )

        assert dedup(store.catalog, 0.985) == 1
        assert store.rows("statement", "rejection_code", "confidence") == [
            ("The device weighs 7 kg.", None, None),
            ("The device weighs 4 kg.", None, None),
            ("The device weighs 7 kg.", Rejection.DUPLICATE, 0.0),
        ]
        assert dedup(store.catalog, 0.985) == 0, "a second run gives nothing back"

    def test_a_twin_naming_its_numbers_past_a_nearer_one_keeps_it_refused(
        self, store, corpus
    ) -> None:
        """The nearest stored fee says 10 EUR; the next says 25 Euro, as it does."""
        from extraction.service import dedup

        _nearer_names_another_number(store, corpus)
        third = corpus["b"][0]
        store.store(
            third,
            checked(
                third,
                "The fee is 25 EUR.",
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                validation_error="says what the 25 Euro fact already says",
                embedding=_axis(0),
            ),
        )

        assert dedup(store.catalog, 0.985) == 0
        assert store.rows(
            "rejection_code", where="statement = 'The fee is 25 EUR.'"
        ) == [(Rejection.DUPLICATE,)]


class TestRevalidatingRefusals:
    """`make extract-revalidate` validating what a check refused when read."""

    @pytest.fixture
    def twins(self, store) -> list[int]:
        """Two passages of two documents stating one claim, each refused for it."""
        passages = store.corpus(
            ("x", ["The device weighs 4 kg."]), ("y", ["The device weighs 4 kg."])
        )
        for passage_id in (passages["x"][0], passages["y"][0]):
            store.store(
                passage_id,
                checked(
                    passage_id,
                    validated=False,
                    rejection_code=Rejection.UNRESOLVED_REFERENCE,
                    validation_error="a check since relaxed",
                    embedding=_axis(0),
                ),
            )
        return [passages["x"][0], passages["y"][0]]

    def test_the_refusals_among_them_come_back_with_their_vectors(
        self, store, corpus
    ) -> None:
        """Of any code, in id order, and never a validated fact."""
        from extraction.models import Refused

        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first, "A claim.", embedding=_axis(1)))
        store.store(
            other,
            checked(
                other,
                "Refused.",
                validated=False,
                rejection_code=Rejection.COPIED,
                embedding=_axis(2),
            ),
        )
        ids = [one for (one,) in store.rows("id")]

        assert store.catalog.refused(ids) == [
            Refused(
                fact_id=ids[1],
                passage_id=other,
                language="en",
                kind=FactKind.ATOMIC,
                statement="Refused.",
                embedding=_axis(2),
            )
        ]
        assert store.catalog.refused([]) == []

    def test_two_refused_twins_validated_together_leave_one_a_duplicate(
        self, store, twins
    ) -> None:
        """The first one validated is the second one's twin."""
        from extraction.service import revalidate
        from extraction.validation import FactChecker

        revalidate(store.catalog, FactChecker(0.6), threshold=0.985)

        assert store.rows("validated", "rejection_code") == [
            (True, None),
            (False, Rejection.DUPLICATE),
        ]

    def test_the_passage_of_a_refusal_validated_is_re_capped(
        self, store, twins
    ) -> None:
        """Neither was counted against the cap when it was refused.

        Their passage states one sentence, so its room under a cap of one is
        one, and the second validated there goes over it.
        """
        from extraction.service import revalidate
        from extraction.validation import FactChecker

        first = twins[0]
        store.store(
            first,
            *(
                checked(
                    first,
                    validated=False,
                    rejection_code=Rejection.UNRESOLVED_REFERENCE,
                    embedding=_axis(at),
                )
                for at in (3, 4)
            ),
        )

        revalidate(store.catalog, FactChecker(0.6), threshold=0.985, cap=1)

        assert store.rows(
            "rejection_code",
            where="id IN (SELECT fact_id FROM fact_passages WHERE passage_id = :at)",
            at=first,
        ) == [(None,), (Rejection.OVER_CAP,)]


def _reading(store: FactStore, answer: dict):
    """The per-passage service over this database, with a scripted model.

    The dedup gate on, through vectors that need no weights, so the drain
    replays it where it ends.
    """
    from drivers import DIGEST_SHARE, Model, Vectors

    from extraction.extractors import ExtractorRegistry, LlmExtractor, TableExtractor
    from extraction.service import ExtractionService
    from extraction.validation import FactChecker

    return ExtractionService(
        repository=store.queue,
        extractors=ExtractorRegistry(
            extractors=(TableExtractor(),),
            default=LlmExtractor(Model(answer)),  # type: ignore[arg-type]
        ),
        checker=FactChecker(DIGEST_SHARE),
        embedder=Vectors(),  # type: ignore[arg-type]
        duplicate_cosine=0.985,
        catalog=store.catalog,
    )


class TestTheReplayWhereTheDrainEnds:
    """The extract worker's dedup replay, against the database it writes to."""

    def test_a_passage_a_fact_cites_is_one_its_store_replaces(
        self, store, corpus
    ) -> None:
        """A bridge resting on it is not: `store` leaves bridges alone."""
        first, other = corpus["a"][0], corpus["b"][0]
        store.store(first, checked(first))
        store.bridges(
            checked(
                other,
                "A bridge.",
                kind=FactKind.BRIDGE,
                passage_ids=[other, corpus["b"][1]],
            )
        )

        assert store.queue.cited(first)
        assert not store.queue.cited(other)
        assert not store.queue.cited(corpus["a"][1])

    def test_the_lock_is_held_until_the_replay_ends(self, store, engine) -> None:
        """A second worker's replay waits for it rather than interleaving."""
        from sqlalchemy import text

        from extraction.repository import _REPLAYING

        def free() -> bool:
            """Whether another connection could take the lock now."""
            with engine.connect() as other:
                taken = other.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": _REPLAYING}
                ).scalar()
                if taken:
                    other.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": _REPLAYING}
                    )
                return bool(taken)

        with store.catalog.replaying():
            assert not free()
        assert free()

    def test_a_rerun_ends_with_the_dedup_replay(self, store) -> None:
        """A refusal whose twin the rerun deleted is given back.

        The passage read again yields nothing this time, so its fact goes,
        and the copy another document holds is the claim's only statement.
        """
        passages = store.corpus(
            ("x", ["The device weighs 4 kg."]), ("y", ["The device weighs 4 kg."])
        )
        first, other = passages["x"][0], passages["y"][0]
        store.store(first, checked(first, embedding=_axis(0)))
        store.store(
            other,
            checked(
                other,
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                validation_error="says what fact 1 already says",
                embedding=_axis(0),
            ),
        )
        store.queued(first)

        assert _reading(store, {"facts": []}).drain() == 1
        assert store.rows("validated", "rejection_code") == [(True, None)]

    def test_a_drain_of_new_passages_leaves_the_refusals_alone(self, store) -> None:
        """Nothing it stored replaced a fact, so no refusal lost its twin."""
        passages = store.corpus(
            ("x", ["The device weighs 4 kg."]), ("y", ["The device weighs 4 kg."])
        )
        first, other = passages["x"][0], passages["y"][0]
        store.store(
            other,
            checked(
                other,
                validated=False,
                rejection_code=Rejection.DUPLICATE,
                validation_error="says what a deleted fact said",
                embedding=_axis(0),
            ),
        )
        store.queued(first)

        _reading(store, {"facts": []}).drain()

        assert store.rows("rejection_code") == [(Rejection.DUPLICATE,)]


class TestBridgeReading:
    """A bridge keeps the relation it was written with and the question it was tested with."""

    READING: ClassVar = {
        "relation": "defines",
        "question": "What fee?",
        "answer": "10 EUR",
    }

    def test_a_bridge_keeps_its_reading(self, store, corpus) -> None:
        """Written with the fact, read back into the candidate a re-judgement checks."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor,
                "A bridge.",
                kind=FactKind.BRIDGE,
                passage_ids=[anchor, other],
                bridge=self.READING,
            )
        )

        assert store.rows("bridge") == [(self.READING,)]
        ((_, _, candidate, _),) = store.catalog.judged()
        assert candidate.relation == "defines"
        assert candidate.probe == ("What fee?", "10 EUR")

    def test_a_re_judgement_leaves_the_reading_alone(self, store, corpus) -> None:
        """The verdict is rewritten; what the model wrote and was asked is not."""
        anchor, other = corpus["a"][0], corpus["b"][0]
        store.bridges(
            checked(
                anchor,
                "A bridge.",
                kind=FactKind.BRIDGE,
                passage_ids=[anchor, other],
                bridge=self.READING,
            )
        )
        ((fact_id, _, _, _),) = store.catalog.judged()

        store.catalog.rejudge(
            [
                (
                    fact_id,
                    checked(
                        anchor,
                        "A bridge.",
                        kind=FactKind.BRIDGE,
                        validated=False,
                        rejection_code=Rejection.NOT_BRIDGING,
                        passage_ids=[anchor, other],
                    ),
                )
            ]
        )

        assert store.rows("bridge") == [(self.READING,)]


@pytest.mark.parametrize(
    "language,first,second",
    [
        ("en", "Orders ship within 2 days.", "Returns are free within 30 days."),
        (
            "de",
            "Bestellungen werden in 2 Tagen versandt.",
            "Rückgaben sind 30 Tage kostenlos.",
        ),
    ],
)
def test_a_passage_deleted_during_the_bridge_pass_drops_only_its_link(
    engine, database, monkeypatch, language, first, second
) -> None:
    """database-10: a link's passage gone before its write is dropped, the pass goes on."""
    from sqlalchemy import text

    from extraction import service
    from extraction.links import Link

    store = FactStore(engine, language=language)
    ids = store.corpus(("a", [first, first + " Ja."]), ("b", [second, second + " Ja."]))
    both = [ids["a"][0], ids["a"][1], ids["b"][0], ids["b"][1]]
    for one, said in zip(both, (first, first, second, second), strict=True):
        store.store(one, checked(one, said))
    store.topic("t", *both)
    seen = {p.id: p for _, held in store.catalog.by_topic(None) for p in held}
    links = [
        Link((seen[both[0]], seen[both[2]]), "sibling", "x"),
        Link((seen[both[1]], seen[both[3]]), "sibling", "y"),
    ]
    monkeypatch.setattr(service, "linked", lambda *a, **k: links)

    class Reader:
        provenance = None
        calls = 0

        def extract(self, offered, link, facts):
            Reader.calls += 1
            if (
                Reader.calls == 1
            ):  # the second link's passage goes while the first is read
                with engine.begin() as c:
                    c.execute(
                        text("DELETE FROM passages WHERE id = :i"), {"i": both[3]}
                    )
            return [offered]

    class Judge:
        def check_bridge(self, offered, candidate, provenance):
            return checked(
                offered[0].id,
                f"Both say {offered[0].id}.",
                kind=FactKind.BRIDGE,
                passage_ids=[one.id for one in offered],
            )

    written = service.bridge(store.catalog, Reader(), Judge(), 1, 2, force=True)

    assert written == 1


class TestTheDigestPass:
    """Giving a digest to passages that finished extraction without one."""

    NOTE = "digest failed: the provider filtered the answer"

    def _extracted_without_digest(self, store, *passage_ids: int) -> None:
        """Extracts each passage with one atomic fact and a note."""
        store.queued(*passage_ids)
        for one in passage_ids:
            store.queue.claim()
            store.queue.store(
                one, [checked(one, f"Fact of passage {one}.")], note=self.NOTE
            )

    def test_only_the_digest_is_written_and_the_atomic_ids_stay(
        self, store, corpus
    ) -> None:
        """The facts questions rest on are untouched."""
        from extraction.repository import DigestQueue

        first, second = corpus["a"]
        self._extracted_without_digest(store, first, second)
        before = store.rows("id", "statement", where="kind = 'atomic'")
        queue = DigestQueue()

        claimed = queue.claim()
        assert claimed is not None and claimed.id == first
        queue.store_digests(
            first,
            [
                checked(first, "A summary.", kind=FactKind.SUMMARY),
                checked(first, "- a point", kind=FactKind.OUTLINE),
            ],
        )

        assert store.rows("id", "statement", where="kind = 'atomic'") == before
        assert [row[0] for row in store.rows("kind", where="kind <> 'atomic'")] == [
            FactKind.SUMMARY,
            FactKind.OUTLINE,
        ]
        errors = store._execute("SELECT extract_error FROM passages ORDER BY id")
        assert errors == [(None,), (self.NOTE,), (None,), (None,)]
        assert store.statuses()[:2] == [Status.EXTRACTED, Status.EXTRACTED]

    def test_a_digest_given_again_replaces_the_one_before(self, store, corpus) -> None:
        """A second digest does not sit beside the first."""
        from extraction.repository import DigestQueue

        (first, _) = corpus["a"]
        self._extracted_without_digest(store, first)
        queue = DigestQueue()
        queue.claim()
        queue.store_digests(first, [checked(first, "One.", kind=FactKind.SUMMARY)])
        queue.store_digests(first, [checked(first, "Two.", kind=FactKind.SUMMARY)])

        assert [
            row[0] for row in store.rows("statement", where="kind = 'summary'")
        ] == ["Two."]

    def test_each_passage_is_claimed_once_whether_or_not_it_is_digested(
        self, store, corpus
    ) -> None:
        """A digest that fails again keeps its note and is not the next claim."""
        from extraction.repository import DigestQueue

        first, second = corpus["a"]
        self._extracted_without_digest(store, first, second)
        queue = DigestQueue()

        seen = []
        while (claimed := queue.claim()) is not None:
            seen.append(claimed.id)
            queue.store_digests(claimed.id, [], note=self.NOTE)

        assert seen == [first, second]
        assert store.statuses()[:2] == [Status.EXTRACTED, Status.EXTRACTED]

    def test_a_passage_with_no_note_under_the_floor_is_never_claimed(
        self, store, corpus
    ) -> None:
        """Nor is one still pending, which the passage reader owns."""
        from extraction.repository import DigestQueue

        first, second = corpus["a"]
        store.queued(first, second)
        store.queue.claim()
        store.queue.store(first, [checked(first)])

        assert DigestQueue(min_chars=10_000).claim() is None
        claimed = DigestQueue().claim()
        assert claimed is not None and claimed.id == first, "pending is not claimed"

    def test_a_released_passage_goes_back_extracted_not_pending(
        self, store, corpus
    ) -> None:
        """Pending would read it again and replace its atomic facts."""
        from extraction.repository import DigestQueue

        (first, _) = corpus["a"]
        self._extracted_without_digest(store, first)
        queue = DigestQueue()
        queue.claim()
        queue.release(first)

        assert store.statuses()[0] == Status.EXTRACTED
        assert store._execute("SELECT extract_error FROM passages ORDER BY id")[0] == (
            self.NOTE,
        )

    def test_a_long_passage_with_no_digest_is_claimed_without_a_note(
        self, store, corpus
    ) -> None:
        """A floor lowered since it was read reaches it, and only it."""
        from extraction.repository import DigestQueue

        long, short = corpus["a"]
        store._execute(
            "UPDATE passages SET text = :text WHERE id = :id",
            text="A long enough passage. " * 40,
            id=long,
        )
        store.queued(long, short)
        for one in (long, short):
            store.queue.claim()
            store.queue.store(one, [checked(one, f"Fact of passage {one}.")])
        before = store.rows("id", "statement", where="kind = 'atomic'")
        queue = DigestQueue(min_chars=200)

        claimed = queue.claim()
        assert claimed is not None and claimed.id == long
        queue.store_digests(long, [checked(long, "Summary.", kind=FactKind.SUMMARY)])

        assert queue.claim() is None, "short is under the floor, long is digested"
        assert store.rows("id", "statement", where="kind = 'atomic'") == before
        assert DigestQueue(min_chars=200).claim() is None
