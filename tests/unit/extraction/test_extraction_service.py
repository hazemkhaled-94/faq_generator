"""What the per-passage service does with one claimed passage.

A passage that yields nothing is not a failure and neither is a fact that
fails a check; the failures are the passage the model would not read and the
passage that raised something nobody expected.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from drivers import Extraction, Vectors, passage, table_passage

from database.qa_generator import FactKind, Rejection
from extraction.models import Twin
from llm.client import ModelRefused, ModelUnavailable

pytestmark = pytest.mark.nlp

ATOMIC = {"facts": [{"sentences": [0], "statement": "The device weighs 4 kg."}]}
DIGEST = {
    "summary": "The device weighs 4 kg.",
    "outline": ["Weighs 4 kg", "Runs for 12 hours"],
}
BOTH = (FactKind.SUMMARY, FactKind.OUTLINE)


def test_an_empty_queue_is_not_worked() -> None:
    """Nothing to claim, nothing to do."""
    run = Extraction()

    assert run.next() is None
    assert run.run() == 0
    assert run.model.calls == 0


def test_a_passage_is_read_and_its_facts_stored() -> None:
    """The id comes back, and the facts are written against it."""
    from extraction.extractors import llm

    run = Extraction(passage(), facts=ATOMIC)

    assert run.next() == 1
    assert run.queue.kinds() == [FactKind.ATOMIC]
    (stored,) = run.queue.stored[1]
    assert stored.statement == "The device weighs 4 kg."
    assert stored.extraction_model == run.model.model
    assert stored.prompt_version == llm.PROMPT_VERSION


def test_a_passage_asserting_nothing_never_reaches_the_model() -> None:
    """A heading returns its own text back."""
    run = Extraction(passage("Risiko", language="de"), facts=ATOMIC)
    run.next()

    assert run.model.calls == 0
    assert run.queue.stored == {1: []}, "read with nothing found, not failed"
    assert run.queue.failed == {}


def test_both_readings_are_written_for_one_passage() -> None:
    """The atomic pass and the digest pass, in that order."""
    run = Extraction(passage(), facts=ATOMIC, digest=DIGEST, kinds=BOTH)
    run.next()

    assert run.queue.kinds() == [
        FactKind.ATOMIC,
        FactKind.SUMMARY,
        FactKind.OUTLINE,
    ]
    assert run.model.calls == 1 and run.digest_model.calls == 1


def test_no_digest_reader_means_no_extra_call() -> None:
    """A deployment that writes neither pays for neither."""
    run = Extraction(passage(), facts=ATOMIC, digest=DIGEST)
    run.next()

    assert run.queue.kinds() == [FactKind.ATOMIC]
    assert run.digest_model.calls == 0


def test_a_passage_carrying_one_claim_is_not_digested() -> None:
    """It is already as short as its own summary."""
    run = Extraction(
        passage("The device weighs 4 kg."), facts=ATOMIC, digest=DIGEST, kinds=BOTH
    )
    run.next()

    assert run.queue.kinds() == [FactKind.ATOMIC]
    assert run.digest_model.calls == 0, "the passage carries one claim"


def test_a_model_that_will_not_answer_fails_the_passage() -> None:
    """The row carries the reason rather than being left in progress."""
    run = Extraction(passage(), facts=ModelUnavailable("Timeout: took too long"))
    run.next()

    assert run.queue.stored == {}
    assert "took too long" in run.queue.failed[1]


# A digest is optional: the atomic facts were paid for and are what questions
# rest on, so a digest that cannot be had must not take them with it.
LANGUAGES = {
    "en": "The device weighs 4 kg. It runs for 12 hours.",
    "de": "Das Gerät wiegt 4 kg. Es läuft 12 Stunden lang.",
}
DIGEST_FAILURES = {
    "unreachable": ModelUnavailable("Timeout: took too long"),
    "content filter": ModelRefused("the provider filtered the answer"),
}


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("failure", DIGEST_FAILURES)
def test_a_digest_the_model_will_not_give_keeps_the_atomic_facts(
    language: str, failure: str
) -> None:
    """The passage finishes with its facts, and says what it lacks."""
    run = Extraction(
        passage(LANGUAGES[language], language=language),
        facts=ATOMIC,
        digest=DIGEST_FAILURES[failure],
        kinds=BOTH,
    )

    assert run.run() == 1
    assert run.queue.kinds() == [FactKind.ATOMIC]
    assert run.queue.failed == {}
    assert run.queue.notes[1].startswith("digest failed: ")


def test_a_digest_that_came_leaves_no_note() -> None:
    """A passage with both readings has nothing outstanding."""
    run = Extraction(passage(), facts=ATOMIC, digest=DIGEST, kinds=BOTH)
    run.next()

    assert run.queue.notes == {1: None}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_digest_pass_digests_what_the_first_pass_could_not(
    language: str,
) -> None:
    """Only the digest kinds are written, and the note is cleared."""
    run = Extraction(
        passage(LANGUAGES[language], language=language),
        digest=DIGEST,
        kinds=BOTH,
        digests_only=True,
    )

    assert run.run() == 1
    assert run.queue.stored == {}, "no atomic fact is written or replaced"
    assert [fact.kind for fact in run.queue.digests[1]] == list(BOTH)
    assert run.queue.notes == {1: None}
    assert run.model.calls == 0, "the passage reader is not asked"


def test_the_digest_pass_keeps_the_note_when_the_digest_fails_again() -> None:
    """The row stays as it was, and is not failed."""
    run = Extraction(
        passage(),
        digest=ModelRefused("the provider filtered the answer"),
        kinds=BOTH,
        digests_only=True,
    )

    assert run.run() == 1
    assert run.queue.digests == {1: []}
    assert run.queue.notes[1].startswith("digest failed: ")
    assert run.queue.failed == {}


#: Navigation the first pass never sends to a model: a contents page of any
#: document, in each language the corpus configures, over 500 characters with
#: more than two claims, which is what the digest pass would otherwise digest.
CONTENTS = {
    "en": "\n".join(
        f"| Section {n} The member pays the fee within the period. ______ {n + 3} |"
        for n in range(1, 14)
    ),
    "de": "\n".join(
        f"| Abschnitt {n} Das Mitglied zahlt die Gebühr innerhalb der Frist. ______ {n + 3} |"
        for n in range(1, 14)
    ),
}


@pytest.mark.parametrize("language", CONTENTS)
def test_the_digest_pass_asks_no_model_about_what_the_first_pass_skips(
    language: str,
) -> None:
    """A contents page is finished with no call, as the passage reader does."""
    from extraction.service import skipped

    contents = passage(
        CONTENTS[language], language=language, block_type="document_index"
    )
    assert skipped(contents) is not None and len(CONTENTS[language]) >= 500
    assert contents.claims >= 2, "enough to be digested, were it not skipped"
    run = Extraction(contents, digest=DIGEST, kinds=BOTH, digests_only=True)

    assert run.run() == 1
    assert run.digest_model.calls == 0, "no digest is asked for a contents page"
    assert run.queue.digests == {1: []}
    assert run.queue.notes == {1: None}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_digest_pass_never_fails_an_extracted_passage(language: str) -> None:
    """An unexpected error is the passage's digest note, and its status stays."""
    run = Extraction(
        passage(LANGUAGES[language], language=language),
        digest=RuntimeError("disk full"),
        kinds=BOTH,
        digests_only=True,
    )

    run.run()

    assert run.queue.failed == {}, "make extract-retry would read it again"
    assert run.queue.notes[1] == "digest failed: RuntimeError: disk full"


