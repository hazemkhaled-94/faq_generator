"""Choosing a balanced release out of everything a run accepted.

The gates decide whether a question is sound; nothing before this decides
what the SET looks like.

Three marginals are held at once - answerability, difficulty band and kind -
and they are marginals rather than a joint distribution on purpose. An even
spread of kinds WITHIN each band is not reachable: a factoid answers with a
value, a value is short, and a short answer cannot earn the length point a
hard question generally needs.
"""

from __future__ import annotations

import pytest

from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import (
    Quota,
    Release,
    Row,
    choose,
    close_enough,
    composition,
    largest,
    quota_of,
    shares,
)
from question_generation.service import _report, _supplied

BANDS = {Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1}
TYPES = {QuestionType.FACTOID: 1, QuestionType.REASON: 1}


def row(
    id: int,
    band: str = Difficulty.EASY,
    kind: str = QuestionType.FACTOID,
    answerable: bool = True,
) -> Row:
    """One accepted question, as the choosing reads it."""
    return Row(id=id, answerable=answerable, difficulty=band, question_type=kind)


#: A pool whose kinds sit unevenly across the bands, as a real run's do.
SKEWED = {
    (Difficulty.EASY, QuestionType.FACTOID, True): 90,
    (Difficulty.MEDIUM, QuestionType.FACTOID, True): 20,
    (Difficulty.HARD, QuestionType.FACTOID, True): 2,
    (Difficulty.EASY, QuestionType.REASON, True): 10,
    (Difficulty.MEDIUM, QuestionType.REASON, True): 40,
    (Difficulty.HARD, QuestionType.REASON, True): 30,
    (Difficulty.EASY, QuestionType.COMPARISON, True): 5,
    (Difficulty.MEDIUM, QuestionType.COMPARISON, True): 30,
    (Difficulty.HARD, QuestionType.COMPARISON, True): 40,
}
SKEWED_TYPES = {**TYPES, QuestionType.COMPARISON: 1}


def pool(counts: dict[tuple[str, str, bool], int]) -> list[Row]:
    """A pool holding this many questions of each band, kind and answerability."""
    built: list[Row] = []
    for (band, kind, answerable), count in counts.items():
        for _ in range(count):
            built.append(row(len(built) + 1, band, kind, answerable))
    return built


# ── Spreading a size over weights ──────────────────────────────────────────


def test_whole_shares_are_exact() -> None:
    """Nothing to round, so nothing is rounded."""
    assert shares({"a": 1, "b": 1}, 10) == {"a": 5, "b": 5}


def test_the_shares_always_sum_to_the_size() -> None:
    """A quota that does not add up is a release short of its own target."""
    for size in range(1, 60):
        assert sum(shares(BANDS, size).values()) == size


def test_the_remainder_goes_to_the_largest_fractions() -> None:
    """Largest remainder, so the spread is as even as the size allows."""
    got = shares({"a": 1, "b": 1, "c": 1}, 10)

    assert sum(got.values()) == 10
    assert sorted(got.values()) == [3, 3, 4]


def test_the_same_weights_give_the_same_answer_twice() -> None:
    """Ties by name, so a release is reproducible from its settings."""
    assert shares({"a": 1, "b": 1, "c": 1}, 10) == shares({"c": 1, "b": 1, "a": 1}, 10)


@pytest.mark.parametrize("size", [0, -1])
def test_no_size_is_no_quota(size) -> None:
    """Rather than a negative one, or a division by nothing."""
    assert set(shares(BANDS, size).values()) == {0}


def test_a_weight_of_zero_takes_no_place() -> None:
    """Which is how a deployment turns a type off."""
    assert shares({"a": 1, "b": 0}, 10) == {"a": 10, "b": 0}


# ── Filling a quota ────────────────────────────────────────────────────────


def test_a_pool_that_matches_the_quota_fills_it_exactly() -> None:
    """The case every shortfall below is measured against."""
    counted = {
        (band, kind, True): 10
        for band in (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)
        for kind in (QuestionType.FACTOID, QuestionType.REASON)
    }

    release = choose(pool(counted), quota_of(6, BANDS, TYPES, 0.0))

    assert release.size == 6
    assert release.short == {}


def test_the_unanswerable_share_is_a_ceiling() -> None:
    """Too many and the release mostly tests whether a chatbot can say no."""
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, False): 50,
        (Difficulty.EASY, QuestionType.FACTOID, True): 50,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 50,
        (Difficulty.HARD, QuestionType.FACTOID, True): 50,
        (Difficulty.EASY, QuestionType.REASON, True): 50,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 50,
        (Difficulty.HARD, QuestionType.REASON, True): 50,
    }
    held = pool(counted)

    release = choose(held, quota_of(100, BANDS, TYPES, 0.10))
    got = composition(held, release.ids)

    assert release.size == 100
    assert got["answerable"]["unanswerable"] == 10


