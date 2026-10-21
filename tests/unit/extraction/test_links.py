"""Which passages are put in front of the model together.

A bridge is only worth the call if the two passages could plausibly share a
claim. The documents say which: a passage names another section's heading,
two sections sit under one parent heading, or a term almost nothing else
uses turns up in both. Pairing by these is `links.linked`.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

import pytest
from drivers import passage

from extraction.links import Link, _near, linked

pytestmark = pytest.mark.nlp


def one(text: str, path: str, ident: int, language: str = "en", **kwargs):
    """Builds one readable passage under a heading trail."""
    return replace(
        passage(text, language=language, section_path=path, id=ident),
        doc_sha256="doc-a",
        **kwargs,
    )


def pairs(links: list[Link]) -> list[tuple[int, ...]]:
    """The ids each link offers, in order."""
    return [tuple(p.id for p in link.passages) for link in links]


def run(passages, topics=None, wanted=5, size=2, done=frozenset(), heads=None):
    """Links a list of passages, every one a head by default."""
    topic_of = topics or {p.id: 1 for p in passages}
    return linked(heads or passages, passages, topic_of, wanted, size, done)


BANK = {
    "en": (
        (
            "Accounts > Dormant accounts",
            (
                "An account is dormant when its holder has made no payment for 24 "
                "months. Fees for dormant accounts are set out in Section 7."
            ),
        ),
        (
            "Section 7 > Yearly fees",
            "A dormant account is charged a yearly fee of 10 EUR.",
        ),
        "Section 7",
    ),
    "de": (
        (
            "Konten > Ruhende Konten",
            (
                "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung "
                "geleistet hat. Die Gebühren für ruhende Konten regelt Abschnitt 7."
            ),
        ),
        (
            "Abschnitt 7 > Jahresgebühren",
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
        ),
        "Abschnitt 7",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_numbered_heading_named_outside_its_section_links_the_two(language) -> None:
    """A passage saying 'Section 7' is paired with what sits under it, across topics."""
    (path_a, text_a), (path_b, text_b), named = BANK[language]
    a, b = one(text_a, path_a, 1, language), one(text_b, path_b, 2, language)

    got = run([a, b], {a.id: 1, b.id: 2}, heads=[a])

    assert got == [Link((a, b), "reference", named, a.id)]


def test_a_plural_label_and_its_conjoined_numbers_all_refer() -> None:
    """'Sections 7 and 9' reaches both."""
    for language, text, label in (
        ("en", "Fees are set out in Sections 7 and 9.", "Section"),
        ("de", "Die Gebühren regeln die Abschnitte 7 und 9.", "Abschnitt"),
    ):
        a = one(
            text,
            "Fees > Overview" if language == "en" else "Gebühren > Überblick",
            1,
            language,
        )
        b = one(
            "The yearly fee is 10 EUR."
            if language == "en"
            else "Die Jahresgebühr beträgt 10 EUR.",
            f"{label} 7 > Yearly",
            2,
            language,
        )
        c = one(
            "A card costs 5 EUR." if language == "en" else "Eine Karte kostet 5 EUR.",
            f"{label} 9 > Cards",
            3,
            language,
        )

        got = run([a, b, c], {1: 1, 2: 2, 3: 3}, heads=[a, b, c], wanted=9)

        keys = {frozenset(ids) for ids in pairs(got)}
        assert {frozenset((1, 2)), frozenset((1, 3))} <= keys, (language, pairs(got))


@pytest.mark.parametrize(
    ("language", "text_a", "path_a", "text_b", "path_b", "named"),
    [
        (
            "en",
            "An order can be cancelled until it ships; after that, see “Returns”.",
            "Orders > Cancelling an order",
            "Items can be returned within 30 days of delivery.",
            "Returns > Time limit",
            "Returns",
        ),
        (
            "de",
            "Eine Bestellung kann storniert werden, bis sie versandt ist; danach gilt „Rücksendungen“.",
            "Bestellungen > Stornierung",
            "Artikel können innerhalb von 30 Tagen nach der Lieferung zurückgesendet werden.",
            "Rücksendungen > Frist",
            "Rücksendungen",
        ),
    ],
)
def test_a_quoted_heading_links_the_two(
    language, text_a, path_a, text_b, path_b, named
) -> None:
    """A quoted heading of another section is a reference."""
    a, b = one(text_a, path_a, 1, language), one(text_b, path_b, 2, language)

    assert run([a, b], {1: 1, 2: 2}, heads=[a]) == [
        Link((a, b), "reference", named, a.id)
    ]


def test_the_deepest_of_two_quoted_headings_is_followed() -> None:
    """'Time limit' under 'Returns' means the passage under both."""
    a = one("To return an item, see 'Time limit' under 'Returns'.", "Orders > Help", 1)
    b = one(
        "Items can be returned within 30 days of delivery.", "Returns > Time limit", 2
    )
    c = one("Refunds are paid within 14 days of the return.", "Returns > Refunds", 3)

    got = run([a, b, c], {1: 1, 2: 2, 3: 2}, heads=[a])

    assert pairs(got) == [(1, 2)]


def test_a_passage_naming_its_own_section_refers_to_nothing() -> None:
    """'Section 7' inside Section 7 is not a reference."""
    b = one("Section 7 applies to every account.", "Section 7 > Yearly fees", 2)
    c = one("A card costs 5 EUR.", "Cards > Fees", 3)

    got = run([b, c], {2: 1, 3: 2}, heads=[b])

    assert not [k for k in got if k.kind == "reference"]


def test_a_reference_outranks_a_sibling() -> None:
    """A head with both takes the reference."""
    (path_a, text_a), (path_b, text_b), named = BANK["en"]
    a = one(text_a, path_a, 1)
    b = one(text_b, path_b, 2)
    s = one("A card costs 5 EUR.", "Accounts > Cards", 3)

    got = run([a, b, s], {1: 1, 2: 2, 3: 1}, heads=[a])

    assert got == [Link((a, b), "reference", named, a.id)]


@pytest.mark.parametrize(
    ("language", "first", "second", "parent"),
    [
        (
            "en",
            (
                "Fees > Yearly fees",
                "A dormant account is charged a yearly fee of 10 EUR.",
            ),
            ("Fees > Card fees", "A replacement card costs 5 EUR."),
            "Fees",
        ),
        (
            "de",
            (
                "Gebühren > Jahresgebühren",
                "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
            ),
            ("Gebühren > Kartengebühren", "Eine Ersatzkarte kostet 5 EUR."),
            "Gebühren",
        ),
    ],
)
def test_two_sections_under_one_heading_are_siblings(
    language, first, second, parent
) -> None:
    """The same parent heading, a different own heading."""
    a, b = one(first[1], first[0], 1, language), one(second[1], second[0], 2, language)

    assert run([a, b], {1: 1, 2: 1}, heads=[a]) == [
        Link((a, b), "sibling", parent, a.id)
    ]


def test_two_chunks_of_one_section_are_not_siblings() -> None:
    """Same full path: one section cut in two, not two sections."""
    a = one(
        "A dormant account is charged a yearly fee of 10 EUR.", "Fees > Yearly fees", 1
    )
    b = one("The statement is sent by post.", "Fees > Yearly fees", 2)

    assert run([a, b]) == []


@pytest.mark.parametrize(
    ("language", "first", "second", "term"),
    [
        (
            "en",
            ("Delivery > Options", "Express delivery costs 9 EUR."),
            ("Furniture > Delivery", "Express delivery is not offered for furniture."),
            "express",
        ),
        (
            "de",
            ("Lieferung > Optionen", "Expresslieferung kostet 9 EUR."),
            ("Möbel > Lieferung", "Für Möbel gibt es keine Expresslieferung."),
            "expresslieferung",
        ),
    ],
)
def test_a_term_almost_no_other_passage_uses_links_the_two(
    language, first, second, term
) -> None:
    """Eight passages, two of which carry the term."""
    fillers = {
        "en": [
            "Delivery takes 3 days.",
            "Returns are free.",
            "Cards cost 5 EUR.",
            "Orders ship on Monday.",
            "Refunds take 14 days.",
            "Gifts are wrapped.",
        ],
        "de": [
            "Die Lieferung dauert 3 Tage.",
            "Rücksendungen sind kostenlos.",
            "Karten kosten 5 EUR.",
            "Bestellungen werden montags versandt.",
            "Erstattungen dauern 14 Tage.",
            "Geschenke werden verpackt.",
        ],
    }[language]
    passages = [
        one(first[1], first[0], 1, language),
        one(second[1], second[0], 2, language),
    ]
    passages += [
        one(t, f"Chapter {i} > Part {i}", 3 + i, language)
        for i, t in enumerate(fillers)
    ]
    topics = {p.id: p.id for p in passages}

    got = run(passages, topics, heads=passages[:1])

    assert got == [Link((passages[0], passages[1]), "term", term, passages[0].id)]


def test_two_languages_are_never_linked() -> None:
    """The only occurrence of a term in each language is not a link."""
    a = one("Express delivery costs 9 EUR.", "Delivery > Options", 1, "en")
    b = one("Express delivery costs 9 EUR.", "Lieferung > Optionen", 2, "de")

    assert run([a, b]) == []


def test_no_more_links_than_wanted_per_topic_of_the_head() -> None:
    """Spread over the topic's heads, the first and the last included."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(30)
    ]

    got = run(passages, wanted=4)

    assert len(got) == 4
    reached = [p.id for link in got for p in link.passages]
    assert min(reached) == 1 and max(reached) >= 28, reached


