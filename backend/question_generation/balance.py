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
    #: The categories its writer was told, as `categorization=category`
    #: labels, sorted. Reported and never held to a quota.
    categories: tuple[str, ...] = ()


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


#: How far short of its own quota one bucket may come and still be taken,
#: as a share of that quota. The target is "about a third each", not exactly
#: a third: the marginals cannot all land on zero together out of a finite
#: pool, and the last few places are where it always fails.
TOLERANCE = 0.10


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


def _slack(count: int, tolerance: float) -> int:
    """How many places short of `count` `close_enough` lets a bucket come."""
    return int(max(1, tolerance * count))


def _capped(
    weights: Mapping[str, int],
    size: int,
    supply: Mapping[str, int],
    tolerance: float,
) -> dict[str, int]:
    """`shares`, with a bucket the pool cannot fill held to what it has.

    A bucket short of its share by more than `close_enough` allows would
    refuse the size, and with it every size that asks it for that much. It is
    asked for what the pool holds instead, and the places it cannot take go
    to the others by the same largest remainder, but no bucket is asked for
    more than its own share plus the slack `close_enough` allows, nor for
    more than the pool holds of it. So the spread over the kinds stays within
    the tolerance of the weights, and the places no bucket may take are left
    unplaced: the size is then too big to fill, and the scan goes below it.
    """
    spread = shares(weights, size)
    capped = {
        name: supply.get(name, 0)
        for name, count in spread.items()
        if count - supply.get(name, 0) > _slack(count, tolerance)
    }
    if not capped:
        return spread
    room = {
        name: max(0, min(count + _slack(count, tolerance), supply.get(name, 0)) - count)
        for name, count in spread.items()
        if name not in capped
    }
    freed = sum(spread[name] - held for name, held in capped.items())
    result = capped | {name: spread[name] for name in room}
    open_weights = {name: weights[name] for name in room}
    while freed > 0 and open_weights:
        extra = shares(open_weights, freed)
        full = {name for name, more in extra.items() if more >= room[name]}
        if not full:
            for name, more in extra.items():
                result[name] += more
            break
        for name in full:
            result[name] += room[name]
            freed -= room[name]
            del open_weights[name]
    return result