def test_a_band_the_pool_cannot_supply_is_reported_short() -> None:
    """Rather than a release quietly missing a third of what it claims."""
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 50,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 50,
        (Difficulty.EASY, QuestionType.REASON, True): 50,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 50,
    }

    release = choose(pool(counted), quota_of(30, BANDS, TYPES, 0.0))

    assert release.short.get(Difficulty.HARD) == 10
    assert release.size == 20


def test_a_scarce_pair_gets_its_place_before_a_plentiful_one() -> None:
    """The reason the pool is walked scarcest first.

    Taken in id order the common pairs spend the whole `reason` quota on easy
    ones, and the single hard reason - the only question that can fill that
    cell - is passed over because its type is full.
    """
    counted = {
        (Difficulty.EASY, QuestionType.REASON, True): 40,
        (Difficulty.HARD, QuestionType.REASON, True): 1,
        (Difficulty.EASY, QuestionType.FACTOID, True): 40,
        (Difficulty.HARD, QuestionType.FACTOID, True): 40,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 40,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 40,
    }
    held = pool(counted)

    release = choose(held, quota_of(6, BANDS, TYPES, 0.0))
    taken = {one.id for one in held if one.id in set(release.ids)}
    hard_reasons = [
        one
        for one in held
        if one.id in taken
        and one.difficulty == Difficulty.HARD
        and one.question_type == QuestionType.REASON
    ]

    assert release.short == {}
    assert len(hard_reasons) == 1


# ── The largest release a pool can fill ────────────────────────────────────


def test_the_largest_release_comes_within_a_place_of_every_quota() -> None:
    """Which is what makes it the largest one worth shipping.

    One place per bucket, not zero: a quota of eight cannot absorb a
    proportional tolerance, and being one short of eight is where the
    rounding fell rather than a pool that cannot supply the kind.
    """
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 30,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 30,
        (Difficulty.HARD, QuestionType.FACTOID, True): 5,
        (Difficulty.EASY, QuestionType.REASON, True): 30,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 30,
        (Difficulty.HARD, QuestionType.REASON, True): 5,
    }
    held = pool(counted)

    release = largest(held, BANDS, TYPES, 0.0)
    got = composition(held, release.ids)

    assert close_enough(release)
    assert all(short <= 1 for short in release.short.values())
    # Ten hard questions is what caps it, give or take the one place each
    # bucket may be short.
    assert 30 <= release.size <= 34
    assert got["difficulty"][Difficulty.HARD] == 10


def test_the_scarcest_band_is_what_caps_the_size() -> None:
    """A pool short of hard questions fills no release that wants a third hard."""
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 100,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 100,
        (Difficulty.HARD, QuestionType.FACTOID, True): 3,
    }

    release = largest(pool(counted), BANDS, {QuestionType.FACTOID: 1}, 0.0)

    # Three hard questions, and one place of slack per bucket on top.
    assert close_enough(release)
    assert 9 <= release.size <= 13


def test_no_larger_release_fills_than_the_one_drawn() -> None:
    """Whether a size fills does not fall steadily with the size, so a bisection stopped early.

    Here it settled on 29 while 41 fills: a size failing between them sent
    it down and it never looked above again.
    """
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 8,
        (Difficulty.EASY, QuestionType.REASON, True): 5,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 10,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 3,
        (Difficulty.HARD, QuestionType.FACTOID, True): 9,
        (Difficulty.HARD, QuestionType.REASON, True): 12,
    }
    held = pool(counted)

    release = largest(held, BANDS, TYPES, 0.0)

    assert close_enough(release)
    assert not any(
        close_enough(choose(held, quota_of(size, BANDS, TYPES, 0.0)))
        for size in range(release.quota.size + 1, len(held) + 1)
    )
    assert release.quota.size == 41


def test_a_kind_the_pool_has_none_of_is_dropped_from_the_quota() -> None:
    """One empty bucket would otherwise refuse every size of release."""
    supplied = _supplied([row(1)], TYPES, "kind", "question_type")

    assert supplied == {QuestionType.FACTOID: 1}


def test_an_empty_pool_releases_nothing() -> None:
    """Rather than bisecting over nothing and returning a quota it cannot fill."""
    release = largest([], BANDS, TYPES, 0.0)

    assert release.ids == []
    assert release.size == 0


def test_a_release_may_come_a_little_short_of_its_quota() -> None:
    """Three marginals cannot all reach zero together.

    The target is "about a third each", so a few places short is taken and
    reported rather than thrown away.
    """
    held = pool(SKEWED)

    release = largest(held, BANDS, SKEWED_TYPES, 0.0)
    exact = largest(held, BANDS, SKEWED_TYPES, 0.0, tolerance=0.0)

    assert release.short, "the pool fills every quota, so nothing was tolerated"
    assert close_enough(release)
    assert release.size > exact.size


def test_what_it_could_not_fill_is_still_reported() -> None:
    """The tolerance is not a reason to stop saying what was missing."""
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 50,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 50,
        (Difficulty.EASY, QuestionType.REASON, True): 50,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 50,
    }

    release = choose(pool(counted), quota_of(30, BANDS, TYPES, 0.0))

    assert release.short.get(Difficulty.HARD) == 10


