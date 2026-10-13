"""Choosing a balanced release out of everything a run accepted.

The gates decide whether a question is sound. Nothing before this decides
what the SET looks like, and the two are different problems: what survives a
filter is whatever the material happened to offer.

So the composition is chosen here instead, out of a pool deliberately larger
than the release. Four marginals are held at once - how many questions have
no answer, and how they spread over the difficulty bands, over the kinds and
over the languages - and they are marginals rather than a joint distribution
on purpose. Demanding an even spread of kinds WITHIN each band is not
reachable and not wanted: a `factoid` answers with a value, a value is short,
and a short answer cannot earn the length point that a `hard` question
generally needs. Asking for both marginals is achievable; asking for their
product is asking the corpus to be something it is not.

Nothing is deleted and nothing is rewritten. A release is a column on the
rows already there, so the questions left out stay queryable and a second
run with different shares replaces the first.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Row:
    """One accepted question, as the choosing reads it."""

    id: int
    answerable: bool
    difficulty: str
    question_type: str
    #: The turn this one follows, or None for a root.
    follows_id: int | None = None
    #: The language it is written in, which a release holds a share of.
    language: str = ""


@dataclass(frozen=True)
class Quota:
    """How many of each marginal one release wants.

    `unanswerable` is a ceiling and the rest are targets. That asymmetry is
    the point of the setting: a release with too few unanswerable questions
    tests a little less than it could, and one with too many is mostly
    testing whether a chatbot can say no.
    """

    size: int
    unanswerable: int
    difficulty: dict[str, int]
    types: dict[str, int]
    #: Empty holds no share of any language.
    languages: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Release:
    """What was chosen, and what the quotas could not find."""

    ids: list[int]
    quota: Quota
    #: Bucket name to how many of it were missing, empty when all were met.
    short: dict[str, int]

    @property
    def size(self) -> int:
        """How many questions are in it."""
        return len(self.ids)


def shares(weights: Mapping[str, int], size: int) -> dict[str, int]:
    """Spreads `size` over named weights, summing to exactly `size`.

    Largest remainder: everybody gets their whole part, and the seats left
    over go to the largest fractions. Ties by name, so the same weights over
    the same size give the same answer twice.
    """
    total = sum(max(weight, 0) for weight in weights.values())
    if total <= 0 or size <= 0:
        return dict.fromkeys(weights, 0)
    exact = {name: size * max(weight, 0) / total for name, weight in weights.items()}
    whole = {name: int(value) for name, value in exact.items()}
    order = sorted(exact, key=lambda name: (whole[name] - exact[name], name))
    for name in order[: size - sum(whole.values())]:
        whole[name] += 1
    return whole


def quota_of(
    size: int,
    bands: Mapping[str, int],
    types: Mapping[str, int],
    unanswerable: float,
    languages: Mapping[str, int] | None = None,
) -> Quota:
    """The quota a release of this size wants."""
    return Quota(
        size=size,
        unanswerable=int(size * unanswerable),
        difficulty=shares(bands, size),
        types=shares(types, size),
        languages=shares(languages, size) if languages else {},
    )


def _rank(row: Row) -> str:
    """Where a question stands in the draw: a hash of its id.

    Not the id itself. Ids are creation order, so a draw in id order is a
    draw of whatever the run happened to write first - the first topics it
    claimed, in the first language it wrote. A hash is as reproducible and
    says nothing about when a row was written. The same hash the assessment
    sample is stratified by.
    """
    return hashlib.md5(str(row.id).encode()).hexdigest()


def _celled(pool: Sequence[Row]) -> dict[tuple[bool, str, str, str], list[Row]]:
    """The pool grouped by the cell a question would spend its places in.

    Each in `_rank` order, so the same pool draws the same release twice.
    """
    held: dict[tuple[bool, str, str, str], list[Row]] = {}
    for row in sorted(pool, key=_rank):
        held.setdefault(
            (row.answerable, row.difficulty, row.question_type, row.language), []
        ).append(row)
    return held


def choose(pool: Sequence[Row], quota: Quota) -> Release:
    """The questions filling this quota, and whatever it could not fill.

    Largest deficit first. A question spends a place in four buckets at
    once - answerability, band, kind and language - so at each step the cell
    taken from is the one whose band, kind and language are the furthest,
    as a SHARE of what each was asked for, from being filled. Measured as a
    share and not as a count: a band's quota is three times a kind's, so
    compared raw the band term decided every step and the kinds ran out
    underneath it.

    That keeps the marginals in step for almost all of the draw and not for
    the end of it, where three marginals cannot all reach zero together -
    which is what `TOLERANCE` is for, in `largest` above. This reports what
    it could not fill and leaves that judgement there.

    Ties go to the cell whose next question ranks first by `_rank`, so the
    draw is reproducible and does not lean on the order rows were written.

    Threads are drawn whole: only a root is chosen, and it brings every turn
    under it, each counted against its own buckets. A follow-up whose root
    is not in the pool is never drawn.
    """
    bands = dict(quota.difficulty)
    types = dict(quota.types)
    languages = dict(quota.languages)
    # A ceiling: places the pool has no unanswerable row for go to answerable.
    held = min(quota.unanswerable, sum(not row.answerable for row in pool))
    places = {True: quota.size - held, False: held}
    left = dict(places)
    cells = _celled([row for row in pool if row.follows_id is None])
    turns: dict[int, list[Row]] = {}
    for row in sorted(pool, key=lambda one: one.id):
        if row.follows_id is not None:
            turns.setdefault(row.follows_id, []).append(row)
    chosen: list[int] = []

    while len(chosen) < quota.size:
        best: tuple[float, str, tuple[bool, str, str, str]] | None = None
        for key, rows in cells.items():
            answerable, band, kind, language = key
            if not rows or left[answerable] <= 0:
                continue
            if bands.get(band, 0) <= 0 or types.get(kind, 0) <= 0:
                continue
            if quota.languages and languages.get(language, 0) <= 0:
                continue
            # The SHARE of each bucket still to be filled, not the count.
            # Compared raw, a band's quota is three times a kind's, so the
            # band term decided every step and the kinds ran out under it.
            share = bands[band] / max(quota.difficulty.get(band, 1), 1)
            share += types[kind] / max(quota.types.get(kind, 1), 1)
            # Answerability too. Its places are held for it, and a draw that
            # spent the band and kind they need first left them unfilled.
            share += left[answerable] / max(places[answerable], 1)
            if quota.languages:
                share += languages[language] / max(quota.languages[language], 1)
            head = _rank(rows[0])
            if best is None or share > best[0] or (share == best[0] and head < best[1]):
                best = (share, head, key)
        if best is None:
            break
        # ponytail: pop(0) shifts the cell each draw. Upgrade: deque.popleft().
        thread = [cells[best[2]].pop(0)]
        for turn in thread:
            thread.extend(turns.get(turn.id, ()))
        for turn in thread:
            chosen.append(turn.id)
            left[turn.answerable] -= 1
            bands[turn.difficulty] = bands.get(turn.difficulty, 0) - 1
            types[turn.question_type] = types.get(turn.question_type, 0) - 1
            if quota.languages:
                languages[turn.language] = languages.get(turn.language, 0) - 1

    short = {
        name: count for name, count in (bands | types | languages).items() if count > 0
    }
    if left[True] > 0:
        short["answerable"] = left[True]
    return Release(ids=sorted(chosen), quota=quota, short=short)


#: How far short of its own quota one bucket may come and still be taken,
#: as a share of that quota. The target is "about a third each", not exactly
#: a third: three marginals cannot all land on zero together out of a finite
#: pool, and the last few places are where it always fails.
TOLERANCE = 0.10


def close_enough(release: Release, tolerance: float = TOLERANCE) -> bool:
    """Whether every bucket came within its slack of what was asked for.

    Measured per bucket, not on the total.

    One place is always allowed. A quota of eight cannot absorb a
    proportional tolerance, and being one short of eight is where the
    rounding fell rather than a pool that cannot supply the kind.
    """
    wanted = {
        **release.quota.difficulty,
        **release.quota.types,
        **release.quota.languages,
        "answerable": release.quota.size - release.quota.unanswerable,
    }
    return all(
        short <= max(1, tolerance * wanted.get(name, 0))
        for name, short in release.short.items()
    )


def largest(
    pool: Sequence[Row],
    bands: Mapping[str, int],
    types: Mapping[str, int],
    unanswerable: float,
    tolerance: float = TOLERANCE,
    languages: Mapping[str, int] | None = None,
) -> Release:
    """The biggest release this pool fills, near enough, found by bisection.

    The size a balanced set can reach is set by whichever bucket is furthest
    from being able to supply its share. Rather than working that bound out
    for three interacting marginals, the choosing itself is the test, and
    the largest size it fills to within `tolerance` is bisected for.

    What the release actually came out as is reported rather than assumed -
    `composition` reads it off the rows - so the few places a bucket ends
    short are visible instead of being promised away.

    When no size fills, the largest draw attempted is handed back with its
    shortfall rather than nothing at all. A thin pool has an empty cell
    somewhere, one empty cell refuses every size down to one, and returning
    nothing for that reason tells a reader less than returning the best set
    available beside a note of what is missing from it.
    """
    low, high = 1, len(pool)
    empty = Release(
        ids=[], quota=quota_of(0, bands, types, unanswerable, languages), short={}
    )
    best, most = empty, empty
    while low <= high:
        size = (low + high) // 2
        release = choose(pool, quota_of(size, bands, types, unanswerable, languages))
        if release.size > most.size:
            most = release
        if close_enough(release, tolerance):
            best, low = release, size + 1
        else:
            high = size - 1
    return best if best.ids else most


def composition(pool: Sequence[Row], ids: Sequence[int]) -> dict[str, dict[str, int]]:
    """What a chosen set actually came out as, for the report."""
    chosen = set(ids)
    taken = [row for row in pool if row.id in chosen]
    return {
        "answerable": Counter(
            "unanswerable" if not row.answerable else "answerable" for row in taken
        ),
        "difficulty": Counter(row.difficulty for row in taken),
        "type": Counter(row.question_type for row in taken),
        "language": Counter(row.language for row in taken),
    }