def test_a_passage_heads_at_most_one_link_and_a_pair_is_offered_once() -> None:
    """Each pair once, each head once."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(6)
    ]

    got = run(passages, wanted=9)

    keys = [frozenset(p.id for p in link.passages) for link in got]
    assert len(set(keys)) == len(keys)
    heads = [
        next(p for p in link.passages if p.id in {h for h in range(1, 7)})
        for link in got
    ]
    assert len(got) <= 6 and heads


def test_a_group_of_three_follows_the_partners_own_link() -> None:
    """size=3 extends with the last member's best link."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(5)
    ]

    got = run(passages, wanted=2, size=3)

    assert got and all(len(link.passages) == 3 for link in got)
    assert all(len({p.id for p in link.passages}) == 3 for link in got)


def test_a_head_whose_topic_already_holds_a_bridge_is_skipped() -> None:
    """`done` is the topics a missing pass leaves."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(4)
    ]

    assert run(passages, done=frozenset({1})) == []


def test_nothing_is_asked_for_when_nothing_is_wanted() -> None:
    """No calls when no groups are wanted, and no group of one."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(4)
    ]

    assert run(passages, wanted=0) == []
    assert run(passages, size=1) == []
    assert run(passages[:1]) == []


def _vector(*first: float) -> tuple[float, ...]:
    """A vector of the width the column holds."""
    return (*first, *((0.0,) * (1024 - len(first))))