def test_the_tolerance_is_set_above_the_endgame_not_below_it() -> None:
    """A tolerance under the shortfall buys almost no release at all.

    The last places of a draw cannot be filled - three marginals do not
    reach zero together - so this is a floor as much as a ceiling.
    """
    held = pool(SKEWED)

    release = largest(held, BANDS, SKEWED_TYPES, 0.0)
    tight = largest(held, BANDS, SKEWED_TYPES, 0.0, tolerance=0.03)

    assert release.size > tight.size


def test_a_bucket_the_pool_genuinely_cannot_supply_is_still_refused() -> None:
    """Loosening the tolerance must not turn the check off."""
    short = Release(
        ids=[1],
        quota=quota_of(140, BANDS, {**TYPES, QuestionType.AGGREGATION: 1}, 0.0),
        short={QuestionType.AGGREGATION: 6},
    )

    assert not close_enough(short)


# ── Threads ────────────────────────────────────────────────────────────────


def test_a_follow_up_is_never_drawn_without_the_turn_it_follows() -> None:
    """`Why are they shown there?` is a question only after its parent."""
    quota = quota_of(2, {Difficulty.EASY: 1}, TYPES, 0.0)
    pool = [
        row(1),
        row(2),
        Row(3, True, Difficulty.EASY, QuestionType.REASON, follows_id=2),
    ]

    chosen = set(choose(pool, quota).ids)

    assert all(
        one.follows_id in chosen for one in pool if one.id in chosen and one.follows_id
    )


def test_a_root_drawn_carries_its_thread_with_it() -> None:
    """The follow-ups are the part of the set that tests multi-turn retrieval."""
    types = {QuestionType.FACTOID: 1, QuestionType.REASON: 2}
    quota = quota_of(3, {Difficulty.EASY: 1}, types, 0.0)
    pool = [
        row(1),
        Row(2, True, Difficulty.EASY, QuestionType.REASON, follows_id=1),
        Row(3, True, Difficulty.EASY, QuestionType.REASON, follows_id=2),
    ]

    assert choose(pool, quota).ids == [1, 2, 3]


def test_unanswerable_places_the_pool_cannot_fill_go_to_answerable_rows() -> None:
    """A ceiling, not a reservation: the release is not smaller for it."""
    quota = quota_of(10, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.1)

    assert choose([row(n) for n in range(1, 21)], quota).size == 10


# ── Languages ──────────────────────────────────────────────────────────────

#: Equal weight on two languages, which is what an unset
#: QUESTIONS_RELEASE_LANGUAGES gives a pool holding as many of each.
LANGUAGES = {"de": 1, "en": 1}


def spoken(id: int, language: str, answerable: bool = True, **bucket: str) -> Row:
    """One accepted question in one language, easy and factoid unless told."""
    return Row(
        id=id,
        answerable=answerable,
        difficulty=bucket.get("band", Difficulty.EASY),
        question_type=bucket.get("kind", QuestionType.FACTOID),
        language=language,
    )


def written_in(languages: tuple[str, ...], per_cell: int) -> list[Row]:
    """The same pool in each language, one language after the other.

    Ids follow creation order, and a run writes one language's topics before
    the next, so every row of the first language has a lower id than every
    row of the second.
    """
    built: list[Row] = []
    for language in languages:
        for band in BANDS:
            for kind in TYPES:
                for _ in range(per_cell):
                    built.append(spoken(len(built) + 1, language, band=band, kind=kind))
    return built


def test_an_even_bilingual_pool_is_released_evenly() -> None:
    """Half of each language in, half of each out, within a place.

    Without a language quota every place went to the language written
    first: each cell drained in id order, and its ids were all lower.
    """
    held = written_in(("de", "en"), per_cell=10)

    release = choose(held, quota_of(60, BANDS, TYPES, 0.0, LANGUAGES))
    got = composition(held, release.ids)

    assert release.size == 60
    assert all(abs(got["language"][one] - 30) <= 1 for one in LANGUAGES), got


def test_the_unanswerable_ceiling_is_shared_by_the_languages() -> None:
    """Not filled from whichever language was written first."""
    held: list[Row] = []
    for language in LANGUAGES:
        for answerable in (True, False):
            for _ in range(10):
                held.append(spoken(len(held) + 1, language, answerable))

    release = choose(
        held,
        quota_of(20, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.5, LANGUAGES),
    )
    unanswerable = composition(
        [one for one in held if not one.answerable], release.ids
    )["language"]

    assert sum(unanswerable.values()) == 10
    assert min(unanswerable[one] for one in LANGUAGES) >= 3, unanswerable


def test_a_language_the_pool_has_none_of_is_dropped_from_the_quota() -> None:
    """A German-only pool would otherwise refuse every size of release."""
    supplied = _supplied([spoken(1, "de")], LANGUAGES, "language", "language")

    assert supplied == {"de": 1}


