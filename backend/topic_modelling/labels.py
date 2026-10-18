"""Naming a fitted topic with the model that reads the passages."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, Field

from llm.client import Client, ModelUnavailable
from llm.prompt import fill
from topic_modelling.models import FittedTopic

log = logging.getLogger(__name__)

#: How much of each representative passage the model is shown.
_EXCERPT_CHARS = 400

#: Recorded on every topic named with the prompt below. Bumped whenever that
#: prompt changes what a name is.
PROMPT_VERSION = "2"

_SYSTEM = """ROLE
You are a cataloguer. You name the subjects a set of documents covers, for
a coverage report a person reads by its names.

ACTION
Name every topic in the message with the subject it is about, or answer
"Mixed" for a topic that has none.

STEPS
1. Read every topic's defining terms and excerpts before naming any.
2. For each topic, count how many of its terms name PARTS OF A DOCUMENT
   rather than a subject. If more than half do, answer "Mixed" for it.
3. Work out what each topic's excerpts are about.
4. Work out what the whole set shares: the domain every topic belongs to.
   Leave it out of every name, and name what sets each topic apart within
   it.
5. Make the names distinct from each other and from the names already
   taken. Where two would be the same, name what separates them; where one
   has nothing of its own, answer "Mixed" for it.
6. Spell every word as the excerpts spell it.
7. Write the names in the language you are asked for.

CONTEXT
You are given, for each topic, the terms a statistical model found to
define it and a few excerpts the model placed in it; the language to
answer in; and the names already given to other topics of the same fit.

A wrong name is worse than none, because a coverage report is read by its
names. Two topics under one name cannot be told apart in that report, and
a name every topic could carry tells none of them apart.

EXAMPLES
  Topic 1 terms: card, fee, annual, statement, limit
  Topic 2 terms: transfer, abroad, currency, rate, payee
  Topic 3 terms: contents, foreword, appendix, index, card
    -> 1 "Card fees", 2 "Transfers abroad", 3 "Mixed"
  WRONG: 1 "Card fees in retail banking", 2 "Transfers abroad in retail
  banking" - the domain both share names neither.

FORMAT
Return `labels`: one entry per topic, each with `topic`, the number the
message gives it, and `label`, its name.

- A name is a short noun phrase, at most six words. Not a sentence.
- Name the SUBJECT, not the document type: "Warehouse safety", not
  "Procedural document about warehouse safety".
- Write it in the language named in the message, because the report it
  appears in is read in that language.
- Spell every word as the excerpts spell it: the report quotes the
  documents, and a word spelled otherwise is not theirs.
- Use the terms and excerpts only. If a topic's share no subject, say
  exactly "Mixed" and nothing else.
- ANSWER "Mixed" WHEN MORE THAN HALF A TOPIC'S TERMS NAME PARTS OF A
  DOCUMENT rather than a subject: contents, foreword, acknowledgements,
  copyright notice, revision history, release notes, appendix, index,
  glossary, version. One subject word among them does not make the topic
  that subject.
- DO NOT NAME THE DOMAIN EVERY TOPIC SHARES, and do not end every name on
  the same words.
- DO NOT GIVE TWO TOPICS ONE NAME, AND DO NOT REUSE A NAME ALREADY TAKEN.
- No quotation marks, no trailing punctuation."""

#: The user message, as the catalogue records it and `_prompt` renders it.
_USER = """Language: {{language}}

{{taken}}{{topics}}"""

#: One topic in the user message.
_TOPIC = """Topic {{number}}
Defining terms, strongest first:
{{terms}}

