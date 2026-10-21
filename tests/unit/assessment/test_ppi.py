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
from scipy.stats import norm

from assessment.ppi import Corrected, _at, corrected_mean, pooled

Z = norm.ppf(0.975)
APPROX = {"abs": 1e-6}

#: A judge saying yes on six of eight, agreeing with two of four labels.
F1 = ([1, 1, 0, 1, 1, 0, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1])
#: A judge scoring on a 1-to-3 scale.
F2 = ([3, 2.5, 3, 1.5, 2, 3, 2.5, 1], [3, 2, 2.5, 1.5], [1, 1, 1, 0])


def test_the_weight_at_one_is_algorithm_one() -> None:
    """At weight 1 the method is the paper's Algorithm 1."""
    result = _at(1, *F1)
    assert result.estimate == pytest.approx(0.5, **APPROX)
    assert result.interval() == pytest.approx((-0.019714, 1.019714), **APPROX)


def test_a_real_valued_judge_at_one() -> None:
    """A judge scoring on a scale, not yes or no, is read the same way."""
    result = _at(1, *F2)
    assert result.estimate == pytest.approx(0.8125, **APPROX)
    assert result.interval() == pytest.approx((0.213951, 1.411049), **APPROX)


def test_the_weight_is_tuned() -> None:
    """The tuned weight is the covariance over the scaled variance."""
    result = corrected_mean(*F1)
    assert result.weight == pytest.approx(0.407407, **APPROX)
    assert result.estimate == pytest.approx(0.5, **APPROX)
    assert result.interval() == pytest.approx((0.067440, 0.932560), **APPROX)
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
        assert result.interval() == pytest.approx((0.416303, 1.116566), **APPROX)


def test_a_judge_predicting_the_opposite_gets_a_negative_weight() -> None:
    """A judge that says the reverse of every label is read backwards."""
    result = corrected_mean([1, 0, 1, 0], [1, 1, 0, 0, 1, 0], [0, 0, 1, 1, 0, 1])
    assert result.weight == pytest.approx(-0.36, **APPROX)
    assert result.estimate == pytest.approx(0.5, **APPROX)
    assert result.interval() == pytest.approx((0.189071, 0.810929), **APPROX)


def test_a_constant_judge_falls_back_to_the_labels() -> None:
    """With nothing to learn from the judge the labels' mean stands alone."""
    result = corrected_mean([1, 1, 1], [1, 1, 1, 1], [1, 0, 1, 1])
    assert result.weight == 0
    assert result.estimate == pytest.approx(0.75, **APPROX)
    assert result.se == pytest.approx(math.sqrt(0.1875 / 4), **APPROX)


def test_strata_are_pooled_by_their_size() -> None:
    """Strata combine by their rows: 40 and 60 of 100."""
    a = Corrected(0.5, 0.2 / Z, math.nan, 10, 30)
    b = Corrected(0.8, 0.1 / Z, math.nan, 10, 50)
    result = pooled([a, b])
    assert result.estimate == pytest.approx(0.68, **APPROX)
    assert result.interval() == pytest.approx((0.58, 0.78), **APPROX)
    assert (result.labelled, result.judged) == (20, 80)
    assert math.isnan(result.weight)


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
    assert result.se == pytest.approx(math.sqrt(0.1875 / 4), **APPROX)
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
    """A constant judge leaves the labels' mean and its normal interval."""
    result = corrected_mean([constant] * judged, [constant] * len(labels), labels)
    y = np.asarray(labels, float)
    half = Z * math.sqrt(np.var(y) / len(y))
    assert result.estimate == pytest.approx(y.mean(), abs=1e-9)
    assert result.interval() == pytest.approx(
        (y.mean() - half, y.mean() + half), abs=1e-9
    )


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
