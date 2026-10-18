"""Invariants of the arithmetic question generation is built on.

The example tests say what these functions do to the corpus in front of
them. These say what must hold for any corpus at all - a quota that sums to
the size asked for, an ordering that drops nothing, a band that agrees with
its own score, and a figure reader that reads a number wherever a sentence
happens to put it.

Every one of them is pure and total, so there is nothing to stub and no
deadline worth setting. The ones marked `nlp` read a spaCy parse, and are
pure all the same.
"""

from __future__ import annotations

from collections import Counter
from math import ceil, floor, isinf, isnan

import pytest
from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import AnswerForm, Difficulty, QuestionType
from question_generation.balance import (
    Quota,
    Row,
    choose,
    composition,
    quota_of,
    shares,
)
from question_generation.gates import BOUNDS, agrees, figures, fitting, restates
from question_generation.models import Categorization, Category, band, criteria_of
from question_generation.planning import categories
from question_generation.selection import spread, strided
from question_generation.types import SPECS

#: A mix as a setting writes one: names nobody has to be told, weights that
#: may include a zero, and at least one that is not.
WEIGHTS = st.dictionaries(
    st.sampled_from("abcdefg"), st.integers(0, 9), min_size=1, max_size=7
).filter(lambda mix: any(weight > 0 for weight in mix.values()))


# ── Spreading a size over named weights ──────────────────────────────────


@given(weights=WEIGHTS, size=st.integers(0, 500))
def test_a_spread_sums_to_exactly_the_size_asked_for(weights, size) -> None:
    """Largest remainder: the leftovers are handed out, not dropped."""
    assert sum(shares(weights, size).values()) == size


@given(weights=WEIGHTS, size=st.integers(0, 500))
def test_a_spread_names_every_weight_and_invents_none(weights, size) -> None:
    """A caller reads the answer by name, so a missing key is a KeyError."""
    assert set(shares(weights, size)) == set(weights)


@given(weights=WEIGHTS, size=st.integers(0, 500))
def test_nothing_is_given_a_negative_share(weights, size) -> None:
    """A share below zero is a quota that can never be filled."""
    assert all(count >= 0 for count in shares(weights, size).values())


@given(weights=WEIGHTS, size=st.integers(1, 500))
def test_a_weight_of_zero_never_takes_a_place(weights, size) -> None:
    """Which is how a type is turned off."""
    given_out = shares(weights, size)

    assert all(given_out[name] == 0 for name, w in weights.items() if w <= 0)


@given(weights=WEIGHTS, size=st.integers(0, 200))
def test_the_same_weights_spread_the_same_way_twice(weights, size) -> None:
    """A reference dataset whose composition moves is not a reference."""
    assert shares(weights, size) == shares(dict(reversed(list(weights.items()))), size)


# ── Dealing a topic's passages ───────────────────────────────────────────


@given(items=st.lists(st.integers(), max_size=40), wanted=st.integers(-2, 40))
def test_striding_drops_nothing_and_invents_nothing(items, wanted) -> None:
    """The first `wanted` are spread; the rest follow in their own order."""
    assert sorted(strided(list(items), wanted)) == sorted(items)


@given(share=st.floats(0.0, 1.0), over=st.integers(1, 200))
def test_a_share_picks_about_that_share_of_them(share, over) -> None:
    """Spread by position, so it picks one in every `1/share` exactly."""
    picked = sum(1 for index in range(over) if spread(index, share))

    assert abs(picked - over * share) <= 1


# ── The band a question turns out to be ──────────────────────────────────


@given(
    passages=st.integers(1, 6),
    documents=st.integers(1, 6),
    topics=st.integers(0, 6),
    answer_chars=st.one_of(st.none(), st.integers(0, 2000)),
    follows=st.booleans(),
    long_answer=st.integers(1, 500),
)
def test_a_band_always_agrees_with_its_own_score(
    passages, documents, topics, answer_chars, follows, long_answer
) -> None:
    """A row disagreeing with its own score is what this exists to catch.

    `criteria_of` is read three times - by the service, by the writer and
    by a re-check - and the band has to be recomputable from the object.
    """
    read = criteria_of(
        passages=passages,
        documents=documents,
        topics=topics,
        answer_chars=answer_chars,
        follows=follows,
        long_answer=long_answer,
    )

    assert read.difficulty == band(read.score)


@given(score=st.integers(0, 5))
def test_a_band_never_falls_as_the_score_rises(score) -> None:
    """More of the things that make a question harder is never easier."""
    order = {Difficulty.EASY: 0, Difficulty.MEDIUM: 1, Difficulty.HARD: 2}

    assert order[band(score)] <= order[band(score + 1)]


# ── Drawing a release ────────────────────────────────────────────────────