Excerpts this topic covers:
{{excerpts}}"""


#: What the prompt asks for where the terms share no subject, and that word
#: as a model writing in German translates it.
#:
#: ponytail: a word list in the two languages NLP_MODELS configures.
#: Upgrade: a boolean field on `_Label` the model sets instead.
_REFUSALS = frozenset({"mixed", "gemischt"})


class _Named(BaseModel):
    """The name the model gives one topic."""

    topic: int = Field(description="The topic's number, as the message gives it.")
    label: str = Field(
        description="A short noun phrase naming the subject, at most six "
        "words, in the language asked for. 'Mixed' if the terms share none."
    )


class _Labels(BaseModel):
    """The names the model gives every topic it was shown."""

    labels: list[_Named]


#: A word, as the excerpts' spelling is read.
_WORD = re.compile(r"\w+")

#: The longest run of trailing words read as an affix the names share.
_AFFIX_WORDS = 3


class TopicLabeller:
    """Names a topic from its terms and a few of the passages it holds."""

    def __init__(self, client: Client, languages: dict[str, str]) -> None:
        """Initialises the labeller.

        Args:
            client: The served model.
            languages: ISO 639-1 code to the language's name, for the prompt.
        """
        self._client = client
        self._languages = languages

    @property
    def model(self) -> str:
        """The model that names a topic, recorded on it."""
        return self._client.model

    def label(
        self,
        topic: FittedTopic,
        language: str,
        excerpts: list[str],
        taken: Sequence[str] = (),
    ) -> str | None:
        """Names one topic, as `label_all` names a set of one."""
        return self.label_all([(topic, excerpts)], language, taken).get(
            topic.topic_index
        )

    def label_all(
        self,
        topics: Sequence[tuple[FittedTopic, list[str]]],
        language: str,
        taken: Sequence[str] = (),
    ) -> dict[int, str]:
        """Names a language's topics, in one call, so the model sees the set.

        Seen one at a time, the model names each after the domain the whole
        corpus shares and in its own spelling, and the report reads as one
        topic. Shown together, it is asked for distinct names; and what it
        answers is held to the excerpts: each word the excerpts print takes
        their spelling, a letter they never use is folded (`ß` where they
        write `ss`), and words more than half the names end on - the domain
        again - are taken off.

        Args:
            topics: Each topic, read for its top terms, with the text of the
                passages it holds most strongly.
            language: ISO 639-1 code of the language to answer in.
            taken: Names already given to other topics of this fit.

        Returns:
            Each named topic's name by its index. A topic is left out where
            the model was unreachable, found no shared subject, or gave a
            name another topic or `taken` already has.
        """
        if not topics:
            return {}
        try:
            answer = self._client.answer(
                system=_SYSTEM,
                user=self._prompt(topics, language, taken),
                shape=_Labels,
                prompt_version=PROMPT_VERSION,
            )
        except ModelUnavailable as exc:
            log.warning("could not name the %s topics: %s", language, exc)
            return {}
        asked = [topic.topic_index for topic, _ in topics]
        said: dict[int, str] = {}
        for one in answer.labels:
            # One strip over the whole set, so a full stop inside a closing
            # quote takes the quote with it. German and typographic quotes too.
            name = one.label.strip("\"'. \n\t“”„‚‘’«»‹›")
            if (
                one.topic in asked
                and one.topic not in said
                and name
                and name.casefold() not in _REFUSALS
            ):
                said[one.topic] = name
        shown = "\n".join(text for _, excerpts in topics for text in excerpts)
        said = _unshared({index: _spelled(name, shown) for index, name in said.items()})
        # Asked for in the prompt and enforced here: an unnamed topic reads as
        # unnamed, where two topics under one name read as one topic.
        seen = {one.casefold() for one in taken}
        named: dict[int, str] = {}
        for index in asked:
            name = said.get(index)
            if name is None:
                continue
            if name.casefold() in seen:
                log.info("topic %d repeated the name %r", index, name)
                continue
            seen.add(name.casefold())
            named[index] = name
        return named

    def _prompt(
        self,
        topics: Sequence[tuple[FittedTopic, list[str]]],
        language: str,
        taken: Sequence[str] = (),
    ) -> str:
        """Builds the user message for a language's topics."""
        blocks = "\n\n".join(
            fill(
                _TOPIC,
                {
                    "{{number}}": str(topic.topic_index),
                    "{{terms}}": ", ".join(topic.top_terms),
                    "{{excerpts}}": "\n".join(
                        f"- {excerpt[:_EXCERPT_CHARS].strip()}" for excerpt in excerpts
                    ),
                },
            )
            for topic, excerpts in topics
        )
        already = f"Names already taken:\n{', '.join(taken)}\n\n" if taken else ""
        return fill(
            _USER,
            {
                "{{language}}": self._languages.get(language, language),
                "{{taken}}": already,
                "{{topics}}": blocks,
            },
        )


def _spelled(name: str, excerpts: str) -> str:
    """A name in the excerpts' own spelling, its own case kept.

    A word the excerpts print, case aside but not spelling, takes their
    form: `Großkunden` where they write `Grosskunden`. A word they print as
    written keeps its spelling, since a case fold joins two words as well
    as two spellings of one: `Masse` and `Maße`. Then a letter they never
    use is replaced by its case fold, which is what reaches a compound they
    do not print. Read off the excerpts alone, so it holds for any language
    and any spelling convention.
    """
    forms: dict[str, str] = {}
    printed: set[str] = set()
    for word in _WORD.findall(excerpts):
        forms.setdefault(word.casefold(), word)
        printed.add(word.lower())

    def respelled(found: re.Match[str]) -> str:
        word = found[0]
        if word.lower() in printed:
            return word
        form = forms.get(word.casefold())
        if form is None:
            return word
        first = form[0].upper() if word[0].isupper() else form[0].lower()
        return first + form[1:]

    name = _WORD.sub(respelled, name)
    letters = {char.lower() for char in excerpts if char.isalpha()}
    if not letters:
        return name
    return "".join(
        char.casefold()
        if char.isalpha()
        and char.lower() not in letters
        and char.casefold() != char.lower()
        else char
        for char in name
    )


def _unshared(names: dict[int, str]) -> dict[int, str]:
    """The names with the trailing words more than half of them share taken off.

    `... im Fussball` on nine names of ten is the domain the corpus shares,
    and it tells no topic apart. Two words or more, so a head noun two
    names share - `Debit cards`, `Credit cards` - stays; three names or
    more, so a pair is not read as the whole set; and a name the affix is
    all of keeps it.
    """
    if len(names) < 3:
        return names
    split = {index: name.split() for index, name in names.items()}
    for size in range(_AFFIX_WORDS, 1, -1):
        ends = Counter(
            tuple(word.casefold() for word in words[-size:])
            for words in split.values()
            if len(words) > size
        )
        if not ends:
            continue
        affix, held = ends.most_common(1)[0]
        if held * 2 > len(names):
            return {
                index: " ".join(words[:-size])
                if len(words) > size
                and tuple(word.casefold() for word in words[-size:]) == affix
                else names[index]
                for index, words in split.items()
            }
    return names