def test_a_head_is_paired_with_the_sibling_it_most_nearly_meets() -> None:
    """Inside a tier the vectors decide."""
    near, far = _vector(1.0), _vector(0.0, 1.0)
    head = one("A costs 1 EUR.", "Fees > A", 1, embedding=near)
    other = one("B costs 2 EUR.", "Fees > B", 2, embedding=far)
    close = one("C costs 3 EUR.", "Fees > C", 3, embedding=near)

    got = run([head, other, close], heads=[head])

    assert pairs(got) == [(1, 3)]


def test_a_tie_between_two_equally_near_passages_goes_to_the_lower_id() -> None:
    """The same corpus has to deal the same links twice."""
    same = _vector(1.0)
    head = one("A costs 1 EUR.", "Fees > A", 1, embedding=same)
    late = one("C costs 3 EUR.", "Fees > C", 3, embedding=same)
    early = one("B costs 2 EUR.", "Fees > B", 2, embedding=same)

    assert pairs(run([head, late, early], heads=[head])) == [(1, 2)]


def test_without_vectors_the_first_in_reading_order_is_taken() -> None:
    """`make extract-embed` is what gives an older corpus some."""
    head = one("A costs 1 EUR.", "Fees > A", 1)
    first = one("B costs 2 EUR.", "Fees > B", 2)
    second = one("C costs 3 EUR.", "Fees > C", 3)

    assert pairs(run([head, first, second], heads=[head])) == [(1, 2)]


