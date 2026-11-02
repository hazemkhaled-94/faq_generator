"""A question word is read from the morphology or the language's own interrogative tags, not a tag prefix.

Documents are built by hand with the tags each tagset gives, since no Dutch or
Polish pipeline is installed: the Dutch tagset tags every verb WW and the
Polish one tags `powinien` WINIEN, which a W prefix read as question words.
"""

from __future__ import annotations

import pytest
import spacy
from spacy.tokens import Doc

from nlp.analysis import _asking, _interrogative


def _question(lang, words, tags, deps, heads, morphs):
    return Doc(
        spacy.blank(lang).vocab,
        words=words,
        tags=tags,
        deps=deps,
        heads=heads,
        morphs=morphs,
    )


_CASES = [
    # Who must file the application?
    (
        "en",
        ["Who", "must", "file", "the", "application", "?"],
        ["WP", "MD", "VB", "DT", "NN", "."],
        ["nsubj", "aux", "ROOT", "det", "dobj", "punct"],
        [2, 2, 2, 4, 2, 2],
        ["", "VerbForm=Fin", "VerbForm=Inf", "", "", ""],
    ),
    (
        "de",
        ["Wer", "muss", "den", "Antrag", "stellen", "?"],
        ["PWS", "VMFIN", "ART", "NN", "VVINF", "$."],
        ["sb", "ROOT", "nk", "oa", "oc", "punct"],
        [1, 1, 3, 4, 1, 1],
        ["PronType=Int", "VerbForm=Fin", "", "", "VerbForm=Inf", ""],
    ),
    (
        "nl",
        ["Wie", "moet", "de", "aanvraag", "indienen", "?"],
        [
            "VNW|vrag|pron|stan|nadr|3o|ev",
            "WW|pv|tgw|ev",
            "LID|bep|stan|rest",
            "N|soort|ev|basis|zijd|stan",
            "WW|inf|vrij|zonder",
            "LET",
        ],
        ["nsubj", "ROOT", "det", "obj", "xcomp", "punct"],
        [1, 1, 3, 4, 1, 1],
        ["PronType=Int", "VerbForm=Fin", "", "", "VerbForm=Inf", ""],
    ),
    (
        "pl",
        ["Kto", "powinien", "złożyć", "wniosek", "?"],
        ["PPRON3", "WINIEN", "INF", "SUBST", "INTERP"],
        ["nsubj", "ROOT", "xcomp", "obj", "punct"],
        [1, 1, 1, 2, 1],
        ["PronType=Int", "", "VerbForm=Inf", "", ""],
    ),
]


@pytest.mark.parametrize(
    ("lang", "words", "tags", "deps", "heads", "morphs"),
    _CASES,
    ids=[case[0] for case in _CASES],
)
def test_a_one_verb_question_asks_one_thing(lang, words, tags, deps, heads, morphs):
    """A modal verb is no question word in any tagset, and the question word still is."""
    doc = _question(lang, words, tags, deps, heads, morphs)
    verbs = [t.text for t in doc if t.tag_ in {"MD", "VMFIN", "WW|pv|tgw|ev", "WINIEN"}]

    assert not any(_interrogative(t) for t in doc if t.text in verbs), verbs
    assert [t.text for t in doc if _asking(t)] == [words[0]]