_BANDS = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)
_TYPES = (QuestionType.FACTOID, QuestionType.REASON, QuestionType.COMPARISON)

POOL = st.lists(
    st.tuples(st.booleans(), st.sampled_from(_BANDS), st.sampled_from(_TYPES)),
    max_size=60,
)


@given(pool=POOL, size=st.integers(0, 40))
def test_a_draw_never_exceeds_the_size_it_was_asked_for(pool, size) -> None:
    """A release larger than its quota is a quota that decided nothing."""
    rows = [
        Row(id=at, answerable=a, difficulty=b, question_type=t)
        for at, (a, b, t) in enumerate(pool, 1)
    ]
    quota = quota_of(size, dict.fromkeys(_BANDS, 1), dict.fromkeys(_TYPES, 1), 0.3)

    assert choose(rows, quota).size <= size


@given(pool=POOL, size=st.integers(0, 40))
def test_a_draw_takes_each_question_at_most_once(pool, size) -> None:
    """A cell is popped from, so a row cannot fill two places."""
    rows = [
        Row(id=at, answerable=a, difficulty=b, question_type=t)
        for at, (a, b, t) in enumerate(pool, 1)
    ]
    quota = quota_of(size, dict.fromkeys(_BANDS, 1), dict.fromkeys(_TYPES, 1), 0.3)
    drawn = choose(rows, quota).ids

    assert len(drawn) == len(set(drawn))
    assert set(drawn) <= {row.id for row in rows}


@given(pool=POOL, size=st.integers(0, 40))
def test_a_draw_never_takes_more_unanswerable_than_the_ceiling(pool, size) -> None:
    """A ceiling and not a target: too many tests whether a chatbot says no."""
    rows = [
        Row(id=at, answerable=a, difficulty=b, question_type=t)
        for at, (a, b, t) in enumerate(pool, 1)
    ]
    quota = quota_of(size, dict.fromkeys(_BANDS, 1), dict.fromkeys(_TYPES, 1), 0.3)
    by_id = {row.id: row for row in rows}
    drawn = choose(rows, quota).ids

    assert sum(1 for one in drawn if not by_id[one].answerable) <= quota.unanswerable


@given(pool=POOL, size=st.integers(0, 40))
def test_the_same_pool_draws_the_same_release_twice(pool, size) -> None:
    """Ties go by a hash of the id, so nothing here is order-dependent."""
    rows = [
        Row(id=at, answerable=a, difficulty=b, question_type=t)
        for at, (a, b, t) in enumerate(pool, 1)
    ]
    quota = quota_of(size, dict.fromkeys(_BANDS, 1), dict.fromkeys(_TYPES, 1), 0.3)

    assert choose(rows, quota).ids == choose(list(reversed(rows)), quota).ids


_LANGUAGES = ("de", "en", "fr")


@given(
    size=st.integers(0, 12),
    weights=st.fixed_dictionaries(
        {language: st.integers(0, 3) for language in _LANGUAGES}
    ).filter(lambda mix: any(mix.values())),
    written=st.permutations(_LANGUAGES),
    extra=st.lists(
        st.tuples(
            st.sampled_from(_BANDS),
            st.sampled_from(_TYPES),
            st.sampled_from(_LANGUAGES),
        ),
        max_size=30,
    ),
)
def test_every_language_that_can_fill_its_share_is_released_at_it(
    size, weights, written, extra
) -> None:
    """The language a run wrote first takes no more than its share.

    A run writes one language's topics before the next, so its ids come in
    one block per language. Drawn by id, or by anything that ignores
    language, the first block fills every cell before the next is reached.

    Over a pool where every language holds every band and kind `size` deep,
    so each one can fill whatever share it is weighed to, and whatever else
    on top. There the draw fills every quota, so each language comes out
    within a place of its own.
    """
    pool = [
        (band, kind, language)
        for language in written
        for band in _BANDS
        for kind in _TYPES
        for _ in range(size)
    ] + extra
    rows = [
        Row(id=at, answerable=True, difficulty=b, question_type=t, language=lang)
        for at, (b, t, lang) in enumerate(pool, 1)
    ]
    quota = quota_of(
        size, dict.fromkeys(_BANDS, 1), dict.fromkeys(_TYPES, 1), 0.0, weights
    )

    got = composition(rows, choose(rows, quota).ids)["language"]

    for language in _LANGUAGES:
        assert abs(got[language] - quota.languages[language]) <= 1, (language, got)