def test_a_digest_pass_cut_short_releases_its_row() -> None:
    """An interrupt leaves no claim for the next start to sweep into failed."""
    run = Extraction(
        passage(), digest=KeyboardInterrupt(), kinds=BOTH, digests_only=True
    )

    with pytest.raises(KeyboardInterrupt):
        run.run()

    assert run.queue.released == [1]
    assert run.queue.failed == {}


def test_an_unexpected_failure_is_named_by_its_type() -> None:
    """A row failed by something nobody planned for still says what it was."""
    run = Extraction(passage(), facts=ValueError("nonsense came back"))
    run.next()

    assert run.queue.failed[1] == "ValueError: nonsense came back"


def test_draining_works_every_passage_and_stops() -> None:
    """The loop ends on the first empty claim rather than spinning."""
    from dataclasses import replace

    first = passage()
    run = Extraction(first, replace(first, id=2), facts=ATOMIC)

    assert run.run() == 2
    assert sorted(run.queue.stored) == [1, 2]


def test_a_claim_an_earlier_run_left_behind_is_swept_first() -> None:
    """A drain begins by failing whatever no worker is on any more."""
    run = Extraction(passage(), facts=ATOMIC)
    run.queue.swept = 3

    assert run.run() == 1, "the sweep does not count as work"


def test_a_rejected_fact_is_stored_rather_than_dropped() -> None:
    """The share that failed is how extraction is judged."""
    invented = {"facts": [{"sentences": [0], "statement": "The device weighs 9 kg."}]}
    run = Extraction(passage(), facts=invented)
    run.next()

    stored = run.queue.stored[1]
    assert len(stored) == 1
    assert not stored[0].validated
    assert stored[0].rejection_code == "unsupported_addition"