def test_sibling_pairs_are_not_all_stored() -> None:
    """A parent heading over N sections would hold N^2/2 of them."""
    from extraction.links import _Edges, _siblings

    passages = [
        one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1) for i in range(50)
    ]
    edges = _Edges()

    _siblings(edges, passages)

    assert not edges.found


def _flat(count: int, vectors: str, width: int = 1024) -> list:
    """One flat parent of `count` sections; vectors 'none', 'random', 'ties' or 'partial'."""
    rng = random.Random(count)
    pool = []
    for _ in range(5):
        raw = [rng.gauss(0, 1) for _ in range(width)]
        norm = math.sqrt(sum(x * x for x in raw))
        pool.append(tuple(x / norm for x in raw))
    made = []
    for i in range(count):
        if vectors == "none" or (vectors == "partial" and i % 3 == 0):
            vector = None
        elif vectors == "ties":
            vector = pool[i % 5]
        else:
            raw = [rng.gauss(0, 1) for _ in range(width)]
            norm = math.sqrt(sum(x * x for x in raw))
            vector = tuple(x / norm for x in raw)
        made.append(
            one(f"Item {i} costs {i} EUR.", f"Fees > Part {i}", i + 1, embedding=vector)
        )
    return made


def _dealt_by_hand(passages: list) -> list[tuple[int, ...]]:
    """What the heads offer when each takes its nearest sibling, lowest id on a tie."""
    seen: set[frozenset[int]] = set()
    out = []
    for head in passages:
        for other in sorted(
            (p for p in passages if p.id != head.id),
            key=lambda p: (-_near(head, p), p.id),
        ):
            key = frozenset((head.id, other.id))
            if key not in seen:
                seen.add(key)
                out.append(tuple(sorted((head.id, other.id))))
                break
    return out


@pytest.mark.parametrize("vectors", ["none", "random", "ties", "partial"])
def test_a_flat_parent_is_dealt_as_each_head_nearest_sibling(vectors) -> None:
    """The vectors are read in one product per head, and the order stays the same."""
    passages = _flat(60, vectors, width=32)

    got = pairs(run(passages, wanted=1000))

    assert got == _dealt_by_hand(passages)


@pytest.mark.parametrize("count", [40, 160])
def test_a_flat_family_is_scored_in_one_product_not_one_dot_product_per_pair(
    count, monkeypatch
) -> None:
    """A head must not read its whole family in pure Python, at any size."""
    from extraction import links

    scored = []
    monkeypatch.setattr(
        links, "_near", lambda left, right: scored.append(1) or _near(left, right)
    )
    passages = _flat(count, "random", width=16)

    run(passages, wanted=1000)

    assert scored == []  # base: count * (count - 1) calls


@pytest.mark.parametrize(
    "language, texts",
    [
        (
            "en",
            (
                "The overdraft limit is reviewed every spring.",
                "Savings earn interest at a fixed rate.",
                "Parcels leave the warehouse on weekdays.",
                "Returns are refunded to the original card.",
                "Gift vouchers expire after three years.",
            ),
        ),
        (
            "de",
            (
                "Der Dispositionskredit wird jedes Frühjahr geprüft.",
                "Sparguthaben werden mit einem festen Satz verzinst.",
                "Pakete verlassen das Lager an Werktagen.",
                "Rücksendungen werden auf die ursprüngliche Karte erstattet.",
                "Geschenkgutscheine verfallen nach drei Jahren.",
            ),
        ),
    ],
)
def test_a_pair_that_cannot_grow_gives_its_slot_to_one_that_can(
    language, texts
) -> None:
    """At size 3 a head whose partner has no further link is not worth a slot."""
    a, b, c, d, e = (
        one(text, path, ident, language)
        for ident, (text, path) in enumerate(
            zip(
                texts,
                ("Bank > A", "Bank > B", "Shop > C", "Shop > D", "Shop > E"),
                strict=True,
            ),
            start=1,
        )
    )

    got = run([a, b, c, d, e], wanted=1, size=3)

    assert pairs(got) == [(3, 4, 5)]


