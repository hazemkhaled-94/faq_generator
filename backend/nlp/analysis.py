"""Reading claims, sentences and vocabulary out of text with spaCy."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise, takewhile

from spacy.pipeline import Lemmatizer
from spacy.tokens import Doc, Span, Token

from nlp.language import URL
from nlp.models import Claim, Sentence
from nlp.pipelines import pipeline
from settings import optional

#: Parts of speech kept as vocabulary. Everything else is grammar, which is
#: what a stopword list used to be needed for.
_CONTENT = frozenset({"NOUN", "PROPN", "ADJ"})

#: Parts of speech a noun is tagged with, in the languages that capitalise one.
_NOMINAL = frozenset({"NOUN", "PROPN"})


#: How many texts to hand spaCy at once.
_BATCH = 64

_WHITESPACE = re.compile(r"\s+")

#: Sentence punctuation the tokenizer keeps inside a token's surface form. The
#: German tokenizer reads a year ending a sentence as one token, `2026.`, and
#: the same year anywhere else as `2026`.
_TRAILING = ".,;:"

#: How many parsed texts to keep. The gates below read one question and one
#: answer between six and eight ways each, and none of them knew another had
#: already parsed the string: putting one candidate through
#: `QuestionChecker.check` parsed its question six times, its target answer
#: seven, and - in `asserted`, `explains` and `about` - the cited passages
#: joined together up to three times, which is the expensive one.
#:
#: ponytail: sized for one candidate's worth of strings, not for a corpus.
#: A Doc holds its own tokens and vectors, so a large cache is real memory in
#: a worker that already carries the embedding model; this is small enough to
#: be free and large enough that nothing within one `check` misses. The
#: upgrade, if a caller ever needs more, is to thread one Doc through the
#: gates instead of a string.
_PARSED = 64


@lru_cache(maxsize=_PARSED)
def _read(text: str, language: str | None) -> Doc:
    """Parses one text, remembering the last few.

    Keyed on the text and the language rather than on the pipeline, because
    the pipeline is what `pipeline` already caches and two languages
    resolving to one model give one Doc either way.

    Read-only to every caller here, which is what makes sharing a Doc safe:
    nothing below writes to a token, a span or an extension.
    """
    return _grouped(pipeline(language)(text), language)


def _grouped(document: Doc, language: str | None) -> Doc:
    """Merges the digit groups a space joins where the text writes an amount.

    The tokenizer splits `100 000` and `12 500.00` at the space, so a reader
    of tokens takes each for two figures. A merge keeps every offset and
    gives the token its own text as its lemma. A full stop the tokenizer
    kept on the last group, at a sentence's end, goes with it.
    """
    spans = []
    for found in _SPACED.finditer(document.text):
        if _amount(document.text, found.start(), found.end(), language):
            span = document.char_span(
                found.start(), found.end(), alignment_mode="expand"
            )
            if span is not None and len(span) > 1:
                spans.append(span)
    if spans:
        with document.retokenize() as merger:
            for span in spans:
                merger.merge(span, attrs={"LEMMA": span.text})
    return document


def parse(text: str, language: str | None) -> Doc:
    """The parse every reading here is made on: `_read`, for a gate that needs a token."""
    return _read(text, language)


@lru_cache(maxsize=1)
def _capitalises_nouns() -> frozenset[str]:
    """Reads the languages whose every noun is written with a capital.

    Optional: a deployment configured for languages that capitalise nothing
    names none, and no token is judged on its case.
    """
    named = optional("NLP_CAPITALISED_NOUNS") or ""
    return frozenset(code.strip().lower() for code in named.split(",") if code.strip())


def _bare(form: str) -> str:
    """Trims the sentence punctuation a token carried into its surface form.

    Trailing only, so `12,5` and `12.5` stay the different values they are.
    """
    return form.rstrip(_TRAILING) or form


def normalised(text: str) -> str:
    """Collapses spacing and case, for comparing two strings as words.

    `casefold` rather than `lower`, because this corpus is partly German and
    only casefold folds ß to ss - "STRASSE" and "Straße" are the same word.
    """
    return _WHITESPACE.sub(" ", text).strip().casefold()


#: Dependency labels that hang a clause off another one rather than standing
#: it beside. A finite verb under one of these is a modifier, not a second
#: assertion: German `rc` (relative), `oc` (clausal object), `mo` (adverbial),
#: `sb` (clausal subject), `re` (reported), and the UD names for the same.
#: Coordination is deliberately absent - `cj` and `conj` join two claims.
_SUBORDINATE = frozenset(
    {
        "rc",
        "oc",
        "mo",
        "sb",
        "re",
        "relcl",
        "ccomp",
        "xcomp",
        "advcl",
        "csubj",
        "acl",
    }
)


def _dependent(token) -> bool:
    """Whether a token sits inside a clause hung off another one."""
    return token.dep_ in _SUBORDINATE or any(
        parent.dep_ in _SUBORDINATE for parent in token.ancestors
    )


#: Dependency labels that join one clause to another as an equal, in Universal
#: Dependencies and in the TIGER scheme. A clause reaching the root through
#: these alone stands beside the rest; any other attachment embeds it.
_COORDINATION = frozenset({"conj", "cj", "cd", "parataxis"})

#: Word runs that open an exception or a condition without a subordinator in
#: the parse, keyed by ISO language. "es sei denn" carries a finite verb of
#: its own, and the clause it opens only restricts the rule before it.
_EXCEPTIVE: dict[str, tuple[tuple[str, ...], ...]] = {
    "de": (
        ("es", "sei", "denn"),
        ("außer",),
        ("ausser",),
        ("ausgenommen",),
        ("vorausgesetzt",),
        ("sofern",),
        ("soweit",),
        ("solange",),
    ),
    "en": (
        ("unless",),
        ("except",),
        ("provided",),
        ("providing",),
        ("as", "long", "as"),
        ("so", "long", "as"),
        ("on", "condition", "that"),
    ),
}

#: The languages whose subordinate clause ends on its finite verb, so a clause
#: of that order after a comma and "und" goes on with the subordinate clause
#: before it rather than starting a main clause: "..., wenn der Kunde zahlt,
#: und die Ware geliefert wurde". A language not named reads every conjunct as
#: a main clause; a newly configured one names itself here if its subordinate
#: clauses are verb-final.
_VERB_FINAL_SUBORDINATE = frozenset({"de", "nl"})

#: Coordinators that offer alternatives, keyed by ISO language. "A or B" does
#: not entail A, so a conjunct joined by one is not a claim of its own.
_DISJUNCTIVE: dict[str, frozenset[str]] = {
    "de": frozenset({"oder", "bzw.", "beziehungsweise", "noch", "entweder"}),
    "en": frozenset({"or", "nor", "either"}),
}


def _clause_verb(token):
    """Climbs from an auxiliary or copula to the verb whose clause it is in."""
    while token.dep_ in _CARRIERS and token.head.i != token.i:
        token = token.head
    return token


def _coordinated_to_root(token) -> bool:
    """Whether a token's clause reaches the sentence root through coordination alone."""
    token = _clause_verb(token)
    while token.head.i != token.i:
        if token.dep_ not in _COORDINATION:
            return False
        token = token.head
    return True


def _own_subject(verb) -> bool:
    """Whether a verb, or an auxiliary or copula under it, has a subject of its own."""
    return any(
        child.dep_ in _OWN_SUBJECTS
        or (
            child.dep_ in _CARRIERS
            and any(one.dep_ in _OWN_SUBJECTS for one in child.children)
        )
        for child in verb.children
    )


def _finite_of(verb):
    """The finite token of a clause: the verb, or an auxiliary or copula under it."""
    for one in (verb, *(child for child in verb.children if child.dep_ in _CARRIERS)):
        if "Fin" in one.morph.get("VerbForm", []):
            return one
    return verb


def _ends_on_verb(verb) -> bool:
    """Whether a conjunct clause has several constituents before its finite verb and ends on it.

    The clause's own tokens, without the clauses coordinated to it and their
    coordinators: German subordinate order, the finite verb last. One
    constituent before it is a subject and its verb, which main-clause order
    also writes: "und der Kunde zahlt".
    """
    dropped: set[int] = set()
    for child in verb.children:
        if child.dep_ in _COORDINATION or child.dep_ in ("cc", "cd"):
            dropped |= {one.i for one in child.subtree}
    own = [one for one in verb.subtree if one.i not in dropped and not one.is_punct]
    finite = _finite_of(verb)

    def constituent(token) -> int:
        while token.head.i not in (token.i, verb.i):
            token = token.head
        return token.i

    before = {constituent(one) for one in own if one.i < finite.i}
    return len(before) >= 2 and max(own, key=lambda one: one.i).i == finite.i


def _after_subordinate(verb, verbs: list) -> bool:
    """Whether the clause before a conjunct is a subordinate one.

    The nearest verb before the conjunct's clause, of any form because the
    parser reads a subordinate verb as a participle at times, is one a
    subordinator or a relative adverb opens, or a relative clause, or a verb-final conjunct that
    itself goes on with one: "wenn der Kunde zahlt, und die Ware geliefert
    wurde". After a main clause a verb-final conjunct is a second main clause:
    "Der Kunde zahlt, und der Händler liefert".
    """
    start = min(one.i for one in verb.subtree)
    before = [one for one in verbs if one.i < start]
    if not before:
        return False
    earlier = _clause_verb(before[-1])
    return (
        any(
            child.dep_ in _SUBORDINATOR or child.pos_ == "SCONJ"
            for child in earlier.children
        )
        or earlier.dep_ in _RELATIVE
        or (
            earlier.dep_ in _COORDINATION
            and _ends_on_verb(earlier)
            and _after_subordinate(earlier, verbs)
        )
    )


def _coordination_top(verb):
    """The first clause of the coordination a conjunct is in."""
    while verb.dep_ in _COORDINATION and verb.head.i != verb.i:
        verb = verb.head
    return verb


def _closed_by_alternative(verb, alternatives: frozenset[str]) -> bool:
    """Whether a conjunct, joined by a comma, is a member of a list closed by "or".

    "The card is returned, exchanged or repaired": the list's last member is
    joined by an alternative and no coordinator that adds stands between, so
    each member is one of the alternatives.
    """
    top = _coordination_top(verb)
    if top.dep_ in ("cc", "cd"):
        top = top.head
    members: list = []
    stack = [top]
    while stack:
        for child in stack.pop().children:
            if child.dep_ in _COORDINATION:
                members.append(child)
                stack.append(child)
            elif child.dep_ in ("cc", "cd"):
                for one in child.children:
                    if one.dep_ in _COORDINATION:
                        members.append(one)
                        stack.append(one)
    after = sorted((one for one in members if one.i > verb.i), key=lambda one: one.i)
    if not after:
        return False
    between: set[str] = set()
    for one in after[:-1]:
        between |= _coordinator_words(one)
    return bool(_coordinator_words(after[-1]) & alternatives) and not (
        between - alternatives
    )


def _exceptive_tokens(doc: Doc) -> tuple[set[int], set[int]]:
    """Indices of exceptive-run tokens, and of the token right after each run.

    A one-word run the tagger reads as a finite verb is no exception opened
    where it has a subject of its own: "The bank provided the card" states
    what `provided` would otherwise only restrict, and "provided the card is
    unused" has the card for its subject.
    """
    words = [token.text.casefold() for token in doc]
    inside: set[int] = set()
    after: set[int] = set()
    for run in _EXCEPTIVE.get(doc.lang_, ()):
        for start in range(len(words) - len(run) + 1):
            if tuple(words[start : start + len(run)]) != run:
                continue
            if (
                len(run) == 1
                and "Fin" in doc[start].morph.get("VerbForm", [])
                and _own_subject(doc[start])
            ):
                continue
            inside.update(range(start, start + len(run)))
            end = start + len(run)
            while end < len(doc) and doc[end].is_punct:
                end += 1
            after.add(end)
    return inside, after


def _coordinator_words(token) -> set[str]:
    """The case-folded words joining a token's clause to the one before it."""
    verb = _clause_verb(token)
    words = [child for child in verb.children if child.dep_ == "cc"]
    if verb.head.dep_ == "cd":
        words.append(verb.head)
    if verb.dep_ == "conj":
        # English hangs the cc on the first conjunct, ahead of this one.
        words += [
            child
            for child in verb.head.children
            if child.dep_ == "cc" and child.i < verb.i
        ]
    return {word.text.casefold() for word in words}