def test_a_table_is_read_without_a_model() -> None:
    """The block type routes the passage to the deterministic reader."""
    run = Extraction(table_passage(), facts=ATOMIC)
    run.next()

    assert run.model.calls == 0, "a table needs no model"
    assert run.queue.stored[1], "and still yields facts"
    assert run.queue.stored[1][0].extraction_method == "deterministic"


class TestProseMergedWithATable:
    """The chunker labels a passage `table` if ANY item in it is one.

    It then numbers the whole of it by rendered line with no predicates
    recorded, so `claims` is zero for every table and prose merged into one
    is invisible. The cell reader walks the grid; nothing read the rest.
    """

    #: One line, one finite verb, and nothing in the grid.
    PROSE = "The compact model replaced the previous range in March."

    def test_the_prose_is_read_by_the_model_as_well(self) -> None:
        """Both readers, so neither half of the passage is thrown away."""
        run = Extraction(table_passage(prose=self.PROSE), facts=ATOMIC)
        run.next()

        assert run.model.calls == 1, "the prose beside the grid is worth a call"
        methods = {one.extraction_method for one in run.queue.stored[1]}
        assert methods == {"deterministic", "llm"}

    def test_the_model_is_shown_the_prose_and_not_the_grid(self) -> None:
        """The cell reader has the grid; the model restating it would mislabel."""
        run = Extraction(table_passage(prose=self.PROSE), facts=ATOMIC)
        run.next()

        assert self.PROSE in run.model.sent["user"]
        assert "| Compact | 4 |" not in run.model.sent["user"]

    def test_a_table_with_no_prose_still_needs_no_model(self) -> None:
        """The rendered rows and the `|---|` separator carry no finite verb."""
        run = Extraction(table_passage(), facts=ATOMIC)
        run.next()

        assert run.model.calls == 0

    def test_the_cell_facts_are_kept_beside_the_prose(self) -> None:
        """The grid is still read deterministically, which is what it is for."""
        run = Extraction(table_passage(prose=self.PROSE), facts=ATOMIC)
        run.next()

        composed = [
            one
            for one in run.queue.stored[1]
            if one.extraction_method == "deterministic"
        ]
        assert composed, "the grid is still read from its cells"


