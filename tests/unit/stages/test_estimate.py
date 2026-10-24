"""`make estimate`: what the queued rows will take, from the rates a build measured.

The rates are the reviewed build's own (30 documents, 1,973 passages, 41
topics: 5 h 41 min and USD 75.53), so an estimate for that corpus has to give
its actuals back, and one for a corpus ten times larger multiplies them.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from stages import estimate

#: The build's stage times in minutes and spend in USD, from its log.
ACTUALS = {
    "parse": (3.3, 0.0),
    "chunk": (1.3, 0.0),
    "extract": (121.2, 13.11),
    "topics": (1.1, 0.04),
    "bridges": (12.0, 2.14),
    "questions": (167.1, 55.17),
    "release": (11.7, 1.47),
    "assess": (23.2, 3.59),
}

#: Its corpus: what is still to be done before anything has run.
BUILD = estimate.Rows(
    documents=30, passages=1_973, topics=41, accepted=2_175, corpus=1_973
)


def _by_stage(lines):
    return {line.stage: line for line in lines}


def test_the_estimate_for_the_reviewed_build_is_within_a_fifth_of_its_actuals() -> None:
    """Time and spend, every stage, at the two drains the build ran questions with."""
    got = _by_stage(estimate.estimate(BUILD, drains={"questions": 2}))

    for stage, (minutes, usd) in ACTUALS.items():
        line = got[stage]
        assert line.seconds / 60 == pytest.approx(minutes, rel=0.2), stage
        assert line.usd == pytest.approx(usd, rel=0.2, abs=0.01), stage


def test_the_total_is_the_sum_of_the_stages() -> None:
    """Hours and dollars for the lot, as the runner counts a build."""
    lines = estimate.estimate(BUILD, drains={"questions": 2})

    assert sum(line.usd for line in lines) == pytest.approx(75.53, rel=0.2)
    assert sum(line.seconds for line in lines) / 3600 == pytest.approx(5.7, rel=0.2)


def test_a_corpus_ten_times_the_size_costs_ten_times_in_the_stages_that_follow_it() -> (
    None
):
    """Extraction is one passage at a time: 20,000 passages are about 20 hours and USD 131."""
    ten = estimate.Rows(
        documents=300, passages=19_730, topics=410, accepted=21_750, corpus=19_730
    )

    got = _by_stage(estimate.estimate(ten))

    assert got["extract"].seconds / 3600 == pytest.approx(20, rel=0.1)
    assert got["extract"].usd == pytest.approx(131, rel=0.1)
    assert got["questions"].usd == pytest.approx(
        10 * _by_stage(estimate.estimate(BUILD))["questions"].usd
    )


def test_drains_divide_the_time_and_not_the_spend() -> None:
    """Two drains of one queue take half as long and cost the same."""
    one = _by_stage(estimate.estimate(BUILD, drains={"questions": 1}))
    two = _by_stage(estimate.estimate(BUILD, drains={"questions": 2}))

    assert two["questions"].seconds == pytest.approx(one["questions"].seconds / 2)
    assert two["questions"].usd == one["questions"].usd
    assert two["parse"].seconds == one["parse"].seconds, "a stage not named"
    assert two["bridges"].seconds == one["bridges"].seconds, "a stage with one worker"


def test_a_stage_with_nothing_queued_costs_nothing() -> None:
    """Rows done are not done again."""
    got = _by_stage(estimate.estimate(estimate.Rows(0, 0, 0, 0)))

    assert all(line.usd == 0 and line.seconds == 0 for line in got.values())


def test_the_table_names_every_stage_and_its_total(capsys) -> None:
    """What `make estimate` prints."""
    estimate.report(estimate.estimate(BUILD, drains={"questions": 2}))

    printed = capsys.readouterr().out
    for stage in ACTUALS:
        assert stage in printed
    assert "total" in printed


def test_rows_a_stage_has_not_reached_are_projected_from_the_ones_before() -> None:
    """Before chunking there are no passages: documents stand in, at the build's ratio."""
    projected = estimate.projected(documents=30, passages=0, topics=0, accepted=0)

    assert projected.passages == pytest.approx(1_973, rel=0.05)
    assert projected.topics == pytest.approx(41, rel=0.1)
    assert projected.accepted == pytest.approx(2_175, rel=0.1)
    assert estimate.projected(30, 1_973, 41, 2_175) == BUILD


def _later_stages(rows: estimate.Rows) -> dict[str, estimate.Line]:
    return _by_stage(estimate.estimate(estimate.projected(**asdict(rows))))


@pytest.mark.parametrize("passages", [0, 987])
def test_the_stages_after_extraction_are_projected_from_the_corpus(passages) -> None:
    """Extracted or half extracted, but not fitted: the topics are the corpus's, not the remainder's."""
    got = _later_stages(estimate.Rows(0, passages, 0, 0, corpus=1_973, fitted=False))
    whole = _by_stage(estimate.estimate(BUILD))

    assert got["extract"].rows == passages
    assert got["topics"].rows == 1_973
    for stage in ("bridges", "questions", "release", "assess"):
        assert got[stage].usd == pytest.approx(whole[stage].usd, rel=0.1), stage
    assert got["questions"].rows == pytest.approx(41, rel=0.1)


def test_a_corpus_that_is_extracted_and_fitted_and_finished_costs_nothing() -> None:
    """The topics count 0 because they are done, not because none were fitted."""
    got = _later_stages(estimate.Rows(0, 0, 0, 0, corpus=1_973, fitted=True))

    assert all(line.usd == 0 and line.seconds == 0 for line in got.values())


def test_a_fitted_corpus_keeps_the_topics_still_to_question() -> None:
    """The fit is done: only the topics left are asked about."""
    got = _later_stages(estimate.Rows(0, 0, 10, 0, corpus=1_973, fitted=True))

    assert got["topics"].rows == 0
    assert got["questions"].rows == 10
