"""How far a judged share can be trusted, by prediction-powered inference.

A judge can score every question, but only a few have a reviewer's label.
Prediction-powered inference takes the mean of the judge's predictions on
the many and corrects it by how far the judge is from the labels on the
few, which keeps the estimate unbiased and gives it a confidence interval.
The weight on the judge's predictions is tuned as PPI++ does, so a judge
that agrees poorly with the labels falls back towards the labels' own mean
instead of widening the interval, as the unweighted method would.

References:
- Jon Saad-Falcon, Omar Khattab, Christopher Potts and Matei Zaharia. 2024.
  `ARES: An Automated Evaluation Framework for Retrieval-Augmented
  Generation Systems <https://aclanthology.org/2024.naacl-long.20/>`_.
  In Proceedings of the 2024 Conference of the North American Chapter of the
  Association for Computational Linguistics: Human Language Technologies
  (Volume 1: Long Papers), pages 338-354, Mexico City, Mexico. Association
  for Computational Linguistics. doi:10.18653/v1/2024.naacl-long.20.
- Anastasios N. Angelopoulos, Stephen Bates, Clara Fannjiang, Michael I.
  Jordan and Tijana Zrnic. 2023. `Prediction-powered inference
  <https://doi.org/10.1126/science.adi6000>`_. Science 382(6671):669-674.
  doi:10.1126/science.adi6000. Preprint arXiv:2301.09633.
- Anastasios N. Angelopoulos, John C. Duchi and Tijana Zrnic. 2023.
  `PPI++: Efficient Prediction-Powered Inference
  <https://arxiv.org/abs/2311.01453>`_. arXiv:2311.01453.

Valid only if the labelled rows are a random sample of the same rows the
judge scored, and the judge was fixed before the labels were read. The
guarantee is asymptotic, so an interval on a few dozen labels is rough, and
one interval covers the share, not any single row.

Pure functions over numbers: the predictions and the labels come from
elsewhere.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike
from scipy.stats import norm

#: The confidence level's complement: a 95% interval.
ALPHA = 0.05


class Corrected(NamedTuple):
    """A corrected share with what it rests on."""

    estimate: float
    se: float
    #: The weight on the judge's predictions; NaN for a pooled result.
    weight: float
    #: The rows with a label.
    labelled: int
    #: The judged rows without one.
    judged: int

    def interval(self, alpha: float = ALPHA) -> tuple[float, float]:
        """The estimate plus and minus its normal quantile times its error.

        Not clipped to [0, 1]: a caller that shows a share clips it there.
        """
        half = float(norm.ppf(1 - alpha / 2)) * self.se
        return self.estimate - half, self.estimate + half


def _arrays(
    judged: ArrayLike, labelled: ArrayLike, labels: ArrayLike
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The three as float arrays, refusing what no estimate can be made of."""
    f_judged, f_labelled, y = (np.asarray(a, float) for a in (judged, labelled, labels))
    if len(f_labelled) != len(y):
        raise ValueError("labelled and labels must be the same length")
    if len(f_labelled) < 2:
        raise ValueError("at least two labelled rows are needed")
    return f_judged, f_labelled, y


def _at(
    weight: float, judged: ArrayLike, labelled: ArrayLike, labels: ArrayLike
) -> Corrected:
    """The estimate and its error at a given weight on the predictions.

    With no judged row the judge's term is empty and only weight 0 makes
    sense: the labels' own mean.
    """
    f_judged, f_labelled, y = _arrays(judged, labelled, labels)
    rectifier = y - weight * f_labelled
    imputed = weight * f_judged
    return Corrected(
        estimate=float(
            (np.mean(imputed) if len(imputed) else 0.0) + np.mean(rectifier)
        ),
        se=math.sqrt(
            (np.var(imputed) / len(imputed) if len(imputed) else 0.0)
            + np.var(rectifier) / len(rectifier)
        ),
        weight=float(weight),
        labelled=len(y),
        judged=len(f_judged),
    )


def corrected_mean(
    judged: ArrayLike, labelled: ArrayLike, labels: ArrayLike
) -> Corrected:
    """The mean of the labels' scale, estimated from a judge and a few labels.

    `judged` is the judge's prediction on the rows without a label;
    `labelled` and `labels` are its prediction and the label on the rows
    with one, in the same order. The weight is the one that minimises the
    variance (PPI++), clipped to [-1, 1]: negative because a label whose
    good side is "no" is predicted by the judge's refusal. Any fixed weight
    keeps the estimate unbiased. It is 0 where the judge never varies, and
    where every row is labelled, which leaves the labels' own mean.
    """
    f_judged, f_labelled, y = _arrays(judged, labelled, labels)
    n, big_n = len(y), len(f_judged)
    variance = np.var(np.concatenate([f_labelled, f_judged]), ddof=1)
    if big_n == 0 or variance == 0:
        return _at(0, f_judged, f_labelled, y)
    covariance = np.mean((y - y.mean()) * (f_labelled - f_labelled.mean()))
    weight = np.clip(covariance / ((1 + n / big_n) * variance), -1, 1)
    return _at(float(weight), f_judged, f_labelled, y)


def pooled(parts: Sequence[Corrected]) -> Corrected:
    """Strata estimated apart, combined by their size.

    The weights are each stratum's rows, labelled and judged, over all the
    rows, so a stratum labelled evenly with the others still counts as big
    as it is.
    """
    if not parts:
        raise ValueError("nothing to pool")
    sizes = np.array([p.labelled + p.judged for p in parts], float)
    share = sizes / sizes.sum()
    return Corrected(
        estimate=float(np.sum(share * [p.estimate for p in parts])),
        se=math.sqrt(float(np.sum(share**2 * [p.se**2 for p in parts]))),
        weight=math.nan,
        labelled=sum(p.labelled for p in parts),
        judged=sum(p.judged for p in parts),
    )