class TestTheDedupGate:
    """A statement the corpus already holds is stored refused, not dropped."""

    TWICE: ClassVar[dict] = {
        "facts": [
            {"sentences": [0], "statement": "The device weighs 4 kg."},
            {"sentences": [0], "statement": "The device weighs 4 kg."},
        ]
    }

    #: The passage's claim, and a summary of it saying the same thing.
    REPEATED: ClassVar[dict] = {
        "summary": "The device weighs 4 kg.",
        "outline": ["Weighs 4 kg", "Runs for 12 hours"],
    }

    def test_two_atomic_facts_of_one_passage_are_never_duplicates(self) -> None:
        """Two items of a list differ by a word and are two claims.

        The passage's own facts of one kind are compared word for word only,
        so two of its claims are kept however near their vectors sit; the
        question dedup refuses a second question on a near repeat.
        """
        from extraction.service import _closest

        vector = [1.0, 0.0]
        kept = [("The card is blocked abroad.", FactKind.ATOMIC, vector)]

        assert (
            _closest(
                "The card is blocked at home.",
                FactKind.ATOMIC,
                "en",
                vector,
                None,
                kept,
            )
            is None
        )

    def test_a_word_for_word_repeat_in_one_passage_is_a_duplicate(self) -> None:
        """The model writing one claim twice is one fact, and one cap place."""
        run = Extraction(passage(), facts=self.TWICE, duplicate_cosine=0.9)
        run.next()

        first, second = run.queue.stored[1]
        assert first.validated, first.validation_error
        assert second.rejection_code == Rejection.DUPLICATE, second.validation_error
        assert "a fact this passage kept" in (second.validation_error or "")

    def test_a_summary_repeating_an_atomic_fact_is_still_refused(self) -> None:
        """The index holds nothing yet, so only the run's own memory catches it."""
        run = Extraction(
            passage(),
            facts=ATOMIC,
            digest=self.REPEATED,
            kinds=(FactKind.SUMMARY,),
            duplicate_cosine=0.9,
        )
        run.next()

        atomic, summary = run.queue.stored[1]
        assert atomic.validated, atomic.validation_error
        assert summary.rejection_code == Rejection.DUPLICATE
        assert summary.twin_id is None, "its twin has no id until stored"
        assert "a fact this passage kept" in (summary.validation_error or "")

    def test_a_refused_duplicate_is_kept_with_its_reason(self) -> None:
        """Drop-rate evidence, like every other refusal."""
        run = Extraction(
            passage(),
            facts=ATOMIC,
            digest=self.REPEATED,
            kinds=(FactKind.SUMMARY,),
            duplicate_cosine=0.9,
        )
        run.next()

        refused = run.queue.stored[1][1]
        assert "already says" in (refused.validation_error or "")
        assert refused.embedding is not None, "the vector it was judged on is kept"

    def test_a_statement_already_in_the_corpus_is_refused(self) -> None:
        """What the HNSW probe answers is what the gate reads."""
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.9)
        run.queue.twin = Twin(
            fact_id=7, statement="The device weighs 4 kg.", similarity=0.99
        )
        run.next()

        stored = run.queue.stored[1]
        assert stored[0].rejection_code == Rejection.DUPLICATE
        assert "fact 7" in (stored[0].validation_error or "")
        assert stored[0].twin_id == 7, "the refusal names fact 7"

    def test_the_duplicate_message_names_the_bar_as_set(self) -> None:
        """0.985 is not 0.98: the refusal says the bar the operator set."""
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.985)
        run.queue.twin = Twin(
            fact_id=7, statement="The device weighs 4 kg.", similarity=0.99
        )
        run.next()

        (stored,) = run.queue.stored[1]
        assert "over the 0.985 EXTRACTION_DUPLICATE_COSINE" in (
            stored.validation_error or ""
        ), stored.validation_error

    def test_a_twin_stating_other_numbers_is_not_a_duplicate(self) -> None:
        """4 kg and 7 kg share every word but one, and are two claims."""
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.9)
        run.queue.twin = Twin(
            fact_id=7, statement="The device weighs 7 kg.", similarity=0.99
        )
        run.next()

        (stored,) = run.queue.stored[1]
        assert stored.validated, stored.validation_error

    def test_a_number_written_as_a_word_is_the_same_number(self) -> None:
        """A count written out restates its digits: the guard reads values."""
        run = Extraction(
            passage("The device has two ports and weighs 4 kg."),
            facts={
                "facts": [{"sentences": [0], "statement": "The device has two ports."}]
            },
            duplicate_cosine=0.9,
        )
        run.queue.twin = Twin(
            fact_id=7, statement="The device has 2 ports.", similarity=0.99
        )
        run.next()

        (stored,) = run.queue.stored[1]
        assert stored.rejection_code == Rejection.DUPLICATE, stored.validation_error

    def test_a_duplicate_takes_no_place_under_the_atomic_cap(self) -> None:
        """Dedup first, then the cap over what is left."""
        facts = {
            "facts": [
                {"sentences": [0], "statement": "The device weighs 4 kg."},
                {"sentences": [0], "statement": "The device runs for 12 hours."},
                {"sentences": [1], "statement": "The device arrives in March 2026."},
            ]
        }
        run = Extraction(passage(), facts=facts, duplicate_cosine=0.9, atomic_cap=2)
        run.queue.twin = Twin(
            fact_id=7, statement="The device weighs 4 kg.", similarity=0.99
        )
        run.next()

        kept = [one.statement for one in run.queue.stored[1] if one.validated]
        assert kept == [
            "The device runs for 12 hours.",
            "The device arrives in March 2026.",
        ]

    def test_the_atomic_cap_refuses_what_the_passage_has_no_room_for(self) -> None:
        """The validated atomic facts past the cap, in the order written.

        Room for two: the passage states two claims, above a cap of one.
        """
        facts = {
            "facts": [
                {"sentences": [0], "statement": "The device weighs 4 kg."},
                {"sentences": [0], "statement": "The device runs for 12 hours."},
                {"sentences": [1], "statement": "The device arrives in March 2026."},
            ]
        }
        run = Extraction(passage(), facts=facts, atomic_cap=1)
        run.next()

        stored = run.queue.stored[1]
        assert [one.rejection_code for one in stored] == [
            None,
            None,
            Rejection.OVER_CAP,
        ]
        assert "or the 1 EXTRACTION_MIN_OTHER_SHARE leaves room for" in (
            stored[2].validation_error or ""
        ), stored[2].validation_error

    def test_the_corpus_is_probed_in_the_candidate_s_language_and_kind(self) -> None:
        """A German summary is never the twin of an English atomic fact."""
        run = Extraction(
            passage(
                "Das Gerät wiegt 4 kg. Es läuft 12 Stunden. Es kommt im März.",
                language="de",
            ),
            facts={"facts": [{"sentences": [0], "statement": "Das Gerät wiegt 4 kg."}]},
            digest={"summary": "Das Gerät läuft 12 Stunden.", "outline": []},
            kinds=(FactKind.SUMMARY,),
            duplicate_cosine=0.9,
        )
        run.next()

        assert run.queue.probed == [("de", FactKind.ATOMIC), ("de", FactKind.SUMMARY)]

    def test_a_near_restatement_below_the_configured_bar_is_kept(self) -> None:
        """Bare statements on one subject score high; the bar sits near identity."""
        from extraction.config import Settings

        run = Extraction(
            passage(), facts=ATOMIC, duplicate_cosine=Settings.load().duplicate_cosine
        )
        run.queue.twin = Twin(
            fact_id=7, statement="The device has a weight of 4 kg.", similarity=0.96
        )
        run.next()

        (stored,) = run.queue.stored[1]
        assert stored.validated, stored.validation_error

    def test_a_twin_below_the_threshold_is_not_a_duplicate(self) -> None:
        """Sharing a subject is not saying the same thing."""
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.9)
        run.queue.twin = Twin(fact_id=7, statement="Something else.", similarity=0.7)
        run.next()

        assert run.queue.stored[1][0].validated

    def test_the_gate_off_still_writes_the_vectors(self) -> None:
        """A deployment may want the embeddings without the refusals."""
        run = Extraction(passage(), facts=self.TWICE, embed=True)
        run.next()

        stored = run.queue.stored[1]
        assert all(one.validated for one in stored)
        assert all(one.embedding is not None for one in stored)

    def test_no_embedder_writes_no_vector_and_refuses_nothing(self) -> None:
        """The default deployment is unchanged."""
        run = Extraction(passage(), facts=self.TWICE)
        run.next()

        stored = run.queue.stored[1]
        assert all(one.validated for one in stored)
        assert all(one.embedding is None for one in stored)
        assert run.queue.embeddings[1] is None

    def test_the_passage_is_embedded_beside_its_facts(self) -> None:
        """One model load writes both, which is why extraction owns the column."""
        run = Extraction(passage(), facts=ATOMIC, embed=True)
        run.next()

        assert run.queue.embeddings[1] is not None

    def test_a_refused_fact_is_not_what_a_later_one_is_compared_against(self) -> None:
        """Otherwise the first copy kept depends on which check ran first.

        The claim is refused against the corpus, so the summary repeating it
        has nothing in this passage to repeat.
        """
        run = Extraction(
            passage(),
            facts=ATOMIC,
            digest=self.REPEATED,
            kinds=(FactKind.SUMMARY,),
            duplicate_cosine=0.9,
        )
        run.queue.twin = Twin(
            fact_id=7, statement="The device weighs 4 kg.", similarity=0.99
        )
        run.queue.twin_kind = FactKind.ATOMIC
        run.next()

        atomic, summary = run.queue.stored[1]
        assert atomic.rejection_code == Rejection.DUPLICATE
        assert summary.validated, summary.validation_error

    def test_both_writers_of_the_column_embed_the_same_text(self) -> None:
        """Extraction and `--embed` write one column and disagreed about it.

        The live path embedded the statement as the model wrote it and the
        backfill embedded it case-folded, so `facts.embedding` held vectors
        of two different strings - and the dedup probe, which compares a
        fresh candidate against every stored fact, compared across them.
        A German statement folded is not the string that was embedded at
        extraction time.
        """
        from extraction.service import embed

        written = "Das Gerät wiegt 4 kg."
        live = Extraction(
            passage(),
            facts={"facts": [{"sentences": [0], "statement": written}]},
            embed=True,
        )
        live.next()

        backfill = Vectors()
        embed(_OneFact(written), backfill)  # type: ignore[arg-type]

        assert written in live.vectors.seen  # type: ignore[union-attr]
        assert backfill.seen == [written]