def quota_of(
    size: int,
    bands: Mapping[str, int],
    types: Mapping[str, int],
    unanswerable: float,
    languages: Mapping[str, int] | None = None,
    supply: Mapping[str, int] | None = None,
    tolerance: float = TOLERANCE,
) -> Quota:
    """The quota a release of this size wants.

    `supply` is how many questions the pool holds of each kind. Given, a kind
    it cannot fill within `tolerance` is capped at what it holds.
    """
    return Quota(
        size=size,
        unanswerable=int(size * unanswerable),
        difficulty=shares(bands, size),
        types=_capped(types, size, supply, tolerance)
        if supply is not None
        else shares(types, size),
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


def _celled(
    pool: Sequence[Row], rank: Mapping[int, str]
) -> dict[tuple[bool, str, str, str], list[Row]]:
    """The pool grouped by the cell a question would spend its places in.

    Each in `_rank` order, read off `rank`, so the same pool draws the same
    release twice.
    """
    held: dict[tuple[bool, str, str, str], list[Row]] = {}
    for row in sorted(pool, key=lambda one: rank[one.id]):
        held.setdefault(
            (row.answerable, row.difficulty, row.question_type, row.language), []
        ).append(row)
    return held


@dataclass(frozen=True)
class _Pool:
    """What a draw reads of a pool, which no size changes.

    Ranked, grouped into cells and into turns once, so `largest`, which draws
    at many sizes, does the sorting once and each draw only walks.
    """

    rank: dict[int, str]
    #: The roots of the pool, by cell, each in `rank` order.
    cells: dict[tuple[bool, str, str, str], list[Row]]
    #: Each root with the cell it is in.
    waiting: dict[int, tuple[tuple[bool, str, str, str], Row]]
    #: The turns under a question, in id order.
    turns: dict[int, list[Row]]


def _prepared(pool: Sequence[Row]) -> _Pool:
    """Ranks, groups and threads a pool."""
    rank = {row.id: _rank(row) for row in pool}
    cells = _celled([row for row in pool if row.follows_id is None], rank)
    turns: dict[int, list[Row]] = {}
    for row in sorted(pool, key=lambda one: one.id):
        if row.follows_id is not None:
            turns.setdefault(row.follows_id, []).append(row)
    return _Pool(
        rank=rank,
        cells=cells,
        waiting={row.id: (key, row) for key, rows in cells.items() for row in rows},
        turns=turns,
    )


def choose(
    pool: Sequence[Row],
    quota: Quota,
    twins: Mapping[int, set[int]] | None = None,
    prepared: _Pool | None = None,
) -> Release:
    """The questions filling this quota, and whatever it could not fill.

    Largest deficit first. A question spends a place in four buckets at
    once - answerability, band, kind and language - so at each step the cell
    taken from is the one whose band, kind and language are the furthest,
    as a SHARE of what each was asked for, from being filled. Measured as a
    share and not as a count: a band's quota is three times a kind's, so
    compared raw the band term decided every step and the kinds ran out
    underneath it.

    That keeps the marginals in step for almost all of the draw and not for
    the end of it, where the marginals cannot all reach zero together -
    which is what `TOLERANCE` is for, in `largest` above. This reports what
    it could not fill and leaves that judgement there.

    Ties go to the cell whose next question ranks first by `_rank`, so the
    draw is reproducible and does not lean on the order rows were written.

    Threads are drawn whole: only a root is chosen, and it brings the turns
    under it, each counted against its own buckets as it joins. A thread ends
    at the first turn whose band, kind or language has no place left, the
    same `fits` test a root passes, and the turns after it go with it, so a
    release never holds a kind past its quota for the follow-ups' sake. A
    follow-up whose root is not in the pool is never drawn.

    `twins` names, for a question, the others the release must not hold
    beside it: a set that asks one thing twice weights it twice. A root
    whose twin is in is skipped. A thread ends at a turn that twins what is
    already in, its own earlier turns included, and the turns after it go
    with it, because they read only after it. And a twin group is visited
    in `_rank` order: where the next root has twins still waiting that fit,
    the one ranked first is taken in its place. Not the one the gates were
    surest of: a later twin's weakest margin is its `near_duplicate` reading
    against the earlier one, so that kept the earlier twin nearly always and
    let creation order back into the draw.

    `prepared` is the pool as `_prepared` read it, for a caller drawing it
    again at another size.
    """
    alike: Mapping[int, set[int]] = twins or {}
    bands = dict(quota.difficulty)
    types = dict(quota.types)
    languages = dict(quota.languages)
    # A ceiling: places the pool has no unanswerable row for go to answerable.
    held = min(quota.unanswerable, sum(not row.answerable for row in pool))
    places = {True: quota.size - held, False: held}
    left = dict(places)
    read = prepared or _prepared(pool)
    rank, cells, waiting, turns = read.rank, read.cells, read.waiting, read.turns
    #: How far into each cell the rows are already taken, which are skipped
    #: where it is read, and how many of its rows are not.
    at = dict.fromkeys(cells, 0)
    remaining = {key: len(rows) for key, rows in cells.items()}
    gone: set[int] = set()
    chosen: list[int] = []
    #: `chosen` as a set, for asking whether a twin is already in.
    held_ids: set[int] = set()

    def fits(row: Row) -> bool:
        """Whether every bucket this question spends a place in has one."""
        return (
            left[row.answerable] > 0
            and bands.get(row.difficulty, 0) > 0
            and types.get(row.question_type, 0) > 0
            and (not quota.languages or languages.get(row.language, 0) > 0)
        )

    def spend(row: Row) -> None:
        """Takes one place from each bucket this question fills."""
        left[row.answerable] -= 1
        bands[row.difficulty] = bands.get(row.difficulty, 0) - 1
        types[row.question_type] = types.get(row.question_type, 0) - 1
        if quota.languages:
            languages[row.language] = languages.get(row.language, 0) - 1

    def taken(row: Row) -> None:
        """Takes a root out of its cell."""
        gone.add(row.id)
        remaining[waiting[row.id][0]] -= 1

    def head(key: tuple[bool, str, str, str]) -> Row:
        """The first row of a cell that is not taken."""
        rows = cells[key]
        while rows[at[key]].id in gone:
            at[key] += 1
        return rows[at[key]]

    while len(chosen) < quota.size:
        best: tuple[float, str, tuple[bool, str, str, str]] | None = None
        for key in cells:
            answerable, band, kind, language = key
            if not remaining[key] or left[answerable] <= 0:
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
            ahead = rank[head(key).id]
            if (
                best is None
                or share > best[0]
                or (share == best[0] and ahead < best[1])
            ):
                best = (share, ahead, key)
        if best is None:
            break
        first = head(best[2])
        rivals = [
            waiting[twin][1]
            for twin in alike.get(first.id, set())
            if twin in waiting and twin not in gone and fits(waiting[twin][1])
        ]
        root = min([first, *rivals], key=lambda one: rank[one.id])
        taken(root)
        spend(root)
        thread = [root]
        within = {root.id}
        for turn in thread:
            for follow in turns.get(turn.id, ()):
                twinned = alike.get(follow.id)
                if twinned and not (
                    twinned.isdisjoint(within) and twinned.isdisjoint(held_ids)
                ):
                    continue
                # The same test a root passes: a turn whose band, kind or
                # language is full ends the thread there, and the turns
                # after it go with it.
                if not fits(follow):
                    continue
                spend(follow)
                thread.append(follow)
                within.add(follow.id)
        for turn in thread:
            for twin in alike.get(turn.id, set()):
                if twin in waiting and twin not in gone:
                    taken(waiting[twin][1])
            chosen.append(turn.id)
            held_ids.add(turn.id)

    short = {
        name: count for name, count in (bands | types | languages).items() if count > 0
    }
    if left[True] > 0:
        short["answerable"] = left[True]
    return Release(ids=sorted(chosen), quota=quota, short=short)


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
    twins: Mapping[int, set[int]] | None = None,
) -> Release:
    """The biggest release this pool fills, near enough, found by scanning down.

    The size a balanced set can reach is set by whichever bucket is furthest
    from being able to supply its share. Rather than working that bound out
    for four interacting marginals, the choosing itself is the test: sizes
    are tried from the largest the pool can place downwards, and the first
    that fills to within `tolerance` is drawn. Not bisected for, because
    whether a size fills does not fall steadily with the size: the draw's
    endgame lands differently at each, so a size failing between two that
    fill sent a bisection down for good, at times to a few rows.

    The scan starts where the kinds cap at what the pool holds and what they
    leave unplaced is no more than the unanswerable ceiling (`_placeable`),
    which is a draw's own limit: above it answerable places are left with no
    kind to take them. A pool whose kinds place nothing that way starts from
    the looser bound `_fillable` gives, as the scan always did.

    What the release actually came out as is reported rather than assumed -
    `composition` reads it off the rows - so the few places a bucket ends
    short are visible instead of being promised away.

    When no size fills, the largest draw attempted is handed back with its
    shortfall rather than nothing at all. A thin pool has an empty cell
    somewhere, one empty cell refuses every size down to one, and returning
    nothing for that reason tells a reader less than returning the best set
    available beside a note of what is missing from it.
    """
    most = Release(
        ids=[], quota=quota_of(0, bands, types, unanswerable, languages), short={}
    )
    drawable = _drawable(pool, languages, twins)
    counts = _counts(drawable)
    start = _placeable(pool, bands, types, unanswerable, languages, tolerance, counts)
    prepared = _prepared(pool)
    for size in range(start, 0, -1):
        supply = _supply_at(counts, unanswerable, size)
        release = choose(
            pool,
            quota_of(size, bands, types, unanswerable, languages, supply, tolerance),
            twins,
            prepared,
        )
        if close_enough(release, tolerance):
            return release
        if release.size > most.size:
            most = release
    return most


