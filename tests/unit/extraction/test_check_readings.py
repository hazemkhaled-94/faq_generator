"""The fact check on bank and shop facts: amounts, section lists, a polite bridge.

Each test here is one a hand-made mutant of `validation.py` or of the
reference reading survived: the suite read the same verdict with the line
changed. A third language, which no table has a row for, is checked too.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from drivers import Checker, cell, passage
from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import Rejection
from extraction.links import linked
from extraction.service import skipped

pytestmark = pytest.mark.nlp


def placed(language: str, *trails: tuple[str, str], first: int = 1) -> list:
    """One document's passages, each its text under its heading trail."""
    return [
        replace(
            passage(text, language=language, section_path=trail, id=first + at),
            doc_sha256="doc-a",
        )
        for at, (text, trail) in enumerate(trails)
    ]


@pytest.mark.parametrize(
    ("language", "text", "heading"),
    [
        (
            "de",
            "Die Gebühren regeln die Abschnitte 4 und 5 AGB abschließend.",
            "Abschnitt 5",
        ),
        ("en", "Fees are set by Sections 4 and 5 GTC in full.", "Section 5"),
    ],
)
def test_a_plural_label_names_a_joined_number_before_a_document_name(
    language, text, heading
) -> None:
    """After a plural label the name counts nothing: "Abschnitte 4 und 5 AGB" names 5.

    The singular "Ziffer 4 und 5 AGB" is the limit the README names.
    """
    ones = placed(
        language,
        (text, "AGB > Abschnitt 1" if language == "de" else "Terms > Section 1"),
        (
            "Studenten zahlen keine Gebühr."
            if language == "de"
            else "Students pay no fee.",
            f"Preise > {heading}",
        ),
    )

    (link,) = linked(ones, ones, {one.id: 1 for one in ones}, 4, 2)

    assert (link.kind, link.named) == ("reference", heading)


BANK = (
    (
        "Bitte geben Sie Ihre IBAN an. Die Kontoführung kostet 5 Euro im Monat.",
        "Konto > Preise",
    ),
    ("Studenten zahlen keine Gebühr für die Kontoführung.", "Konto > Studenten"),
)


def test_a_bridge_opening_on_sie_reads_the_polite_form_in_its_passages() -> None:
    """The passages the bridge rests on address the reader, so Sie is the reader."""
    offered = placed("de", *BANK, first=11)

    judged = Checker(offered[0]).bridge(
        "Sie zahlen für die Kontoführung 5 Euro im Monat, als Student aber keine Gebühr.",
        offered,
        cites={0: (1,), 1: (0,)},
    )

    assert judged.validated, (judged.rejection_code, judged.validation_error)


def test_a_bridge_opening_on_sie_after_a_plural_subject_is_refused() -> None:
    """Händler is what Sie may stand for, so the reference stays unresolved."""
    offered = placed(
        "de",
        (
            (
                "Händler werben Kunden. Sie zahlen für die Kontoführung 5 Euro im Monat. "
                "Bitte geben Sie Ihre IBAN an."
            ),
            "Konto > Preise",
        ),
        BANK[1],
        first=11,
    )

    judged = Checker(offered[0]).bridge(
        "Sie zahlen für die Kontoführung 5 Euro im Monat, als Student aber keine Gebühr.",
        offered,
        cites={0: (1,), 1: (0,)},
    )

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE


#: An amount as a bank or shop passage writes it, and the fact's other spellings.
AMOUNTS = (
    (
        "de",
        "Die Kontoführung kostet 4,90 € im Monat.",
        "Die Kontoführung kostet 4,90 Euro im Monat.",
    ),
    (
        "de",
        "Die Kontoführung kostet 4,90 € im Monat.",
        "Die Kontoführung kostet € 4,90 im Monat.",
    ),
    ("de", "Eine Überweisung kostet EUR 0,50.", "Eine Überweisung kostet 0,50 EUR."),
    (
        "en",
        "Account maintenance costs €4.90 a month.",
        "Account maintenance costs 4.90 EUR a month.",
    ),
    (
        "en",
        "Account maintenance costs €4.90 a month.",
        "Account maintenance costs € 4.90 a month.",
    ),
    ("en", "The limit is EUR 2,500 a day.", "The limit is EUR 2500 a day."),
)


@pytest.mark.parametrize(("language", "text", "statement"), AMOUNTS)
def test_an_amount_with_its_currency_moved_is_the_same_amount(
    language, text, statement
) -> None:
    """The sign before or after, the word for the sign: nothing invented."""
    judged = Checker(passage(text, language=language)).atomic(statement)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Kontoführung kostet 4,90 € im Monat.",
            "Die Kontoführung kostet 5,90 € im Monat.",
        ),
        (
            "de",
            "Die Kontoführung kostet 4,90 € im Monat.",
            "Die Kontoführung kostet 490 € im Monat.",
        ),
        ("de", "Eine Überweisung kostet EUR 0,50.", "Eine Überweisung kostet 50 Cent."),
        (
            "en",
            "Account maintenance costs €4.90 a month.",
            "Account maintenance costs €5.90 a month.",
        ),
        ("en", "The limit is EUR 2500 a day.", "The limit is EUR 25 a day."),
    ],
)
def test_another_amount_is_an_addition(language, text, statement) -> None:
    """A figure the passage does not hold is refused, whatever currency carries it."""
    judged = Checker(passage(text, language=language)).atomic(statement)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION


