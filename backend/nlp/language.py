"""Deciding which language a piece of text is in.

The candidates are the languages NLP_MODELS names, because detecting one this
deployment has no pipeline for tells nobody anything.
"""

from __future__ import annotations

import re
from functools import lru_cache

from lingua import IsoCode639_1, Language, LanguageDetector, LanguageDetectorBuilder

from nlp.pipelines import languages

#: Shortest text worth detecting. Below this lingua is guessing from a few
#: words, and a heading detected as the wrong language sends the passage to
#: the wrong pipeline.
_MIN_CHARS = 40

#: The confidence a language needs, of lingua's values that sum to one, to be
#: taken as the text's where a wrong call splits something: with two languages
#: configured the detector always picks one, and a line of loanwords or of
#: another language's names is a coin toss at lower confidence.
_SURE = 0.9

#: The confidence a language needs to name a whole document, over every
#: language lingua knows, where a wrong call refuses the document. Prose of a
#: language reads at 0.9 or more even in one sentence, and a body of figures,
#: units and abbreviations spreads its confidence below 0.45 over many.
_DOCUMENT_SURE = 0.7

#: A web address. Markdown renders a link as [text](url), and a site writes
#: its path segments in its own language whatever the page they lead to says.
URL = re.compile(r"https?://\S+|www\.\S+")


def _language(code: str) -> Language | None:
    """Turns an ISO 639-1 code into the language lingua knows by it, or None."""
    iso = getattr(IsoCode639_1, code.upper(), None)
    try:
        return Language.from_iso_code_639_1(iso) if iso else None
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _detector() -> LanguageDetector:
    """Builds the detector over the configured languages, once per process."""
    known = {code: _language(code) for code in languages()}
    missing = sorted(code for code, found in known.items() if found is None)
    if missing:
        raise RuntimeError(
            f"NLP_MODELS names {', '.join(missing)}, which lingua has no "
            f"language for, so nothing could be detected as one."
        )
    return LanguageDetectorBuilder.from_languages(
        *(language for language in known.values() if language is not None)
    ).build()


@lru_cache(maxsize=1)
def _any_detector() -> LanguageDetector:
    """Builds the detector over every language lingua knows, once per process.

    Not in low-accuracy mode: that mode reads one rare token of a table, an
    abbreviation or a unit, as another language with full confidence, and a
    document of its own configured language would be refused for it. The
    detector is built on the first document, and asked once per document and
    once per line of each passage, so a passage in another language is found.
    """
    return LanguageDetectorBuilder.from_all_languages().build()


def document_language(text: str) -> tuple[str, str] | None:
    """Names the language of a whole document, whether or not it is configured.

    Unlike `detect` this may answer with a language `NLP_MODELS` does not
    name, so a document in one is found out instead of read as another.

    Returns:
        The ISO 639-1 code and the English name, or None when the text is
        too short to tell or the detector is not sure of any language, as a
        body of figures, units and abbreviations is not.
    """
    prose = URL.sub(" ", text).strip()
    if len(prose) < _MIN_CHARS:
        return None
    best = max(
        _any_detector().compute_language_confidence_values(prose),
        key=lambda one: one.value,
        default=None,
    )
    if best is None or best.value < _DOCUMENT_SURE:
        return None
    return best.language.iso_code_639_1.name.lower(), best.language.name.title()


def detect(text: str) -> str | None:
    """Names the language of a text, or None when it is too short to tell.

    Addresses are removed before the text is read, and the length is measured
    on what is left: a list of links carries no prose, and its addresses are
    written in the site's own language rather than the page's.
    """
    prose = URL.sub(" ", text).strip()
    if len(prose) < _MIN_CHARS:
        return None
    found = _detector().detect_language_of(prose)
    return found.iso_code_639_1.name.lower() if found else None


#: The share of a line's words that start with a capital, over which the line
#: is names or titles and no sentence: a signature, a heading, a list of places.
_NAMES = 0.5


def _names(line: str) -> bool:
    """Whether most of a line's words start with a capital."""
    words = line.split()
    return bool(words) and sum(word[0].isupper() for word in words) > _NAMES * len(
        words
    )


def outside(text: str) -> bool:
    """Whether a text is surely in a language `NLP_MODELS` does not name.

    Read over every language lingua knows, as a whole document is, at the
    same confidence: the configured detector picks one of its languages
    whatever the text is, so a French paragraph in a German document reads
    German there. Read line by line, since the lines of a passage are its
    items, and a signature or a run of names among them reads as any language
    at all. The text is outside when more of its characters are in lines
    surely read as another language than in lines surely read as a configured
    one; a line too short to tell, a body of figures, a table row and a line
    of names or titles (most of its words start with a capital) count for
    neither.
    """
    outside_characters = inside_characters = 0
    for line in text.splitlines():
        # A table row is terms and figures rather than prose, as a table is
        # everywhere else a language is read.
        line = " ".join(line.split())
        found = (
            None if line.startswith("|") or _names(line) else document_language(line)
        )
        if found is None:
            continue
        if found[0] in languages():
            inside_characters += len(line)
        else:
            outside_characters += len(line)
    return outside_characters > inside_characters


def passage_language(text: str, fallback: str | None) -> str | None:
    """Names the language a passage is read in: a configured one, or None.

    Args:
        text: The passage's text.
        fallback: The document's language, for a text too short to tell.

    Returns:
        None when the passage is surely in a language no pipeline is
        configured for, so it is read by none of them. Otherwise the
        configured language it reads as, or `fallback`.
    """
    return None if outside(text) else detect(text) or fallback


def detect_surely(text: str) -> str | None:
    """Names the language of a text, or None unless the detector is sure of it.

    Read as `detect` reads it, but a language must also hold at least `_SURE`
    of the detector's confidence, so a line that merely tips towards one of
    two languages is no evidence of a change of language.
    """
    prose = URL.sub(" ", text).strip()
    if len(prose) < _MIN_CHARS:
        return None
    best = max(
        _detector().compute_language_confidence_values(prose),
        key=lambda one: one.value,
        default=None,
    )
    if best is None or best.value < _SURE:
        return None
    return best.language.iso_code_639_1.name.lower()
