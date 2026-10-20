"""One ranking, one scale: cosine and word overlap are never compared."""

from __future__ import annotations

import math

import pytest

from nlp.analysis import content
from question_generation.models import SourceFact, SourcePassage
from question_generation.selection import Deal, Shape, closest, meets, overlap

pytestmark = pytest.mark.nlp


def unit(c):
    """A unit vector whose cosine with (1, 0) is `c`."""
    return (c, math.sqrt(1 - c * c))


def P(i, text, lang, emb=None):
    """A passage."""
    return SourcePassage(
        id=i,
        text=text,
        doc_sha256="d",
        language=lang,
        topic_id=1,
        ordinal=i,
        document_title="d",
        lemmas=tuple(sorted(content(text, lang))),
        embedding=emb,
    )


def F(i, st, p, emb=None):
    """A fact resting on one passage."""
    return SourceFact(
        id=i,
        statement=st,
        passages=(p,),
        kind="atomic",
        units=("u",),
        embedding=emb,
        evidence=st,
    )


CASES = [
    (
        "en",
        "The daily cash limit at a cash machine is 1,000 euros.",
        "Withdrawals at machines abroad are capped at 500 euros a day.",
        "An account is closed by a signed letter to the branch.",
    ),
    (
        "de",
        "Das tägliche Bargeldlimit am Automaten beträgt 1.000 Euro.",
        "Abhebungen an Automaten im Ausland sind auf 500 Euro pro Tag begrenzt.",
        "Ein Konto wird durch einen unterschriebenen Brief an die Filiale geschlossen.",
    ),
    (
        "en",
        "Standard delivery takes 3 to 5 working days.",
        "Parcels sent by courier usually arrive within two working days.",
        "Gift wrapping costs 3 euros.",
    ),
    (
        "de",
        "Die Standardlieferung dauert 3 bis 5 Werktage.",
        "Pakete per Kurier kommen meist innerhalb von zwei Werktagen an.",
        "Die Geschenkverpackung kostet 3 Euro.",
    ),
]


def trio(lang, a, near, far, vectored):
    """Head, near and far facts, all with vectors or none."""
    vec = (lambda c: unit(c)) if vectored else (lambda c: None)
    h, n, f = (
        P(1, a, lang, vec(1.0)),
        P(2, near, lang, vec(0.9)),
        P(3, far, lang, vec(0.75)),
    )
    return (
        F(1, a, h, vec(1.0)),
        F(2, near, n, vec(0.9)),
        F(3, far, f, vec(0.75)),
    )


@pytest.mark.parametrize("lang,a,near,far", CASES)
def test_a_vectorless_passage_is_apart_on_its_words_not_on_a_cosine(lang, a, near, far):
    """Test a vectorless passage is apart on its words not on a cosine."""
    h, n, f = (
        P(1, a, lang, unit(1.0)),
        P(2, near, lang, None),
        P(3, far, lang, unit(0.75)),
    )
    facts = [F(1, a, h, unit(1.0)), F(2, near, n), F(3, far, f, unit(0.75))]
    apart = Deal(facts, wanted=3, size=2, rounds=1, floor=0.0, share=0.0).sample(
        Shape.APART
    )
    assert [p.id for p in apart.resting][1:] == [3]
    assert overlap([facts[0]], [facts[1]], vectors=False) >= overlap(
        [facts[0]], [facts[2]], vectors=False
    )


@pytest.mark.parametrize("lang,a,near,far", CASES)
def test_a_vectorless_fact_is_ranked_on_its_words_not_on_a_cosine(lang, a, near, far):
    """Test a vectorless fact is ranked on its words not on a cosine."""
    h, n, f = (
        P(1, a, lang, unit(1.0)),
        P(2, near, lang),
        P(3, far, lang, unit(0.75)),
    )
    fh, fn, ff = F(1, a, h, unit(1.0)), F(2, near, n), F(3, far, f, unit(0.75))
    assert closest([fh], [ff, fn], 1)[0].id == 2
    assert meets([fh], fn, vectors=False) >= meets([fh], ff, vectors=False)


@pytest.mark.parametrize("lang,a,near,far", CASES)
def test_all_vectors_still_rank_on_cosine(lang, a, near, far):
    """Test all vectors still rank on cosine."""
    fh, fn, ff = trio(lang, a, near, far, True)
    assert [one.id for one in closest([fh], [ff, fn], 2)] == [2, 3]
    assert meets([fh], fn) == pytest.approx(0.9)
    assert overlap([fh], [ff]) == pytest.approx(0.75)


@pytest.mark.parametrize("lang,a,near,far", CASES)
def test_no_vectors_still_rank_on_words(lang, a, near, far):
    """Test no vectors still rank on words."""
    fh, fn, _ = trio(lang, a, near, far, False)
    jaccard = meets([fh], fn)
    assert meets([fh], fn, vectors=False) == jaccard
    assert overlap([fh], [fn]) == overlap([fh], [fn], vectors=False)
