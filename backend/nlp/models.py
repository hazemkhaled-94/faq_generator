"""The things the nlp package hands back.

Plain values, and no spaCy import: a caller that only needs the shape of a
sentence should not load a pipeline to get it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sentence:
    """One sentence of a passage, located in the passage text."""

    index: int
    start: int
    end: int
    text: str
    predicates: int


@dataclass(frozen=True)
class Claim:
    """What a statement asserts, and what it leaves unsaid."""

    predicates: int
    units: tuple[str, ...]
    references: tuple[str, ...]
    #: Verbs of any form, finite or not. `predicates` counts the finite ones,
    #: which is how many claims a statement makes; this counts all of them,
    #: which is how a phrase that names a thing is told from one that
    #: describes an action. An infinitive makes no claim and is still not an
    #: answer: `Gebuehren erheben` has no predicate and one verb.
    verbs: int = 0
    #: Figures written as one token `like_num` does not mark: a time, a
    #: score, a figure glued to its unit - `08:00`, `2.5x`. Apart from
    #: `units` because only the checks for an invented value read them.
    figures: tuple[str, ...] = ()
    #: The months and weekdays the statement names, each folded to its base
    #: form. Apart from `units` because only the fact check compares them: the
    #: question gates compare units, and a key and its recovery are not asked
    #: for a date.
    calendar: tuple[str, ...] = ()

    @property
    def asserted(self) -> tuple[str, ...]:
        """What the fact check asks the cited text for by its words: units, figures and dates."""
        # dict.fromkeys: English tags a month as a name, so it is a unit and a calendar name both
        return tuple(dict.fromkeys(self.units + self.figures + self.calendar))


#: What each configured language is called, for a prompt that has to name it.
#:
#: A prompt telling a model to write "in the language of the excerpt" asks it
#: to infer the answer from the material, and on a corpus that is mostly one
#: language it infers that language. Nothing in extraction checks a language,
#: so the drift reached question generation as a German question labelled
#: English and was thrown out as `malformed`.
#:
#: Named rather than left as a code because that is what the instruction
#: says: "Write in English" is an instruction, "write in en" is a riddle.
_NAMED = {"de": "German", "en": "English"}


def named(language: str | None) -> str:
    """What to call one language in a prompt.

    Falls back to the code itself, which is the honest thing for a language
    `NLP_MODELS` has gained and this has not: an ISO 639-1 code is still an
    instruction a model can follow, where a wrong name is not. A language of
    None falls back to nothing: a template then drops its language sentence,
    through `with_language`.
    """
    if not language:
        return ""
    return _NAMED.get(language.lower(), language)


#: The sentence a prompt template ends in to name the language, with the blank
#: lines before it.
_LANGUAGE_SENTENCE = re.compile(r"\n*Write [^\n.]*\{\{language\}\}\.")


def with_language(template: str, language: str | None) -> str:
    """The template, without its `Write ... in {{language}}.` sentence for no language.

    Told to write in an empty name, a model reads a sentence ending `in .`.
    """
    return template if language else _LANGUAGE_SENTENCE.sub("", template)