def _root(token):
    """The root of the sentence a token is parsed in."""
    while token.head.i != token.i:
        token = token.head
    return token


def _predicates(span: Doc | Span) -> int:
    """Counts the claims a span makes, as its independent finite verbs.

    A finite verb counts as a claim of its own only when its clause stands
    beside the main one: it reaches the sentence root through coordination
    alone, whatever else the parse hangs it from. A relative, a reported or
    a conditional clause is a modifier of something already said rather than
    a second thing said: "TPI NEXT gehört zu den Prozessmodellen, die die
    Testprozessverbesserung unterstützen" carries two finite verbs and one
    claim. Two main clauses joined by "und" are two claims.

    A rule with its exception is one claim, not two: the verb of "unless"
    or "es sei denn", and of the clause it opens, only restricts what the
    first clause says. So are two alternatives: "the card is blocked or the
    account is closed" does not entail either half, so a clause joined by
    "or" is no claim of its own. A language with no entry in the exception
    and alternative tables falls back to the attachment rule alone.

    A span carrying a finite verb makes at least one claim. A parse that
    hangs every clause off something else has mis-read the sentence, which
    is not the same as a sentence that asserts nothing. Nor is one rooted on
    a clause its subordinator opens: the parser made the condition the main
    clause and hung what it governs beside it, so the span is read as the
    one rule it states.
    """
    finite = [token for token in span if "Fin" in token.morph.get("VerbForm", [])]
    if not finite:
        return 0
    doc = span.doc
    verbs = [token for token in doc if token.pos_ in ("VERB", "AUX")]
    inside, after = _exceptive_tokens(doc)
    disjunctive = _DISJUNCTIVE.get(doc.lang_, frozenset())
    # Where the sentences start once the parser's cuts are corrected, for a
    # whole statement: a root the parser cut off in the middle of one is no
    # claim of its own.
    starts = set(_boundaries(doc)) if span is doc else None
    # The clauses that restrict or offer an alternative to another, which
    # carry their coordinated members with them: in "es sei denn, der Kunde
    # ruft an und bestätigt", bestätigt is part of the case left out.
    excluded: set[int] = set()
    counted = []
    for token in finite:
        if not _coordinated_to_root(token):
            continue
        verb = _clause_verb(token)
        start = min(one.i for one in verb.subtree)
        conjunct = verb.dep_ in _COORDINATION
        words = _coordinator_words(token) if conjunct else set()
        if (
            token.i in inside
            or start in inside
            or start in after
            or (conjunct and words & disjunctive)
            # A conjunct its own subordinator opens is a condition however the
            # parser hangs it: "but only if it has not been executed".
            or (
                conjunct and any(child.dep_ in _SUBORDINATOR for child in verb.children)
            )
            # A member of a list a comma joins that "or" closes offers an
            # alternative: "returned, exchanged or repaired".
            or (conjunct and not words and _closed_by_alternative(verb, disjunctive))
            # A subordinate clause of a language that ends it on its verb,
            # after a comma and "und", goes on with the subordinate clause
            # before it; after a main clause it is a second one.
            or (
                conjunct
                and doc.lang_ in _VERB_FINAL_SUBORDINATE
                and _ends_on_verb(verb)
                and _after_subordinate(verb, verbs)
            )
            or (verb.head.i == verb.i and starts is not None and _cut(verb, starts))
        ):
            # Only a conjunct carries its members with it: a main clause
            # opening on "Unless" is not counted, but what is joined to it is.
            if conjunct:
                excluded.add(verb.i)
            continue
        counted.append(verb)
    claims = sum(not _joined_to(verb, excluded) for verb in counted)
    if claims > 1 and any(
        child.dep_ in _SUBORDINATOR
        for root in {_root(token) for token in finite}
        for child in root.children
    ):
        return 1
    return claims or 1


def _cut(root, starts: set[int]) -> bool:
    """Whether a parser root begins a sentence only by the parser's cut.

    One that the corrected boundaries do not start, or that follows text on
    its line ending in no sentence mark ("circular no. 33 are not included"),
    is the rest of the sentence before it.
    """
    sentence = root.sent
    before = root.doc.text[: sentence.start_char].rstrip(" \t")
    return sentence.start not in starts or bool(before and before[-1] not in ".!?;:\n")


def _joined_to(verb, excluded: set[int]) -> bool:
    """Whether a clause reaches one of these through coordination alone."""
    while verb.dep_ in _COORDINATION and verb.head.i != verb.i:
        verb = verb.head
        if verb.i in excluded:
            return True
    return False


def _verbs(span: Doc | Span) -> int:
    """Counts verbs of any form, which is how an action is told from a thing."""
    return sum(1 for token in span if token.pos_ in ("VERB", "AUX"))


#: Tag prefixes of an interrogative word. Penn tags English ones WDT, WP, WP$
#: and WRB; STTS tags German ones PWS, PWAT and PWAV. Read off the tagger
#: rather than from a word list per language, so a pipeline added to
#: NLP_MODELS brings its own.
_INTERROGATIVE = ("W", "PW")


def _interrogative(token) -> bool:
    """Whether a token is a question word, under either naming.

    Two readings because no one of them covers every pipeline. Penn and STTS
    say so in the tag, and the English model leaves the morphology empty;
    a Universal Dependencies tagset says so in `PronType=Int` and its tags
    carry no such prefix. Either answer is taken, so a language whose
    pipeline uses only one of the two conventions still reports its question
    words.
    """
    return token.tag_.startswith(_INTERROGATIVE) or "Int" in token.morph.get(
        "PronType", []
    )


def _asking(token) -> bool:
    """Whether a question word asks the question rather than opening a clause in it.

    Not one under a relative or adverbial clause, in either tag set: `wo` in
    `ein Ort, wo es keine Filiale gibt`, `which` in `an account, which I
    opened`, `When` in `When I travel abroad, why ...`. And not a Penn
    W-word inside any clause hung off another. Penn only for that wider
    reading: STTS labels a German question word itself `mo` and hangs a
    modal's infinitive as `oc`, so it would drop `Wie` from `Wie viele
    Karten darf ein Kunde besitzen?`.
    """
    return (
        _interrogative(token)
        and not (token.tag_.startswith("W") and _dependent(token))
        and not any(parent.dep_ in _EMBEDDED for parent in token.ancestors)
    )


def interrogatives(text: str, language: str | None) -> tuple[str, ...]:
    """The question words one question uses.

    More than one is two questions joined by a conjunction - `Welche
    Vorschriften gelten für X und wie hoch ist die Gebühr für Y?` - which a
    chatbot can answer half of, and which nobody types.

    A finite-verb count does not separate those: `Welche Arten von Kryptowerten
    gelten als reguliert?` carries two and is one question.
    """
    return tuple(token.text for token in _read(text, language) if _asking(token))


#: What ends a premise before the question it leads to: a sentence, or a
#: clause set off by a comma, a colon, a semicolon or a dash.
_PREMISE_ENDS = frozenset({".", "!", ",", ":", ";", "\u2013", "\u2014"})


def asked(text: str, language: str | None) -> str:
    """The question itself, from where it begins after any premise.

    A question may open on what the asker says about themselves - `Ich bin
    neu bei der Bank. Wann ...?`, `As a new customer, why ...?` - which puts
    its question word mid-text. The question begins after the last sentence
    or clause end before its first question word, one `interrogatives`
    counts: `When I travel abroad, why ...?` asks `why`. Where none is
    counted - the parser hangs `I'm new here, when ...?` under its premise -
    it begins at the first question word at all. A text with no question
    word, or none of those ends before it, is the question whole.
    """
    start = 0
    first = None
    for token in _read(text, language):
        if _asking(token):
            return text[start:].strip()
        if first is None and _interrogative(token):
            first = text[start:].strip()
        if token.text in _PREMISE_ENDS:
            start = token.idx + len(token.text)
    return text if first is None else first


def is_number(token: Token) -> bool:
    """Whether a token `like_num` marks states a number, as against being spelled like one.

    `like_num` is a spelling test, so it holds for the pronoun in "No one may
    pass" and in "the one you bought". Such a word counts when it holds a
    digit or the tagger reads it as a numeral, `NUM`, or as an ordinal, an
    adjective in the language's `_ORDINALS`. "One card per account" is tagged
    `NUM` and stays a 1.
    """
    if not token.like_num:
        return False
    if any(char.isdigit() for char in token.text):
        return True
    return token.pos_ == "NUM" or (token.pos_ == "ADJ" and ordinal(token) is not None)


def ordinal(token: Token) -> str | None:
    """The digits an ordinal, `third`, `3rd` or a German `3.`, names, or None.

    A full stop after a figure is an ordinal only inside a sentence: at its
    end it closes the sentence.
    """
    language, text = token.doc.lang_, token.lower_
    for suffix in ORDINAL_SUFFIX.get(language, ()):
        if text.endswith(suffix) and text[: -len(suffix)].isdigit():
            return (
                None
                if token.is_sent_end and not suffix.isalpha()
                else text[: -len(suffix)]
            )
    return _ORDINALS.get(language, {}).get(text)


def _units(span: Doc | Span) -> tuple[str, ...]:
    """Collects the values a statement may not introduce on its own.

    Numbers and proper nouns only. Both are things a writer reports rather
    than chooses, so one appearing in a statement and nowhere in the sentence
    it cites was invented.

    Three things are deliberately left out. Common nouns, because a statement
    is supposed to name its subject in its own words. Verbs, because the
    statement is written rather than quoted, so its predicate is the model's
    to choose - "Die Digitalisierung schreitet fort" drawn from
    "fortschreitender Digitalisierung" is the same claim and shares no verb
    lemma. And named entities, because the tagger's entity decision moves with
    the surrounding words, so the two sides never agree: "Umbrüchen" came back
    a MISC entity in a short statement and no entity at all in the longer
    sentence it was drawn from.

    A number keeps its surface form, because 12,5 and 12.5 are different
    values. A proper noun is lemmatised, so an inflection is not an addition,
    and loses the sentence punctuation the tagger left on it ("m."). In a
    language that capitalises its nouns, a word the tagger calls a proper noun
    yet writes in lower case ("gelten") is no name and no unit.
    """
    found = set()
    capitalising = span.doc.lang_ in _capitalises_nouns()
    for token in span:
        if is_number(token):
            # An ordinal keeps what marks it, so `3.` is not the count 3.
            found.add((token.text if ordinal(token) else _bare(token.text)).casefold())
        elif token.pos_ == "PROPN":
            if (
                capitalising
                and token.text[:1].islower()
                and not any(letter.isupper() for letter in token.text[1:])
            ):
                continue
            found.add(_bare(token.lemma_.casefold()))
    return tuple(sorted(found))


#: A figure written as one token: digits first, then separators, then at
#: most four letters of a unit glued on - `08:00`, `2:2`, `2.5x`, `1,100g`.
#: A compound carrying a figure - `90-minütigen`, `4-m-Bereich` - runs on
#: past its unit and is a word; a name ending in digits starts with a letter.
#: The unit follows a digit directly: after a dash - `2-mal`, `3-fach` - the
#: letters make the digits a number word, which states no figure.
_FIGURE_TOKEN = re.compile(r"[+±−-]?\(?\d[\d.,:/()– -]*(?:(?<=\d)[^\W\d_]{1,4})?%?")


def _figures(span: Doc | Span) -> tuple[str, ...]:
    """The figures a statement writes that `_units` does not read.

    A token `like_num` marks, or the tagger calls a proper noun, is
    `_units`' already, so no figure is read twice. Kept as written, as a
    number there is, so `08:00` against `09:00` is a different figure.
    """
    return tuple(
        sorted(
            {
                _bare(token.text).casefold()
                for token in span
                if not token.like_num
                and token.pos_ != "PROPN"
                and _FIGURE_TOKEN.fullmatch(token.text)
            }
        )
    )


def _valued(words: str, start: int = 0) -> dict[str, str]:
    """Number words, spaced and in order, each mapped to the digits of its value."""
    return {word: str(value) for value, word in enumerate(words.split(), start)}


@dataclass(frozen=True)
class _Spelling:
    """How a language writes a cardinal.

    The words nought to nineteen and the tens twenty to ninety, in order; the
    words for a hundred and a thousand; what joins a unit and a ten
    (`twenty-five`, `fünfundzwanzig`) and which comes first; the form a one
    takes inside a compound; and whether a scale word glues to its multiplier
    (`zweitausend`) or stands apart (`twenty thousand`). Spelling variants
    name the second spelling of a word.
    """

    units: str
    tens: str
    hundred: str
    thousand: str
    join: str
    unit_first: bool
    one: str
    glued: bool
    variants: tuple[tuple[str, str], ...] = ()