def _drawable(
    pool: Sequence[Row],
    languages: Mapping[str, int] | None,
    twins: Mapping[int, set[int]] | None,
) -> list[Row]:
    """The rows a draw could release.

    Not a language it gives no weight, and one of any rows that are twins of
    each other, the first by `_rank`.
    """
    alike = twins or {}
    held: set[int] = set()
    for row in sorted(pool, key=_rank):
        if languages and languages.get(row.language, 0) <= 0:
            continue
        if alike.get(row.id, set()).isdisjoint(held):
            held.add(row.id)
    return [row for row in pool if row.id in held]


def _counts(drawable: Sequence[Row]) -> tuple[Counter[str], Counter[str]]:
    """How many rows of each kind are answerable, and how many are not."""
    answered: Counter[str] = Counter()
    unanswered: Counter[str] = Counter()
    for row in drawable:
        (answered if row.answerable else unanswered)[row.question_type] += 1
    return answered, unanswered


def _supply_at(
    counts: tuple[Counter[str], Counter[str]], unanswerable: float, size: int
) -> Counter[str]:
    """How many questions a release of this size could draw of each kind.

    Unanswerable rows count only up to the ceiling of that size.
    """
    answered, unanswered = counts
    ceiling = int(size * unanswerable)
    supply: Counter[str] = Counter(answered)
    for kind, count in unanswered.items():
        supply[kind] += min(count, ceiling)
    return supply


