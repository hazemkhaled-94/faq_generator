"""What must hold of this cycle's new logic for any input at all.

The example tests pin the passages, keys and mixes this corpus holds. These
say what must hold for a corpus, a number, a list or a mix nobody has seen:
the links the documents give, the refusal of a range for a plain figure, the items a recovery
adds to a key, the atomic cap beside repaired pieces and the kinds an
unanswerable slot takes.
"""

from __future__ import annotations

import string
from collections import Counter
from dataclasses import replace

import pytest
from drivers import passage
from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import FactKind
from extraction.extractors.llm import REPAIR_PROMPT_VERSION
from extraction.links import linked
from extraction.models import CheckedFact
from extraction.service import over_cap
from question_generation.gates import agrees, unnamed
from question_generation.planning import PERTURBABLE, plans
from question_generation.types import SPECS

# ── Links ──────────────────────────────────────────────────────────────────

#: Headings with a number, without one, and none at all.
TRAILS = st.sampled_from(
    [
        "Part A > Section 1",
        "Part A > Section 2",
        "Part B > Section 3",
        "Section 4",
        "Chapter 2 > Rules",
        "Part A > Fees",
        "Part B > Fees",
        "Fees",
        None,
    ]
)
NUMBERLESS = st.sampled_from(["Part A > Fees", "Part A > Rules", "Fees", "Rules", None])
SENTENCES = st.sampled_from(
    [
        "See Section 1 for the fees.",
        "Chapter 2 and Section 3 apply to every holder.",
        "The deposit is held for 30 days.",
        "A dormant account is charged a yearly fee.",
        "Siehe Abschnitt 4 und Regel 2 für die Gebühren.",
        "The 'Fees' are set out below.",
        "Sibling sections share the rare term quokka.",
    ]
)
#: Any two letters: a language no pipeline is configured for falls back.
LANGUAGES = st.one_of(
    st.sampled_from(["en", "de", "fr", "ja"]),
    st.text(string.ascii_lowercase, min_size=2, max_size=2),
)


def corpus(rows):
    """Passages built from (trail, text, language, document, topic) rows."""
    passages = [
        replace(
            passage(text, language=language, section_path=trail, id=at + 1),
            doc_sha256=document,
        )
        for at, (trail, text, language, document, _) in enumerate(rows)
    ]
    return passages, {p.id: row[4] for p, row in zip(passages, rows, strict=True)}


def rows_of(trails):
    """Up to six rows whose headings are drawn from `trails`."""
    return st.lists(
        st.tuples(
            trails,
            st.lists(SENTENCES, min_size=1, max_size=2).map(" ".join),
            LANGUAGES,
            st.sampled_from(["a", "b"]),
            st.integers(1, 2),
        ),
        max_size=6,
    )


@given(
    rows=rows_of(TRAILS),
    wanted=st.integers(1, 4),
    size=st.integers(2, 3),
)
@pytest.mark.nlp
def test_links_are_distinct_one_language_labelled_by_the_corpus_and_capped(
    rows, wanted, size
) -> None:
    """No self-link, one language a link, a real label, and a cap per topic."""
    passages, topic_of = corpus(rows)
    result = linked(passages, passages, topic_of, wanted, size)

    carried = {
        part.strip() for p in passages for part in (p.section_path or "").split(" > ")
    }
    for link in result:
        ids = [p.id for p in link.passages]
        assert len(ids) == len(set(ids)) == size
        assert len({p.language for p in link.passages}) == 1
        if link.kind == "reference":
            assert link.named in carried
    # The cap is per topic of the head, and a link lists its passages in the
    # order the model reads them, not the head first, so the head's topic is
    # not recoverable: a language holds at most `wanted` links per topic it has.
    topics = Counter((p.language, topic_of[p.id]) for p in passages)
    per_language = Counter(link.passages[0].language for link in result)
    assert all(
        count <= wanted * len({t for lang, t in topics if lang == language})
        for language, count in per_language.items()
    )
    # The same input is the same result.
    assert linked(passages, passages, topic_of, wanted, size) == result


@given(rows=rows_of(NUMBERLESS), size=st.integers(2, 3))
@pytest.mark.nlp
def test_a_corpus_with_no_numbered_heading_still_links_or_offers_none(
    rows, size
) -> None:
    """Sibling, term or heading-name links, or none, and never an error."""
    passages, topic_of = corpus(rows)
    result = linked(passages, passages, topic_of, 3, size)

    assert all(
        link.kind != "reference" or not any(c.isdigit() for c in link.named)
        for link in result
    )