#: The spelling of each language's cardinals, by ISO 639-1 code.
#:
#: ponytail: German and English. A language missing here reads its digits and
#: whatever `like_num` says, as written. Upgrade: a row per language.
_SPELLING: dict[str, _Spelling] = {
    "en": _Spelling(
        units="zero one two three four five six seven eight nine ten eleven "
        "twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen",
        tens="twenty thirty forty fifty sixty seventy eighty ninety",
        hundred="hundred",
        thousand="thousand",
        join="-",
        unit_first=False,
        one="one",
        glued=False,
    ),
    "de": _Spelling(
        units="null eins zwei drei vier fünf sechs sieben acht neun zehn elf "
        "zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn",
        tens="zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig",
        hundred="hundert",
        thousand="tausend",
        join="und",
        unit_first=True,
        one="ein",
        glued=True,
        variants=(("dreißig", "dreissig"),),
    ),
}


def _spelled_cardinals(row: _Spelling) -> dict[str, int]:
    """Every cardinal one language spells, as the value it names."""
    units = row.units.split()
    below = dict(enumerate(units))
    for index, ten in enumerate(row.tens.split(), 2):
        below[index * 10] = ten
        for unit in range(1, 10):
            word = row.one if unit == 1 and row.unit_first else units[unit]
            below[index * 10 + unit] = (
                f"{word}{row.join}{ten}" if row.unit_first else f"{ten}{row.join}{word}"
            )
    words = {word: value for value, word in below.items()}
    words[row.hundred] = 100
    words[row.thousand] = 1000
    if row.glued:
        glue = {**below, 1: row.one}
        for multiple in range(1, 10):
            head = f"{glue[multiple]}{row.hundred}"
            words[head] = multiple * 100
            words |= {
                f"{head}{below[rest]}": multiple * 100 + rest for rest in range(1, 100)
            }
        words |= {f"{row.hundred}{below[rest]}": 100 + rest for rest in range(1, 100)}
        words |= {f"{glue[many]}{row.thousand}": many * 1000 for many in range(1, 100)}
    for word, variant in row.variants:
        words[variant] = words[word]
    return words


#: Cardinals by ISO 639-1 code, each as the value it names. The one table
#: every reader of a count written out holds: `numbers` below, and the
#: question gates, which read the cardinals alone, so an ordinal -
#: `second half` - never counts anything there. A count past this table is
#: read as written; two words that make one - `twenty thousand` - are joined
#: by `numbers` and `numerals`.
CARDINALS: dict[str, dict[str, int]] = {
    language: _spelled_cardinals(row) for language, row in _SPELLING.items()
}

#: The mark each language writes a decimal with, by ISO 639-1 code. One
#: such mark before three digits is a fraction, not a thousands group: a
#: German `1,234 %` is a rate and `1.234` a count, and English the reverse.
#: A language missing here reads three digits after either mark as thousands.
DECIMAL_MARK: dict[str, str] = {"de": ",", "en": "."}

#: The words that mark an amount of money, by ISO 639-1 code, as lower case:
#: codes and names. A number grouped by a space - `5 000 Euro`,
#: `EUR 100 000`, `12 500.00 GBP` (DIN 5008 and SI) - is read as one figure
#: only with one of them, an ISO 4217 code or a currency sign (`€`, `¥`, `₹`:
#: any of Unicode's category Sc, so none is listed here) directly before or
#: after it, see `is_currency`. Anywhere else a space is no thousands mark: a
#: flattened table row, a phone number. A language missing here reads the
#: groups as separate figures beside a word, and as one beside a code or a
#: sign, which are no language's words.
#:
#: ponytail: one group of three digits after the head, so an amount past
#: 999 999 written `1 000 000` stays three figures, and a two-cell table row
#: whose second cell is an amount (`Kontoführung 5 120 Euro`, monthly 5 and
#: yearly 120) is read as 5120. Upgrade: read a longer run where a currency
#: stands beside each of its numbers, and a row by its table cells.
AMOUNT_WORDS: dict[str, frozenset[str]] = {
    "de": frozenset(
        [
            "eur",
            "euro",
            "usd",
            "dollar",
            "gbp",
            "pfund",
            "chf",
            "franken",
        ]
    ),
    "en": frozenset(
        [
            "eur",
            "euro",
            "euros",
            "usd",
            "dollar",
            "dollars",
            "gbp",
            "pound",
            "pounds",
            "chf",
        ]
    ),
}

