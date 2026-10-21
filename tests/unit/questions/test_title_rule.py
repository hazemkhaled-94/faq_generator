"""The free half of the source-leak check, where its mutants survived the suite.

`structural` refuses a question quoting a document title of at least
`_TITLE_CHARS` characters, word for word, when an attribution leads to it or
its material does not write every noun and adjective of it. Each test here
pins one edge of that rule a targeted mutation run found unguarded: the
length boundary, a title at the question's end, punctuation inside a title,
an attribution in mid-question, the lemma a declined title word is carried
by, an adjective the material lacks, and a title only a cited passage writes.
"""

from __future__ import annotations

import pytest

from database.qa_generator import QuestionRejection
from question_generation.gates import _TITLE_CHARS, structural

pytestmark = pytest.mark.nlp


def code(question: str, answer: str, title: str, statements=(), passages=()):
    """The code `structural` refuses a German question with, or None."""
    failed, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language="de",
        statements=statements,
        passages=passages,
        titles=(title,),
    )
    return failed[0] if failed else None


def test_a_title_exactly_as_long_as_the_bound_is_matched() -> None:
    """`_TITLE_CHARS` is the shortest title matched, not the longest one skipped."""
    assert len("Preisaushang") == _TITLE_CHARS

    assert (
        code(
            "Was steht im Preisaushang zur Kontoführung?",
            "5 Euro im Monat",
            "Preisaushang",
            statements=("Die Kontoführung kostet 5 Euro im Monat.",),
        )
        == QuestionRejection.LEAKS_SOURCE
    )


def test_a_title_closing_the_question_is_matched() -> None:
    """The last place a title can start is read too."""
    assert (
        code(
            "Was kostet eine Ersatzkarte im Preis- und Leistungsverzeichnis?",
            "15 Euro",
            "Preis- und Leistungsverzeichnis",
            statements=("Eine Ersatzkarte kostet 15 Euro.",),
        )
        == QuestionRejection.LEAKS_SOURCE
    )


def test_a_title_holding_a_dash_is_matched_across_it() -> None:
    """Punctuation is left out on both sides, so `Druckversion - Jahresbericht` still matches."""
    assert (
        code(
            "Was steht in Druckversion - Jahresbericht 2025 über die Zinsen?",
            "sinkende Zinsen",
            "Druckversion - Jahresbericht 2025",
            statements=("Die Zinsen sinken.",),
        )
        == QuestionRejection.LEAKS_SOURCE
    )


def test_an_attribution_in_mid_question_leads_to_the_title() -> None:
    """`... laut Preis- und Leistungsverzeichnis?` is read where the attribution ends.

    The material writes every word of the title, so only the attribution
    refuses it.
    """
    passage = "Gemäß Preis- und Leistungsverzeichnis kostet eine Ersatzkarte 15 Euro."

    assert (
        code(
            "Was kostet eine Ersatzkarte laut Preis- und Leistungsverzeichnis?",
            "15 Euro",
            "Preis- und Leistungsverzeichnis",
            statements=(passage,),
            passages=(passage,),
        )
        == QuestionRejection.LEAKS_SOURCE
    )


def test_a_title_word_the_material_writes_in_another_inflection_is_carried() -> None:
    """`Kreditkarten` is carried by a fact writing `Kreditkarte`: its lemma."""
    assert (
        code(
            "Welche Gebühr fällt für Kreditkarten im Ausland an?",
            "1,5 Prozent",
            "Kreditkarten",
            statements=("Für eine Kreditkarte berechnet die Bank im Ausland 1,5 Prozent.",),
        )
        is None
    )


def test_an_adjective_of_the_title_the_material_lacks_names_a_source() -> None:
    """Every noun and adjective is held to the material, not the nouns alone."""
    assert (
        code(
            "Was kosten Internationale Überweisungen bei der Bank?",
            "5 Euro",
            "Internationale Überweisungen",
            statements=("Überweisungen ins Ausland kosten 5 Euro.",),
        )
        == QuestionRejection.LEAKS_SOURCE
    )


def test_a_title_only_a_cited_passage_writes_is_the_subject() -> None:
    """The passages are material too, beside the statements."""
    assert (
        code(
            "Was kostet eine Ersatzkarte im Kartenpreisverzeichnis?",
            "15 Euro",
            "Kartenpreisverzeichnis",
            statements=("Eine Ersatzkarte kostet 15 Euro.",),
            passages=("Das Kartenpreisverzeichnis nennt: Eine Ersatzkarte kostet 15 Euro.",),
        )
        is None
    )