# ── Ranges ─────────────────────────────────────────────────────────────────

UNITS = st.sampled_from(["cm", "m", "days", "kg", "hours", "minutes"])
ENDS = st.tuples(st.integers(1, 900), st.integers(2, 99)).map(
    lambda one: (one[0], one[0] + one[1])
)


@given(ends=ENDS, unit=UNITS, style=st.sampled_from(["between", "to", "dash"]))
@pytest.mark.nlp
def test_a_key_with_no_range_is_not_met_by_a_range_that_merely_holds_it(
    ends, unit, style
) -> None:
    """`7 cm` is not what `between 5 and 9 cm` says."""
    low, high = ends
    inside = (low + high) // 2
    recovered = {
        "between": f"between {low} and {high} {unit}",
        "to": f"{low} to {high} {unit}",
        "dash": f"{low}–{high} {unit}",
    }[style]

    assert not agrees(recovered, f"{inside} {unit}", "en")


# ── Items a recovery adds to a key ─────────────────────────────────────────

ITEMS = ["fees", "taxes", "rent", "insurance", "deposits", "refunds"]
FILLER = st.sampled_from(["", "namely ", "also ", "all of ", "both "])


@given(
    chosen=st.lists(st.sampled_from(ITEMS), min_size=2, max_size=4, unique=True),
    data=st.data(),
    filler=FILLER,
)
@pytest.mark.nlp
def test_a_recovery_repeating_the_keys_items_adds_none_and_one_more_does(
    chosen, data, filler
) -> None:
    """Order and filler words change nothing; a new item always shows."""

    def listed(items):
        return ", ".join(items[:-1]) + " and " + items[-1]

    key = listed(chosen)
    question = "What does the customer pay?"
    shuffled = data.draw(st.permutations(chosen))

    assert not unnamed(f"{filler}{listed(shuffled)}.", key, "en", question)

    extra = data.draw(st.sampled_from(["penalties", "commissions", "tariffs"]))
    longer = data.draw(st.permutations([*chosen, extra]))
    assert unnamed(f"{filler}{listed(longer)}.", key, "en", question)


# ── The atomic cap ─────────────────────────────────────────────────────────


def fact(statement: str, units: bool, repaired: bool) -> CheckedFact:
    """One validated atomic fact, written by the model or by the repair call."""
    return CheckedFact(
        statement=statement,
        evidence_text=statement,
        extraction_method="llm",
        validated=True,
        rejection_code=None,
        validation_error=None,
        kind=FactKind.ATOMIC,
        units_statement=["5"] if units else [],
        prompt_version=REPAIR_PROMPT_VERSION if repaired else None,
    )


@given(
    written=st.lists(st.booleans(), max_size=8),
    pieces=st.lists(st.tuples(st.integers(0, 8), st.booleans()), max_size=6),
    cap=st.integers(0, 6),
)
def test_a_written_fact_is_capped_the_same_whatever_repaired_pieces_sit_beside_it(
    written, pieces, cap
) -> None:
    """Repaired pieces neither take a place nor push out a model's fact."""
    own = [fact(f"Claim {at}.", units, False) for at, units in enumerate(written)]
    mixed = list(own)
    for at, units in pieces:
        mixed.insert(min(at, len(mixed)), fact(f"Piece {at}.", units, True))

    refused = {mixed[at].statement for at in over_cap(mixed, cap)}

    assert refused == {own[at].statement for at in over_cap(own, cap)}


# ── Unanswerable kinds ─────────────────────────────────────────────────────

MIX = st.dictionaries(
    st.sampled_from(sorted(SPECS)), st.integers(0, 5), min_size=1, max_size=8
)


@given(
    types=MIX,
    wanted=st.integers(0, 24),
    share=st.floats(0, 1),
)
def test_unanswerable_slots_take_one_detail_kind_and_the_rest_are_unmoved(
    types, wanted, share
) -> None:
    """Only factoid, entity or reason, and answerable slots as at share 0."""
    bands = {"easy": 1, "medium": 1, "hard": 1}
    swept = plans(wanted=wanted, types=types, bands=bands, unanswerable_share=share)
    base = plans(wanted=wanted, types=types, bands=bands, unanswerable_share=0)

    assert len(swept) == len(base)
    allowed = {
        name
        for name, weight in types.items()
        if weight > 0 and name in PERTURBABLE and not SPECS[name].spans
    }
    for one, plain in zip(swept, base, strict=True):
        if one.answerable:
            assert one == plain
        else:
            assert one.spec.name in allowed