#: The currency codes of ISO 4217: a static international standard, the same
#: in every language, so it is no list of one corpus's words. A code beside a
#: number is an amount whatever the language of the text around it.
ISO_4217 = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB
    BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP
    DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF
    IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK
    LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN
    NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF
    SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND
    TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER
    ZAR ZMW ZWL""".split()  # noqa: SIM905  (a list literal of 160 codes is no clearer)
)


def is_currency(word: str, language: str | None) -> bool:
    """Whether a word marks an amount of money: an ISO 4217 code, a currency sign, or the language's own word.

    A sign is a character of Unicode category Sc, in any script. Case matters
    for a code, which is written in capitals: `ALL` is a code and `all` is not.
    """
    bare = word.strip(".,;:()")
    return (
        bare in ISO_4217
        or (len(bare) == 1 and unicodedata.category(bare) == "Sc")
        or bare.casefold() in AMOUNT_WORDS.get((language or "").strip().lower(), ())
    )


#: The words that label a reference by a number, by ISO 639-1 code, as lower
#: case: `Section 3 100 customers` is a section and a count, whatever stands
#: after it.
REFERENCE_LABELS: dict[str, frozenset[str]] = {
    "de": frozenset(
        [
            "abschnitt",
            "absatz",
            "artikel",
            "art",
            "ziff",
            "ziffer",
            "nr",
            "kapitel",
            "seite",
            "§",
            "tabelle",
        ]
    ),
    "en": frozenset(
        [
            "section",
            "article",
            "art",
            "clause",
            "chapter",
            "no",
            "page",
            "paragraph",
            "para",
            "table",
        ]
    ),
}

#: A head of one to three digits and one group of exactly three, alone: not
#: part of a longer run of groups, as a table row is.
_SPACED = re.compile(
    r"(?<![\w.,])(?<!\d[ \u00a0\u202f])\d{1,3}[ \u00a0\u202f]\d{3}(?:[.,]\d+)?(?![\w])(?![ \u00a0\u202f]\d)"
)


def _beside(found: re.Match[str] | None, keep_case: bool = False) -> str:
    """The word a match holds, bare of punctuation, lower case unless its case is kept."""
    if not found:
        return ""
    word = found[1].strip(".,;:()")
    return word if keep_case else word.casefold()


#: The word that follows an amount: its letters only, so `Euro/Kunde` and
#: `Euro*` are `Euro`, or one sign, after an optional price dash
#: (`5 000,- EUR`) which only a decimal mark may open: `500-Euro-Scheine` is a
#: hyphen-joined noun, not an amount.
_CURRENCY_AFTER = re.compile(r"\s?(?:[.,][-–—]+\s?)?([^\W\d_]+|[^\w\s])")


def _amount(text: str, start: int, end: int, language: str | None) -> bool:
    """Whether a space-grouped run is an amount: a currency word or sign beside it, no label before.

    A text that is the run alone is one, as a unit read back out of an amount.
    """
    if not text[:start].strip() and not text[end:].strip(" ."):
        return True
    code = (language or "").strip().lower()
    before = _beside(re.search(r"(\S+)\s?$", text[:start]))
    return before not in REFERENCE_LABELS.get(code, ()) and any(
        is_currency(word, language)
        for word in (
            _beside(re.search(r"(\S+)\s?$", text[:start]), keep_case=True),
            _beside(_CURRENCY_AFTER.match(text[end:]), keep_case=True),
        )
    )


#: A figure as either convention writes one: 1.234,56 and 1,234.56 are the
#: same value, and 65 is itself. The second alternative stops at a separator
#: that carries a digit, so 1200 in `1200.` is a figure and the 1 of `1.234`
#: is not. The third alternative is a long figure with a fraction and no
#: thousands mark: `1299,99`, `2500.00`. The first is a number grouped by
#: spaces, which `figures` reads as one only beside a currency, see `_amount`.
FIGURE = re.compile(
    _SPACED.pattern + r"|(?<![\w.,])\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?(?![\w])"
    r"|(?<![\w.,])\d+(?![\w]|[.,]\d)"
    r"|(?<![\w.,])\d{4,}[.,]\d+(?![\w]|[.,]\d)"
)


def figures(text: str, language: str | None = None) -> list[float]:
    """Every number in a text, as a value.

    Anything after the last separator but a group of exactly three digits is
    a fraction, so 12,5 and 12.5 are 12.5. A group of three is a thousands
    group, so 1.234.567 and 1,234.5 hold one, except after a head of zeros -
    0,125 is an eighth, never 125 - and after a lone separator that is the
    language's `DECIMAL_MARK`: a German 1,234 is 1.234 and 1.234 is 1234,
    and English the reverse. A language with no row there, or none given,
    reads either lone mark as thousands. A number that resolves to neither
    is left out rather than guessed at.
    """
    mark = DECIMAL_MARK.get((language or "").strip().lower())
    found: list[float] = []
    for match in FIGURE.finditer(text):
        raw = match.group()
        if any(char.isspace() for char in raw):
            if _amount(text, match.start(), match.end(), language):
                raw = "".join(raw.split())
            else:
                found += [
                    one for part in raw.split() for one in figures(part, language)
                ]
                continue
        head, separator, tail = (
            raw.rpartition(",") if "," in raw[-4:] else raw.rpartition(".")
        )
        whole = head.replace(".", "").replace(",", "")
        decimal = (
            separator == mark
            and raw.count(separator) == 1
            and not (set(".,") - {separator}) & set(head)
        )
        plain = len(head) > 3 and head.isdigit()
        try:
            if not head or (
                len(tail) == 3 and whole.strip("0") and not decimal and not plain
            ):
                found.append(float(raw.replace(".", "").replace(",", "")))
            else:
                found.append(float(f"{whole}.{tail}"))
        except ValueError:
            continue
    return found


def _ordinals_past_twelve(language: str) -> dict[str, str]:
    """The ordinals from thirteenth on, each as the digits it names, composed from the cardinals.

    English puts `th` after the cardinal - `thirteenth`, `hundredth` - and
    `ieth` for `twentieth`. German puts `t` after a cardinal under twenty and
    `st` after any other, in every ending an ordinal takes. English compounds
    (`twenty-first`) are tokens of their own words and are not read.
    """
    spelled = {
        word: value for word, value in CARDINALS[language].items() if value >= 13
    }
    if language == "en":
        return {
            (word[:-1] + "ieth" if word.endswith("y") else word + "th"): str(value)
            for word, value in spelled.items()
            if "-" not in word
        }
    return {
        f"{word}{'t' if value < 20 else 'st'}e{ending}": str(value)
        for word, value in spelled.items()
        for ending in ("", "n", "r", "s", "m")
    }


#: Ordinals by ISO 639-1 code, as the digits a written one carries: `2nd`,
#: and German `2.` once `_bare` has dropped its full stop. German ordinals
#: are listed in every ending they take.
_ORDINALS: dict[str, dict[str, str]] = {
    "en": _valued("first second third fourth fifth sixth", start=1)
    | _valued("seventh eighth ninth tenth eleventh twelfth", start=7)
    | _ordinals_past_twelve("en"),
    "de": {
        f"{stem}e{ending}": value
        for stem, value in (
            _valued("erst zweit dritt viert fünft sechst", start=1)
            | _valued("siebt acht neunt zehnt elft zwölft", start=7)
        ).items()
        for ending in ("", "n", "r", "s", "m")
    }
    | _ordinals_past_twelve("de"),
}

#: What each language writes after the digits of an ordinal figure, by ISO
#: 639-1 code: `3rd`, and German `3.`.
ORDINAL_SUFFIX: dict[str, tuple[str, ...]] = {
    "de": (".",),
    "en": ("st", "nd", "rd", "th"),
}

#: Number words by ISO 639-1 code, as the digits each names: the cardinals
#: and the ordinals. What lets "two ports" restate "2 ports" and keeps "zwei"
#: and "drei" apart: spaCy's `like_num` knows English number words and no
#: German one, so a German count written out is otherwise no number at all.
_NUMBER_WORDS: dict[str, dict[str, str]] = {
    language: {word: str(value) for word, value in cardinals.items()}
    | _ORDINALS.get(language, {})
    for language, cardinals in CARDINALS.items()
}

#: A run of digits, with the decimal or thousands marks inside it. Read off a
#: token rather than off `like_num`, so a figure glued to its unit - `45m` -
#: or written as a time - `08:00` - is still a number.
_DIGITS = re.compile(r"\d+(?: \d{3})*(?:[.,]\d+)*")

#: The zeros a run of digits opens with, which are no part of its value.
_PADDING = re.compile(r"^0+(?=\d)")

#: The parts of speech a number word is tagged with when it is one: a count,
#: or an ordinal, which taggers read as an adjective. A word spelled like a
#: number and used otherwise - the verb `achten`, `Elf` naming a team, `one`
#: in "No one" - is tagged something else and names no value.
_NUMERAL = frozenset({"NUM", "ADJ"})


#: The smallest cardinal that is a number and nothing else. Below it a word
#: is spelled like others the tagger reads as they are used - `acht` in
#: `achten`, `Elf` the team, `one` in "No one" - so its tag decides; from
#: thirteen on it is read whatever the tagger made of it, which gave
#: `fünfundzwanzig` an adverb in "Die Gebühr beträgt fünfundzwanzig Euro".
UNAMBIGUOUS = 13


def _joined(so_far: int, last: int, word: int, unit_first: bool) -> int | None:
    """The number a cardinal word makes with one already read, or None.

    `last` is the value of the word read last. A scale multiplies what it
    follows - `twenty` `thousand`, `two thousand five` `hundred` - and any
    other word is the rest: a unit after a ten (`twenty` `five`, but not in a
    language that puts the unit first), anything
    under the scale a round number leaves open (`one hundred` `twenty`,
    `two thousand` `five hundred`).
    """
    tail = so_far % 1000
    if word == 1000:
        return so_far * word if so_far < word else None
    if word == 100:
        return so_far - tail + tail * word if 0 < tail < word else None
    if word < 10 and 20 <= last < 100 and last % 10 == 0:
        return so_far + word if so_far % 10 == 0 and not unit_first else None
    if word < 100:
        return so_far + word if so_far >= 100 and so_far % 100 == 0 else None
    return so_far + word if so_far >= 1000 and tail == 0 and word < 1000 else None


def _spoken(document: Doc | Span) -> dict[int, str | None]:
    """The value of each number word in a text, by token index.

    A cardinal from `CARDINALS` reads as the digits it names, an ordinal as
    its row in `_ORDINALS`, and a count past both as written. Cardinals side
    by side, or a hyphen apart, make one number where one follows the other
    as a scale or as the rest of it - `twenty-five` is 25, `twenty thousand`
    is 20000, `one hundred twenty` is 120 - and the later word then maps to
    None. Only a token tagged as a numeral is read, unless the word is
    `UNAMBIGUOUS`.
    """
    spelled = _NUMBER_WORDS.get(document.doc.lang_, {})
    cardinals = CARDINALS.get(document.doc.lang_, {})
    spelling = _SPELLING.get(document.doc.lang_)
    unit_first = bool(spelling and spelling.unit_first)
    out: dict[int, str | None] = {}
    # The token holding the number so far, the last token read into it, its
    # value and the value of its last word.
    run: tuple[int, int, int, int] | None = None
    for token in document:
        word = token.text.casefold()
        count = cardinals.get(word)
        if _DIGITS.search(token.text) or not (
            token.pos_ in _NUMERAL or (count or 0) >= UNAMBIGUOUS
        ):
            # A hyphen goes on a number only into another cardinal:
            # `twenty-five`, but not `thirty one-time`.
            ahead = (
                document.doc[token.i + 1].text.casefold()
                if token.i + 1 < len(document.doc)
                else ""
            )
            hyphen = (
                run
                and token.text == "-"
                and token.i == run[1] + 1
                and ahead in cardinals
            )
            run = (run[0], token.i, run[2], run[3]) if run and hyphen else None
            continue
        if count is None:
            run = None
            if word in spelled:
                out[token.i] = spelled[word]
            # A count past the table is read as written: `de_core_news_md` gives
            # `zwanzig` no `like_num`, and it still differs from `dreißig`.
            elif token.like_num or token.pos_ == "NUM":
                out[token.i] = word
            continue
        compound = (
            token.i + 2 < len(document.doc)
            and document.doc[token.i + 1].text == "-"
            and document.doc[token.i + 2].text.casefold() not in cardinals
        )
        total = (
            run
            and not compound
            and run[1] == token.i - 1
            and _joined(run[2], run[3], count, unit_first)
        )
        if run and total:
            out[run[0]], out[token.i] = str(total), None
            run = (run[0], token.i, total, count)
        else:
            out[token.i] = str(count)
            run = (token.i, token.i, count, count)
    return out


def _value(run: str, language: str | None) -> str:
    """A run of digits as the value it writes, in the language's convention.

    `1,000` and `1000`, `5.00` and `5`, a German `4,90` and `4,9` are one
    value each, so they are one string. A run that is no single figure - a
    version, a clock's group - stays as written.
    """
    found = (
        figures(run, language) if FIGURE.fullmatch(run) and not run.isdigit() else []
    )
    if len(found) != 1:
        return run
    return str(int(found[0])) if found[0] == int(found[0]) else repr(found[0])


def numbers(text: str, language: str | None) -> tuple[str, ...]:
    """The numbers a text states, each as often as it states it, sorted.

    What the extraction dedup gate compares before it reads a cosine: two
    statements naming different numbers state different claims however alike
    their words are - a 4 kg and a 7 kg device, a 5,5 % rate and a 16,5 % one.

    A multiset rather than a set, so "2 EUR and 2 EUR" is not "2 EUR". A digit
    is read as the value it writes in the language's convention, so `1,000`
    and `1000` are one value and `1,500` is another; a number word reads as
    the digits it names where the language has a row in `_NUMBER_WORDS` for it, and as written where it
    does not, and only where it is tagged as a numeral. The language is the
    parse's, as every other table here reads it: a text of no language is
    read by the default pipeline and in that pipeline's number words.
    """
    document = _read(text, language)
    spoken = _spoken(document)
    found: list[str] = []
    for token in document:
        if digits := _DIGITS.findall(token.text):
            found += [_value(one, document.lang_) for one in digits]
        elif spoken.get(token.i):
            found.append(str(spoken[token.i]))
    return tuple(sorted(found))


def numerals(text: str, language: str | None) -> frozenset[str]:
    """The digit runs and number-word values a text carries, in any spelling.

    A run is read as the number it is, its leading zeros dropped, so
    `08:00` carries the 8 and the 0 that `8:00` does and `09:00` does not.
    """
    document = _read(text, language)
    found: set[str] = set()
    for token in document:
        if digits := _DIGITS.findall(token.text):
            found.update(
                _PADDING.sub("", _value(one, document.lang_)) for one in digits
            )
    return frozenset(
        found | {one for one in _spoken(document).values() if one and one.isdigit()}
    )


def spoken_numbers(text: str, language: str | None) -> dict[int, str]:
    """The cardinals a text writes out, by token index of `parse`, each as the digits it names.

    Empty for a language with no row in `CARDINALS`: its number words are
    read as words, never as figures.
    """
    document = _read(text, language)
    cardinals = CARDINALS.get(document.lang_, {})
    spoken = _spoken(document)
    return {
        token.i: value
        for token in document
        if token.text.casefold() in cardinals
        and (value := spoken.get(token.i))
        and value.isdigit()
    }


def as_noun(word: str, language: str | None) -> frozenset[str]:
    """The lemmas the language's rule lemmatizer gives a word read as a common noun.

    Empty where the pipeline has no lemmatizer in "rule" mode.
    """
    nlp = pipeline(language)
    if "lemmatizer" not in nlp.pipe_names:
        return frozenset()
    lemmatizer = nlp.get_pipe("lemmatizer")
    if not isinstance(lemmatizer, Lemmatizer) or lemmatizer.mode != "rule":
        return frozenset()
    token = Doc(nlp.vocab, words=[word.lower()])[0]
    token.pos_ = "NOUN"
    return frozenset(form.casefold() for form in lemmatizer.rule_lemmatize(token))


#: What opens a list item in running text, besides a line break.
_BULLETS = ("-", "\u2022", "*")


def _opens_line(token: Token) -> bool:
    """Whether a token is the first word of a sentence or of a list item."""
    if token.i == 0 or token.is_sent_start:
        return True
    before = token.doc[token.i - 1]
    return (
        before.text in _BULLETS
        or "\n" in before.text_with_ws
        or (
            token.i >= 2
            and "\n" in token.doc[token.i - 2].text_with_ws
            and before.is_punct
        )
    )


def written_in(
    unit: str,
    statement: str,
    known: set[str],
    endings: Sequence[str],
    language: str | None,
) -> bool:
    """Whether a statement's unit is a form the evidence carries, read by how words are written.

    A word is carried when it, or the form the statement spells it in, is one
    of the evidence's after the spelling differences a text layer leaves: an
    inflection (`endings`, the language's own table), a hyphen split in either
    text, a hyphen dropped, or each part of a hyphenated word. In a language
    that capitalises only names, a capitalised first word of a sentence or
    list item is no name: it is capitalised for its place.

    Args:
        unit: A statement unit no form of which is in the evidence's words.
        statement: The text the unit was read from.
        known: The evidence's word forms.
        endings: The endings a word of this language inflects with.
        language: The language of both texts.
    """
    document = _read(statement, language)
    own = [
        token
        for token in document
        if _bare(token.lemma_.casefold()) == unit
        or _bare(token.text).casefold() == unit
    ]
    numeric = bool(numerals(unit, language))

    def inflected(word: str) -> bool:
        return any(word + end in known for end in endings) or any(
            word.endswith(end) and word[: -len(end)] in known for end in endings
        )

    parts = {part for form in known if "-" in form for part in form.split("-") if part}
    joined = {form.replace("-", "") for form in known}
    for word in {unit} | {_bare(token.text).casefold() for token in own}:
        word = word.rstrip("-")
        if word in known or word in parts or word.replace("-", "") in joined:
            return True
        if numeric:
            continue
        if inflected(word) or (
            "-" in word
            and all(
                part in known or part in parts or inflected(part)
                for part in word.split("-")
                if part
            )
        ):
            return True
    if numeric or language in _capitalises_nouns():
        return False
    names = [token for token in own if token.pos_ == "PROPN"]
    return bool(names) and all(
        token.pos_ == "PROPN"
        and token.text.istitle()
        and _opens_line(token)
        and not token.ent_type_
        for token in names
    )


#: Dependency labels for a pronoun that stands in for no antecedent: German
#: `ph` (Platzhalter) and `ep` (expletive es), and English `expl`. "Es gibt
#: Best Practices", "Es besteht Potenzial" and "There is potential" name
#: nothing and leave nothing dangling.
_EXPLETIVE = frozenset({"ph", "ep", "expl"})

#: Word runs whose pronoun is part of a fixed phrase and stands for nothing,
#: by ISO 639-1 code: German "es sei denn", "unless". The tagger reads its
#: `es` as an ordinary pronoun.
_EXPLETIVE_RUNS: dict[str, tuple[tuple[str, ...], ...]] = {
    "de": (("es", "sei", "denn"),),
    "en": (),
}

#: Dependency labels of a verb's subject, German and English.
_SUBJECTS = frozenset({"sb", "sbp", "nsubj", "nsubjpass", "nsubj:pass", "csubj"})

#: The subjects, with the expletive ones a verb has of its own.
_OWN_SUBJECTS = _SUBJECTS | {"expl", "ep"}

#: How a verb is coordinated with the one before it, German and English.
_CONJUNCT = frozenset({"conj", "cj"})


def _fixed_expletive(token) -> bool:
    """Whether a token opens one of its language's fixed expletive runs."""
    runs = _EXPLETIVE_RUNS.get(token.doc.lang_, ())
    return any(
        tuple(t.text.casefold() for t in token.doc[token.i : token.i + len(run)]) == run
        for run in runs
    )


def _clausal_correlate(token) -> bool:
    """Whether a neuter singular pronoun anticipates a clause of its verb.

    "Es ist wichtig, den Vertrag zu lesen" and "It is important to read the
    contract": the pronoun is a placeholder for the infinitive or the
    complement clause that its head, or the verb chain under it, governs
    later. Read off the structure, so no word list is involved.

    Only a subject, and only before a complement: an object pronoun before a
    purpose clause, "The bank asks it to confirm the transfer" or "Der Kunde
    muss es zurückgeben, um eine Erstattung zu erhalten", still points at
    something the statement never named.
    """
    if token.dep_ not in _SUBJECTS and token.dep_ not in _EXPLETIVE:
        return False
    if "Neut" not in token.morph.get("Gender") and token.doc.lang_ != "en":
        return False
    if "Sing" not in token.morph.get("Number"):
        return False
    chain, frontier = [token.head], [token.head]
    while frontier:
        frontier = [
            child
            for one in frontier
            for child in one.children
            if (child.dep_ in _CARRIERS or child.dep_ in {"oc", "pd", "acomp", "attr"})
            and child.pos_ in {"VERB", "AUX", "ADJ", "ADV"}
        ]
        chain += frontier
    return any(
        child.i > token.i
        and child.dep_ in {"oc", "ccomp", "xcomp", "re", "csubj"}
        and any(
            t.tag_ in {"PTKZU", "TO"} or t.dep_ in _SUBORDINATOR for t in child.subtree
        )
        for child in (c for one in chain for c in one.children)
    )


def _refers(token, passages: Sequence[str] = ()) -> bool:
    """Reports whether a pronoun points at something outside the statement.

    A reflexive belongs to its own verb - `sich` in `ergibt sich aus` - and an
    expletive stands in for no antecedent, so neither leaves a reader without
    a subject. Nor does the `es` of a fixed phrase, "es sei denn", or an
    `it` or `es` that anticipates the infinitive or clause its verb governs
    further on, "It is easy to close the account". Nor does a polite form,
    read against the passages the statement was drawn from.
    """
    if token.pos_ != "PRON" or token.dep_ in _EXPLETIVE:
        return False
    if "Yes" in token.morph.get("Reflex"):
        return False
    if _fixed_expletive(token) or _clausal_correlate(token):
        return False
    if _polite(token, passages):
        return False
    return "3" in token.morph.get("Person") or "Dem" in token.morph.get("PronType")


#: Forms of polite address by ISO 639-1 code, as written. The tagger reads
#: them as the third person plural, which they are spelled like: German
#: `Sie können Ihre Karte sperren` names the reader, not someone earlier.
_POLITE: dict[str, frozenset[str]] = {
    "de": frozenset(
        {"Sie", "Ihnen", "Ihr", "Ihre", "Ihren", "Ihrem", "Ihrer", "Ihres"}
    ),
    "en": frozenset(),
}


def _polite(token, passages: Sequence[str] = ()) -> bool:
    """Whether a pronoun is the polite form of address, which names the reader.

    The capitalised form is the signal, so one inside a statement is polite.
    One opening a statement is capitalised either way, and `Sie werden
    geliefert` cannot be told from the third person plural, so it is polite
    only where the statement also holds a capitalised polite form after it,
    `Sie können Ihre Karte sperren`, or one of the passages it was drawn from
    holds one inside a sentence, `Bitte geben Sie Ihre IBAN an`, and opens no
    sentence on the form after one whose subject is plural, which the form
    may be the third person of: "Händler werben Kunden. Sie erhalten ...".
    Otherwise it stays a reference.
    """
    forms = _POLITE.get(token.doc.lang_, frozenset())
    if token.text not in forms:
        return False
    if any(not one.is_punct for one in token.doc[: token.i]):
        return True
    if any(one.text in forms for one in token.doc[token.i + 1 :]):
        return True
    return any(
        _addresses(_read(text, token.doc.lang_), forms, token.text)
        for text in passages
        if any(form in text for form in forms)
    )


def _addresses(document: Doc, forms: frozenset[str], form: str) -> bool:
    """Whether a passage addresses its reader, and only its reader, as `form`."""
    inside = any(
        one.text in forms
        and any(not before.is_punct for before in document[one.sent.start : one.i])
        for one in document
    )
    rival = any(
        next((one.text for one in after if not one.is_punct), None) == form
        and any(
            one.dep_ in _SUBJECTS
            and one.pos_ in _NOMINAL
            and "Plur" in one.morph.get("Number", [])
            for one in before
        )
        for before, after in pairwise(document.sents)
    )
    return inside and not rival


#: What a pronoun and a noun it stands for agree in, where both carry it.
_AGREEMENT = ("Gender", "Number")

#: Pronouns that stand for one person as well as several, by ISO 639-1 code:
#: English "The account holder may use their card".
_SINGULAR_THEY: dict[str, frozenset[str]] = {
    "en": frozenset({"they", "them", "their", "theirs", "themselves", "themself"}),
    "de": frozenset(),
}

#: Languages whose plural pronouns carry no gender, so a plural is compared
#: on number alone.
_PLURAL_GENDERLESS = frozenset({"de", "en", "nl", "sv", "da", "nb"})

#: Languages whose feminine singular and plural pronoun forms coincide: German
#: `sie`, `ihre`.
_SYNCRETIC_FEMININE = frozenset({"de"})

#: Dependency labels for a subject or an object, German and English: what a
#: noun is read as an antecedent by when the morphology says nothing.
_ARGUMENTS = frozenset(
    {
        "sb",
        "sbp",
        "oa",
        "da",
        "og",
        "nsubj",
        "nsubjpass",
        "nsubj:pass",
        "dobj",
        "obj",
        "iobj",
        "dative",
    }
)

#: Pronouns that stand in for a clause or an object beside them rather than
#: for a noun, by ISO 639-1 code: German `es` in "sofern es die
#: Vertragsbedingungen gestatten", which the parser reads with the object as
#: its sibling and a verb that does not agree with it.
#:
#: ponytail: German only. A language missing here flags its correlates as it
#: always has. Upgrade: a list per language, as a setting.
_CORRELATES: dict[str, frozenset[str]] = {"de": frozenset({"es"})}

#: What a correlate stands beside: an object, a clause, a repeated element.
_BESIDE = frozenset({"oa", "oc", "re"})

#: How a possessive determiner is attached - "its cards", "his address" - in
#: English and Universal Dependencies. A standalone possessive, "hers", is an
#: object like any other pronoun. German needs no entry: `de_core_news_md`
#: tags `sein` and `ihre` as determiners, which are never read as pronouns.
_POSSESSIVE_DEPS = frozenset({"poss", "nmod:poss"})

#: The German demonstratives that stand for a noun as an adnominal genitive,
#: "die Bank und deren Lieferanten", and the relation the parser gives them:
#: a possessive in all but name, so read like one, by ISO 639-1 code. A closed
#: class of the language; a newly configured language supplies its own or reads
#: no genitive demonstrative as resolved.
_GENITIVE_DEMONSTRATIVES: dict[str, tuple[frozenset[str], str]] = {
    "de": (frozenset({"dessen", "deren"}), "ag"),
    "en": (frozenset(), ""),
}

#: The demonstratives that carry a clause of their own, "except those related
#: to the price cap", by ISO 639-1 code: what they stand for is that clause
#: and the noun before it. A closed class of the language.
_CLAUSE_DEMONSTRATIVES: dict[str, frozenset[str]] = {
    "de": frozenset(),
    "en": frozenset({"those"}),
}

#: What opens a clause of its own beneath another: a subordinator on its verb,
#: or the verb hung off its head as an adverbial or a relative clause. English
#: and German labels, and the Universal Dependencies names for the same. A
#: scheme naming none of them reads every statement as one clause, so its
#: pronouns resolve only as a correlate or a possessive, which is the safe
#: side of the line.
_SUBORDINATOR = frozenset({"mark", "cp"})
_EMBEDDED = frozenset({"advcl", "relcl", "acl", "acl:relcl", "rc"})

#: How a relative clause hangs off its noun, German and English. It opens a
#: clause whatever its verb is tagged.
_RELATIVE = frozenset({"rc", "relcl", "acl:relcl"})

#: How an auxiliary or a copula hangs off the verb it carries the tense of,
#: in English and in Universal Dependencies.
_CARRIERS = frozenset({"aux", "auxpass", "aux:pass", "cop"})


def _finite(verb) -> bool:
    """Whether a verb, or an auxiliary or copula under it, is finite."""
    return any(
        "Fin" in one.morph.get("VerbForm", [])
        for one in (
            verb,
            *(child for child in verb.children if child.dep_ in _CARRIERS),
        )
    )


def _exception_verbs(doc: Doc) -> frozenset[int]:
    """Indices of the verbs heading the clause an exceptive run opens.

    The parsers hang that clause as a coordinated conjunct of the root, or as
    the complement of the run's own word, so it carries no subordinator;
    `_exceptive_tokens` knows where it starts. Kept on the document, because
    `_clause` asks for every token.
    """
    if "exception_verbs" not in doc.user_data:
        heads = set()
        for start in _exceptive_tokens(doc)[1]:
            if start >= len(doc):
                continue
            at = doc[start]
            while at.pos_ not in {"VERB", "AUX"} and at.head.i != at.i:
                at = at.head
            if at.pos_ in {"VERB", "AUX"} and at.head.i != at.i:
                heads.add(at.i)
        doc.user_data["exception_verbs"] = frozenset(heads)
    return doc.user_data["exception_verbs"]


def _clause(token) -> int:
    """Where the clause a token sits in is headed, as a token index.

    The nearest head above the token that carries a subordinator, or that
    hangs off its own head as an adverbial or relative clause with a finite
    verb; failing one, the root of its sentence, so two sentences' main
    clauses are two clauses. Read off the labels rather than the part of
    speech: a tagger that calls the verb of a `wenn` clause an adverb still
    hangs the `wenn` from it. Finite, because a to-infinitive hung off a noun
    has no subject of its own: `it` in "The customer has the right to return
    it" sits in the customer's clause, and is not resolved by the customer.
    A relative clause needs no finite verb: the German tagger reads the verb
    of "Filialen, die ihre Kunden bedienen" as an infinitive, the third person
    plural being spelled like one. The clause an exceptive run opens, "es sei
    denn, er wurde benutzt", is a clause of its own as well.
    """
    at = token.head
    while True:
        if _heads_clause(at):
            return at.i
        if at.head.i == at.i:
            return at.i
        at = at.head


def _agrees(pronoun, noun) -> bool:
    """Whether a noun can be what a pronoun stands for.

    Only the features both carry are compared: an English noun carries no
    gender, so `it` agrees with any singular noun, and German `er` with a
    masculine singular one. Where they share none, the noun has to be a
    subject or an object, which is all the parse has to say.

    Three things the grammar says about the pronoun are read first. A plural
    has no gender in most languages, so gender is compared only where both
    are singular. A feminine pronoun whose singular and plural forms coincide,
    German `sie`, stands for a singular or a plural noun. And a pronoun such
    as English `their` may stand for one person as well as several.
    """
    lang = pronoun.doc.lang_
    features = _AGREEMENT
    if lang in _PLURAL_GENDERLESS and (
        "Plur" in pronoun.morph.get("Number") or "Plur" in noun.morph.get("Number")
    ):
        features = tuple(one for one in features if one != "Gender")

    def values(token, feature: str) -> set[str]:
        got = set(token.morph.get(feature))
        if token is not pronoun:
            return got
        if lang in _SYNCRETIC_FEMININE:
            if feature == "Number" and (
                "Plur" in got or "Fem" in pronoun.morph.get("Gender")
            ):
                got = {"Sing", "Plur"}
            if feature == "Gender" and "Plur" in noun.morph.get("Number"):
                return set()
        if feature == "Number" and token.text.casefold() in _SINGULAR_THEY.get(
            lang, frozenset()
        ):
            got = {"Sing", "Plur"}
        return got

    shared = [one for one in features if values(pronoun, one) and values(noun, one)]
    if not shared:
        return noun.dep_ in _ARGUMENTS
    return all(values(pronoun, one) & values(noun, one) for one in shared)


def _correlate(token) -> bool:
    """Whether a pronoun stands beside the object or clause it anticipates.

    A clause beside it only where its head is not an auxiliary, whose own
    `oc` is the rest of its verb chain rather than a clause. And only where
    that verb disagrees with it in number - "sofern es die
    Vertragsbedingungen gestatten" - which says the verb's subject is
    something else: a verb agreeing with it, as in "bevor es den Ruhemodus
    verlässt", has it as its subject, and then it stands for a noun the
    passage named.
    """
    if token.text.casefold() not in _CORRELATES.get(token.doc.lang_, frozenset()):
        return False
    # A missing tag on either side says nothing disagrees, so it stays a
    # pronoun: refusing a sound statement is the cheaper mistake here.
    verb, own = set(token.head.morph.get("Number")), set(token.morph.get("Number"))
    if not verb or not own or verb & own:
        return False
    return any(
        sibling.dep_ in _BESIDE and (sibling.dep_ == "oa" or token.head.pos_ != "AUX")
        for sibling in token.head.children
        if sibling.i != token.i
    )


#: Languages whose demonstrative pronouns ordinarily point back to a noun,
#: German `der`, `dieser`; also gates the propositional neuter demonstrative.
_NOUN_ANAPHORIC_DEMONSTRATIVES = frozenset({"de"})

#: Words that read as the same thing again rather than as a pointer, by ISO
#: 639-1 code: German `derselbe`, "the same", opens a statement with no
#: reference to anything before it.
_IDENTITY: dict[str, frozenset[str]] = {
    "de": frozenset({"derselbe", "dieselbe", "dasselbe"}),
    "en": frozenset(),
}


def _heads_clause(verb) -> bool:
    """Whether a verb heads a clause of its own beneath another, as `_clause` reads one.

    `_clause` starts at a token's head, so the verb of a `wenn` clause, which
    carries the subordinator, is seen from inside as sitting in the main clause.
    """
    return (
        verb.dep_ in _RELATIVE
        or (verb.dep_ in _EMBEDDED and _finite(verb))
        or any(child.dep_ in _SUBORDINATOR for child in verb.children)
        or verb.i in _exception_verbs(verb.doc)
    )


def _propositional(token) -> bool:
    """Whether a neuter demonstrative stands for an earlier clause of the statement.

    "Wenn die Karte gesperrt ist, gilt dies als Kündigung": `dies` is the
    finite clause before it, which is not the pronoun's own. A relative clause
    is not one: it modifies a noun and states nothing for `dies` to be. A free
    relative is, "Wer die Karte verliert, muss dies melden": opened by a
    question word, it modifies no noun and stands as its head's subject or
    object, stating the event as a `wenn` clause does.
    """
    if token.doc.lang_ not in _NOUN_ANAPHORIC_DEMONSTRATIVES:
        return False
    if not ("Dem" in token.morph.get("PronType") and token.pos_ == "PRON"):
        return False
    if "Plur" in token.morph.get("Number") or token.morph.get("Gender") not in (
        [],
        ["Neut"],
    ):
        return False
    own = _clause(token)
    return any(
        "Fin" in one.morph.get("VerbForm", [])
        and one.i != own
        and (
            _clause(one) != own
            or (_heads_clause(one) and one.dep_ not in _RELATIVE)
            or (
                one.dep_ in _ARGUMENTS
                and any(_interrogative(child) for child in one.children)
            )
        )
        for one in token.doc[: token.i]
    )


def _predicate_verb(token):
    """The verb whose predicate a token belongs to, a carried tense looked through."""
    at = token.head if token.head.i != token.i else token
    while at.pos_ not in {"VERB", "AUX"} and at.head.i != at.i:
        at = at.head
    while (
        (at.dep_ in _CARRIERS or at.dep_ == "oc")
        and at.pos_ == "AUX"
        and at.head.i != at.i
    ):
        at = at.head
    return at


def _conjuncts(verb) -> list:
    """The verbs coordinated with a verb, itself included."""
    top = verb
    while top.dep_ in _CONJUNCT:
        top = top.head.head if top.head.dep_ == "cd" else top.head
    found, stack = [], [top]
    while stack:
        one = stack.pop()
        found.append(one)
        for child in one.children:
            if child.dep_ in _CONJUNCT:
                stack.append(child)
            if child.dep_ == "cd":
                stack += [c for c in child.children if c.dep_ == "cj"]
    return found


def _other_conjunct(token, noun) -> bool:
    """Whether a non-subject noun hangs off another verb coordinated with the token's."""
    if noun.dep_ in _SUBJECTS:
        return False
    own, other = _predicate_verb(token), _predicate_verb(noun)
    return own.i != other.i and other in _conjuncts(own)


def _genitive(token) -> bool:
    """Whether a token is a demonstrative standing as the genitive of a noun."""
    words, relation = _GENITIVE_DEMONSTRATIVES.get(token.doc.lang_, (frozenset(), ""))
    return token.dep_ == relation and token.text.casefold() in words


def _carries_clause(token) -> bool:
    """Whether a demonstrative has a relative clause or participle of its own."""
    return token.pos_ == "PRON" and (
        token.text.casefold()
        in _CLAUSE_DEMONSTRATIVES.get(token.doc.lang_, frozenset())
        and any(child.dep_ in _EMBEDDED for child in token.children)
    )


def _resolved(token) -> bool:
    """Whether a pronoun names something earlier in its own statement.

    "The card is blocked if it is reported stolen": `it` is the card, and
    refusing the statement throws its condition away. Resolved by a noun
    before it that agrees with it, or by being a correlate.

    Only a noun outside the pronoun's own clause: a personal pronoun never
    names a noun of its own clause, which takes a reflexive, so `it` in "The
    customer must return it" is something the passage named before. A
    possessive determiner is the exception - "The bank replaces its cards" -
    because English has no reflexive possessive to take its place; a
    standalone one, "The customer must return hers", is not. Nor is a noun
    of another verb coordinated with the pronoun's own, unless it is that
    verb's subject: in "The bank blocks the card and informs it", the card is
    outside the pronoun's predicate.

    A demonstrative pronoun is read like a personal one in the languages
    whose demonstratives ordinarily point back to a noun, German `der` and
    `dieser`; there a neuter `dies` may also stand for a finite clause before
    it. Elsewhere a demonstrative is never resolved here, and nor is a pronoun
    opening its statement, with no noun before it to stand for: both are what
    a reader without the passage cannot place.
    """
    if _propositional(token):
        return True
    if _carries_clause(token) and any(
        one.pos_ in _NOMINAL for one in token.doc[: token.i]
    ):
        return True
    demonstrative = (
        "Dem" in token.morph.get("PronType")
        and token.pos_ == "PRON"
        and token.doc.lang_ in _NOUN_ANAPHORIC_DEMONSTRATIVES
    )
    if "Prs" not in token.morph.get("PronType") and not demonstrative:
        return False
    earlier = [one for one in token.doc[: token.i] if one.pos_ in _NOMINAL]
    if not earlier:
        return False
    if _correlate(token):
        return True
    if token.dep_ not in _POSSESSIVE_DEPS and not _genitive(token):
        own = _clause(token)
        kept = [noun for noun in earlier if _clause(noun) != own]
        kept += [
            noun
            for noun in earlier
            if noun not in kept and _other_conjunct(token, noun)
        ]
        earlier = kept
    return any(_agrees(token, noun) for noun in earlier)


#: Nouns naming the source document, as lemma or as written.
_SOURCE = frozenset(
    {
        "syllabus",
        "section",
        "chapter",
        "document",
        "lehrplan",
        "lehrplans",
        "abschnitt",
        "kapitel",
        "dokument",
    }
)


def _sourced(token, named: frozenset[str] = frozenset()) -> bool:
    """Whether a determiner's head or next word names the source document.

    `named` is what the document's own title calls it, `_titled`: a noun that
    is the last part of a longer one it names, `Bedingungen` of
    `Geschäftsbedingungen`, names it as well.
    """
    nouns = [token.head] + ([token.nbor()] if token.i + 1 < len(token.doc) else [])
    for noun in nouns:
        forms = {noun.lemma_.casefold(), noun.text.casefold()}
        if forms & (_SOURCE | named) or any(
            len(one) >= len(form) + _COMPOUND_PART and one.endswith(form)
            for form in forms
            if form.isalpha()
            for one in named
        ):
            return True
    return False


#: The letters a compound's own head must leave before the part that ends it
#: for that part to name the compound: `Bedingungen` ends `Geschäftsbedingungen`.
_COMPOUND_PART = 3


#: What separates the lines of a title the converter joined: a line break or a
#: slash with space around it.
_TITLE_LINES = re.compile(r"\n| / ")


#: How a noun is attached as a part of the noun phrase it modifies, in the
#: labels the pipelines give.
_PART_OF_NOUN_PHRASE = frozenset({"compound", "nmod"})

#: How a noun set right after another is attached to it, in the labels the
#: pipelines give: an apposition, a flat name, a German noun kernel.
_JUXTAPOSED = frozenset({"app", "appos", "flat", "nk"})


@lru_cache(maxsize=256)
def _titled(title: str | None, language: str | None) -> frozenset[str]:
    """The nouns a document's title is about: those heading each of its lines.

    The root of each line's parse and the nouns coordinated with it, as lemma
    and as written - "Terms" and "Conditions" of "General Terms and Conditions
    of Sale" - so a statement saying "these terms" under it names the
    document. A noun that only modifies the head is not one: "card" of
    "Credit Card Agreement" is what the agreement is about, not the agreement.
    Read from the parse, so no word is listed.
    """
    heads: set[str] = set()
    for line in _TITLE_LINES.split(title or ""):
        if not line.strip():
            continue
        # A parser that cuts one line into two sentences leaves its head on
        # the last, as nouns end their noun phrase: "Sparkonto
        # Sonderbedingungen" is about conditions, not about an account.
        for sentence in list(_read(line, language).sents)[-1:]:
            for noun in _conjuncts(sentence.root):
                if noun.pos_ not in _NOMINAL:
                    continue
                # A root with a noun set right after it is two nouns side by
                # side, "Girokonto Preisverzeichnis": the parse cannot say
                # which one the title is about, so neither names it.
                if any(
                    child.i == noun.i + 1
                    and child.pos_ in _NOMINAL
                    and child.dep_ in _JUXTAPOSED
                    for child in noun.children
                ):
                    continue
                heads |= {noun.lemma_.casefold(), noun.text.casefold()}
                # A head that a number labels, "Edition 2026", names no
                # document but the noun phrase it labels, whose head is the
                # noun before it: "Regulations" of "Customer Regulations
                # Edition 2026". Only a plural one, which names the document
                # as a set of rules; a singular is what the document is
                # about: "Card" of "Credit Card Conditions 2025". Nor when the
                # plural noun is the title's own head, which a number dates:
                # "Services" of "Payment Services Terms 2026".
                if "Plur" not in noun.morph.get("Number") and any(
                    child.pos_ == "NUM" for child in noun.children
                ):
                    labelled = [
                        child
                        for child in noun.children
                        if child.dep_ in _PART_OF_NOUN_PHRASE
                        and child.pos_ in _NOMINAL
                        and child.i < noun.i
                        and "Plur" in child.morph.get("Number")
                    ]
                    if labelled:
                        last = max(labelled, key=lambda child: child.i)
                        heads |= {last.lemma_.casefold(), last.text.casefold()}
    return frozenset(heads)


#: Modifiers that make their noun one the passage named before, by ISO 639-1
#: code, as lemma or as written, alone or joined to the word before it (`oben
#: genannt`): `such a card`, `eine solche Karte`, `the aforementioned card`.
#: Before their noun only, so `Withdrawals above EUR 500` points nowhere. Not
#: `_ANAPHORIC`, which the question side reads as a measurement that may
#: over-read: `former customers` names no earlier mention. Nor a bare
#: `genannt`, for the reason given there.
_ANAPHORIC_MODIFIERS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {"solcher", "vorgenannt", "obengenannt", "vorstehend", "obig", "besagt"}
    ),
    "en": frozenset({"such", "aforementioned", "abovementioned", "above", "said"}),
}