def _supply(drawable: Sequence[Row], unanswerable: float, size: int) -> Counter[str]:
    """How many questions a release of this size could draw of each kind."""
    return _supply_at(_counts(drawable), unanswerable, size)


def _fillable(
    pool: Sequence[Row],
    bands: Mapping[str, int],
    types: Mapping[str, int],
    unanswerable: float,
    languages: Mapping[str, int] | None,
    tolerance: float,
    twins: Mapping[int, set[int]] | None = None,
    counts: tuple[Counter[str], Counter[str]] | None = None,
    placeable: bool = False,
) -> int:
    """The largest size whose every quota the pool holds rows enough for, within its slack.

    No draw above it can fill, whatever it picks, so the scan starts here
    rather than at the size of the pool. Unanswerable rows count per bucket
    only up to the ceiling, the most a draw takes from any one.

    With `placeable`, the places the capped kinds leave unplaced may be no
    more than the unanswerable ceiling, with no slack: the places a draw can
    give up for want of a kind are the unanswerable ones.
    """
    held = Counter(
        name
        for row in pool
        if row.answerable
        for name in (row.difficulty, row.question_type, row.language)
    )
    spare = Counter(
        name
        for row in pool
        if not row.answerable
        for name in (row.difficulty, row.question_type, row.language)
    )
    unanswered = sum(not row.answerable for row in pool)
    counts = counts or _counts(_drawable(pool, languages, twins))
    for size in range(len(pool), 0, -1):
        supply = _supply_at(counts, unanswerable, size)
        quota = quota_of(size, bands, types, unanswerable, languages, supply, tolerance)
        wanted = {**quota.difficulty, **quota.types, **quota.languages}
        answerable = size - quota.unanswerable
        missing = {
            name: count - held[name] - min(spare[name], quota.unanswerable)
            for name, count in wanted.items()
        }
        missing["answerable"] = (
            size - min(quota.unanswerable, unanswered) - (len(pool) - unanswered)
        )
        wanted["answerable"] = answerable
        # Places the capped kinds leave unplaced: the draw cannot spend them,
        # and only unanswerable places are not reported when unspent.
        unplaced = size - sum(quota.types.values())
        room = 0 if placeable else _slack(answerable, tolerance)
        if unplaced > quota.unanswerable + room:
            continue
        if all(
            short <= max(1, tolerance * wanted[name]) for name, short in missing.items()
        ):
            return size
    return 0


def _placeable(
    pool: Sequence[Row],
    bands: Mapping[str, int],
    types: Mapping[str, int],
    unanswerable: float,
    languages: Mapping[str, int] | None,
    tolerance: float,
    counts: tuple[Counter[str], Counter[str]],
) -> int:
    """The size a scan starts from: what the pool can place, else what it can hold.

    The largest size every quota is held for rows enough for and whose
    capped kinds leave no more than the unanswerable ceiling unplaced. That
    holds where the ceiling is at least as much as the tolerance: every size
    above it leaves a bucket more places than the tolerance forgives, which a
    release of any other pool does not, so a ceiling under the tolerance (and
    none at all) starts from what the pool can hold, and the scan is then as
    long as it always was.
    """
    args = (pool, bands, types, unanswerable, languages, tolerance, None, counts)
    if unanswerable < tolerance:
        return _fillable(*args)
    return _fillable(*args, placeable=True) or _fillable(*args)


def composition(pool: Sequence[Row], ids: Sequence[int]) -> dict[str, dict[str, int]]:
    """What a chosen set actually came out as, for the report.

    A question counts once under each category it was told, keyed by label
    on an axis of its own, so a category named like a kind is never counted
    as one.
    """
    chosen = set(ids)
    taken = [row for row in pool if row.id in chosen]
    return {
        "answerable": Counter(
            "unanswerable" if not row.answerable else "answerable" for row in taken
        ),
        "difficulty": Counter(row.difficulty for row in taken),
        "type": Counter(row.question_type for row in taken),
        "language": Counter(row.language for row in taken),
        "category": Counter(label for row in taken for label in row.categories),
    }