class _OneFact:
    """A catalogue holding one unembedded fact and no unembedded passage."""

    def __init__(self, statement: str) -> None:
        """Holds the statement until it has been read once."""
        self._left = [(1, statement)]

    def unembedded_passages(self, limit: int, within=None) -> list:
        """No passage is waiting for a vector."""
        del limit, within
        return []

    def embed_passages(self, vectors: list) -> int:
        """Nothing to write."""
        return len(vectors)

    def unembedded(self, limit: int, within=None) -> list:
        """The fact, once."""
        del limit, within
        found, self._left = self._left, []
        return found

    def embed_facts(self, vectors: list) -> int:
        """Records that the vector was written."""
        return len(vectors)


# ── A readable passage the model found nothing in ──────────────────────────

EMPTY: dict = {"facts": []}


def test_a_readable_passage_with_no_facts_is_warned_about(caplog) -> None:
    """A model answering empty marks the corpus read and writes nothing.

    `skipped` has already refused everything nothing could be read from,
    so reaching the model and getting none back is not the same answer as
    "this passage carries none". It used to be recorded as though it were:
    the row went to `extracted` with nothing under it and the run looked
    clean, which is how a whole corpus is lost without one error.
    """
    run = Extraction(passage(), facts=EMPTY)

    with caplog.at_level("WARNING"):
        run.next()

    assert "proposed nothing" in caplog.text
    assert "LLM_REASONING_EFFORT" in caplog.text, "the log names the first fix"


