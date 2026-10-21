"""What the release draw holds for any pool, not just the ones the examples name.

`largest` scans sizes down from a supply bound and keeps the first draw that
fills within the tolerance; `choose` draws threads root first, capped kinds
at what the pool holds. These say what must hold for every pool the strategy
can build: no kind past its share plus the slack, no follow-up without the
root it follows, no twin beside its twin, and the size kept the first that
fills when every size is tried from the pool's own size down.
"""

from __future__ import annotations

from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import (
    TOLERANCE,
    Row,
    _drawable,
    _slack,
    _supply,
    choose,
    close_enough,
    largest,
    quota_of,
    shares,
)

_BANDS = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)
_TYPES = (
    QuestionType.FACTOID,
    QuestionType.REASON,
    QuestionType.COMPARISON,
    QuestionType.AGGREGATION,
)
_LANGUAGES = ("de", "en")

#: A mix as a setting writes one, with at least one weight above zero.
_MIX = st.fixed_dictionaries({kind: st.integers(0, 4) for kind in _TYPES}).filter(
    lambda mix: any(mix.values())
)


@st.composite
def pools(draw):
    """Rows over a few bands, kinds and languages, threads and twin pairs among them.

    A follow-up follows an earlier row, as a thread is written; twins are
    symmetric, as the catalogue reads them.
    """
    count = draw(st.integers(0, 40))
    rows = []
    for at in range(1, count + 1):
        follows = draw(st.none() | st.integers(1, at - 1)) if at > 1 else None
        rows.append(
            Row(
                id=at,
                answerable=draw(st.booleans()) if follows is None else True,
                difficulty=draw(st.sampled_from(_BANDS)),
                question_type=draw(st.sampled_from(_TYPES)),
                follows_id=follows,
                language=draw(st.sampled_from(_LANGUAGES)),
            )
        )
    twins: dict[int, set[int]] = {}
    if count >= 2:
        for one, other in draw(
            st.lists(
                st.tuples(st.integers(1, count), st.integers(1, count)), max_size=6
            )
        ):
            if one != other:
                twins.setdefault(one, set()).add(other)
                twins.setdefault(other, set()).add(one)
    return rows, twins


_DRAW = {
    "pool": pools(),
    "types": _MIX,
    "unanswerable": st.sampled_from([0.0, 0.1, 0.3]),
    "languages": st.none() | st.just({"de": 1, "en": 1}),
}


def _released(pool, types, unanswerable, languages):
    rows, twins = pool
    bands = dict.fromkeys(_BANDS, 1)
    return (
        rows,
        twins,
        largest(rows, bands, types, unanswerable, TOLERANCE, languages, twins),
    )


@given(**_DRAW)
def test_no_kind_is_released_past_its_share_plus_the_slack(
    pool, types, unanswerable, languages
) -> None:
    """A capped kind's places go to the others only up to their share plus the tolerance."""
    rows, _, release = _released(pool, types, unanswerable, languages)
    by_id = {row.id: row for row in rows}
    held = Counter(by_id[one].question_type for one in release.ids)
    spread = shares(types, release.quota.size)

    for kind, count in held.items():
        assert count <= spread.get(kind, 0) + _slack(spread.get(kind, 0), TOLERANCE), (
            kind,
            held,
            spread,
        )


@given(**_DRAW)
def test_a_follow_up_is_never_released_without_its_root(
    pool, types, unanswerable, languages
) -> None:
    """Threads are drawn root first, and cut at a full bucket with what follows."""
    rows, _, release = _released(pool, types, unanswerable, languages)
    by_id = {row.id: row for row in rows}
    chosen = set(release.ids)

    for one in chosen:
        follows = by_id[one].follows_id
        assert follows is None or follows in chosen, (one, follows)


@given(**_DRAW)
def test_no_release_holds_a_question_beside_its_twin(
    pool, types, unanswerable, languages
) -> None:
    """A set that asks one thing twice weights it twice."""
    _, twins, release = _released(pool, types, unanswerable, languages)
    chosen = set(release.ids)

    for one in chosen:
        assert twins.get(one, set()).isdisjoint(chosen), (one, twins[one])


@given(**_DRAW)
def test_a_release_takes_no_more_unanswerable_than_its_ceiling(
    pool, types, unanswerable, languages
) -> None:
    """The unanswerable share is a ceiling at whatever size the scan kept."""
    rows, _, release = _released(pool, types, unanswerable, languages)
    by_id = {row.id: row for row in rows}

    assert (
        sum(not by_id[one].answerable for one in release.ids)
        <= release.quota.unanswerable
    )


@given(**_DRAW)
def test_the_size_kept_is_the_first_that_fills_scanning_down_from_the_pool(
    pool, types, unanswerable, languages
) -> None:
    """The supply bound skips only sizes no draw fills.

    Every size from the pool's own size down is drawn as `largest` draws it;
    the first that comes within the tolerance is the size `largest` keeps.
    """
    rows, twins, release = _released(pool, types, unanswerable, languages)
    bands = dict.fromkeys(_BANDS, 1)
    drawable = _drawable(rows, languages, twins)
    first = None
    for size in range(len(rows), 0, -1):
        supply = _supply(drawable, unanswerable, size)
        quota = quota_of(size, bands, types, unanswerable, languages, supply, TOLERANCE)
        if close_enough(choose(rows, quota, twins), TOLERANCE):
            first = size
            break

    if first is not None:
        assert release.quota.size == first
        assert close_enough(release, TOLERANCE)
    else:
        assert not close_enough(release, TOLERANCE) or release.size == 0