#: Modifiers that make a plural noun a list the passage gives after the
#: statement, by ISO 639-1 code, as lemma or as written: `the following
#: fees`, `die folgenden Gebühren`. On a singular noun, or one a figure
#: counts, they mean the next, `am folgenden Tag`, `the following 12
#: months`, and a list the statement gives after a colon is the one meant:
#: neither points outside.
_CATAPHORIC_MODIFIERS: dict[str, frozenset[str]] = {
    "de": frozenset({"folgend", "nachstehend"}),
    "en": frozenset({"following"}),
}

#: The endings an adjective takes to inflect, by ISO 639-1 code: a word that is
#: a modifier above with one of them is that modifier where the lemmatizer
#: leaves a capitalised opening as written, `Besagter Kunde`.
_ADJECTIVE_ENDINGS: dict[str, tuple[str, ...]] = {
    "de": ("e", "em", "en", "er", "es"),
    # English adjectives take no ending, so the form as written is the lemma.
    "en": (),
}


def _opens(token, named: frozenset[str] = frozenset()) -> bool:
    """Whether a token opening a statement points at something before it.

    A demonstrative determiner, `Diese Bibliotheken`, unless it names the
    source document, `Dieser Lehrplan`; or a German pronominal adverb,
    `Hierfür`. Not an identity determiner, `Derselbe Kunde`, which says the
    same thing again without pointing at anything. Or a modifier of a noun
    that points as far, `Eine solche Karte`, `Die folgenden Gebühren`.
    """
    language = token.doc.lang_
    if token.lemma_.casefold() in _IDENTITY.get(language, frozenset()):
        return False
    if (
        token.pos_ == "DET"
        and "Dem" in token.morph.get("PronType", [])
        and not _sourced(token, named)
    ) or token.tag_ == "PROAV":
        return True
    # A preposition, or a word heading its object, modifies nothing, whatever
    # the tagger made its own head: `Above EUR 500`, `Following the update`.
    if token.pos_ == "ADP" or (
        token.pos_ != "ADJ"
        and any(one.pos_ in _NOMINAL and one.i > token.i for one in token.children)
    ):
        return False
    noun = token.head
    if noun.pos_ not in _NOMINAL:
        # An adjective the parser made its noun's head, `Obengenannte Gebühren`.
        noun = next((one for one in token.children if one.pos_ in _NOMINAL), None)
        if noun is None:
            return False
    if noun.i < token.i:
        return False
    # The first part of a hyphen compound, `above-average`, is no word alone.
    glued = not token.whitespace_ and token.i + 1 < len(token.doc)
    if glued and token.nbor().text in ("-", "\u2013"):
        return False
    text = token.text.casefold()
    before = token.doc[: token.i]
    # Written apart, `oben genannt`, or with its hyphen, `above-mentioned`.
    forms = {text, before[-1:].text.casefold() + text}
    hyphen = len(before) > 1 and before[-1].text in ("-", "\u2013")
    if hyphen and not (before[-2].whitespace_ or before[-1].whitespace_):
        forms.add(before[-2].text.casefold() + text)
    words = {token.lemma_.casefold(), *forms} | {
        form.removesuffix(end)
        for form in forms
        for end in _ADJECTIVE_ENDINGS.get(language, ())
        if form.endswith(end)
    }
    if words & _ANAPHORIC_MODIFIERS.get(language, frozenset()):
        return True
    if not words & _CATAPHORIC_MODIFIERS.get(language, frozenset()):
        return False
    colon = next((one for one in token.doc[token.i :] if one.text == ":"), None)
    return (
        "Plur" in noun.morph.get("Number", [])
        and not any(child.pos_ == "NUM" for child in noun.children)
        and not (
            colon is not None
            and any(not one.is_punct for one in token.doc[colon.i + 1 :])
        )
    )