@given(
    counts=st.fixed_dictionaries(
        {language: st.integers(0, 40) for language in _LANGUAGES}
    ).filter(lambda held: any(held.values())),
    size=st.integers(1, 40),
)
def test_an_unset_language_share_holds_each_language_to_its_share_of_the_pool(
    counts, size
) -> None:
    """QUESTIONS_RELEASE_LANGUAGES unset: the pool's own split is the share.

    Each language comes out within a place of the release size times its
    part of the pool, however lopsided the pool is.
    """
    from dataclasses import replace
    from uuid import uuid4

    from unit.questions.test_question_service import SETTINGS

    from question_generation.service import balance

    written = [language for language, count in counts.items() for _ in range(count)]
    rows = [
        Row(
            id=at,
            answerable=True,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language=language,
        )
        for at, language in enumerate(written, 1)
    ]
    size = min(size, len(rows))
    drawn: list[int] = []

    class Catalog:
        """Offers the rows, holds no twin, and keeps what was drawn."""

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return rows

        def twins(self, floor):
            return []

        def release(self, ids):
            drawn[:] = ids
            return uuid4(), len(drawn)

    balance(
        Catalog(),
        replace(
            SETTINGS,
            release_size=size,
            release_difficulty={Difficulty.EASY: 1},
            release_unanswerable=0.0,
            release_types={QuestionType.FACTOID: 1},
            release_languages=None,
        ),
    )

    got = composition(rows, drawn)["language"]
    for language, count in counts.items():
        assert abs(got[language] - size * count / len(rows)) <= 1, (language, got)


def test_an_empty_quota_draws_an_empty_release() -> None:
    """A pool with nothing in it is not an error."""
    assert choose([], Quota(size=5, unanswerable=1, difficulty={}, types={})).ids == []


# ── Reading a number out of a sentence ───────────────────────────────────


@given(
    value=st.integers(0, 10**9),
    before=st.sampled_from(["", "There were ", "Total: ", "(", "about "]),
    after=st.sampled_from(["", ".", ",", " people.", ")", " in total"]),
)
def test_a_whole_number_is_read_wherever_a_sentence_puts_it(
    value, before, after
) -> None:
    """The gap this closes: 1200 in `1200.` was not a figure at all.

    A four-digit number before a full stop matched neither alternative of
    the pattern, so an aggregation over it was refused for finding no
    arithmetic.
    """
    assert float(value) in figures(f"{before}{value}{after}")


@given(value=st.integers(1, 999), group=st.integers(100, 999))
def test_a_thousands_group_is_one_number_in_either_convention(value, group) -> None:
    """1.234 and 1,234 are 1234 where no language names its decimal mark.

    From 1: a head of zeros carries no thousands, so 0.125 is a fraction.
    """
    expected = float(f"{value}{group:03d}")

    assert figures(f"{value}.{group:03d}") == [expected]
    assert figures(f"{value},{group:03d}") == [expected]


@given(group=st.integers(0, 999))
def test_a_zero_head_is_a_fraction_in_either_convention(group) -> None:
    """0,125 % is an eighth of a percent, in German as 0.125 % is in English."""
    assert figures(f"0,{group:03d}", "de") == [group / 1000]
    assert figures(f"0.{group:03d}", "en") == [group / 1000]


@given(value=st.integers(1, 999), group=st.integers(0, 999))
def test_a_thousands_group_is_read_by_the_languages_mark(value, group) -> None:
    """German writes 1,234 for a rate and 1.234 for a count; English the reverse."""
    count = float(f"{value}{group:03d}")
    rate = float(f"{value}.{group:03d}")

    assert figures(f"{value}.{group:03d}", "de") == [count]
    assert figures(f"{value},{group:03d}", "de") == [rate]
    assert figures(f"{value},{group:03d}", "en") == [count]
    assert figures(f"{value}.{group:03d}", "en") == [rate]


@given(text=st.text(max_size=200))
def test_reading_figures_never_raises_and_never_returns_a_nan(text) -> None:
    """It is handed passage text, which is whatever the corpus holds."""
    found = figures(text)

    assert not any(isnan(one) or isinf(one) for one in found), found


# ── The form an answer is read in ────────────────────────────────────────

#: Two things a key may name, in a language NLP_MODELS configures: noun
#: phrases carrying no verb, which is what the property covers. A verb on
#: either side - and a participle inside a noun phrase is one, `a failed
#: login` tags `failed` VERB - makes the pair an explanation wherever the
#: type takes that form.
ITEMS = st.sampled_from(
    [
        (
            "en",
            ("card fraud", "a court order", "a theft report", "an unpaid balance"),
        ),
        (
            "de",
            (
                "ein Betrugsverdacht",
                "eine Pfändung",
                "eine Kontosperre",
                "ein Gerichtsbeschluss",
            ),
        ),
    ]
).flatmap(
    lambda pair: st.tuples(
        st.just(pair[0]), st.sampled_from(pair[1]), st.sampled_from(pair[1])
    )
)

