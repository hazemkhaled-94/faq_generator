"""Prediction-powered inference, against values worked out by hand first.

The fixtures are small enough to follow on paper: the judged rows and the
labelled rows with their labels, then the estimate, the weight and the
interval. Each was also reproduced from Algorithm 1 of the paper.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from scipy.stats import norm, t

from assessment.ppi import MIN_LABELS, Corrected, _at, corrected_mean, pooled

Z = norm.ppf(0.975)
APPROX = {"abs": 1e-6}


def wilson(share: float, n: int) -> tuple[float, float]:
    """The Wilson score interval, from its closed form."""
    centre = (share + Z**2 / (2 * n)) / (1 + Z**2 / n)
    half = Z * math.sqrt(share * (1 - share) / n + Z**2 / (4 * n**2)) / (1 + Z**2 / n)
    return centre - half, centre + half


#: A judge saying yes on six of eight, agreeing with two of four labels.
F1 = ([1, 1, 0, 1, 1, 0, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1])
#: A judge scoring on a 1-to-3 scale.
F2 = ([3, 2.5, 3, 1.5, 2, 3, 2.5, 1], [3, 2, 2.5, 1.5], [1, 1, 1, 0])


def test_the_weight_at_one_is_algorithm_one() -> None:
    """At weight 1 the method is the paper's Algorithm 1.

    The error takes the sample variance: 1.5 over 7 for the eight judged
    rows, and 0.75 over 3 for the four residuals.
    """
    result = _at(1, *F1)
    assert result.estimate == pytest.approx(0.5, **APPROX)
    assert result.se == pytest.approx(math.sqrt(1.5 / 7 / 8 + 0.75 / 3 / 4), **APPROX)


def test_a_real_valued_judge_at_one() -> None:
    """A judge scoring on a scale, not yes or no, is read the same way."""
    result = _at(1, *F2)
    assert result.estimate == pytest.approx(0.8125, **APPROX)
    assert result.label_mean == pytest.approx(0.75, **APPROX)


def test_the_weight_is_tuned() -> None:
    """The tuned weight is the covariance over the scaled variance."""
    result = corrected_mean(*F1)
    assert result.weight == pytest.approx(0.407407, **APPROX)
    assert result.estimate == pytest.approx(0.5, **APPROX)
    assert (result.labelled, result.judged) == (4, 8)


def test_the_judges_scale_does_not_matter() -> None:
    """Rescaling the predictions moves the weight, not the result."""
    plain = corrected_mean(*F2)
    judged, labelled, labels = F2
    rescaled = corrected_mean(
        [(f - 1) / 2 for f in judged], [(f - 1) / 2 for f in labelled], labels
    )
    assert plain.weight == pytest.approx(0.262948, **APPROX)
    assert rescaled.weight == pytest.approx(0.525896, **APPROX)
    for result in (plain, rescaled):
        assert result.estimate == pytest.approx(0.766434, **APPROX)
    assert plain.se == pytest.approx(rescaled.se, **APPROX)


def test_a_judge_predicting_the_opposite_gets_a_negative_weight() -> None:
    """A judge that says the reverse of every label is read backwards."""
    result = corrected_mean([1, 0, 1, 0], [1, 1, 0, 0, 1, 0], [0, 0, 1, 1, 0, 1])
    assert result.weight == pytest.approx(-0.36, **APPROX)
    assert result.estimate == pytest.approx(0.5, **APPROX)


def test_a_constant_judge_falls_back_to_the_labels() -> None:
    """With nothing to learn from the judge the labels' mean stands alone."""
    result = corrected_mean([1, 1, 1], [1, 1, 1, 1], [1, 0, 1, 1])
    assert result.weight == 0
    assert result.estimate == pytest.approx(0.75, **APPROX)
    assert result.se == pytest.approx(math.sqrt(0.25 / 4), **APPROX)