def test_a_heavier_language_takes_its_weighted_share() -> None:
    """`de:2,en:1` releases about two thirds German."""
    held = written_in(("de", "en"), per_cell=20)

    release = choose(held, quota_of(60, BANDS, TYPES, 0.0, {"de": 2, "en": 1}))
    got = composition(held, release.ids)

    assert release.size == 60
    assert abs(got["language"]["de"] - 40) <= 1, got


def test_a_third_language_is_held_to_its_share_too() -> None:
    """No language is special: any code the pool holds is a bucket."""
    languages = {"de": 1, "en": 1, "fr": 1}
    held = written_in(tuple(languages), per_cell=10)

    release = choose(held, quota_of(60, BANDS, TYPES, 0.0, languages))
    got = composition(held, release.ids)

    assert all(abs(got["language"][one] - 20) <= 1 for one in languages), got


def test_a_bilingual_pool_releases_the_largest_size_that_fills() -> None:
    """With a language quota too, no size above the one drawn would have filled.

    The same uneven pool in German and English, one language written after
    the other, as a bank's or a shop's two editions are.
    """
    counted = {
        (Difficulty.EASY, QuestionType.FACTOID, True): 8,
        (Difficulty.EASY, QuestionType.REASON, True): 5,
        (Difficulty.MEDIUM, QuestionType.FACTOID, True): 10,
        (Difficulty.MEDIUM, QuestionType.REASON, True): 3,
        (Difficulty.HARD, QuestionType.FACTOID, True): 9,
        (Difficulty.HARD, QuestionType.REASON, True): 12,
    }
    held: list[Row] = []
    for language in LANGUAGES:
        for (band, kind, answerable), count in counted.items():
            for _ in range(count):
                held.append(
                    spoken(len(held) + 1, language, answerable, band=band, kind=kind)
                )

    release = largest(held, BANDS, TYPES, 0.0, languages=LANGUAGES)

    assert close_enough(release)
    assert not any(
        close_enough(choose(held, quota_of(size, BANDS, TYPES, 0.0, LANGUAGES)))
        for size in range(release.quota.size + 1, len(held) + 1)
    )


def test_the_composition_reports_the_language() -> None:
    """The report logs it, so a skew towards one is visible."""
    held = [spoken(1, "de"), spoken(2, "de"), spoken(3, "en")]

    assert composition(held, [1, 2, 3])["language"] == {"de": 2, "en": 1}


CONCISE = "Phrasing=concise-and-natural"
VERBOSE = "Phrasing=verbose-and-natural"


def told(id: int, *categories: str) -> Row:
    """One accepted question its writer was told these categories of."""
    return Row(
        id=id,
        answerable=True,
        difficulty=Difficulty.EASY,
        question_type=QuestionType.FACTOID,
        categories=categories,
    )


def test_the_composition_reports_the_categories() -> None:
    """Each label counted once per question told it; no quota holds them."""
    held = [told(1, CONCISE), told(2, VERBOSE), told(3, CONCISE)]

    assert composition(held, [1, 2, 3])["category"] == {CONCISE: 2, VERBOSE: 1}


def test_a_category_named_like_a_kind_is_its_own_bucket() -> None:
    """Keyed `categorization=category`, so it never counts as a type."""
    got = composition([told(1, "Factuality=factoid")], [1])

    assert got["type"] == {QuestionType.FACTOID: 1}
    assert got["category"] == {"Factuality=factoid": 1}


def test_a_question_told_no_category_adds_none() -> None:
    """An unanswerable question, a follow-up, or one written before categories."""
    assert composition([row(1), told(2, CONCISE)], [1, 2])["category"] == {CONCISE: 1}


# ── Order ──────────────────────────────────────────────────────────────────