def _references(
    span: Doc | Span, passages: Sequence[str] = (), title: str | None = None
) -> tuple[str, ...]:
    """Collects what leaves a statement dependent on its context.

    The pronouns anywhere that the statement does not resolve itself, and
    what `_opens` reads before the first finite verb. A pronoun it resolves
    is not recorded at all: a validated claim may carry no reference. The
    passages it was drawn from tell a polite form from a pronoun.
    """
    opening = takewhile(lambda t: "Fin" not in t.morph.get("VerbForm", []), span)
    named = _titled(title, span.doc.lang_) if title else frozenset()
    return tuple(
        sorted(
            {
                t.text.casefold()
                for t in span
                if _refers(t, passages) and not _resolved(t)
            }
            | {t.text.casefold() for t in opening if _opens(t, named)}
        )
    )


#: Lemmas that point at an earlier mention without any morphology saying so.
#: Every tagset reads these as ordinary adjectives - `aforementioned` and
#: `latter` are `ADJ/JJ`, `besagt` and `vorgenannt` likewise - so unlike the
#: two readings below them there is no feature to test and a list is the only
#: thing available. Kept short and kept here rather than in a setting: it can
#: only ever ADD a pointer for the verdict to rule on, so a language whose
#: triggers are missing loses recall on one measurement and nothing else.
#:
#: Bare `genannt` was here and is deliberately gone. It points at an earlier
#: mention in `die genannten Anforderungen` and at nothing in `die im
#: Korrekturverzeichnis genannten Abschnitte`, which says inside the question
#: where to look. The compounds that carry the pointing in the word itself stay.
#:
#: ponytail: German and English only, here and in `_ASKING`, so a third
#: language loses recall on this measurement. Upgrade: a list per language,
#: as a setting.
_ANAPHORIC = frozenset(
    {
        "aforementioned",
        "forementioned",
        "former",
        "latter",
        "said",
        "besagt",
        "obig",
        "obengenannt",
        "vorgenannt",
        "letzterer",
        "ersterer",
    }
)