# ── Pairs a stored bridge already rests on ────────────────────────────────

_SIBLINGS = {
    "en": (
        ("Fees > Yearly fees", "A dormant account is charged a yearly fee of 10 EUR."),
        ("Fees > Card fees", "A replacement card costs 5 EUR."),
        ("Fees > Cash fees", "Cash withdrawals abroad cost 3 EUR."),
    ),
    "de": (
        (
            "Versand > Standardversand",
            "Der Standardversand kostet 4 EUR und dauert 3 Tage.",
        ),
        ("Versand > Expressversand", "Der Expressversand kostet 9 EUR."),
        ("Versand > Abholung", "Die Abholung im Markt ist kostenlos."),
    ),
}


def _three(language: str):
    return [
        one(text, path, ident, language)
        for ident, (path, text) in enumerate(_SIBLINGS[language], start=1)
    ]


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_head_never_offers_a_pair_a_stored_bridge_rests_on(language) -> None:
    """It takes its next link instead, whichever of the two ordered the pair."""
    a, b, c = _three(language)
    topics = {1: 1, 2: 1, 3: 1}
    (first,) = linked([a], [a, b, c], topics, 5, 2)
    taken = frozenset(p.id for p in first.passages)

    (again,) = linked([a], [a, b, c], topics, 5, 2, held=frozenset({taken}))

    assert frozenset(p.id for p in again.passages) != taken
    assert a in again.passages, "the head still offers a link, of its own next best"


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_head_with_nothing_but_held_pairs_offers_nothing(language) -> None:
    """Every partner of the head is a pair already written."""
    a, b, c = _three(language)
    held = frozenset({frozenset({1, 2}), frozenset({1, 3})})

    assert linked([a], [a, b, c], {1: 1, 2: 1, 3: 1}, 5, 2, held=held) == []


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_held_pair_is_held_against_the_other_side_heading_it(language) -> None:
    """A cross-topic pair stored from one side is not offered from the other."""
    a, b, _ = _three(language)
    held = frozenset({frozenset({1, 2})})

    assert linked([b], [a, b], {1: 1, 2: 2}, 5, 2, held=held) == []
    offered = linked([b], [a, b], {1: 1, 2: 2}, 5, 2)
    assert [frozenset(p.id for p in link.passages) for link in offered] == [
        frozenset({1, 2})
    ], "without the hold the head offers it"


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_held_pair_leaves_the_other_pairs_alone(language) -> None:
    """Holding one pair costs only that pair."""
    a, b, c = _three(language)
    topics = {1: 1, 2: 1, 3: 1}
    free = linked([a, b, c], [a, b, c], topics, 5, 2)
    held = frozenset({frozenset(p.id for p in free[0].passages)})

    left = linked([a, b, c], [a, b, c], topics, 5, 2, held=held)

    assert all(frozenset(p.id for p in link.passages) not in held for link in left)
    assert left, "the other heads still offer theirs"


@pytest.mark.parametrize(
    ("language", "parents"),
    [
        ("en", ["Fees", "Fees", "Fees", "Fees", "Delivery", "Delivery"]),
        ("de", ["Gebühren", "Gebühren", "Gebühren", "Gebühren", "Versand", "Versand"]),
    ],
)
def test_holding_pairs_the_pass_would_not_offer_changes_nothing(
    language, parents
) -> None:
    """Six shop passages in one topic worth three links: a hold off the stride moves none."""
    passages = [
        one(f"Item {i} costs {i} EUR.", f"{parents[i - 1]} > Part {i}", i, language)
        for i in range(1, 7)
    ]
    topics = {p.id: 1 for p in passages}
    free = linked(passages, passages, topics, 3, 2)
    held = frozenset({frozenset({2, 3}), frozenset({2, 4})})
    assert not {frozenset(pair) for pair in pairs(free)} & held

    assert pairs(linked(passages, passages, topics, 3, 2, held=held)) == pairs(free)