def test_strata_are_pooled_by_their_size() -> None:
    """Strata combine by their rows: 40 and 60 of 100."""
    a = Corrected(0.5, 0.02, math.nan, 20, 20, 0.5)
    b = Corrected(0.8, 0.01, math.nan, 20, 40, 0.8)
    result = pooled([a, b])
    assert result.estimate == pytest.approx(0.68, **APPROX)
    assert result.se == pytest.approx(0.01, **APPROX)
    assert (result.labelled, result.judged) == (40, 60)
    assert math.isnan(result.weight)
    half = t.ppf(0.975, 40 - 2) * 0.01
    assert result.interval() == pytest.approx((0.68 - half, 0.68 + half), **APPROX)


def test_nothing_is_pooled_from_no_strata() -> None:
    """Pooling no strata is refused rather than dividing by zero."""
    with pytest.raises(ValueError):
        pooled([])


def test_too_few_labels_are_refused() -> None:
    """One label has no variance to estimate from."""
    with pytest.raises(ValueError, match="labelled"):
        corrected_mean([1, 0], [1], [1])


def test_no_judged_rows_read_the_labels_alone() -> None:
    """Every row labelled: the labels' mean and its classical error, no weight."""
    result = corrected_mean([], [1, 0, 1, 1], [1, 0, 1, 1])
    assert result.estimate == pytest.approx(0.75, **APPROX)
    assert result.se == pytest.approx(math.sqrt(0.25 / 4), **APPROX)
    assert (result.weight, result.labelled, result.judged) == (0.0, 4, 0)


def test_mismatched_lengths_are_refused() -> None:
    """Every labelled prediction needs its label."""
    with pytest.raises(ValueError, match="same length"):
        corrected_mean([1, 0], [1, 0, 1], [1, 0])


bits = st.lists(st.integers(0, 1), min_size=2, max_size=30)


@given(
    constant=st.integers(-3, 3),
    judged=st.integers(1, 30),
    labels=bits,
)
def test_a_judge_that_never_varies_gives_the_classical_interval(
    constant: int, judged: int, labels: list[int]
) -> None:
    """A constant judge leaves the labels' mean and its own error and interval."""
    result = corrected_mean([constant] * judged, [constant] * len(labels), labels)
    y = np.asarray(labels, float)
    assert result.estimate == pytest.approx(y.mean(), abs=1e-9)
    assert result.se == pytest.approx(math.sqrt(np.var(y, ddof=1) / len(y)), abs=1e-9)
    assert result.interval() == pytest.approx(wilson(y.mean(), len(y)), abs=1e-9)


@given(
    judged=st.lists(st.integers(0, 4), min_size=2, max_size=20),
    pairs=st.lists(
        st.tuples(st.integers(0, 4), st.integers(0, 1)), min_size=2, max_size=20
    ),
    a=st.sampled_from([0.5, 1.5, 2, 3]),
    b=st.integers(-3, 3),
)
def test_an_affine_rescaling_of_the_judge_changes_nothing(
    judged: list[int], pairs: list[tuple[int, int]], a: float, b: int
) -> None:
    """Scaling and shifting every prediction leaves the result where the weight is not clipped."""
    labelled = [f for f, _ in pairs]
    labels = [y for _, y in pairs]
    plain = corrected_mean(judged, labelled, labels)
    scaled = corrected_mean(
        [a * f + b for f in judged], [a * f + b for f in labelled], labels
    )
    # the clip at [-1, 1] is the one place a rescaling can show
    assume(abs(plain.weight) < 1 and abs(scaled.weight) < 1)
    assert scaled.estimate == pytest.approx(plain.estimate, abs=1e-6)
    assert scaled.interval() == pytest.approx(plain.interval(), abs=1e-6)


def test_under_the_floor_the_interval_is_the_labels_own_by_wilson() -> None:
    """Two of four: the corrected interval is not printed, Wilson's is."""
    result = corrected_mean(*F1)

    assert result.rough
    assert result.interval() == pytest.approx(wilson(0.5, 4), **APPROX)
    assert result.interval() == pytest.approx((0.15, 0.85), abs=1e-3)
    assert result.labels_interval() == result.interval()