#: Words a tagger reads as demonstrative that are ASKING rather than
#: pointing. German `wessen` - "whose" - comes back PDS with
#: `PronType=Dem`, which is simply wrong: it is an interrogative, and
#: `_interrogative` does not catch it because that tag carries neither a W
#: prefix nor `PronType=Int`. English `whose` is tagged WP$ and needs no
#: help, which is why this list is one word long per language at most.
#:
#: A question word cannot point outside the question it is asking, so this
#: corrects a parse rather than making a judgement.
_ASKING = frozenset({"wessen", "whose"})

#: What an anaphoric trigger has to be tagged as. `said` is the past tense of
#: `say` far more often than it is `the said document`, and the tagger tells
#: them apart: one is a VERB and the other a modifier.
_ANAPHORIC_POS = frozenset({"ADJ", "DET", "PRON"})


def _counted(token):
    """The quantifier on a noun that is both made definite and counted.

    `den beiden Lehrplänen` and `the two editions` name a set of a known size
    that the text never introduced, which is pointing outward as surely as
    `diesen beiden` is - and neither language says so in a way `PronType=Dem`
    catches. German tags `den` `PronType=Art` and `beiden` `PronType=Ind`;
    English tags `the` a definite article and `two` `NumType=Card`.

    What they share is structural rather than lexical, so this needs no word
    list: one noun carrying BOTH a definite determiner and a quantifier.
    `die drei Wege` is caught too and is a perfectly good question - which is
    allowed, because this measurement may only ever offer a pointer for the
    verdict to rule on. A figure with a slash in it is a period, not a count:
    `the 2026/27 budget` names its own.
    """
    definite = False
    quantified = None
    for child in token.children:
        morph = child.morph
        definiteness = morph.get("Definite", [])
        if "Def" in definiteness or (
            "Art" in morph.get("PronType", []) and "Ind" not in definiteness
        ):
            definite = True
        # A figure with a slash in it, `2026/27` or `3/4`, names a period or a
        # fraction and is not the size of a set.
        if "/" not in child.text and (
            "Card" in morph.get("NumType", [])
            or (child.pos_ == "DET" and "Ind" in morph.get("PronType", []))
        ):
            quantified = child
    return quantified if definite else None


def pointing(text: str, language: str | None) -> tuple[str, ...]:
    """The words in a text that point at something outside it.

    Three readings, because no one of them covers the ways a question reaches
    for something the asker cannot see:

    - `PronType=Dem` off the morphology, which every Universal Dependencies
      tagset marks. Determiners as well as pronouns: `diesen beiden
      Lehrplänen` and `these two syllabi` point outward through the
      determiner, and the noun beside it is what makes the pointing look
      harmless.
    - a noun made definite AND counted - `den beiden Lehrplänen`, `the two
      editions` - which names a set of a known size the text never
      introduced. This is the reading the first one misses: the question
      that prompted the gate was `zwischen den beiden Lehrplänen`, where
      `den` is an article and `beiden` is `PronType=Ind`.
    - the anaphoric adjectives, which carry no feature at all.

    A measurement and not a verdict. Pointing is only a fault when there is
    nothing in the text to point AT, and a question carrying one can set
    a case up first and then refer back to it - `Wenn ein KI-System ...,
    wie wird dieses Problem eingeordnet?` is self-contained. Deciding which
    is which is a reading, so this only says a pointer is present and the
    verdict says whether it lands.
    """
    found: set[str] = set()
    for token in _read(text, language):
        # A question word asks; it cannot point outside the question it is
        # asking. The tagger does not always agree - see `_ASKING`.
        if _interrogative(token) or token.lemma_.casefold() in _ASKING:
            continue
        if "Dem" in token.morph.get("PronType", []) or (
            token.pos_ in _ANAPHORIC_POS and token.lemma_.casefold() in _ANAPHORIC
        ):
            found.add(token.text.casefold())
        elif token.pos_ in _NOMINAL and (counted := _counted(token)):
            found.add(counted.text.casefold())
    return tuple(sorted(found))


def phrases(text: str, language: str | None) -> tuple[str, ...]:
    """The noun phrases a text is about, longest first.

    spaCy's own `noun_chunks`, carrying content and with the asking stripped
    off the front. A question word inside a chunk is dropped rather than
    taking the chunk with it - `How many faults` is asked about faults, and
    `Welche spezifischen Komponenten` is asked about nothing, and what
    separates those two is not in either chunk. Whether a question names
    anything is the caller's to decide; this reports what it named.

    A chunk with no content word is left out, which is what the German
    parser offers for the reflexive in `unterscheiden sich`.

    Ordered by how much a chunk carries rather than by where it sits, because
    the caller wants the one that says what the question is about and a
    question opens with the word asking rather than with its subject.
    """
    document = _read(text, language)
    kept = []
    for chunk in document.noun_chunks:
        content_words = [token for token in chunk if token.pos_ in _CONTENT]
        if not content_words:
            continue
        words = [token for token in chunk if not _interrogative(token)]
        written = "".join(token.text_with_ws for token in words).strip()
        if written:
            kept.append((len(content_words), chunk.start, written))
    return tuple(
        written for _, _, written in sorted(kept, key=lambda one: (-one[0], one[1]))
    )


def _foreign(token, language: str) -> bool:
    """Whether a token is a foreign word read as a noun of this language.

    A language named in NLP_CAPITALISED_NOUNS writes every noun with a
    capital, so a lower-case one is a word from another language: the German
    pipeline tags the English `the`, `and` and `of` as proper nouns, which
    puts them in the German vocabulary as subjects.

    A lower-case German adjective the tagger reads as a noun goes with them.

    Only in a text that writes its words with capitals at all. A keyword
    query typed all in lower case - `girokonto kündigungsfrist gebühr` -
    says nothing by its case, and dropping its nouns left it naming nothing.

    shortcut: one capitalised brand (`girokonto kündigungsfrist Sparkasse`)
    makes a query read as cased again; read a capitalised common noun
    instead if such queries are refused for it.
    """
    return (
        language in _capitalises_nouns()
        and token.pos_ in _NOMINAL
        and token.text[:1].islower()
        # `eGovernment`, `iOS`: a capital after the first letter is a name.
        and not any(char.isupper() for char in token.text[1:])
        and _cased(token.doc)
    )


def _cased(document: Doc) -> bool:
    """Whether a text writes some word after its first with a capital.

    The first word is capitalised as the start of a text, and an acronym
    (`EU`) as itself, so neither says the text writes nouns with capitals.
    """
    return any(
        token.text[:1].isupper() and not token.text.isupper() for token in document[1:]
    )


def _lemmas(document: Doc) -> list[str]:
    """Collects the content lemmas of a document.

    A web address is not vocabulary. Its path segments arrive tagged as nouns
    and proper nouns, and one repeated link put `publikationen`, `fokus`, `im`
    and `en` among the most widespread terms in the corpus.
    """
    addresses = [match.span() for match in URL.finditer(document.text)]
    return [
        token.lemma_.casefold()
        for token in document
        if token.pos_ in _CONTENT
        and not _foreign(token, document.lang_)
        # The lemma, not the token: the lemma is what is stored, and a
        # lemmatiser handed a word from another language returns the
        # placeholder "--" for a token that is itself perfectly alphabetic.
        # Any letter rather than every one, so `KI-Verordnung` is kept.
        and any(char.isalpha() for char in token.lemma_)
        and len(token.lemma_) > 1
        and not any(start <= token.idx < end for start, end in addresses)
    ]