#: The forms of every type that asks for a list before anything else.
LIST_FIRST = [spec.forms for spec in SPECS.values() if spec.forms[0] == AnswerForm.LIST]


@pytest.mark.nlp
@given(
    items=ITEMS, forms=st.sampled_from(LIST_FIRST), joined=st.sampled_from([",", ";"])
)
def test_a_two_item_answer_to_a_list_first_type_is_read_as_a_list(
    items, forms, joined
) -> None:
    """Which is what puts it in front of `answer_incomplete`.

    The shape hint wants three items before it calls an answer a list, so
    `Berlin, 2025` is a value where a value was asked for. A type that asked
    for a list first is taken at its word for two that carry no verb.
    """
    language, first, second = items

    form, failed = fitting(f"{first}{joined} {second}", forms, BOUNDS, language)

    assert failed is None
    assert form == AnswerForm.LIST


# ── The answer that only says the question again ─────────────────────────


@pytest.mark.nlp
@given(
    noun=st.sampled_from(["device", "transfer", "account", "request", "card"]),
    verb=st.sampled_from(["cancelled", "approved", "rejected", "shipped", "refunded"]),
)
def test_a_predicate_the_question_lacks_is_something_new(noun, verb) -> None:
    """`The card is cancelled.` answers `What happens to the card?` with its verb."""
    assert not restates(
        f"What happens to the {noun} in that case?", f"The {noun} is {verb}.", "en"
    )


# ── A number, however it is written ──────────────────────────────────────

#: Two to twelve written out, and what is counted, in the two configured
#: languages. Written here rather than read off the gate, so the gate's own
#: table is what is tested.
WRITTEN = {
    "en": ("two three four five six seven eight nine ten eleven twelve", "hours"),
    "de": ("zwei drei vier fünf sechs sieben acht neun zehn elf zwölf", "Stunden"),
}


def _written(n: int, language: str, words: bool) -> str:
    """`n` hours, in words where that is asked for and there is a word."""
    counts, unit = WRITTEN[language]
    spelled = counts.split()
    number = spelled[n - 2] if words and 2 <= n <= len(spelled) + 1 else str(n)
    return f"{number} {unit}"


@pytest.mark.nlp
@given(
    n=st.integers(2, 12),
    language=st.sampled_from(sorted(WRITTEN)),
    recovered_in_words=st.booleans(),
    target_in_words=st.booleans(),
)
def test_a_count_is_the_same_count_in_words_or_digits_and_no_other(
    n, language, recovered_in_words, target_in_words
) -> None:
    """`zehn Stunden` is `10 Stunden`, and neither is `11 Stunden`."""
    recovered = _written(n, language, recovered_in_words)

    assert agrees(recovered, _written(n, language, target_in_words), language)
    assert not agrees(recovered, _written(n + 1, language, target_in_words), language)
    assert not agrees(_written(n + 1, language, target_in_words), recovered, language)


# ── Dealing the paper's categories ───────────────────────────────────────


def _categorization(name: str, weights: list[float]) -> Categorization:
    """A categorization whose probabilities are these weights, scaled to 1."""
    total = sum(weights)
    return Categorization(
        name=name,
        categories=tuple(
            Category(name, f"{name}{i}", "a question", weight / total)
            for i, weight in enumerate(weights)
        ),
    )


#: Two even categorizations, the smallest case where pairings can be missed.
_PAIRED = (_categorization("a", [1, 1]), _categorization("b", [1, 1]))


@given(
    weights=st.lists(st.floats(0, 1), min_size=1, max_size=5).filter(
        lambda weights: sum(weights) > 0
    ),
    slots=st.integers(0, 300),
    seed=st.text(max_size=8),
)
def test_each_category_is_dealt_its_share_rounded_one_way_or_the_other(
    weights, slots, seed
) -> None:
    """A quota, not a draw: no category is short of its share by a whole slot."""
    one = _categorization("c", weights)
    dealt = categories((one,), slots, seed)
    assert len(dealt) == slots
    counted = Counter(category.name for (category,) in dealt)
    for category in one.categories:
        exact = slots * category.probability
        assert floor(exact) <= counted[category.name] <= ceil(exact)


@given(slots=st.integers(0, 200), seed=st.text(max_size=8))
def test_the_same_seed_deals_the_same_categories(slots, seed) -> None:
    """Nothing random: a rerun over a topic is told what the first run was."""
    assert categories(_PAIRED, slots, seed) == categories(_PAIRED, slots, seed)


@given(seed=st.text(max_size=8))
def test_two_categorizations_meet_in_every_pairing(seed) -> None:
    """Over a topic's 120 slots, every combination of the two is written."""
    dealt = categories(_PAIRED, 120, seed)
    assert len({tuple(category.name for category in one) for one in dealt}) == 4
