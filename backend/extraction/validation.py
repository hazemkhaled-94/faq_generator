"""Checking a proposed fact against the passages it came from.

Which checks a candidate faces is decided by its kind. See README.md for the
matrix and for what each one is protecting against.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field, replace
from functools import partial

from database.qa_generator import FactKind, Rejection
from database.qa_generator.passages import headings_of
from extraction.models import (
    BULLET,
    MIN_POINTS,
    WRITTEN,
    CandidateFact,
    CheckedFact,
    Citation,
    Cited,
    PassageToExtract,
    Provenance,
)
from nlp.analysis import (
    as_noun,
    claim,
    is_currency,
    normalised,
    numerals,
    parse,
    spoken_numbers,
    vocabulary,
    written_in,
)
from nlp.models import Claim, Sentence
from nlp.pipelines import name as pipeline_name
from nlp.pipelines import pipeline
from nlp.pipelines import version as pipeline_version
from settings import decimal

#: What joins the cited spans into the evidence stored on the fact. Two
#: passages' spans do not run on, so they are not joined with a space. Nor
#: do two sentences of one passage with a sentence between them that the
#: claim did not cite.
_JOIN = "\n"


def _lines_of(sentence: Sentence) -> list[Sentence]:
    """The non-empty lines of a sentence, each located in the passage.

    A line keeps the index of the sentence it is in, so a citation of it
    resolves again as that sentence does.
    """
    lines = []
    at = sentence.start
    for line in sentence.text.split("\n"):
        if line.strip():
            start = at + len(line) - len(line.lstrip())
            lines.append(
                replace(
                    sentence,
                    start=start,
                    end=start + len(line.strip()),
                    text=line.strip(),
                )
            )
        at += len(line) + 1
    return lines


def _cited_text(passage: PassageToExtract, cited: Sequence[Sentence]) -> str:
    """The text a citation rests on: those sentences and nothing else.

    A run of adjacent sentences is taken whole, which keeps the passage's
    own spacing between them and is what a reader sees highlighted.

    Sentences with a gap between them are joined instead. The covering range
    would hand the checks every sentence in between as well, so a claim
    citing 0 and 5 of a six-sentence passage would be judged against all six
    - and `unsupported_addition`, which is the gate that says nothing was
    invented, would accept a number from a sentence the claim never named.
    """
    span = range(cited[0].index, cited[-1].index + 1)
    if [one.index for one in cited] == list(span):
        return passage.text[cited[0].start : cited[-1].end]
    return _JOIN.join(one.text for one in cited)


#: One ' > ' segment of a heading trail that is a word and a number
#: ('Section 7', 'Regel 5.1', '§ 3'): the document's own way to number a part.
HEADING_LABEL = re.compile(r"^([^\W\d_]+|§)\s?(\d+(?:\.\d+)*)$")

#: A heading number as the documents write it ('7', '5.1').
NUMBER = re.compile(r"\d+(?:\.\d+)*")

#: A token holding a section number, with any subsection the tokenizer glued
#: on after it ('7(2'): the section it names is the number before the bracket.
_SECTION_TOKEN = re.compile(rf"({NUMBER.pattern})(?:\(.*)?")


def _section(text: str) -> str | None:
    """The section number a token names, a closing full stop dropped, or None."""
    found = _SECTION_TOKEN.fullmatch(text.rstrip("."))
    return found[1] if found else None


#: A failed check, as its code and the measurement behind it.
Failure = tuple[str, str]
Check = Callable[["Judged"], Failure | None]


@dataclass(frozen=True)
class Judged:
    """One candidate resolved against its passages and parsed.

    Attributes:
        statement: The candidate's statement, stripped.
        evidence: The cited spans, joined in the order they were cited.
        evidence_predicates: Finite verbs across the cited sentences.
        claim: What the statement itself asserts.
        evidence_vocabulary: Every form a word of the evidence appears in,
            over every passage the candidate rests on.
        supported: Units of the statement read as present in the evidence
            though no form of them is: a number spelled another way, a
            hyphenated unit of words it holds, a name it holds as a noun.
        citations: One entry per passage the candidate rests on, in the order
            the model was shown them.
        labels: On a bridge, the numbered headings ("Section 7") of the
            passages it rests on.
        language: The language the statement is read in.
        claims: The most claims the statement may carry: one, or two on a
            bridge that states a contrast or an exception.
        swaps: The figures of the statement that only the rest of the passage
            states, each with the figure of its own kind that the cited
            sentences state instead.
    """

    statement: str
    evidence: str
    evidence_predicates: int
    claim: Claim
    evidence_vocabulary: frozenset[str]
    supported: frozenset[str] = frozenset()
    citations: tuple[Citation, ...] = field(default=())
    labels: tuple[str, ...] = ()
    language: str | None = None
    claims: int = 1
    swaps: tuple[tuple[str, str], ...] = ()

    @property
    def added(self) -> tuple[str, ...]:
        """Units the statement asserts that its evidence does not carry.

        Carried is a form in the vocabulary, or a unit read as supported: the
        one place that decides what is added. A figure `like_num` misses - a
        time, `08:00` - is a unit here too.
        """
        added = tuple(
            unit
            for unit in self.claim.units + self.claim.figures
            if unit not in self.evidence_vocabulary and unit not in self.supported
        )
        return added + tuple(unit for unit, _ in self.swaps if unit not in added)


def _copied(judged: Judged) -> Failure | None:
    """Refuses a statement that is its evidence copied.

    Evidence carrying exactly one claim is exempt: it already is the fact.
    """
    if normalised(judged.statement) != normalised(judged.evidence):
        return None
    if judged.evidence_predicates == 1:
        return None
    return (
        Rejection.COPIED,
        (
            f"the statement is its evidence copied rather than written, and "
            f"that evidence carries {judged.evidence_predicates} claims, so it "
            "restates the passage instead of drawing one claim out of it"
        ),
    )


def _quoted(judged: Judged) -> Failure | None:
    """Refuses a written statement that is more than one sentence copied.

    A copy of one sentence is left to `_atomic`, which counts the claims the
    statement reads as now rather than the ones its sentence was counted as
    carrying when the passage was chunked: carrying one, it is the fact, and
    carrying two, it is refused for those.
    """
    if sum(len(one.sentence_ids or ()) for one in judged.citations) == 1:
        return None
    return _copied(judged)


def _asserts(judged: Judged) -> Failure | None:
    """Refuses a statement carrying no finite verb."""
    if judged.claim.predicates:
        return None
    return (
        Rejection.ASSERTS_NOTHING,
        (
            "the statement has no finite verb, so it names something rather "
            "than asserting anything about it"
        ),
    )


#: The relations of a bridge that state a rule and its other side - a contrast,
#: an exception - so it may carry two claims. Names of `llm.spans.RELATIONS`.
_TWO_SIDED = frozenset({"contrast", "limits"})


def _atomic(judged: Judged) -> Failure | None:
    """Refuses a statement carrying more than one claim."""
    found = judged.claim.predicates
    if found <= judged.claims:
        return None
    return (
        Rejection.NOT_ATOMIC,
        (
            f"the statement carries {found} claims; a fact carries "
            f"{'one' if judged.claims == 1 else judged.claims}, and the rest "
            "belong to facts of their own"
        ),
    )


def _supported(judged: Judged) -> Failure | None:
    """Refuses a statement asserting what the cited text does not say."""
    added = judged.added
    if not added:
        return None
    swapped = "".join(
        f"; the cited text gives {cited} where the statement says {unit}"
        for unit, cited in judged.swaps
    )
    return (
        Rejection.UNSUPPORTED_ADDITION,
        (
            f"the statement asserts {', '.join(added)}, which the cited text does not "
            f"say{swapped}"
        ),
    )


def _self_contained(judged: Judged) -> Failure | None:
    """Refuses a statement a reader cannot understand without the passage."""
    references = judged.claim.references
    if not references:
        return None
    return (
        Rejection.UNRESOLVED_REFERENCE,
        (
            f"the statement leaves {', '.join(references)} unresolved, so a "
            "question drawn from it cannot be answered on its own"
        ),
    )


def _condensed(judged: Judged, share: float) -> Failure | None:
    """Refuses a digest no shorter than the passage it stands in for.

    Args:
        judged: The candidate under check.
        share: The longest a digest may be, as a share of its evidence.

    Returns:
        The refusal and its measurement, or None.
    """
    written, source = (
        len(normalised(judged.statement)),
        len(normalised(judged.evidence)),
    )
    if not source or written <= share * source:
        return None
    return (
        Rejection.NOT_CONDENSED,
        (
            f"the digest is {written} characters against {source} of passage, "
            f"which is {written / source:.0%} of it and above the {share:.0%} a "
            "reader gains anything by reading instead"
        ),
    )


def _listed(judged: Judged) -> Failure | None:
    """Refuses an outline holding fewer than two points.

    An outline is checked on its shape and not on its grammar: a point is
    written as a fragment, and a parser reads a fragment as having no verb.
    """
    points = sum(1 for line in judged.statement.splitlines() if line.startswith(BULLET))
    if points >= MIN_POINTS:
        return None
    return (
        Rejection.NOT_LISTED,
        (
            f"the outline holds {points} point(s); a list of fewer than "
            f"{MIN_POINTS} is a label"
        ),
    )


def _bridging(judged: Judged) -> Failure | None:
    """Refuses a bridge citing sentences in fewer than two passages.

    Counted on what resolved, not on what was named: a claim that named two
    passages and cited a real sentence in only one of them rests on one.
    """
    if len(judged.citations) >= 2:
        return None
    return (
        Rejection.NOT_BRIDGING,
        (
            f"the statement cites {len(judged.citations)} passage(s); a bridge "
            "carries a claim no single passage states"
        ),
    )


#: The endings a label word takes to inflect (plural, case), by ISO 639-1
#: code. A word that merely begins with a label word is not one of its forms.
_INFLECTIONS: dict[str, tuple[str, ...]] = {
    "de": ("s", "n", "e", "en", "es"),
    "en": ("s",),
}


def label_word(
    tokens: Sequence, at: int, words: Collection[str], language: str | None
) -> str | None:
    """The learned label word the token at `at` is, or None.

    By form or lemma ("section"), or inflected and directly followed by a
    number ("Sections 7": a tagger that reads it as a proper noun leaves its
    lemma as written). An inflection is an ending of the language's table.
    """
    token = tokens[at]
    forms = {token.text.casefold(), token.lemma_.casefold()}
    if found := next((w for w in words if w in forms), None):
        return found
    if at + 1 < len(tokens) and _section(tokens[at + 1].text):
        text = token.text.casefold()
        ends = _INFLECTIONS.get(language or "", ())
        return next(
            (w for w in words if any(text == w + end for end in ends)),
            None,
        )
    return None


#: What a number counts when it stands before one: a noun, a name, a unit.
_COUNTED = frozenset({"NOUN", "PROPN", "SYM"})


def numbered(tokens: Sequence, at: int) -> list[str]:
    """The numbers a label word at `at` names, a closing full stop dropped.

    The one directly after it, and each joined to that by a conjunction or a
    comma: "Sections 7, 9 and 11" names all three. After a singular label a
    joined number that counts what follows it is no section: "Section 7, 3
    transfers a month".
    """
    found = []
    plural = "Plur" in tokens[at].morph.get("Number", [])
    nxt = at + 1
    while nxt < len(tokens) and (number := _section(tokens[nxt].text)):
        found.append(number)
        joined = nxt + 2
        if (
            joined < len(tokens)
            and tokens[nxt + 1].pos_ in ("CCONJ", "PUNCT")
            and _section(tokens[joined].text)
            and (plural or not _counts(tokens, joined))
        ):
            nxt = joined
        else:
            break
    return found


def _counts(tokens: Sequence, at: int) -> bool:
    """Whether the number at `at` counts something after it: "3 other rules"."""
    number = tokens[at]
    after = tokens[at + 1] if at + 1 < len(tokens) else None
    return (after is not None and after.pos_ in _COUNTED) or (
        number.head.i > number.i and number.head.pos_ in _COUNTED
    )


def _names(tokens: Sequence, word: str, number: str, language: str | None) -> bool:
    """Reports whether the label word names its number.

    The word by form, lemma or inflection ("Sections 7"), the number after it
    or conjoined to the one after it ("Sections 7 and 9"), or both glued in
    one token ("§7").
    """
    for at, token in enumerate(tokens):
        if word + number in {token.text.casefold(), token.lemma_.casefold()}:
            return True
        if label_word(tokens, at, (word,), language) and number in numbered(tokens, at):
            return True
    return False


def _located(judged: Judged) -> Failure | None:
    """Refuses a bridge naming the numbered heading one of its passages sits under."""
    tokens = list(pipeline(judged.language)(judged.statement))
    for label in judged.labels:
        match = HEADING_LABEL.match(label.strip())
        if match and _names(
            tokens, match.group(1).casefold(), match.group(2), judged.language
        ):
            return (
                Rejection.NOT_BRIDGING,
                (
                    f"the statement names where its passage sits ({label.strip()}), "
                    "which is a claim about the document and not one either "
                    "passage makes"
                ),
            )
    return None


#: Applied to a statement a deterministic reader composed, whatever its kind.
#: Nothing else is asked of one: it is neither written nor a sentence.
_COMPOSED: tuple[Check, ...] = (_copied,)


class FactChecker:
    """Judges a candidate against the passages it was drawn from.

    A candidate that passes carries the span its citation covers. One that
    fails comes back marked invalid, with the code that refused it and
    everything the checks read.
    """

    def __init__(self, digest_share: float | None = None) -> None:
        """Initialises the checker.

        Args:
            digest_share: The longest a summary or an outline may be, as a
                share of its passage. Read from EXTRACTION_DIGEST_MAX_SHARE
                when not given.
        """
        share = (
            digest_share
            if digest_share is not None
            else decimal("EXTRACTION_DIGEST_MAX_SHARE")
        )
        condensed = partial(_condensed, share=share)
        self._by_kind: dict[str, tuple[Check, ...]] = {
            FactKind.ATOMIC: (_quoted, _asserts, _atomic, _supported, _self_contained),
            FactKind.SUMMARY: (_asserts, _supported, condensed),
            FactKind.OUTLINE: (_listed, _supported, condensed),
            FactKind.BRIDGE: (
                _asserts,
                _atomic,
                _supported,
                _self_contained,
                _bridging,
                _located,
            ),
        }

    def check(
        self,
        passage: PassageToExtract,
        candidate: CandidateFact,
        method: str,
        provenance: Provenance | None = None,
    ) -> CheckedFact:
        """Checks one candidate drawn from one passage.

        Args:
            passage: The passage it was drawn from.
            candidate: What the extractor proposed.
            method: llm or deterministic.
            provenance: What produced it, recorded on the fact.

        Returns:
            The candidate as a storable fact, validated or refused.
        """
        cited = (
            passage.sentences
            if candidate.kind in (FactKind.SUMMARY, FactKind.OUTLINE)
            else self._cited(passage, candidate)
        )
        if not cited:
            return _absent([passage], candidate, method, provenance)

        return self._verdict(
            passage,
            candidate,
            self._judge(passage, candidate, list(cited)),
            method,
            provenance,
        )

    def check_bridge(
        self,
        offered: Sequence[PassageToExtract],
        candidate: CandidateFact,
        provenance: Provenance | None = None,
    ) -> CheckedFact:
        """Checks one candidate drawn from a group of passages.

        Args:
            offered: The passages the model was shown, in the order it saw
                them. A candidate names them by position.
            candidate: What the extractor proposed.
            provenance: What produced it, recorded on the fact.

        Returns:
            The candidate as a storable fact, carrying a span in each passage
            it cites.
        """
        # One citation per passage, whichever position named it first: two
        # rows for one passage would collide on fact_passages' primary key,
        # and would let a claim resting on one passage count as a bridge.
        rested: list[tuple[PassageToExtract, Citation]] = []
        seen: set[int] = set()
        for one in sorted(candidate.passages, key=lambda cited: cited.position):
            resolved = _resolve(offered, one)
            if resolved is None or resolved[0].id in seen:
                continue
            seen.add(resolved[0].id)
            rested.append(resolved)
        if not rested:
            return _absent(offered, candidate, WRITTEN, provenance)

        anchor = rested[0][0]
        statement = candidate.statement.strip()
        # Each passage's cited sentences, in the order it named them. Read
        # once: the evidence and the vocabulary are the same text.
        texts = [
            _cited_text(
                passage, [passage.sentences[at] for at in one.sentence_ids or ()]
            )
            for passage, one in rested
        ]
        known: set[str] = set()
        numbers: set[str] = set()
        for (passage, _), text in zip(rested, texts, strict=True):
            more, figures = _carried(text, passage)
            known |= more
            numbers |= figures
        known |= numbers
        said = claim(
            statement, anchor.language, tuple(passage.text for passage, _ in rested)
        )
        judged = Judged(
            statement=statement,
            evidence=_JOIN.join(texts),
            # Over the cited sentences of every passage, not over every
            # sentence of them: what the claim rests on is what it named.
            evidence_predicates=sum(
                passage.sentences[index].predicates
                for passage, one in rested
                for index in one.sentence_ids or ()
            ),
            claim=said,
            evidence_vocabulary=frozenset(known),
            supported=_supported_units(
                said.units + said.figures, known, numbers, anchor.language, statement
            ),
            citations=tuple(one for _, one in rested),
            labels=tuple(
                segment
                for passage, _ in rested
                for segment in headings_of(passage.section_path)
                if HEADING_LABEL.match(segment.strip())
            ),
            language=anchor.language,
            claims=2 if candidate.relation in _TWO_SIDED else 1,
        )
        return self._verdict(anchor, candidate, judged, WRITTEN, provenance)

    def _verdict(
        self,
        passage: PassageToExtract,
        candidate: CandidateFact,
        judged: Judged,
        method: str,
        provenance: Provenance | None,
    ) -> CheckedFact:
        """Runs the checks this kind and method call for, first failure wins."""
        checks = self._by_kind[candidate.kind] if method == WRITTEN else _COMPOSED
        for check in checks:
            failed = check(judged)
            if failed:
                return _fact(passage, judged, candidate, method, provenance, failed)
        return _fact(passage, judged, candidate, method, provenance, None)

    @staticmethod
    def _cited(passage: PassageToExtract, candidate: CandidateFact) -> list | None:
        """Resolves the cited sentence indices, or None if any is not one.

        Stricter than `_resolve`, which drops the indices a passage does not
        have and keeps the rest, and the difference is deliberate. Here the
        citation is the whole of what the claim rests on, so one number the
        passage does not have means the model was not reading the excerpt it
        was shown and the fact is refused entire. There the citation is one
        of several the bridge names, `_bridging` already requires two
        passages to resolve, and refusing the lot for one bad number in one
        of them would throw away a claim that does rest on the others.

        One exception: a passage whose last sentence holds list lines is read
        by the model line by line, so an index past the end, by at most the
        lines of that sentence less one, names that line of it. It resolves
        to the last sentence, cut to the line.
        """
        ids = sorted(set(candidate.sentences))
        sentences = passage.sentences
        if not ids or not sentences:
            return None
        lines = _lines_of(sentences[-1])
        past = len(sentences) - 1
        if any(i < 0 or (i >= len(sentences) and i - past >= len(lines)) for i in ids):
            return None
        return [sentences[i] if i < len(sentences) else lines[i - past] for i in ids]

    @staticmethod
    def _judge(
        passage: PassageToExtract, candidate: CandidateFact, cited: list
    ) -> Judged:
        """Reads what the statement and its cited sentences each assert.

        What an atomic fact's evidence carries is its passage, with the
        section path and the document's title: a figure the list lead-in
        states, or a name the sentence before gives, is said by the passage
        the fact was drawn from. A name or a number no sentence of it has is
        still added. A digest's evidence is the sentences it cites. Neither
        counts a dotted number that numbers a part of the heading's own
        number ("3.2" under "Article 3") unless the cited text says it. A
        number is read in any spelling ("1st" is "1 st"), a hyphenated unit by
        its parts, a name the tagger took for a proper noun by the common noun
        it is, and a word by the form its text layer wrote it in.
        """
        start, end = cited[0].start, cited[-1].end
        evidence = _cited_text(passage, cited)
        language = passage.language
        statement = candidate.statement.strip()
        said = claim(statement, language, (passage.text,), passage.title)
        units = said.units + said.figures
        known, numbers = _carried(evidence, passage)
        known |= numbers
        supported = _supported_units(units, known, numbers, language, statement)
        swaps: dict[str, str] = {}
        if candidate.kind == FactKind.ATOMIC:
            alone = known | supported
            swaps = _swapped(statement, evidence, numbers, passage, language)
            known |= vocabulary(passage.text, language)
            numbers |= numerals(passage.text, language)
            known |= numbers
            numbered = {
                unit
                for unit in units
                if unit not in alone and _numbers_part_of(unit, passage.section_path)
            }
            known -= numbered
            supported = _supported_units(units, known, numbers, language, statement)
            supported -= numbered
        return Judged(
            statement=statement,
            evidence=evidence,
            evidence_predicates=sum(sentence.predicates for sentence in cited),
            claim=said,
            evidence_vocabulary=frozenset(known),
            supported=supported,
            citations=(
                Citation(
                    passage_id=passage.id,
                    sentence_ids=[sentence.index for sentence in cited],
                    start=start,
                    end=end,
                ),
            ),
            swaps=tuple(swaps.items()),
        )


def _carried(evidence: str, passage: PassageToExtract) -> tuple[set[str], set[str]]:
    """Reads what a passage's cited text, heading trail and title carry.

    The trail and the title name what a sentence under them leaves as "the
    card" or "the bank", so they are evidence of a name or a number.

    Returns:
        Every form a word appears in, and the numerals, of all three.
    """
    language = passage.language
    known = set(vocabulary(evidence, language))
    numbers = set(numerals(evidence, language))
    headings = "\n".join(part for part in (passage.section_path, passage.title) if part)
    if headings:
        known |= vocabulary(headings, language)
        numbers |= numerals(headings, language)
    return known, numbers


#: The parts of speech of a word naming what a figure measures or counts: the
#: unit after it ("30 days"), the code or sign beside it ("EUR 5").
_UNIT_WORDS = frozenset({"NOUN", "PROPN", "SYM"})

#: What may stand between a figure and the noun it counts: "5 working days".
_MODIFIERS = frozenset({"ADJ", "VERB"})

#: The words of a language that name a share, by ISO 639-1 code, as lower
#: case: `%` is one in every language. A newly configured language supplies
#: its own word, or reads a share written out as a word of its own kind.
_SHARE_WORDS: dict[str, frozenset[str]] = {
    "de": frozenset({"%", "prozent"}),
    "en": frozenset({"%", "percent"}),
}

#: The lemmas of a language's units of time that a period is counted in, by
#: ISO 639-1 code, as lower case: "30 days" and "2 weeks" are two figures of
#: one kind. A newly configured language supplies its days, weeks and months,
#: or its periods are compared by the unit as written.
_TIME_UNITS: dict[str, frozenset[str]] = {
    "de": frozenset({"tag", "woche", "monat"}),
    "en": frozenset({"day", "week", "month"}),
}


def _named_kind(word: str, language: str | None) -> str | None:
    """The kind a word names whatever its spelling: a currency, a share, a period.

    A currency is an ISO 4217 code, a sign or the language's own word, so
    `EUR`, `€` and `Euro` are one kind; None for any other word.
    """
    bare = word.strip(".,;:()")
    code = (language or "").strip().lower()
    if is_currency(bare, language):
        return "currency"
    if bare.casefold() in _SHARE_WORDS.get(code, ()):
        return "share"
    if bare.casefold() in _TIME_UNITS.get(code, ()):
        return "period"
    return None


def _kind_of(tokens: Sequence, at: int, language: str | None) -> str | None:
    """What the figure at `at` measures or counts, from the word beside it.

    A sign or unit written on the figure ("5%", "$5"), else the noun or
    sign after it, the last of a run of nouns ("5 working days"), else before it: "EUR" of
    "EUR 5 per month" and of "5 EUR", "days" of "30 days". None where the
    parse names none, which is every figure of a language no pipeline is
    configured for.
    """
    token = tokens[at]
    if any(one.isdigit() for one in token.text) and (
        attached := re.sub(r"[\d.,:/\s()+\-−±]+", "", token.text)
    ):
        return _named_kind(attached, language) or attached.casefold()
    ahead = at + 1
    while ahead < min(at + 3, len(tokens) - 1) and tokens[ahead].pos_ in _MODIFIERS:
        ahead += 1
    while (
        ahead < min(at + 4, len(tokens) - 1)
        and tokens[ahead].pos_ == "NOUN"
        and tokens[ahead + 1].pos_ == "NOUN"
    ):
        ahead += 1
    for near in (ahead, at - 1):
        if 0 <= near < len(tokens) and tokens[near].pos_ in _UNIT_WORDS:
            word = tokens[near]
            return (
                _named_kind(word.text, language)
                or _named_kind(word.lemma_, language)
                or word.lemma_.casefold()
            )
    return None


def _figure_tokens(
    text: str, language: str | None
) -> list[tuple[str, frozenset[str], tuple[int, ...], str]]:
    """The figures of a text as written: with their numerals, their digit runs and kind.

    The digit runs make `23.59` and `23:59`, or `9,95` and `9.95`, one figure
    however it is punctuated. A cardinal written out ("four euros") is a
    figure of the digits it names, in a configured language.
    """
    tokens = list(parse(text, language))
    spoken = spoken_numbers(text, language)
    found = []
    for at, token in enumerate(tokens):
        if at in spoken:
            digits, runs = frozenset({spoken[at]}), (int(spoken[at]),)
        elif any(one.isdigit() for one in token.text):
            digits = numerals(token.text, language)
            runs = tuple(int(run) for run in re.findall(r"\d+", token.text))
        else:
            continue
        if digits and (kind := _kind_of(tokens, at, language)):
            found.append((token.text.strip(".,;:()").casefold(), digits, runs, kind))
    return found


def _swapped(
    statement: str,
    evidence: str,
    cited: set[str],
    passage: PassageToExtract,
    language: str | None,
) -> dict[str, str]:
    """Finds the figures a statement took from the passage in place of the cited one.

    A figure only the rest of the passage states, where the cited sentences
    state another of its kind (a currency amount, a share, a count of days, a
    time of day: what stands beside it is the same), is a swap, not a figure
    the passage supports: "costs EUR 2" for a cited "costs EUR 5". Maps each
    such figure as the statement writes it to the one the evidence writes. A
    cited figure the statement writes too is kept, not swapped out:
    "EUR 4.95 for orders under EUR 50" keeps the 4.95.
    """
    elsewhere = numerals(passage.text, language) - cited
    swaps: dict[str, str] = {}
    own = None
    said = _figure_tokens(statement, language)
    for unit, digits, runs, kind in said:
        if digits <= cited or not digits <= elsewhere:
            continue
        if own is None:
            own = _figure_tokens(evidence, language)
        kept = [(one, there) for _, one, there, near in said if near == kind]
        for written, theirs_digits, theirs, there in own:
            if there != kind or theirs == runs or theirs_digits == digits:
                continue
            if any(theirs == run or theirs_digits == one for one, run in kept):
                continue
            swaps[unit] = written
            break
    return swaps


def _numbers_part_of(unit: str, section_path: str | None) -> bool:
    """Whether a dotted number numbers a part of a number the heading trail writes.

    "19.05" under "Article 19": the passage's own heading numbers what it
    holds, so the passage naming it says nothing a statement may rest on.
    """
    if "." not in unit.strip("."):
        return False
    return unit.rsplit(".", 1)[0] in vocabulary(section_path or "", None)


def _supported_units(
    units: Sequence[str],
    known: set[str],
    numbers: set[str],
    language: str | None,
    statement: str | None = None,
) -> frozenset[str]:
    """Picks the units read as present though no form of them is.

    A number spelled another way ("1st" is "1 st"), a hyphenated unit of
    words it holds, a name it holds as a noun, and, when the statement is
    given, a word in the form the text layer wrote it in.
    """
    supported = set()
    for unit in units:
        if unit in known:
            continue
        if figures := numerals(unit, language):
            if figures <= numbers:
                supported.add(unit)
        elif "-" in unit:
            parts = [part for part in unit.split("-") if part]
            if all(part in known for part in parts):
                supported.add(unit)
        elif as_noun(unit, language) & known:
            supported.add(unit)
        if (
            unit not in supported
            and statement is not None
            and written_in(
                unit, statement, known, _INFLECTIONS.get(language or "", ()), language
            )
        ):
            supported.add(unit)
    return frozenset(supported)


def _resolve(
    offered: Sequence[PassageToExtract], cited: Cited
) -> tuple[PassageToExtract, Citation] | None:
    """Resolves one of a bridge's citations against the passage it names.

    Args:
        offered: The passages the model was shown.
        cited: One entry of what it returned.

    Returns:
        The passage and the span its cited sentences cover, or None when the
        position is not one it was shown or none of the sentences is one that
        passage has.
    """
    if not 0 <= cited.position < len(offered):
        return None
    passage = offered[cited.position]
    ids = sorted({i for i in cited.sentences if 0 <= i < len(passage.sentences)})
    if not ids:
        return None
    spans = [passage.sentences[i] for i in ids]
    return passage, Citation(
        passage_id=passage.id,
        sentence_ids=ids,
        start=spans[0].start,
        end=spans[-1].end,
    )


def _reading(candidate: CandidateFact) -> dict | None:
    """What a bridge was written with and tested with, or None when it has neither."""
    if (
        candidate.kind != FactKind.BRIDGE
        or not candidate.relation
        or not candidate.probe
    ):
        return None
    question, answer = candidate.probe
    return {"relation": candidate.relation, "question": question, "answer": answer}


def _fact(
    passage: PassageToExtract,
    judged: Judged,
    candidate: CandidateFact,
    method: str,
    provenance: Provenance | None,
    failed: Failure | None,
) -> CheckedFact:
    """Assembles one checked fact."""
    code, detail = failed if failed else (None, None)
    return CheckedFact(
        statement=judged.statement,
        evidence_text=judged.evidence,
        extraction_method=method,
        validated=code is None,
        rejection_code=code,
        validation_error=detail,
        kind=candidate.kind,
        citations=list(judged.citations),
        statement_predicates=judged.claim.predicates,
        evidence_predicates=judged.evidence_predicates,
        units_statement=list(judged.claim.units),
        units_added=list(judged.added),
        unresolved_references=list(judged.claim.references),
        extraction_model=provenance.model if provenance else None,
        prompt_version=provenance.prompt_version if provenance else None,
        extraction_temperature=provenance.temperature if provenance else None,
        spacy_model=pipeline_name(passage.language),
        spacy_version=pipeline_version(passage.language),
        bridge=_reading(candidate),
    )


def _absent(
    read: Sequence[PassageToExtract],
    candidate: CandidateFact,
    method: str,
    provenance: Provenance | None,
) -> CheckedFact:
    """Builds a fact whose citation names nothing that was offered.

    It still names the passages it was read from, with no span in any of
    them: that is what it was drawn from, and it is what makes the refusal
    visible under those passages and replaceable when they are re-read.
    """
    if candidate.kind == FactKind.BRIDGE:
        named = tuple(one.position for one in candidate.passages)
        detail = "no sentence of any passage of the group it was shown"
    else:
        named = candidate.sentences
        detail = f"the passage has {len(read[0].sentences)}"
    return CheckedFact(
        statement=candidate.statement.strip(),
        evidence_text="",
        extraction_method=method,
        validated=False,
        rejection_code=Rejection.EVIDENCE_ABSENT,
        validation_error=(
            f"the citation names {', '.join(str(i) for i in named) or '(none)'}, "
            f"and {detail}"
        ),
        kind=candidate.kind,
        citations=[Citation(passage_id=one.id) for one in read],
        extraction_model=provenance.model if provenance else None,
        prompt_version=provenance.prompt_version if provenance else None,
        extraction_temperature=provenance.temperature if provenance else None,
        spacy_model=pipeline_name(read[0].language if read else None),
        spacy_version=pipeline_version(read[0].language if read else None),
        bridge=_reading(candidate),
    )
