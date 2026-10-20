"""The helpers a bridge's heading checks stand on, read directly.

The bridge tests in `test_fact_checker.py` go through a whole candidate; these
pin the edges of the pieces: where a statement ends, which language reads a
word, and what a passage's trail and title add to what it carries.
"""

from __future__ import annotations

import pytest
from drivers import Checker, group, passage

from database.qa_generator import Rejection
from extraction.validation import (
    Judged,
    _carried,
    _located,
    _names,
    _supported_units,
)
from nlp.analysis import claim
from nlp.pipelines import pipeline

pytestmark = pytest.mark.nlp


def _read(language: str, text: str):
    return list(pipeline(language)(text))


@pytest.mark.parametrize(
    ("language", "statement", "word", "number", "expected"),
    [
        ("en", "The monthly fee is set in Section 7", "section", "7", True),
        ("en", "The monthly fee is set in Section 7.", "section", "7", True),
        ("en", "The monthly fee is set in Section7", "section", "7", True),
        ("en", "The monthly fee is set in §7", "§", "7", True),
        ("en", "The monthly fee is set in Section", "section", "7", False),
        ("en", "Section 7 is where the shop fee is set", "section", "7", True),
        ("en", "The shop fee is set in Sections 7", "section", "7", True),
        ("de", "Die Kontoführungsgebühr steht in §7", "§", "7", True),
        ("de", "Nach Regel 5. gilt die Gebühr", "regel", "5", True),
        ("de", "Nach Regel 5.1. gilt die Gebühr", "regel", "5.1", True),
        ("de", "Die Gebühr steht in Regeln 5", "regel", "5", True),
        ("de", "Die Gebühr steht in Regel", "regel", "5", False),
        ("de", "Die Gebühr steht in Regel 6", "regel", "5", False),
    ],
)
def test_a_label_word_is_named_by_the_number_that_follows_it(
    language, statement, word, number, expected
) -> None:
    """Glued, spaced, closed by a full stop, at the end of the statement, or inflected."""
    assert _names(_read(language, statement), word, number) is expected


@pytest.mark.parametrize(
    ("language", "statement", "label"),
    [
        ("de", "Die Gebühr für das Girokonto steht in Regeln 5.", "Regel 5"),
        ("en", "The fee for the current account is set in Section 7.", "Section 7"),
    ],
)
def test_the_reason_for_naming_a_section_says_which_one(
    language, statement, label
) -> None:
    """The measurement is what the person reading the rejection is shown."""
    judged = Judged(
        statement=statement,
        evidence="",
        evidence_predicates=0,
        claim=claim(statement, language),
        evidence_vocabulary=frozenset(),
        labels=(label,),
        language=language,
    )

    assert _located(judged) == (
        Rejection.NOT_BRIDGING,
        (
            f"the statement names where its passage sits ({label}), which is a claim "
            "about the document and not one either passage makes"
        ),
    )


def test_a_passage_carries_its_text_its_trail_and_its_title() -> None:
    """The names and numbers of all three, each read in the passage's language."""
    read = passage(
        "Für zwei Konten werden 1.000 Euro im Jahr berechnet.",
        language="de",
        section_path="Gebühren 2026 > Karten",
        document_title="Preisverzeichnis der Bank",
    )

    known, numbers = _carried(read.text, read)

    assert {"konto", "karte", "gebühr"} <= known
    assert {"1.000", "2026"} <= numbers


def test_an_english_passage_carries_the_same_three() -> None:
    """The trail's number joins the text's, whichever of them is read second."""
    read = passage(
        "A dormant account is charged 10 EUR a year.",
        language="en",
        section_path="Fees 2026 > Dormant accounts",
    )

    known, numbers = _carried(read.text, read)

    assert {"account", "fee", "dormant"} <= known
    assert numbers == {"10", "2026"}


@pytest.mark.parametrize(
    ("units", "known", "numbers", "language", "expected"),
    [
        (["dormant", "1st"], {"dormant"}, {"1"}, "en", {"1st"}),
        (
            ["cards", "fee-based"],
            {"card", "fee", "based"},
            set(),
            "en",
            {"cards", "fee-based"},
        ),
        (["fee-based"], {"fee"}, set(), "en", set()),
        (["gebührenfrei", "1."], {"gebührenfrei"}, set(), "de", set()),
        (["1.000"], {"konto"}, {"1.000"}, "de", {"1.000"}),
        (["accounts"], {"account"}, set(), "de", set()),
        (["accounts"], {"account"}, set(), "en", {"accounts"}),
    ],
)
def test_a_unit_is_read_as_present_by_its_number_its_parts_or_its_noun(
    units, known, numbers, language, expected
) -> None:
    """A spelling of a number, a hyphenated unit of known words, a known name as a noun."""
    assert _supported_units(units, known, numbers, language) == frozenset(expected)


