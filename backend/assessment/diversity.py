"""How varied a set of questions is, measured the way the DataMorgana paper does.

Filice et al. (ACL 2025 Industry Track, Appendix E) measure a benchmark's
diversity after Shaib et al. (2024): n-gram diversity, self-repetition and
compression ratio for its words, compression ratio again for its
part-of-speech tags, and the mean pairwise cosine of its embeddings. Each
function here takes the whole set, because none of them is an average of
per-question scores: that is also why a set is only ever compared with
another of the same size and language.

Pure functions: the tags and the vectors a caller passes in come from
elsewhere.
"""

from __future__ import annotations

import gzip
import warnings
from collections import Counter
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

#: The paper's bootstrap: 50 draws, each of 80% of the set, without
#: replacement, because drawing a question twice would read as repetition.
DRAWS = 50
SHARE = 0.8
#: Below this, two sets' scores differ significantly.
ALPHA = 0.05


def _words(texts: Sequence[str]) -> list[str]:
    """The set's words, the questions joined end to end.

    Split on whitespace with case and punctuation kept, as Shaib et al.'s
    reference code does, so "card?" and "card" are two words.
    """
    words = " ".join(texts).split()
    if not words:
        raise ValueError("a set with no words has no diversity")
    return words


def _grams(words: Sequence[str], n: int) -> list[tuple[str, ...]]:
    """Every run of n consecutive words."""
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


def ngram_diversity(texts: Sequence[str], max_n: int = 4) -> float:
    """Distinct n-grams over all n-grams, summed for n = 1 to `max_n`; higher is more varied.

    The n-grams run across question boundaries, because the set is read as
    one text. A size with no n-gram at all adds nothing.
    """
    words = _words(texts)
    total = 0.0
    for n in range(1, max_n + 1):
        grams = _grams(words, n)
        if grams:
            total += len(set(grams)) / len(grams)
    return total


def self_repetition(texts: Sequence[str], n: int = 4) -> float:
    """The share of questions with an n-gram some other question also has; lower is more varied.

    The paper's definition, a fraction. Shaib et al.'s package computes a
    log-scaled count under the same name, which is not this.
    """
    _words(texts)
    grams = [set(_grams(text.split(), n)) for text in texts]
    # How many questions hold each n-gram, each question counted once.
    held = Counter(gram for own in grams for gram in own)
    return sum(any(held[gram] > 1 for gram in own) for own in grams) / len(texts)


def compression_ratio(texts: Sequence[str]) -> float:
    """The joined text's size over its gzip size; lower is more varied.

    On the questions this is the paper's word-CR; on their tag sequences it
    is PoS-CR. One gzip at level 9.
    """
    raw = " ".join(_words(texts)).encode("utf-8")
    return len(raw) / len(gzip.compress(raw, compresslevel=9, mtime=0))


def homogenization(vectors: ArrayLike) -> float:
    """The mean cosine over every ordered pair of distinct questions; lower is more varied.

    The paper's HS. With unit rows u, the pairs sum to |sum(u)|^2 - n, so
    the mean needs no loop over the n(n - 1) pairs. The scale belongs to
    the model the vectors came from: compare two sets only through one model.
    """
    rows = np.asarray(vectors, dtype=float)
    n = len(rows)
    if n < 2:
        raise ValueError("homogenization needs at least two questions")
    unit = rows / np.linalg.norm(rows, axis=1, keepdims=True)
    total = unit.sum(axis=0)
    return float((total @ total - n) / (n * (n - 1)))


def subsamples(
    n: int, size: int, draws: int = DRAWS, seed: int = 0
) -> list[np.ndarray]:
    """`draws` sets of `size` distinct places out of n, the same for the same seed.

    Every metric is computed over the same draws, so a set's five scores
    describe the same questions. Order the questions by id before indexing
    them, or the database's order decides what is drawn.
    """
    rng = np.random.default_rng(seed)
    return [rng.choice(n, size, replace=False) for _ in range(draws)]


def p_value(a: Sequence[float], b: Sequence[float]) -> float:
    """How likely two lists of bootstrap scores are if their means do not differ.

    Welch's t-test, since one set's scores can spread far less than
    another's. The draws overlap, so the value is optimistic, as it is in
    the paper. NaN where neither list varies: equal constants are no
    evidence either way.
    """
    # Imported here: only a comparison of two sets needs scipy.
    from scipy.stats import ttest_ind

    # scipy warns, and then answers NaN, when neither list varies.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        result = ttest_ind(a, b, equal_var=False)
    # scipy's stubs leave `pvalue` off the result its runtime returns.
    return float(result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]