def test_the_passage_is_still_read_rather_than_failed(caplog) -> None:
    """One such passage is ordinary; a page of prose asserting nothing exists.

    It is the RATE that is the signal, so this warns and moves on. Failing
    the row would strand a corpus on its dullest page.
    """
    run = Extraction(passage(), facts=EMPTY)

    with caplog.at_level("WARNING"):
        run.next()

    assert run.queue.stored == {1: []}
    assert run.queue.failed == {}


def test_a_skipped_passage_is_not_warned_about(caplog) -> None:
    """A heading never reached the model, so it proposed nothing correctly."""
    run = Extraction(passage("Risiko", language="de"), facts=EMPTY)

    with caplog.at_level("WARNING"):
        run.next()

    assert run.model.calls == 0
    assert "proposed nothing" not in caplog.text


def test_a_table_read_without_the_model_raises_no_empty_model_warning(caplog) -> None:
    """The cell reader found no row to compose, and no model was asked."""
    from drivers import GRID

    headers = {**GRID, "cells": [one for one in GRID["cells"] if one["row"] == 0]}
    run = Extraction(table_passage(headers), facts=EMPTY)

    with caplog.at_level("WARNING"):
        run.next()

    assert run.model.calls == 0
    assert run.queue.stored == {1: []}
    assert "proposed nothing" not in caplog.text


def test_a_passage_that_yielded_facts_is_not_warned_about(caplog) -> None:
    """The ordinary path stays quiet."""
    run = Extraction(passage(), facts=ATOMIC)

    with caplog.at_level("WARNING"):
        run.next()

    assert "proposed nothing" not in caplog.text


# ── The dedup replay where a drain ends ────────────────────────────────────


class TestTheReplayWhereTheDrainEnds:
    """A passage read again deletes facts a refusal elsewhere may name as its twin.

    A retry or a rerun only queues rows; the drain is what deletes. So the
    replay `make extract-dedup` runs hangs on the drain finding its queue
    empty, after a drain that replaced facts.
    """

    def test_a_drain_that_replaced_facts_ends_with_the_replay(self) -> None:
        """Once, under the lock, after the last passage was stored."""
        from dataclasses import replace

        from drivers import Catalogue

        first = passage()
        catalog = Catalogue()
        run = Extraction(
            first,
            replace(first, id=2),
            facts=ATOMIC,
            duplicate_cosine=0.9,
            catalog=catalog,
        )
        run.queue.read_before = {1, 2}

        assert run.run() == 2
        assert catalog.unfolded_locked == [True]

    def test_a_drain_reading_only_new_passages_replays_nothing(self) -> None:
        """A passage nothing cited yet deletes nothing, so it leaves no ghost."""
        from drivers import Catalogue

        catalog = Catalogue()
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.9, catalog=catalog)

        run.run()

        assert catalog.unfolded_locked == []

    def test_the_replay_waits_for_the_queue_to_empty(self) -> None:
        """Not after each passage: a rerun of many would replay once per row."""
        from drivers import Catalogue

        catalog = Catalogue()
        run = Extraction(passage(), facts=ATOMIC, duplicate_cosine=0.9, catalog=catalog)
        run.queue.read_before = {1}

        run.next()
        assert catalog.unfolded_locked == [], "a passage stored, the queue not empty"
        assert run.next() is None
        assert catalog.unfolded_locked == [True]
        assert run.next() is None
        assert catalog.unfolded_locked == [True], "and not again until facts move"

    def test_a_service_with_the_gate_off_replays_nothing(self) -> None:
        """At EXTRACTION_DUPLICATE_COSINE 0 a replay gives every refusal back.

        That is `make extract-dedup`'s to decide, not a drain's.
        """
        from drivers import Catalogue

        catalog = Catalogue()
        run = Extraction(passage(), facts=ATOMIC, catalog=catalog)
        run.queue.read_before = {1}

        run.run()

        assert catalog.unfolded_locked == []


#: One rule joining two actions under one condition, as the model wrote it.
DISPUTE = (
    "If a card payment is disputed, the bank freezes the amount and informs the "
    "merchant within 3 days."
)
JOINED = {"facts": [{"sentences": [0], "statement": DISPUTE}]}
#: The two claims it joined, each repeating the subject and the condition.
SPLIT = (
    "If a card payment is disputed, the bank freezes the amount.",
    "If a card payment is disputed, the bank informs the merchant within 3 days.",
)
REPAIRED = {"facts": [{"sentences": [0], "statement": one} for one in SPLIT]}


