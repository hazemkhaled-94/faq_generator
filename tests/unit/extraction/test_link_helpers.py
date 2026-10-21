"""The small rules `links.linked` ranks and pairs by, read one at a time.

`test_links.py` goes through whole corpora; these hold each rule at its edge:
what two trails share, which passage a reference most likely means, which of
two links of one pair is kept, and how few passages make a term rare.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from drivers import passage

from database.qa_generator.passages import trail_of
from extraction.links import (
    _Edges,
    _near,
    _nearest,
    _plain,
    _shared_prefix,
    _siblings,
    linked,
)

pytestmark = pytest.mark.nlp


def at(path: str | None, ident: int, text: str = "Text.", **kwargs):
    """One passage under a heading trail."""
    return replace(
        passage(text, section_path=path, id=ident),
        doc_sha256=kwargs.pop("doc", "doc-a"),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("left", "right", "shared"),
    [
        ("Accounts > Fees > Yearly", "Accounts > Fees > Monthly", 2),
        ("Konten > Gebühren", "Karten > Gebühren", 0),
        ("Accounts > Fees", "Accounts", 1),
        ("Accounts", "Accounts > Fees", 1),
        (None, "Accounts > Fees", 0),
        ("Orders > Returns", "Orders > Returns", 2),
    ],
)
def test_two_trails_share_the_headings_they_start_with(left, right, shared) -> None:
    """Counted from the outermost heading, stopping at the first that differs."""
    assert _shared_prefix(at(left, 1), at(right, 2)) == shared


@pytest.mark.parametrize(
    ("raw", "plain"),
    [("Section 7:", "section 7"), (" *Kontoführung*. ", "kontoführung")],
)
def test_a_heading_is_compared_without_its_trailing_marks(raw, plain) -> None:
    """A colon, a full stop or an emphasis mark is no part of the name."""
    assert _plain(raw) == plain


def test_two_passages_with_no_vector_between_them_are_not_near() -> None:
    """Either one lacking a vector is 0, not an error and not a match."""
    with_vector = at("A", 1, embedding=(1.0, 0.0))
    without = at("A", 2)

    assert _near(without, without) == 0.0
    assert _near(with_vector, without) == 0.0
    assert _near(without, with_vector) == 0.0
    assert _near(with_vector, with_vector) == pytest.approx(1.0)


def test_a_reference_means_the_same_document_before_the_nearer_one() -> None:
    """Same document, then the longer shared trail, then the nearer vector, then the id."""
    head = at("Accounts > Fees", 1, embedding=(1.0, 0.0))
    other_document = at("Accounts > Fees", 2, doc="doc-b", embedding=(1.0, 0.0))
    same_document = at("Cards > Fees", 3, embedding=(0.0, 1.0))
    same_branch = at("Accounts > Dormancy", 4, embedding=(0.0, 1.0))
    nearer = at("Accounts > Closing", 5, embedding=(1.0, 0.0))

    assert _nearest(head, [other_document, same_document]) is same_document
    assert _nearest(head, [same_document, same_branch]) is same_branch
    assert _nearest(head, [same_branch, nearer]) is nearer
    assert _nearest(head, [at("Accounts > B", 9), at("Accounts > A", 8)]).id == 8
    assert _nearest(head, [head]) is None


def test_a_pair_keeps_the_first_of_two_links_of_one_strength() -> None:
    """A later link of the same kind does not replace the one found first."""
    edges = _Edges()
    first, second = at("A", 1), at("B", 2)

    edges.add(first, second, "reference", "Section 7")
    edges.add(second, first, "reference", "Section 9")
    edges.add(first, second, "term", "fee")

    ((_, link),) = edges.found.values()
    assert (link.kind, link.named) == ("reference", "Section 7")


def test_a_sibling_group_is_named_by_the_headings_above_its_sections() -> None:
    """Every heading but the last is the parent, however deep the trail is."""
    deep = at("Accounts > Fees > Yearly", 1)
    flat = at("Accounts > Dormancy", 2)
    top = at("Accounts", 3)
    edges = _Edges()

    _siblings(edges, [deep, flat, top])

    assert edges.parent == {1: "Accounts > Fees", 2: "Accounts"}
    assert edges.family["Accounts"] == [flat]


def test_a_heading_holding_the_separator_keeps_its_family_key_unambiguous() -> None:
    """The parent is written as a path again, so `Orders > 50 EUR` stays one heading."""
    deep = at(trail_of(["Shop", "Orders > 50 EUR", "Yearly"]), 1)
    other = at(trail_of(["Shop", "Orders", "50 EUR", "Yearly"]), 2)
    edges = _Edges()

    _siblings(edges, [deep, other])

    assert edges.parent[1] != edges.parent[2]


@pytest.mark.parametrize(
    ("language", "first", "second", "third"),
    [
        (
            "en",
            "A dormant account pays a yearly fee.",
            "The yearly fee for a dormant account is 10 EUR.",
            "The shop ships parcels within two days.",
        ),
        (
            "de",
            "Ein ruhendes Konto zahlt eine Jahresgebühr.",
            "Die Jahresgebühr für ein ruhendes Konto beträgt 10 EUR.",
            "Der Onlineshop verschickt Pakete innerhalb von zwei Tagen.",
        ),
    ],
)
def test_a_term_two_passages_share_links_them_and_a_term_three_share_does_not(
    language, first, second, third
) -> None:
    """Never fewer than two passages, and a share of three is not rare among three."""
    two = [
        replace(at(None, 1, first), language=language),
        replace(at(None, 2, second), language=language),
        replace(at(None, 3, third), language=language),
    ]
    three = [replace(p, text=first) for p in two]

    pair = linked(two, two, {p.id: 1 for p in two}, 5, 2)
    crowd = linked(three, three, {p.id: 1 for p in three}, 5, 2)

    assert pair
    assert all(link.kind == "term" for link in pair)
    assert not crowd


def test_one_link_per_topic_is_still_a_link_and_none_wanted_is_none() -> None:
    """`wanted` of 1 offers one link; of 0, none."""
    parent = "Accounts"
    rows = [
        at(f"{parent} > {name}", ident, f"{name} text.")
        for ident, name in enumerate(("Fees", "Closing", "Dormancy"), start=1)
    ]
    topics = {p.id: 1 for p in rows}

    assert len(linked(rows, rows, topics, 1, 2)) == 1
    assert linked(rows, rows, topics, 0, 2) == []