#: Characters that join two words with no space between them: a sentence
#: never ends inside "Anspucken/Spucken" or "Ball-im-Spiel".
_JOINERS = "/-"

#: The marks that end a sentence, in the scripts read here. A joiner after
#: one and a space is no word joined: it opens what follows.
_SENTENCE_ENDS = ".!?"

#: Characters that carry the sentence before them on: a clause opened by a
#: comma or a closing bracket is not a sentence of its own.
_CONTINUING = ",;:)"

#: Abbreviations that end in a full stop and, on their line, end no sentence
#: whatever follows ("incl. VAT", "gem. Ziff. 3"), by ISO 639-1 code,
#: case-folded, as the tokenizer cuts them.
_ABBREVIATIONS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {
            "bzw.",
            "ca.",
            "nr.",
            "vgl.",
            "inkl.",
            "zzgl.",
            "evtl.",
            "ggf.",
            "sog.",
            "abs.",
            "gem.",
            "ziff.",
            "abschn.",
        }
    ),
    "en": frozenset({"e.g.", "i.e.", "approx.", "vs.", "cf.", "incl."}),
}

#: Abbreviations that may end a sentence as well, and end none when a
#: lower-case word or a figure follows: one closing a list ("etc.", "u. a."),
#: a single letter ("z. B." is two), or one spelled as a word ("No.", "Art.",
#: "Sat."), by ISO 639-1 code, as above.
_CLOSING_ABBREVIATIONS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {
            "etc.",
            "usw.",
            "z.",
            "b.",
            "d.",
            "h.",
            "u.",
            "a.",
            "art.",
            "max.",
            "min.",
            "mtl.",
            "mon.",
            "jährl.",
            "tägl.",
            "mo.",
            "di.",
            "mi.",
            "do.",
            "fr.",
            "sa.",
            "so.",
        }
    ),
    "en": frozenset(
        {
            "etc.",
            "no.",
            "p.a.",
            "art.",
            "sect.",
            "max.",
            "min.",
            "mon.",
            "tue.",
            "wed.",
            "thu.",
            "fri.",
            "sat.",
            "sun.",
        }
    ),
}

#: An item's number alone at the start of its line: "2.", "b)", "(iv)", or
#: one behind a bullet.
_ENUMERATOR = re.compile(r"[-–•*]?\s*\(?(?:\d{1,3}|[a-zA-Z]|[ivxIVX]{1,4})[.)]")


def _boundaries(document: Doc) -> list[int]:
    """Where each sentence starts, by token, the parser's cuts corrected.

    The parser cuts where a statement would not: inside a word joined by a
    slash, before a clause opened by a comma, after an abbreviation that
    ends no sentence on its line ("incl. VAT") or one followed by a
    lower-case word or, on its line, a figure ("max. 3 days", "Sect. 4."),
    before a figure ending a sentence on its line ("EUR 5."), and between
    an item's number, which opens its line, and the item, leaving
    the number at the end of the item before. A citation resolves against
    these sentences, so a cut there leaves a fact's evidence half a rule.
    A cut is dropped in the first four cases and moved to the number in
    the last. Only ever drops or moves a cut the parser made: a full stop
    with no space after it still ends a sentence, as it does in a PDF that
    lost its spaces.

    A slash or dash after a sentence's end and a space joins nothing: it
    opens the next sentence, standing free ("The fee is 50 EUR. - Repeat
    offenders pay 100 EUR.") or as the bullet of the next line, which the
    parser leaves on the line before. The cut is kept there, or moved back
    to the bullet. An abbreviation's full stop is no sentence's end, so
    "inkl. / zzgl. Versand" is still one.
    """
    spans = list(document.sents)
    starts = [spans[0].start] if spans else []
    medial = _ABBREVIATIONS.get(document.lang_, frozenset())
    abbreviations = medial | _CLOSING_ABBREVIATIONS.get(document.lang_, frozenset())
    for previous, sentence in pairwise(spans):
        left, right = previous.text.rstrip(), sentence.text.lstrip()
        if not left or not right:
            starts.append(sentence.start)
            continue
        spaced = previous.text != left or sentence.text != right
        # An opening bracket or quote is no part of the word: "(cf.", "„inkl.".
        word = re.sub(r"^\W+", "", left.split()[-1].casefold())
        # A range or a compound ends on its last abbreviation, "Mo.–Fr.",
        # "Kunden-Nr.", "EUR/Mon.": a noun, which may end a sentence, so it is
        # no medial one.
        last_word = re.split(r"[\u2013/-]", word)[-1]
        compound = last_word != word
        joined = not spaced and (left[-1] in _JOINERS or right[0] in _JOINERS)
        if joined:
            # `text`, not `text_with_ws`, decides `spaced`: read the space
            # after the span here, so a slash a PDF spaced inside a word
            # still joins and only one after a sentence's end does not.
            if (
                right[0] in _JOINERS
                and previous.text_with_ws != left
                and left[-1] in _SENTENCE_ENDS
                and last_word not in abbreviations
            ):
                starts.append(sentence.start)
                continue
            last = previous[-1]
            before = document.text[previous.start_char : last.idx]
            if (
                last.text in tuple(_JOINERS)
                and before != before.rstrip()
                and before.rstrip()[-1:] in tuple(_SENTENCE_ENDS)
                and before.split()[-1].casefold() not in abbreviations
            ):
                if last.i > starts[-1]:
                    starts.append(last.i)
                continue
        # A figure on the next line opens the next item rather than finishing
        # the abbreviation: "etc.\n2. Card fees". On its line it finishes the
        # sentence, after a word as after an abbreviation: "EUR 5.", "Sect. 4.".
        gap = document.text[
            previous.start_char + len(left) : sentence.end_char - len(right)
        ]
        figure = right[0].isdigit() and "\n" not in gap
        if (
            joined
            or right[0] in _CONTINUING
            or (figure and left[-1].isalnum())
            or (last_word in abbreviations and (right[0].islower() or figure))
            or (last_word in medial and not compound and "\n" not in gap)
        ):
            continue
        # The line as the sentence so far reads it, not the parser's span,
        # which may hold alone the figure it cut off the sentence before.
        line = document.text[document[starts[-1]].idx : previous.start_char + len(left)]
        line = line[line.rfind("\n") + 1 :]
        if _ENUMERATOR.fullmatch(line.strip()):
            numbered = previous.start_char + len(left) - len(line.lstrip())
            token = next(one for one in document[starts[-1] :] if one.idx >= numbered)
            if token.i > starts[-1]:
                starts.append(token.i)
            continue
        starts.append(sentence.start)
    return starts


def _sentences(document: Doc) -> list[Sentence]:
    """Reads the sentences out of a parsed document."""
    starts = _boundaries(document)
    spans = [document[start:end] for start, end in pairwise([*starts, len(document)])]
    return [
        Sentence(
            index=index,
            start=sentence.start_char,
            end=sentence.end_char,
            text=sentence.text,
            predicates=_predicates(sentence),
        )
        for index, sentence in enumerate(spans)
    ]


def sentences(text: str, language: str | None) -> list[Sentence]:
    """Splits a passage into sentences, each located in the passage text."""
    return _sentences(_read(text, language))


def vocabulary(text: str, language: str | None) -> frozenset[str]:
    """Every form a word of this text appears in, lemma and surface alike.

    What a statement's units are checked for presence against. Presence is
    asked rather than like-for-like, because the two sides are parsed
    separately and the tagger does not label a word the same way in a short
    statement as in the longer sentence it came from.
    """
    document = _read(text, language)
    return frozenset(
        variant.casefold()
        for token in document
        for form in (token.text, token.lemma_)
        for variant in (form, _bare(form))
        # An ordinal figure, `3.`, is no bare 3 as well.
        if variant and not (variant != form and ordinal(token))
    )


def content(text: str, language: str | None) -> frozenset[str]:
    """The content lemmas of a text: what it is about, and nothing else.

    The nouns, proper nouns and adjectives, lemmatised, which is the same
    reading the topic model is fitted over. Verbs and grammar are left out,
    so two inflections of one answer give the same set - which is what makes
    it possible to ask whether two phrasings say the same thing without
    asking whether they are spelled the same.
    """
    return frozenset(_lemmas(_read(text, language)))


def owned(
    text: str, passages: Sequence[str], language: str | None
) -> tuple[frozenset[str], ...]:
    """What only each passage gives a text: its words and figures no other passage carries.

    A word or figure of the text, whether lemma, surface form or number, that
    one passage has and every other lacks is that passage's; one two passages
    share is nobody's. Passages are given as their text, so a heading word
    belongs to none.
    """
    mine = content(text, language) | numerals(text, language)
    carried = [
        mine & (vocabulary(one, language) | numerals(one, language)) for one in passages
    ]
    return tuple(
        frozenset(
            token
            for token in here
            if not any(
                token in there for other, there in enumerate(carried) if other != at
            )
        )
        for at, here in enumerate(carried)
    )


#: Languages whose third person plural is spelled as the infinitive, and
#: whose statements put the finite verb second, with more of the sentence
#: after it, where a heading built on an infinitive ends on it.
_INFINITIVE_IS_PLURAL = frozenset({"de", "nl"})

#: Tags of the particle that marks a verb as an infinitive, German and English.
_INFINITIVE_MARKERS = frozenset({"PTKZU", "TO"})

#: Fine tags of a finite verb, by ISO 639-1 code: STTS and Penn. The tagger
#: gives one to a verb whose part of speech and morphology it got wrong, as
#: German `genügen` tagged VVFIN and read as an adjective.
_FINITE_TAGS: dict[str, frozenset[str]] = {
    "de": frozenset({"VVFIN", "VAFIN", "VMFIN"}),
    "en": frozenset({"VBZ", "VBP", "VBD", "MD"}),
}


def _untagged_claim(span: Doc | Span) -> bool:
    """Tells whether a statement says something the tagger read as no finite verb.

    A tagger reads the one verb of a short written statement as a bare form
    or an infinitive often enough that the statement would count as saying
    nothing. It is a claim all the same when a sentence root, a verb or an
    auxiliary, has a subject, an expletive included. In a language that spells
    its third person plural as the infinitive, a root infinitive with no
    infinitive marker beside it is that plural verb when it stands where a
    finite verb does, with words before and after it: "Die Verbände
    entscheiden, ob …" says something, and the heading "Konto online
    eröffnen", which ends on its verb, does not. So does a statement any of
    whose words carries a finite verb's fine tag, whatever part of speech
    the tagger gave it.
    """
    language = span.doc.lang_
    for root in (token for token in span if token.head == token):
        if root.pos_ not in ("VERB", "AUX"):
            continue
        children = list(root.children)
        if any(child.dep_ in _SUBJECTS | {"expl", "ep"} for child in children):
            return True
        words = [token.i for token in span if not token.is_punct]
        if (
            language in _INFINITIVE_IS_PLURAL
            and "Inf" in root.morph.get("VerbForm", [])
            and not any(child.tag_ in _INFINITIVE_MARKERS for child in children)
            and words[0] < root.i < words[-1]
        ):
            return True
    finite = _FINITE_TAGS.get(language, frozenset())
    return any(token.tag_ in finite for token in span)


def claim(
    text: str,
    language: str | None,
    passages: Sequence[str] = (),
    title: str | None = None,
) -> Claim:
    """Reads what one written statement asserts.

    A statement the tagger read without a finite verb still counts as one
    claim when its root verb has a subject, or a word of it carries a finite
    verb's fine tag, so that a statement is not refused as asserting nothing
    for the tagger's slip. The sentences a
    passage is chunked into keep the tagger's own reading.

    `passages` are the texts the statement was drawn from, which only its
    references read: a polite form inside one says an opening `Sie` names
    the reader. The `title` of the document they came from names it: a
    demonstrative whose noun the title is about, "these terms", is no reference.
    """
    document = _read(text, language)
    return Claim(
        predicates=_predicates(document) or int(_untagged_claim(document)),
        units=_units(document),
        references=_references(document, passages, title),
        verbs=_verbs(document),
        figures=_figures(document),
    )


def read(
    texts: Iterable[str], language: str | None
) -> Iterator[tuple[list[Sentence], list[str]]]:
    """Reads sentences and vocabulary for many passages, in order."""
    for document in pipeline(language).pipe(texts, batch_size=_BATCH):
        yield _sentences(document), _lemmas(document)