class TestNotAtomicRepair:
    """A statement refused as not_atomic is sent back once to be split.

    The counter is right that two finite verbs are two claims, so the checker
    stays as it is. What was lost was the rule: nothing asked for the facts
    the joined statement should have been.
    """

    def test_one_repair_call_names_the_refused_statement_and_why(self) -> None:
        """Shown the sentences as the atomic call shows them, under its own version."""
        from extraction.extractors import llm

        run = Extraction(passage(DISPUTE), facts=JOINED, repair=REPAIRED)
        run.next()

        assert run.model.calls == 2
        asked = run.model.sent
        assert asked["prompt_version"] == llm.REPAIR_PROMPT_VERSION
        assert f"[0] {DISPUTE}" in asked["user"]
        assert f'"{DISPUTE}"' in asked["user"]
        assert "the statement carries 2 claims" in asked["user"]
        assert "Write every statement in English." in asked["user"]

    def test_the_repaired_facts_are_checked_and_kept_beside_the_refusal(
        self,
    ) -> None:
        """The refusal is stored as it was; the repair says which prompt wrote it."""
        from extraction.extractors import llm

        run = Extraction(passage(DISPUTE), facts=JOINED, repair=REPAIRED)
        run.next()

        refused, *repaired = run.queue.stored[1]
        assert refused.rejection_code == Rejection.NOT_ATOMIC
        assert refused.prompt_version == llm.PROMPT_VERSION
        assert tuple(one.statement for one in repaired) == SPLIT
        assert all(one.validated for one in repaired)
        assert {one.prompt_version for one in repaired} == {llm.REPAIR_PROMPT_VERSION}
        assert {one.extraction_method for one in repaired} == {"llm"}

    @pytest.mark.parametrize(
        "answer",
        [
            ATOMIC,
            {"facts": [{"sentences": [0], "statement": "The device weighs 9 kg."}]},
        ],
        ids=["validated", "refused for another reason"],
    )
    def test_no_not_atomic_refusal_means_no_repair_call(self, answer) -> None:
        """A passage the model read into single claims costs one call."""
        run = Extraction(passage(), facts=answer, repair=REPAIRED)
        run.next()

        assert run.model.calls == 1
        assert len(run.queue.stored[1]) == 1

    #: A shop's return rule, joined, and joined again in other words.
    RETURN = (
        "Wenn der Kunde die Ware zurückschickt, erstattet der Shop den Kaufpreis "
        "und trägt die Versandkosten."
    )
    RETURN_AGAIN = (
        "Bei einer Rücksendung der Ware erstattet der Shop den Kaufpreis und "
        "übernimmt die Versandkosten."
    )
    DISPUTE_AGAIN = (
        "When a card payment is disputed, the bank freezes the amount and then "
        "informs the merchant within 3 days."
    )

    @pytest.mark.parametrize(
        ("text", "language", "rejoined"),
        [(DISPUTE, "en", DISPUTE_AGAIN), (RETURN, "de", RETURN_AGAIN)],
        ids=["bank, English", "shop, German"],
    )
    def test_a_repair_still_two_claims_is_refused_again(
        self, text: str, language: str, rejoined: str
    ) -> None:
        """The checker is unchanged, and a repair is not itself repaired."""
        from extraction.extractors import llm

        run = Extraction(
            passage(text, language=language),
            facts={"facts": [{"sentences": [0], "statement": text}]},
            repair={"facts": [{"sentences": [0], "statement": rejoined}]},
        )
        run.next()

        assert run.model.calls == 2, "one repair call, and none for its refusal"
        refused, again = run.queue.stored[1]
        assert refused.rejection_code == Rejection.NOT_ATOMIC
        assert again.rejection_code == Rejection.NOT_ATOMIC
        assert again.prompt_version == llm.REPAIR_PROMPT_VERSION

    def test_a_failed_repair_call_leaves_the_passage_as_it_was_read(self) -> None:
        """The refusal and the rest are stored, and the passage is not failed."""
        kept = {"sentences": [0], "statement": SPLIT[0]}
        run = Extraction(
            passage(DISPUTE),
            facts={"facts": [kept, *JOINED["facts"]]},
            repair=ModelUnavailable("Timeout: took too long"),
        )
        run.next()

        assert run.model.calls == 2
        assert run.queue.failed == {}
        assert [(one.statement, one.rejection_code) for one in run.queue.stored[1]] == [
            (SPLIT[0], None),
            (DISPUTE, Rejection.NOT_ATOMIC),
        ]

    @pytest.mark.parametrize(
        ("joined", "language", "split"),
        [
            pytest.param(DISPUTE, "en", SPLIT, id="bank, English"),
            pytest.param(
                "Wenn eine Kartenzahlung angefochten wird, sperrt die Bank den "
                "Betrag und informiert den H\u00e4ndler innerhalb von 3 Tagen.",
                "de",
                (
                    (
                        "Wenn eine Kartenzahlung angefochten wird, sperrt die Bank den "
                        "Betrag."
                    ),
                    (
                        "Wenn eine Kartenzahlung angefochten wird, informiert die Bank "
                        "den H\u00e4ndler innerhalb von 3 Tagen."
                    ),
                ),
                id="bank, German",
            ),
            pytest.param(
                "When a customer returns the goods, the shop refunds the price "
                "and pays the shipping costs.",
                "en",
                (
                    "When a customer returns the goods, the shop refunds the price.",
                    (
                        "When a customer returns the goods, the shop pays the shipping "
                        "costs."
                    ),
                ),
                id="shop, English",
            ),
            pytest.param(
                "Wenn der Kunde die Ware zur\u00fcckschickt, erstattet der Shop "
                "den Kaufpreis und tr\u00e4gt die Versandkosten.",
                "de",
                (
                    (
                        "Wenn der Kunde die Ware zur\u00fcckschickt, erstattet der Shop "
                        "den Kaufpreis."
                    ),
                    (
                        "Wenn der Kunde die Ware zur\u00fcckschickt, tr\u00e4gt der Shop "
                        "die Versandkosten."
                    ),
                ),
                id="shop, German",
            ),
        ],
    )
    def test_a_split_claim_keeps_every_piece_under_the_cap_its_statement_fitted(
        self, joined: str, language: str, split: tuple[str, ...]
    ) -> None:
        """The room counted the sentence once; its pieces stand in for it."""
        run = Extraction(
            passage(joined, language=language),
            facts={"facts": [{"sentences": [0], "statement": joined}]},
            repair={"facts": [{"sentences": [0], "statement": one} for one in split]},
            atomic_cap=1,
        )
        run.next()

        refused, *pieces = run.queue.stored[1]
        assert refused.rejection_code == Rejection.NOT_ATOMIC
        assert tuple(one.statement for one in pieces) == split
        assert all(one.validated for one in pieces), [
            (one.statement, one.rejection_code) for one in pieces
        ]