def test_a_draw_does_not_favour_what_was_written_first() -> None:
    """Twenty of forty identical rows come from both halves of the ids.

    Ids are creation order, so a draw in id order is a draw of whatever the
    run happened to write first: the first topics claimed, in the first
    language.
    """
    held = [row(at) for at in range(1, 41)]
    quota = quota_of(20, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    drawn = choose(held, quota).ids
    early = sum(at <= 20 for at in drawn)

    assert len(drawn) == 20
    assert 5 <= early <= 15, drawn
    assert choose(held, quota).ids == drawn


# ── Twins ──────────────────────────────────────────────────────────────────


def ranked(id: int, kind: str = QuestionType.FACTOID) -> Row:
    """One accepted easy question of this kind."""
    return Row(id=id, answerable=True, difficulty=Difficulty.EASY, question_type=kind)


def test_twins_in_one_cell_release_one_of_them() -> None:
    """A set that asks the same thing twice weights it twice."""
    held = [ranked(1), ranked(2), ranked(3)]
    quota = quota_of(3, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    drawn = set(choose(held, quota, twins={1: {2}, 2: {1}}).ids)

    assert len(drawn) == 2
    assert 3 in drawn and len(drawn & {1, 2}) == 1, drawn


def test_twins_in_different_cells_release_one_of_them() -> None:
    """Two kinds asking one thing are still one thing asked."""
    held = [
        ranked(1),
        ranked(2, QuestionType.REASON),
        ranked(3),
        ranked(4, QuestionType.REASON),
    ]
    quota = quota_of(4, {Difficulty.EASY: 1}, TYPES, 0.0)

    drawn = set(choose(held, quota, twins={1: {2}, 2: {1}}).ids)

    assert len(drawn & {1, 2}) == 1, drawn


def test_a_thread_is_cut_at_a_turn_that_twins_what_is_already_in() -> None:
    """A follow-up asking its root's question again ends the thread there.

    The turns before it stay: they are a conversation, and the rest of it
    reads only after the turn that was cut.
    """
    held = [
        ranked(1),
        Row(2, True, Difficulty.EASY, QuestionType.REASON, follows_id=1),
        Row(3, True, Difficulty.EASY, QuestionType.REASON, follows_id=2),
        Row(4, True, Difficulty.EASY, QuestionType.REASON, follows_id=3),
    ]
    quota = quota_of(4, {Difficulty.EASY: 1}, TYPES, 0.0)

    drawn = choose(held, quota, twins={1: {3}, 3: {1}}).ids

    assert drawn == [1, 2]


def test_of_two_twins_the_one_the_draw_ranks_first_is_kept() -> None:
    """Whichever was written first: 6 ranks first, by the hash the draw reads.

    Not the one the gates were surer of. The later twin's weakest margin is
    its `near_duplicate` reading against the earlier one, held near 0, so
    that kept the earlier twin nearly every time.
    """
    held = [ranked(5), ranked(6), ranked(3)]
    quota = quota_of(2, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    drawn = set(choose(held, quota, twins={5: {6}, 6: {5}}).ids)

    assert 6 in drawn and 5 not in drawn, drawn


def test_each_question_is_ranked_once_however_long_the_draw(monkeypatch) -> None:
    """The hash is read off a table, not taken again on every step."""
    from question_generation import balance

    taken: list[int] = []
    hashed = balance._rank

    def counted(one: Row) -> str:
        taken.append(one.id)
        return hashed(one)

    monkeypatch.setattr(balance, "_rank", counted)
    held = written_in(("de", "en"), per_cell=5)

    drawn = choose(held, quota_of(30, BANDS, TYPES, 0.0, LANGUAGES))

    assert drawn.size == 30
    assert len(taken) == len(held), len(taken)


def test_a_release_written_short_of_its_draw_says_so(caplog) -> None:
    """The draw was 3, the write 2: one line gives both and warns."""
    import logging
    import uuid

    pool = [
        Row(id=i, answerable=True, difficulty="easy", question_type="factoid")
        for i in (1, 2, 3)
    ]
    release = Release([1, 2, 3], Quota(3, 0, {"easy": 3}, {"factoid": 3}), {})

    with caplog.at_level(logging.INFO):
        _report(pool, release, uuid.uuid4(), 2)

    assert "drew 3, wrote 2" in caplog.text
    assert any(
        r.levelno == logging.WARNING and "drew 3" in r.message for r in caplog.records
    )


def test_a_release_written_whole_does_not_warn(caplog) -> None:
    """Drawn equals written: the line is there, the warning is not."""
    import logging
    import uuid

    pool = [
        Row(id=i, answerable=True, difficulty="easy", question_type="factoid")
        for i in (1, 2)
    ]
    release = Release([1, 2], Quota(2, 0, {"easy": 2}, {"factoid": 2}), {})

    with caplog.at_level(logging.INFO):
        _report(pool, release, uuid.uuid4(), 2)

    assert "drew 2, wrote 2" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ── What a follow-up may spend ─────────────────────────────────────────────


def _thread(follow: Row, **quota) -> list[int]:
    """What a draw of root 1 and its follow-up 2 releases under this quota."""
    root = Row(1, True, Difficulty.EASY, QuestionType.FACTOID, language="de")
    wanted = {
        "size": 2,
        "unanswerable": 0,
        "difficulty": {Difficulty.EASY: 2},
        "types": {QuestionType.FACTOID: 2},
        "languages": {"de": 2},
    } | quota
    return choose([root, follow], Quota(**wanted)).ids


@pytest.mark.parametrize(
    ("follow", "quota"),
    [
        (Row(2, True, Difficulty.HARD, QuestionType.FACTOID, 1, "de"), {}),
        (
            Row(2, True, Difficulty.HARD, QuestionType.FACTOID, 1, "de"),
            {"difficulty": {Difficulty.EASY: 2, Difficulty.HARD: 0}},
        ),
        (Row(2, True, Difficulty.EASY, QuestionType.REASON, 1, "de"), {}),
        (Row(2, True, Difficulty.EASY, QuestionType.FACTOID, 1, "el"), {}),
        (
            Row(2, True, Difficulty.EASY, QuestionType.FACTOID, 1, "el"),
            {"languages": {"de": 2, "el": 0}},
        ),
        (Row(2, False, Difficulty.EASY, QuestionType.FACTOID, 1, "de"), {}),
    ],
    ids=[
        "band-unweighted",
        "band-full",
        "kind-unweighted",
        "language-unweighted",
        "language-full",
        "no-unanswerable-place",
    ],
)
def test_a_follow_up_with_no_place_left_in_a_bucket_ends_the_thread(
    follow: Row, quota: dict
) -> None:
    """The same test a root passes: a release never holds a bucket past its quota."""
    assert _thread(follow, **quota) == [1]


def test_a_follow_up_taking_the_last_place_of_its_language_is_released() -> None:
    """One place left is a place."""
    follow = Row(2, True, Difficulty.EASY, QuestionType.FACTOID, 1, "fr")

    assert _thread(follow, languages={"de": 1, "fr": 1}) == [1, 2]


def test_a_refused_follow_up_does_not_take_its_sibling_with_it() -> None:
    """Two follow-ups of one root: the one that fits is still released."""
    held = [
        ranked(1),
        Row(2, True, Difficulty.EASY, QuestionType.REASON, follows_id=1),
        Row(3, True, Difficulty.EASY, QuestionType.FACTOID, follows_id=1),
    ]
    quota = quota_of(2, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    assert choose(held, quota).ids == [1, 3]


def test_a_follow_up_twinning_the_thread_does_not_take_its_sibling_with_it() -> None:
    """A follow-up asking its root's question again is cut, not the root's others."""
    held = [
        ranked(1),
        Row(2, True, Difficulty.EASY, QuestionType.FACTOID, follows_id=1),
        Row(3, True, Difficulty.EASY, QuestionType.FACTOID, follows_id=1),
    ]
    quota = quota_of(3, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    assert choose(held, quota, twins={1: {2}, 2: {1}}).ids == [1, 3]


def test_a_root_of_a_band_the_mix_does_not_weigh_is_never_drawn() -> None:
    """A band switched off is not a band with places to spare."""
    held = [ranked(1), Row(2, True, Difficulty.HARD, QuestionType.FACTOID)]
    quota = quota_of(2, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0)

    assert choose(held, quota).ids == [1]


def test_a_twin_in_another_cell_ranked_first_is_drawn_in_its_place() -> None:
    """Of twins 5 and 7 the draw keeps 7, ranked first, though 5's cell leads."""
    quota = Quota(
        size=6,
        unanswerable=1,
        difficulty={E: 2, M: 4},
        types={F: 2, R: 4},
        languages={"de": 3, "en": 3},
    )
    held = _rows(
        (1, True, M, F, "en"),
        (2, True, E, R, "de"),
        (3, True, E, F, "de"),
        (4, True, E, F, "de"),
        (5, True, M, R, "de"),
        (6, True, E, F, "de"),
        (7, True, E, R, "en"),
        (8, False, M, F, "en"),
    )

    drawn = set(choose(held, quota, twins={5: {7}, 7: {5}}).ids)

    assert 7 in drawn and 5 not in drawn, drawn


# ── What a release reports short ──────────────────────────────────────────


def test_a_release_one_place_short_reports_the_one_place() -> None:
    """One place missing is still missing, in its band, its kind and its answerable count."""
    release = choose(
        [ranked(1), ranked(2)],
        quota_of(3, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0),
    )

    assert release.short == {
        Difficulty.EASY: 1,
        QuestionType.FACTOID: 1,
        "answerable": 1,
    }


def test_unanswerable_places_left_unfilled_are_not_reported_short() -> None:
    """The unanswerable share is a ceiling, not a target."""
    held = [ranked(1), ranked(2), Row(3, False, Difficulty.EASY, QuestionType.FACTOID)]
    release = choose(
        held, quota_of(4, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.5)
    )

    assert release.short == {
        Difficulty.EASY: 1,
        QuestionType.FACTOID: 1,
        "answerable": 1,
    }


def test_two_places_short_of_a_small_quota_is_not_close_enough() -> None:
    """One place is always forgiven; two of ten at a tenth's tolerance are not."""
    short = Release(
        ids=[1],
        quota=quota_of(
            20, {Difficulty.EASY: 1, Difficulty.HARD: 1}, {QuestionType.FACTOID: 1}, 0.0
        ),
        short={Difficulty.HARD: 2},
    )

    assert not close_enough(short)


def test_answerable_places_short_are_weighed_against_the_answerable_quota() -> None:
    """Twenty places, ten unanswerable: two answerable short of ten is too many."""
    short = Release(
        ids=[1],
        quota=quota_of(20, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.5),
        short={"answerable": 2},
    )

    assert not close_enough(short)


# ── What the scan hands back ───────────────────────────────────────────────


def test_an_empty_pool_hands_back_an_empty_quota() -> None:
    """Nothing to draw asks for nothing, in every language it weighs."""
    release = largest([], BANDS, TYPES, 0.0, languages={"de": 1, "en": 1})

    assert release.quota.size == 0
    assert release.quota.languages == {"de": 0, "en": 0}


def test_a_pool_of_one_question_releases_it() -> None:
    """The smallest release is one question, not none."""
    assert largest(
        [ranked(1)], {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0
    ).ids == [1]


def test_a_language_the_mix_does_not_weigh_leaves_the_rest_drawable() -> None:
    """A Greek question ranked first is passed over, not the end of the pool."""
    held = [Row(27, True, Difficulty.EASY, QuestionType.FACTOID, language="el")] + [
        Row(i, True, Difficulty.EASY, QuestionType.FACTOID, language="de")
        for i in (6, 33, 36)
    ]

    release = largest(
        held, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0, languages={"de": 1}
    )

    assert release.ids == [6, 33, 36]


E, M = Difficulty.EASY, Difficulty.MEDIUM
F, R = QuestionType.FACTOID, QuestionType.REASON


def _rows(*cells: tuple[int, bool, str, str, str]) -> list[Row]:
    """Rows given as (id, answerable, band, kind, language)."""
    return [
        Row(i, answerable, band, kind, language=lang)
        for i, answerable, band, kind, lang in cells
    ]


#: Pools each holding a release that meets every quota exactly, beside the quota.
_FILLABLE = {
    "bands": (
        _rows(
            (1, True, M, R, "de"),
            (2, False, M, F, "en"),
            (3, True, M, F, "en"),
            (4, True, M, R, "de"),
            (5, False, E, F, "de"),
            (6, False, E, R, "en"),
            (7, True, M, R, "en"),
        ),
        Quota(3, 1, {E: 1, M: 2}, {F: 1, R: 2}),
    ),
    "kinds": (
        _rows(
            (1, True, E, R, "en"),
            (2, True, E, R, "en"),
            (3, False, M, R, "de"),
            (4, True, E, F, "en"),
            (5, True, M, F, "en"),
            (6, False, E, R, "de"),
            (7, True, M, R, "de"),
            (8, False, E, R, "en"),
            (9, True, M, F, "de"),
            (10, True, M, F, "de"),
        ),
        Quota(4, 0, {E: 2, M: 2}, {F: 3, R: 1}),
    ),
    "answerability": (
        _rows(
            (1, True, E, R, "de"),
            (2, True, M, F, "de"),
            (3, True, E, F, "en"),
            (4, True, E, F, "de"),
            (5, True, M, R, "de"),
            (6, True, E, F, "en"),
            (7, False, M, R, "de"),
            (8, True, E, F, "en"),
            (9, True, E, F, "de"),
            (10, True, E, F, "en"),
        ),
        Quota(4, 1, {E: 2, M: 2}, {F: 3, R: 1}),
    ),
    "languages": (
        _rows(
            (1, True, E, F, "de"),
            (2, True, M, F, "de"),
            (3, True, E, F, "en"),
            (4, True, M, F, "de"),
            (5, True, M, R, "de"),
            (6, True, M, R, "en"),
            (7, True, E, R, "de"),
        ),
        Quota(5, 1, {E: 3, M: 2}, {F: 3, R: 2}, {"de": 3, "en": 2}),
    ),
    "one-language-place": (
        _rows(
            (1, False, M, F, "en"),
            (2, True, E, F, "de"),
            (3, True, E, R, "en"),
            (4, True, E, F, "en"),
            (5, True, M, R, "en"),
            (6, False, M, F, "de"),
            (7, False, E, R, "en"),
        ),
        Quota(4, 1, {E: 2, M: 2}, {F: 2, R: 2}, {"de": 1, "en": 3}),
    ),
}


@pytest.mark.parametrize("case", list(_FILLABLE))
def test_a_quota_the_pool_can_fill_is_filled_whole(case: str) -> None:
    """Largest deficit first, as a share of each bucket's quota.

    Each pool holds a release meeting every quota exactly. A draw weighing
    the buckets by raw counts, or one of them by a share of the wrong size,
    takes a cell early that another bucket needed and ends short.
    """
    held, quota = _FILLABLE[case]

    release = choose(held, quota)

    assert (release.size, release.short) == (quota.size, {})


# ── The scan past `_BY_ONES`, at a size a unit test can hold ────────────────

#: Pools the scan reads with its stride lowered from 100 above 2,000 to a
#: few above a few, beside the mixes, the unanswerable share and the
#: tolerance, the stride and where it starts, and the release size it finds.
_STRIDED = {
    "steps-back-over-a-stride": (
        {
            (E, F, True): 8,
            (E, R, True): 9,
            (M, F, True): 9,
            (M, F, False): 1,
            (M, R, True): 7,
            (M, R, False): 3,
        },
        {E: 2, M: 2},
        {F: 3, R: 2},
        0.1,
        0.0,
        (10, 4),
        33,
    ),
    "fills-one-below-a-failure": (
        {
            (E, F, True): 2,
            (E, F, False): 1,
            (E, R, True): 1,
            (E, R, False): 2,
            (M, F, True): 8,
            (M, F, False): 3,
            (M, R, True): 5,
            (M, R, False): 3,
        },
        {E: 2, M: 3},
        {F: 1, R: 1},
        0.2,
        0.0,
        (10, 4),
        12,
    ),
    "loose-tolerance": (
        {
            (E, F, True): 6,
            (E, R, True): 2,
            (E, R, False): 1,
            (M, F, True): 2,
            (M, R, True): 2,
            (M, R, False): 3,
        },
        {E: 3, M: 1},
        {F: 3, R: 3},
        0.1,
        0.3,
        (6, 2),
        12,
    ),
    "loose-tolerance-wide-stride": (
        {
            (E, F, True): 5,
            (E, F, False): 1,
            (E, R, True): 7,
            (E, R, False): 3,
            (M, R, True): 8,
            (M, R, False): 2,
        },
        {E: 2, M: 3},
        {F: 2, R: 3},
        0.1,
        0.3,
        (12, 5),
        17,
    ),
    "strided-from-the-threshold": (
        {
            (E, F, True): 5,
            (E, F, False): 2,
            (E, R, True): 1,
            (E, R, False): 3,
            (M, F, True): 1,
            (M, F, False): 1,
            (M, R, True): 4,
            (M, R, False): 1,
        },
        {E: 2, M: 3},
        {F: 3, R: 1},
        0.0,
        0.3,
        (8, 3),
        4,
    ),
}


@pytest.mark.parametrize("case", list(_STRIDED))
def test_the_strided_scan_finds_the_largest_fill_below_the_size_that_failed(
    monkeypatch, case: str
) -> None:
    """The sizes the last stride stepped over are tried from the top.

    The first of them that fills is the release, at the tolerance asked for,
    so the stride costs at most the sizes it passed over between two that
    both failed.
    """
    from question_generation import balance

    counts, bands, types, unanswerable, tolerance, (by_ones, stride), size = _STRIDED[
        case
    ]
    monkeypatch.setattr(balance, "_BY_ONES", by_ones)
    monkeypatch.setattr(balance, "_STRIDE", stride)

    release = largest(pool(counts), bands, types, unanswerable, tolerance)

    assert release.size == size


def test_the_scan_never_asks_for_more_than_the_pool_holds() -> None:
    """The largest size tried is the pool's own: a quota past it is one no row can fill."""
    counts = {
        (E, F, True): 7,
        (E, F, False): 2,
        (E, R, True): 1,
        (M, F, True): 6,
        (M, F, False): 1,
        (M, R, True): 7,
        (M, R, False): 1,
    }
    held = pool(counts)

    release = largest(held, {E: 2, M: 3}, {F: 2, R: 1}, 0.2)

    assert release.quota.size <= len(held)


# ── A kind capped at what the pool holds ───────────────────────────────────

C, A = QuestionType.CONDITION, QuestionType.AGGREGATION


def test_a_kind_the_pool_holds_none_of_is_given_no_freed_place() -> None:
    """The places a capped kind gives up go to kinds that have rows for them."""
    quota = quota_of(
        6,
        {E: 1},
        {F: 4, R: 4, C: 1, A: 5},
        0.0,
        supply={F: 1, R: 10, A: 0},
        tolerance=0.2,
    )

    assert quota.types[C] == 0


def test_every_place_a_capped_kind_frees_is_placed_where_there_is_room() -> None:
    """Five places, one kind with no rows: the others take all five between them."""
    quota = quota_of(
        5, {E: 1}, {F: 1, R: 2, C: 1, A: 3}, 0.0, supply={F: 3, C: 7}, tolerance=0.2
    )

    assert sum(quota.types.values()) == 5
    assert quota.types[A] == 0


@pytest.mark.parametrize(
    ("counts", "bands", "types", "unanswerable", "tolerance", "size"),
    [
        (
            {
                (E, F, False): 4,
                (E, R, True): 1,
                (M, F, False): 1,
                (M, R, True): 3,
                (M, R, False): 4,
            },
            {E: 1, M: 2},
            {F: 2, R: 2},
            0.3,
            0.1,
            6,
        ),
        (
            {
                (E, F, True): 6,
                (E, F, False): 2,
                (E, R, True): 7,
                (E, R, False): 1,
                (M, F, True): 6,
                (M, F, False): 2,
                (M, R, True): 8,
                (M, R, False): 2,
            },
            {E: 3, M: 3},
            {F: 2, R: 3},
            0.3,
            0.0,
            33,
        ),
    ],
    ids=["unanswerable-heavy", "exact-tolerance"],
)
def test_the_scan_starts_no_lower_than_the_largest_size_that_fills(
    counts, bands, types, unanswerable: float, tolerance: float, size: int
) -> None:
    """A start bound counting the wrong rows, or at the wrong tolerance, begins under a fill."""
    assert largest(pool(counts), bands, types, unanswerable, tolerance).size == size