def test_from_the_floor_on_the_interval_takes_a_t_quantile() -> None:
    """Thirty labels: the estimate plus and minus t on 29 degrees of freedom.

    Not widened to the labels' own interval, which is wider below the
    estimate here: the correction is what the interval rests on, and the
    labels-only width is printed beside it.
    """
    labels = [1, 0, 1, 1, 0, 1] * 5
    judged = [1, 1, 0, 1] * 10
    result = corrected_mean(judged, [1, 1, 0, 1, 0, 1] * 5, labels)

    assert len(labels) == MIN_LABELS
    assert not result.rough
    half = t.ppf(0.975, MIN_LABELS - 1) * result.se
    low, high = wilson(result.label_mean, MIN_LABELS)
    assert low < result.estimate - half
    assert result.interval() == pytest.approx(
        (result.estimate - half, result.estimate + half), **APPROX
    )
    assert result.labels_interval() == pytest.approx((low, high), **APPROX)


def test_labels_that_all_agree_get_the_rule_of_three() -> None:
    """No spread and enough labels: three over the labels each side of the share."""
    result = corrected_mean([1] * 20, [1] * 40, [1] * 40)

    assert result.se == 0
    assert result.interval() == pytest.approx((1 - 3 / 40, 1 + 3 / 40), **APPROX)


def _judged(rng: np.random.Generator, share: float, rows: int) -> tuple:
    """Rows of one model: a true share, and a judge right on 60% of them.

    Where it is not right it says yes at 0.76 whatever the row is. The
    labelled rows and the judged ones are drawn alike, as PPI requires of a
    random sample of the judged rows.
    """
    truth = (rng.random(rows) < share).astype(float)
    said = np.where(
        rng.random(rows) < 0.6, truth, (rng.random(rows) < 0.76).astype(float)
    )
    return truth, said


@pytest.mark.parametrize("labelled", [5, 10, 17, 25, 29, 30, 31, 40, 60, 100])
def test_the_interval_covers_the_true_share_whatever_the_number_of_labels(
    labelled: int,
) -> None:
    """Seeded: shares from 0.5 to 0.95, a judge that agrees with 60% of the labels.

    Averaged over the shares, as a deployment's groups are a mix of them. The
    corrected Wald interval covered about 0.70 at 17 labels.
    """
    rng = np.random.default_rng(labelled)
    shares = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    reps = 300
    covered = 0
    for share in shares:
        for _ in range(reps):
            y, predicted = _judged(rng, share, labelled)
            _, judged = _judged(rng, share, 100)
            low, high = corrected_mean(judged, predicted, y).interval()
            covered += low <= share <= high

    assert covered / (len(shares) * reps) >= 0.93


def test_strata_are_pooled_by_their_population_when_it_is_given() -> None:
    """100 judged each, but 900 and 100 rows in the workbook: weighted 0.9 and 0.1."""
    de = Corrected(0.9, 0.05, math.nan, 20, 80, 0.9)
    en = Corrected(0.5, 0.05, math.nan, 20, 80, 0.5)

    by_judged = pooled([de, en])
    by_rows = pooled([de, en], [900, 100])

    assert by_judged.estimate == pytest.approx(0.7, **APPROX)
    assert by_rows.estimate == pytest.approx(0.86, **APPROX)
    assert by_rows.se == pytest.approx(math.sqrt(0.9**2 * 0.05**2 + 0.1**2 * 0.05**2))


def test_a_size_for_every_stratum_or_none() -> None:
    """A list of the wrong length is refused rather than zipped short."""
    part = Corrected(0.5, 0.1, math.nan, 20, 80, 0.5)

    with pytest.raises(ValueError, match="size"):
        pooled([part, part], [10])
