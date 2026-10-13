"""When a German correlate `es` is read as standing for no noun.

A stand-in token rather than a sentence: what is under test is how a missing
morphology feature is read, and a pipeline that tags `es` at all tags its
number, so no sentence reliably leaves it off.
"""

from __future__ import annotations

from types import SimpleNamespace


class _Morph:
    """A token's morphology, as `token.morph.get` answers it."""

    def __init__(self, **features: list[str]) -> None:
        self._features = features

    def get(self, name: str) -> list[str]:
        return self._features.get(name, [])


def _es(number: list[str] | None):
    """`es` as subject of a plural verb with an object beside it."""
    head = SimpleNamespace(i=3, pos_="VERB", morph=_Morph(Number=["Plur"]), children=[])
    es = SimpleNamespace(
        i=1,
        text="es",
        morph=_Morph(**({"Number": number} if number else {})),
        doc=SimpleNamespace(lang_="de"),
        head=head,
    )
    head.children = [es, SimpleNamespace(i=2, dep_="oa")]
    return es


def test_an_es_with_its_number_disagreeing_with_the_verb_is_a_correlate() -> None:
    """The shape of "sofern es die Bedingungen gestatten"."""
    from nlp.analysis import _correlate

    assert _correlate(_es(["Sing"]))


def test_an_es_the_tagger_gave_no_number_is_not_a_correlate() -> None:
    """Nothing says it disagrees with its verb, so it stays a pronoun."""
    from nlp.analysis import _correlate

    assert not _correlate(_es(None))