_LANGUAGES = st.sampled_from(["de", "en", "fr", "es", None])

_WORDS = st.sampled_from(
    [
        "Sie",
        "zahlen",
        "die",
        "folgenden",
        "Gebühren",
        "4,90",
        "€",
        "EUR",
        "Section",
        "7",
        "and",
        "9",
        "such",
        "a",
        "card",
        "costs",
        "Le",
        "compte",
        "coûte",
        "frais",
        "suivants",
        "La",
        "comisión",
        "es",
        "de",
        "1 000",
        "Abschnitte",
        "und",
        "AGB",
        ":",
        ",",
        ".",
    ]
)


@given(
    words=st.lists(_WORDS, min_size=1, max_size=14),
    language=_LANGUAGES,
    rests=st.lists(st.integers(-1, 2), min_size=1, max_size=3),
)
def test_a_bridge_verdict_and_its_citations_hold_in_any_language(
    words, language, rests
) -> None:
    """Whatever it says and in whatever language: a code iff refused, spans resolve."""
    offered = placed(
        language or "en",
        ("Die Kontoführung kostet 4,90 € im Monat.", "AGB > Abschnitt 7"),
        ("Studenten zahlen keine Gebühr.", "AGB > Abschnitt 9"),
        first=11,
    )
    offered = [replace(one, language=language) for one in offered]

    judged = Checker(offered[0]).bridge(" ".join(words), offered, rests_on=tuple(rests))

    assert judged.validated == (judged.rejection_code is None)
    by_id = {one.id: one for one in offered}
    assert {one.passage_id for one in judged.citations} <= set(by_id)
    for one in judged.citations:
        if one.start is not None:
            text = by_id[one.passage_id].text
            assert 0 <= one.start < one.end <= len(text)


def _grid(columns: int, *texts: str) -> list[dict]:
    return [
        {"cells": [cell(i // columns, i % columns, t, 0) for i, t in enumerate(texts)]}
    ]


@pytest.mark.parametrize(
    "cells",
    [
        ("Basiskonto", "EUR 0", "EUR 0", "Girokonto", "EUR 5", "EUR 60"),
        ("Basic", "GBP 0.00", "GBP 0.00", "Current", "GBP 5.00", "GBP 60.00"),
        ("Standard", "CHF 10", "CHF 120", "Express", "CHF 25", "CHF 300"),
    ],
    ids=["de-eur", "en-gbp", "chf"],
)
def test_a_fee_table_with_currency_codes_is_read(cells) -> None:
    """EUR 5 is an amount, no identifier, so the table is read."""
    fees = passage(
        "| Konto | Monat | Jahr |", block_type="table", table_cells=_grid(3, *cells)
    )

    assert skipped(fees) is None


@pytest.mark.parametrize(
    "cells",
    [
        ("Basiskonto", "0 €", "0 €", "Girokonto", "4,90 €", "58,80 €"),
        ("Basic", "£0.00", "£0.00", "Current", "£5.00", "£60.00"),
    ],
    ids=["de-sign-after", "en-sign-before"],
)
def test_a_fee_table_with_currency_signs_is_read(cells) -> None:
    """The sign before or after an amount leaves the table read."""
    fees = passage(
        "| Konto | Monat | Jahr |", block_type="table", table_cells=_grid(3, *cells)
    )

    assert skipped(fees) is None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A section number with its subsection glued on (Section 7(2), § 7(2)) "
        "names no section: the tokenizer keeps 7(2 as one token, so the link "
        "pass offers no reference"
    ),
)
@pytest.mark.parametrize(
    ("language", "text", "heading"),
    [
        (
            "en",
            "The fee for a dormant account is set in Section 7(2) of these terms.",
            "Section 7",
        ),
        (
            "de",
            "Die Gebühr für ein ruhendes Konto regelt § 7(2) dieser Bedingungen.",
            "§ 7",
        ),
    ],
)
def test_a_subsection_reference_links_its_section(language, text, heading) -> None:
    """Section 7(2) names Section 7, as Section 7 (2) does."""
    ones = placed(
        language,
        (text, "Terms > Section 1" if language == "en" else "AGB > § 1"),
        (
            "A yearly fee of EUR 10 is charged."
            if language == "en"
            else "Es wird eine Jahresgebühr von 10 Euro berechnet.",
            f"Preise > {heading}",
        ),
    )

    (link,) = linked(ones, ones, {one.id: 1 for one in ones}, 4, 2)

    assert (link.kind, link.named) == ("reference", heading)
