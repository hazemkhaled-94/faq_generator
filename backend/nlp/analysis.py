"""Reading claims, sentences and vocabulary out of text with spaCy."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from functools import lru_cache
from itertools import pairwise, takewhile

from spacy.pipeline import Lemmatizer
from spacy.tokens import Doc, Span

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
    return pipeline(language)(text)


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
    "de": (("es", "sei", "denn"), ("außer",), ("ausser",), ("ausgenommen",)),
    "en": (("unless",), ("except",), ("provided",), ("providing",)),
}

#: Coordinators that offer alternatives, keyed by ISO language. "A or B" does
#: not entail A, so a conjunct joined by one is not a claim of its own.
_DISJUNCTIVE: dict[str, frozenset[str]] = {
    "de": frozenset({"oder", "bzw.", "beziehungsweise", "noch"}),
    "en": frozenset({"or", "nor"}),
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


def _exceptive_tokens(doc: Doc) -> tuple[set[int], set[int]]:
    """Indices of exceptive-run tokens, and of the token right after each run.

    A one-word run the tagger reads as a finite verb is no exception opened:
    "The bank provided the card" states what `provided` would otherwise
    only restrict.
    """
    words = [token.text.casefold() for token in doc]
    inside: set[int] = set()
    after: set[int] = set()
    for run in _EXCEPTIVE.get(doc.lang_, ()):
        for start in range(len(words) - len(run) + 1):
            if tuple(words[start : start + len(run)]) != run:
                continue
            if len(run) == 1 and "Fin" in doc[start].morph.get("VerbForm", []):
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
    is not the same as a sentence that asserts nothing.
    """
    finite = [token for token in span if "Fin" in token.morph.get("VerbForm", [])]
    if not finite:
        return 0
    doc = span.doc
    inside, after = _exceptive_tokens(doc)
    disjunctive = _DISJUNCTIVE.get(doc.lang_, frozenset())
    claims = 0
    for token in finite:
        if not _coordinated_to_root(token) or token.i in inside:
            continue
        verb = _clause_verb(token)
        start = min(one.i for one in verb.subtree)
        if start in inside or start in after:
            continue
        if verb.dep_ in _COORDINATION and _coordinator_words(token) & disjunctive:
            continue
        claims += 1
    return claims or 1


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


def interrogatives(text: str, language: str | None) -> tuple[str, ...]:
    """The question words one question uses.

    More than one is two questions joined by a conjunction - `Welche
    Vorschriften gelten für X und wie hoch ist die Gebühr für Y?` - which a
    chatbot can answer half of, and which nobody types.

    A finite-verb count does not separate those: `Welche Arten von Kryptowerten
    gelten als reguliert?` carries two and is one question.
    """
    return tuple(
        token.text
        for token in _read(text, language)
        if _interrogative(token)
        # Not a Penn W-word inside a relative or adverbial clause. Penn only:
        # STTS labels a German question word itself `mo`.
        and not (token.tag_.startswith("W") and _dependent(token))
    )


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
        if token.like_num:
            found.add(_bare(token.text).casefold())
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
_FIGURE_TOKEN = re.compile(r"[+±−-]?\(?\d[\d.,:/()–-]*[^\W\d_]{0,4}%?")


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


#: Cardinals by ISO 639-1 code, nought to twelve, each as the value it names.
#: The one table every reader of a count written out holds: `numbers` below,
#: and the question gates, which read the cardinals alone, so an ordinal -
#: `second half` - never counts anything there.
#:
#: ponytail: German and English, nought to twelve. A language missing here
#: reads its digits and whatever `like_num` says, as written. Upgrade: a
#: table per language, as a setting.
CARDINALS: dict[str, dict[str, int]] = {
    language: {word: value for value, word in enumerate(words.split())}
    for language, words in (
        ("en", "zero one two three four five six seven eight nine ten eleven twelve"),
        ("de", "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf"),
    )
}

