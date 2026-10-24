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

    Low-accuracy mode keeps its memory small, and it is asked once per
    document, of a long text.
    """
    return LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()


def document_language(text: str) -> tuple[str, str] | None:
    """Names the language of a whole document, whether or not it is configured.

    Unlike `detect` this may answer with a language `NLP_MODELS` does not
    name, so a document in one is found out instead of read as another.

    Returns:
        The ISO 639-1 code and the English name, or None when the text is
        too short to tell.
    """
    prose = URL.sub(" ", text).strip()
    if len(prose) < _MIN_CHARS:
        return None
    found = _any_detector().detect_language_of(prose)
    if found is None:
        return None
    return found.iso_code_639_1.name.lower(), found.name.title()


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