def test_a_candidate_naming_a_passage_twice_or_one_not_offered_keeps_the_rest() -> None:
    """Neither a repeated position nor an unknown one ends the walk through them."""
    checker = Checker()
    offered = group(
        "A dormant account is charged a yearly fee of 10 EUR.",
        "An account is dormant when its holder has made no payment for 24 months.",
    )
    statement = "A dormant account whose holder has made no payment for 24 months is charged a yearly fee of 10 EUR."

    repeated = checker.bridge(statement, offered, rests_on=(0, 0, 1))
    unknown = checker.bridge(statement, offered, rests_on=(0, 5, 1))

    assert [one.passage_id for one in repeated.citations] == [11, 22]
    assert [one.passage_id for one in unknown.citations] == [11, 22]


def test_a_bridge_records_what_produced_it_whether_it_is_kept_or_absent() -> None:
    """The model, the prompt and the temperature reach the fact on both paths."""
    from database.qa_generator import FactKind
    from extraction.models import CandidateFact, Cited, Provenance
    from extraction.validation import FactChecker

    made = Provenance(model="gpt-test", prompt_version="v9", temperature=0.2)
    offered = group(
        "A dormant account is charged a yearly fee of 10 EUR.",
        "An account is dormant when its holder has made no payment for 24 months.",
    )

    def candidate(*positions: int) -> CandidateFact:
        return CandidateFact(
            "A dormant account is charged a yearly fee of 10 EUR.",
            (),
            kind=FactKind.BRIDGE,
            passages=tuple(Cited(position=at, sentences=(0,)) for at in positions),
        )

    checker = FactChecker(0.5)
    for fact in (
        checker.check_bridge(offered, candidate(0, 1), made),
        checker.check_bridge(offered, candidate(7), made),
    ):
        assert fact.extraction_method == "llm"
        assert fact.extraction_model == "gpt-test"
        assert fact.prompt_version == "v9"
        assert fact.extraction_temperature == 0.2


def test_a_bridge_counts_the_predicates_of_the_sentences_it_cited() -> None:
    """Over the cited sentences of every passage, not of one."""
    offered = group(
        "A dormant account is charged a yearly fee of 10 EUR.",
        "An account is dormant when its holder has made no payment for 24 months.",
    )

    bridged = Checker().bridge(
        "A dormant account whose holder has made no payment for 24 months is charged a yearly fee of 10 EUR.",
        offered,
    )

    assert bridged.evidence_predicates == sum(
        one.sentences[0].predicates for one in offered
    )
    assert bridged.evidence_predicates > offered[0].sentences[0].predicates


@pytest.mark.parametrize(
    ("language", "first", "second", "statement", "spelled"),
    [
        (
            "en",
            "The first reminder is sent on day 1 after the due date.",
            "The second reminder is sent on day 8 after the due date.",
            "The reminders are sent on the 1st and the 8th day after the due date.",
            ["1st", "8th"],
        ),
    ],
)
def test_a_number_either_passage_carries_supports_its_other_spelling(
    language, first, second, statement, spelled
) -> None:
    """The figures of every passage count, not the last one's alone."""
    bridged = Checker().bridge(statement, group(first, second, language=language))

    assert not set(spelled) & set(bridged.units_added), bridged.units_added


@pytest.mark.parametrize(
    ("language", "path", "text", "statement"),
    [
        (
            "de",
            "Regel 5 > Jahresgebühren",
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
            "Regeln 5 belasten ein ruhendes Konto mit einer Jahresgebühr von 10 EUR.",
        ),
    ],
)
def test_a_bridge_names_its_section_in_the_language_of_its_passages(
    language, path, text, statement
) -> None:
    """`Regeln 5` is `Regel 5` to the German reader, and not to the English one."""
    from dataclasses import replace

    rows = [
        replace(
            passage(text, language=language, section_path=path),
            id=11,
            doc_sha256="doc-0",
        ),
        replace(
            passage(
                "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
                language=language,
                section_path="Konten > Ruhe",
            ),
            id=22,
            doc_sha256="doc-1",
        ),
    ]

    bridged = Checker().bridge(statement, rows)

    assert bridged.rejection_code == Rejection.NOT_BRIDGING
    assert "(Regel 5)" in (bridged.validation_error or "")