#: Ordinals by ISO 639-1 code, as the digits a written one carries: `2nd`,
#: and German `2.` once `_bare` has dropped its full stop. German ordinals
#: are listed in every ending they take.
_ORDINALS: dict[str, dict[str, str]] = {
    "en": _valued("first second third fourth fifth sixth", start=1)
    | _valued("seventh eighth ninth tenth eleventh twelfth", start=7),
    "de": {
        f"{stem}e{ending}": value
        for stem, value in (
            _valued("erst zweit dritt viert fünft sechst", start=1)
            | _valued("siebt acht neunt zehnt elft zwölft", start=7)
        ).items()
        for ending in ("", "n", "r", "s", "m")
    },
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
_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")

#: The parts of speech a number word is tagged with when it is one: a count,
#: or an ordinal, which taggers read as an adjective. A word spelled like a
#: number and used otherwise - the verb `achten`, `Elf` naming a team, `one`
#: in "No one" - is tagged something else and names no value.
_NUMERAL = frozenset({"NUM", "ADJ"})


def numbers(text: str, language: str | None) -> tuple[str, ...]:
    """The numbers a text states, each as often as it states it, sorted.

    What the extraction dedup gate compares before it reads a cosine: two
    statements naming different numbers state different claims however alike
    their words are - a 4 kg and a 7 kg device, a 5,5 % rate and a 16,5 % one.

    A multiset rather than a set, so "2 EUR and 2 EUR" is not "2 EUR". A digit
    keeps its surface form, as `_units` reads one, so `12,5` and `12.5` stay
    two values; a number word reads as the digits it names where the
    language has a row in `_NUMBER_WORDS` for it, and as written where it
    does not, and only where it is tagged as a numeral.
    """
    spelled = _NUMBER_WORDS.get((language or "").strip().lower(), {})
    found: list[str] = []
    for token in _read(text, language):
        written = token.text.casefold()
        if digits := _DIGITS.findall(token.text):
            found += digits
        elif token.pos_ not in _NUMERAL:
            continue
        elif written in spelled:
            found.append(spelled[written])
        # A count past the table is read as written: `de_core_news_md` gives
        # `zwanzig` no `like_num`, and it still differs from `dreißig`.
        elif token.like_num or token.pos_ == "NUM":
            found.append(written)
    return tuple(sorted(found))


def numerals(text: str, language: str | None) -> frozenset[str]:
    """The digit runs and number-word values a text carries, in any spelling."""
    spelled = _NUMBER_WORDS.get((language or "").strip().lower(), {})
    found: set[str] = set()
    for token in _read(text, language):
        if digits := _DIGITS.findall(token.text):
            found.update(digits)
        elif token.pos_ in _NUMERAL and token.text.casefold() in spelled:
            found.add(spelled[token.text.casefold()])
    return frozenset(found)


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


def _refers(token) -> bool:
    """Reports whether a pronoun points at something outside the statement.

    A reflexive belongs to its own verb - `sich` in `ergibt sich aus` - and an
    expletive stands in for no antecedent, so neither leaves a reader without
    a subject. Nor does the `es` of a fixed phrase, "es sei denn", or an
    `it` or `es` that anticipates the infinitive or clause its verb governs
    further on, "It is easy to close the account".
    """
    if token.pos_ != "PRON" or token.dep_ in _EXPLETIVE:
        return False
    if "Yes" in token.morph.get("Reflex"):
        return False
    if _fixed_expletive(token) or _clausal_correlate(token):
        return False
    return "3" in token.morph.get("Person") or "Dem" in token.morph.get("PronType")


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
    plural being spelled like one.
    """
    at = token.head
    while True:
        if (
            at.dep_ in _RELATIVE
            or (at.dep_ in _EMBEDDED and _finite(at))
            or any(child.dep_ in _SUBORDINATOR for child in at.children)
        ):
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


def _propositional(token) -> bool:
    """Whether a neuter demonstrative stands for an earlier clause of the statement.

    "Wenn die Karte gesperrt ist, gilt dies als Kündigung": `dies` is the
    finite clause before it, which is not the pronoun's own.
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
        "Fin" in one.morph.get("VerbForm", []) and _clause(one) != own and one.i != own
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
    if token.dep_ not in _POSSESSIVE_DEPS:
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


def _sourced(token) -> bool:
    """Whether a determiner's head or next word names the source document."""
    nouns = [token.head] + ([token.nbor()] if token.i + 1 < len(token.doc) else [])
    return any({t.lemma_.casefold(), t.text.casefold()} & _SOURCE for t in nouns)


def _opens(token) -> bool:
    """Whether a token opening a statement points at something before it.

    A demonstrative determiner, `Diese Bibliotheken`, unless it names the
    source document, `Dieser Lehrplan`; or a German pronominal adverb,
    `Hierfür`. Not an identity determiner, `Derselbe Kunde`, which says the
    same thing again without pointing at anything.
    """
    if token.lemma_.casefold() in _IDENTITY.get(token.doc.lang_, frozenset()):
        return False
    return (
        token.pos_ == "DET"
        and "Dem" in token.morph.get("PronType", [])
        and not _sourced(token)
    ) or token.tag_ == "PROAV"


def _references(span: Doc | Span) -> tuple[str, ...]:
    """Collects what leaves a statement dependent on its context.

    The pronouns anywhere that the statement does not resolve itself, and
    what `_opens` reads before the first finite verb. A pronoun it resolves
    is not recorded at all: a validated claim may carry no reference.
    """
    opening = takewhile(lambda t: "Fin" not in t.morph.get("VerbForm", []), span)
    return tuple(
        sorted(
            {t.text.casefold() for t in span if _refers(t) and not _resolved(t)}
            | {t.text.casefold() for t in opening if _opens(t)}
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
    verdict to rule on.
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
        if "Card" in morph.get("NumType", []) or (
            child.pos_ == "DET" and "Ind" in morph.get("PronType", [])
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
    """
    return (
        language in _capitalises_nouns()
        and token.pos_ in _NOMINAL
        and token.text[:1].islower()
        # `eGovernment`, `iOS`: a capital after the first letter is a name.
        and not any(char.isupper() for char in token.text[1:])
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

#: Abbreviations that end in a full stop and end no sentence when a
#: lower-case word or a figure follows, by ISO 639-1 code, case-folded, as
#: the tokenizer cuts them ("z. B." is two).
_ABBREVIATIONS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {
            "etc.",
            "usw.",
            "bzw.",
            "z.",
            "b.",
            "d.",
            "h.",
            "ca.",
            "nr.",
            "vgl.",
            "inkl.",
            "evtl.",
            "ggf.",
            "u.",
            "a.",
            "sog.",
            "abs.",
        }
    ),
    "en": frozenset({"etc.", "e.g.", "i.e.", "approx.", "no.", "vs.", "cf.", "incl."}),
}

#: An item's number alone at the start of its line: "2.", "b)", "(iv)", or
#: one behind a bullet.
_ENUMERATOR = re.compile(r"[-–•*]?\s*\(?(?:\d{1,3}|[a-zA-Z]|[ivxIVX]{1,4})[.)]")


def _boundaries(document: Doc) -> list[int]:
    """Where each sentence starts, by token, the parser's cuts corrected.

    The parser cuts where a statement would not: inside a word joined by a
    slash, before a clause opened by a comma, after an abbreviation followed
    by a lower-case word or a figure ("approx. 3 days"), and between an
    item's number and the item, leaving the number at the end of the item
    before. A citation resolves against these sentences, so a cut there
    leaves a fact's evidence half a rule.
    A cut is dropped in the first three cases and moved to the number in
    the last. Only ever drops or moves a cut the parser made: a full stop
    with no space after it still ends a sentence, as it does in a PDF that
    lost its spaces.

    A slash or dash after a sentence's end and a space joins nothing: it
    opens the next sentence, standing free ("The fee is 50 EUR. - Repeat
    offenders pay 100 EUR.") or as the bullet of the next line, which the
    parser leaves on the line before. The cut is kept there, or moved back
    to the bullet.
    """
    spans = list(document.sents)
    starts = [spans[0].start] if spans else []
    abbreviations = _ABBREVIATIONS.get(document.lang_, frozenset())
    for previous, sentence in pairwise(spans):
        left, right = previous.text.rstrip(), sentence.text.lstrip()
        if not left or not right:
            starts.append(sentence.start)
            continue
        spaced = previous.text != left or sentence.text != right
        last_word = left.split()[-1].casefold()
        joined = not spaced and (left[-1] in _JOINERS or right[0] in _JOINERS)
        if joined:
            # `text`, not `text_with_ws`, decides `spaced`: read the space
            # after the span here, so a slash a PDF spaced inside a word
            # still joins and only one after a sentence's end does not.
            if (
                right[0] in _JOINERS
                and previous.text_with_ws != left
                and left[-1] in _SENTENCE_ENDS
            ):
                starts.append(sentence.start)
                continue
            last = previous[-1]
            before = document.text[previous.start_char : last.idx]
            if (
                last.text in tuple(_JOINERS)
                and before != before.rstrip()
                and before.rstrip()[-1:] in tuple(_SENTENCE_ENDS)
            ):
                if last.i > starts[-1]:
                    starts.append(last.i)
                continue
        if (
            joined
            or right[0] in _CONTINUING
            or (
                last_word in abbreviations
                and (right[0].islower() or right[0].isdigit())
            )
        ):
            continue
        line = left[left.rfind("\n") + 1 :]
        if _ENUMERATOR.fullmatch(line.strip()):
            numbered = previous.start_char + len(left) - len(line.lstrip())
            token = next(one for one in previous if one.idx >= numbered)
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
        if variant
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


#: Languages whose third person plural is spelled as the infinitive, and
#: whose statements put the finite verb second, with more of the sentence
#: after it, where a heading built on an infinitive ends on it.
_INFINITIVE_IS_PLURAL = frozenset({"de", "nl"})

#: Tags of the particle that marks a verb as an infinitive, German and English.
_INFINITIVE_MARKERS = frozenset({"PTKZU", "TO"})


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
    eröffnen", which ends on its verb, does not.
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
    return False


def claim(text: str, language: str | None) -> Claim:
    """Reads what one written statement asserts.

    A statement the tagger read without a finite verb still counts as one
    claim when its root verb has a subject, so that a statement is not
    refused as asserting nothing for the tagger's slip. The sentences a
    passage is chunked into keep the tagger's own reading.
    """
    document = _read(text, language)
    return Claim(
        predicates=_predicates(document) or int(_untagged_claim(document)),
        units=_units(document),
        references=_references(document),
        verbs=_verbs(document),
        figures=_figures(document),
    )


def read(
    texts: Iterable[str], language: str | None
) -> Iterator[tuple[list[Sentence], list[str]]]:
    """Reads sentences and vocabulary for many passages, in order."""
    for document in pipeline(language).pipe(texts, batch_size=_BATCH):
        yield _sentences(document), _lemmas(document)