def _digest_down(cause: Exception) -> ModelUnavailable:
    """What the digest client raises for a failure of this kind."""
    failure = ModelUnavailable(type(cause).__name__)
    failure.__cause__ = cause
    return failure


def _litellm_timeout() -> Exception:
    """A provider that does not answer in time."""
    import litellm

    return litellm.exceptions.Timeout(
        "timed out", model="azure/x", llm_provider="azure"
    )


def _litellm_rejected() -> Exception:
    """A provider that rejects this passage's request."""
    import litellm

    return litellm.exceptions.BadRequestError(
        "context_length_exceeded", model="azure/x", llm_provider="azure"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_digest_model_that_is_down_is_asked_no_more_after_five_passages(
    language: str,
) -> None:
    """The atomic extraction goes on, and each passage is noted."""
    from dataclasses import replace

    from stages.service import STOP_AFTER

    first = passage(LANGUAGES[language], language=language)
    rows = [replace(first, id=n) for n in range(1, 13)]
    run = Extraction(
        *rows,
        facts=ATOMIC,
        digest=_digest_down(_litellm_timeout()),
        kinds=BOTH,
    )

    assert run.run() == 12
    assert run.digest_model.calls == STOP_AFTER, "no sixth call to a model that is down"
    assert run.model.calls == 12, "every passage is still read for its facts"
    assert sorted(run.queue.stored) == list(range(1, 13))
    assert all(run.queue.notes[n].startswith("digest failed: ") for n in range(1, 13))
    assert run.service.stalled is None, "the drain itself goes on"
    assert run.queue.failed == {}


def test_a_digest_the_provider_rejects_for_one_passage_is_not_an_outage() -> None:
    """The next passage is asked as before."""
    from dataclasses import replace

    first = passage()
    run = Extraction(
        *[replace(first, id=n) for n in range(1, 13)],
        facts=ATOMIC,
        digest=_digest_down(_litellm_rejected()),
        kinds=BOTH,
    )

    run.run()

    assert run.digest_model.calls == 12


def test_a_new_drain_asks_the_digest_model_again() -> None:
    """The stop is for the rest of one run."""
    from dataclasses import replace

    first = passage()
    run = Extraction(
        *[replace(first, id=n) for n in range(1, 8)],
        facts=ATOMIC,
        digest=_digest_down(_litellm_timeout()),
        kinds=BOTH,
    )
    run.run()
    run.queue._pending.append(replace(first, id=20))

    run.run()

    assert run.digest_model.calls == 6
