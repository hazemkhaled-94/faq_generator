"""The verdict a proposed fact is judged to.

A rejected fact's code is the quality signal this project reports, so each
failure must reach its own code rather than share a bucket with another.
"""

from __future__ import annotations

import pytest
from drivers import Checker, group, passage

from database.qa_generator import FactKind, Rejection
from extraction.models import CandidateFact, Citation, Cited

pytestmark = pytest.mark.nlp


def only(fact) -> Citation:
    """The one citation a fact resting on a single passage carries."""
    (one,) = fact.citations
    return one


@pytest.fixture(scope="module")
def checker() -> Checker:
    """Two English sentences, the first carrying two claims."""
    return Checker()


def test_one_claim_drawn_from_its_sentence_is_accepted(checker) -> None:
    """The fact is validated and carries the span its citation covers."""
    good = checker.atomic("The device weighs 4 kg.")

    assert good.validated, (good.rejection_code, good.validation_error)
    assert good.evidence_text == "The device weighs 4 kg and runs for 12 hours."
    assert only(good).sentence_ids == [0]
    assert good.statement_predicates == 1
    assert good.evidence_predicates == 2, "the cited sentence carries two claims"
    assert not good.units_added, good.units_added
    assert good.rejection_code is None and good.validation_error is None
    assert good.kind == FactKind.ATOMIC
    assert only(good).passage_id == checker.passage.id


def test_a_fact_records_the_version_of_the_pipeline_that_parsed_it(checker) -> None:
    """The model's own version, not spaCy's: the model decides the parse."""
    from nlp.pipelines import pipeline

    good = checker.atomic("The device weighs 4 kg.")

    assert good.spacy_version == pipeline("en").meta["version"]


@pytest.mark.parametrize("cited", [(7,), (), (-1,), (0, 9)])
def test_a_citation_naming_no_sentence_of_the_passage_is_refused(
    checker, cited
) -> None:
    """Out of range, negative and absent are the same failure."""
    judged = checker.atomic("Anything.", cited)
    assert judged.rejection_code == Rejection.EVIDENCE_ABSENT
    assert not judged.validated


def test_a_sentence_carrying_one_claim_may_be_quoted() -> None:
    """Evidence that is already one claim is the fact; quoting two is not."""
    quoted = Checker(
        passage(
            "The market presented a mixed picture in 2025. "
            "Transaction volumes remained low and prices fell further."
        )
    )
    assert [s.predicates for s in quoted.passage.sentences] == [1, 2]

    verbatim = quoted.atomic(quoted.passage.sentences[0].text, 0)
    assert verbatim.validated, (verbatim.rejection_code, verbatim.validation_error)

    restated = quoted.atomic(quoted.passage.sentences[1].text, 1)
    assert restated.rejection_code == Rejection.NOT_ATOMIC, restated.validation_error

    both = quoted.atomic(quoted.passage.text, (0, 1))
    assert both.rejection_code == Rejection.COPIED, both.validation_error


def test_a_copy_of_one_sentence_is_judged_on_its_claims() -> None:
    """Not on the claims its sentence was counted as carrying when it was chunked.

    A passage chunked before the claim reading moved still carries the old
    count, and a copy of one sentence reading as one claim now is the fact.
    """
    from dataclasses import replace

    text = (
        "If the customer accidentally enters the PIN incorrectly three times or the "
        "terminal rejects the card and the payment does not go through, the card is "
        "blocked."
    )
    read = passage(text)
    stale = replace(
        read, sentences=[replace(one, predicates=2) for one in read.sentences]
    )

    judged = Checker(stale).atomic(text, 0)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


def test_two_claims_in_one_statement_are_refused(checker) -> None:
    """Two claims are two facts."""
    both = checker.atomic("The device weighs 4 kg and it runs for 12 hours.")
    assert both.rejection_code == Rejection.NOT_ATOMIC, both.validation_error
    assert both.statement_predicates == 2, both.statement_predicates


#: Bank and shop statements a reader cannot take as one claim drawn from
#: what they cite, as (language, passage, statement, cited sentence, code).
#: Each is refused for what it is, however the claim reading is loosened.
STILL_REFUSED: tuple[tuple[str, str, str, int, str], ...] = (
    (
        "en",
        (
            "Customers may return goods within 30 days, but refunds are paid only to "
            "the original card."
        ),
        (
            "Customers may return goods within 30 days, but refunds are only paid to "
            "the original card."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        (
            "Kunden können Waren innerhalb von 30 Tagen zurückgeben, aber die "
            "Erstattung erfolgt nur auf die ursprüngliche Karte."
        ),
        (
            "Kunden können Waren binnen 30 Tagen zurückgeben, aber die Erstattung "
            "erfolgt nur auf die ursprüngliche Karte."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        (
            "The card is free in the first year, but a fee of 30 EUR is charged from "
            "the second year."
        ),
        (
            "The card is free of charge in the first year, but a fee of 30 EUR is "
            "charged from the second year."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        (
            "Die Karte ist im ersten Jahr kostenlos, jedoch wird ab dem zweiten Jahr "
            "eine Gebühr von 30 EUR berechnet."
        ),
        (
            "Die Karte ist im ersten Jahr gebührenfrei, jedoch wird ab dem zweiten "
            "Jahr eine Gebühr von 30 EUR berechnet."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        (
            "If the card is lost, the bank blocks it and the customer is liable for up "
            "to 50 EUR."
        ),
        (
            "If the card is lost, the bank blocks the card and the customer is liable "
            "for up to 50 EUR."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        (
            "Die Bank erstattet die Gebühr, wenn die Beschwerde berechtigt ist, und "
            "kündigt das Konto."
        ),
        (
            "Die Bank erstattet die Gebühr, wenn die Beschwerde berechtigt ist, und "
            "kündigt das Konto des Kunden."
        ),
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        (
            "The current account costs 5 EUR a month. It is free if at least 1,000 EUR "
            "is paid in each month."
        ),
        "It is free of charge if at least 1,000 EUR is paid in each month.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "de",
        (
            "Das Girokonto kostet 5 EUR im Monat. Es ist kostenlos, wenn monatlich "
            "mindestens 1.000 EUR eingehen."
        ),
        "Es ist gebührenfrei, wenn monatlich mindestens 1.000 EUR eingehen.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "en",
        "The gift box is sold separately. It is free if the order is over 50 EUR.",
        "It is free of charge if the order is over 50 EUR.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "de",
        (
            "Das Geschenkpaket wird separat verkauft. Es ist kostenlos, wenn die "
            "Bestellung über 50 EUR liegt."
        ),
        "Es ist gratis, wenn die Bestellung über 50 EUR liegt.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "en",
        (
            "The current account costs 5 EUR a month. It is free if the holder "
            "agrees to receive statements online."
        ),
        "It is free if the holder agrees to receive statements online.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "de",
        (
            "Das Girokonto kostet 5 EUR im Monat. Es ist kostenlos, wenn der Kunde "
            "zustimmt, Kontoauszüge online zu erhalten."
        ),
        "Es ist kostenlos, wenn der Kunde zustimmt, Kontoauszüge online zu erhalten.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
)


@pytest.mark.parametrize(
    ("language", "text", "statement", "cited", "code"),
    STILL_REFUSED,
    ids=[f"{row[0]}-{row[4]}-{at}" for at, row in enumerate(STILL_REFUSED)],
)
def test_a_bank_or_shop_statement_saying_too_much_is_still_refused(
    language, text, statement, cited, code
) -> None:
    """A second claim, a pronoun naming what came before, a borrowed figure."""
    judged = Checker(passage(text, language=language)).atomic(statement, cited)

    assert judged.rejection_code == code, (judged.validation_error, judged.units_added)


#: Statements that name a figure or a name a neighbouring sentence of their own
#: passage gives: admitted, as the passage is what an atomic fact rests on.
BORROWED_FROM_THE_PASSAGE = (
    (
        "en",
        (
            "Credit cards have a daily limit of 1,000 EUR. Debit cards can be blocked "
            "abroad."
        ),
        "Debit cards with a daily limit of 1,000 EUR can be blocked abroad.",
        1,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "de",
        (
            "Für Kreditkarten gilt ein Tageslimit von 1.000 EUR. Debitkarten können im "
            "Ausland gesperrt werden."
        ),
        (
            "Debitkarten mit einem Tageslimit von 1.000 EUR können im Ausland gesperrt "
            "werden."
        ),
        1,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "en",
        (
            "The S10 phone costs 500 EUR. The S20 phone costs 800 EUR. The phone has "
            "a 2-year warranty."
        ),
        "The S20 phone has a 2-year warranty.",
        2,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "de",
        (
            "Der Tarif M10 kostet 20 EUR im Monat. Der Tarif S5 ist kostenlos. Der "
            "Tarif enthält 5 GB Datenvolumen."
        ),
        "Der Tarif M10 enthält 5 GB Datenvolumen.",
        2,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "en",
        (
            "Visa cards cost 30 EUR. Mastercard cards cost 40 EUR. The card includes "
            "travel insurance."
        ),
        "The Mastercard card includes travel insurance.",
        2,
        Rejection.UNSUPPORTED_ADDITION,
    ),
)


@pytest.mark.parametrize(
    ("language", "text", "statement", "cited", "code"),
    BORROWED_FROM_THE_PASSAGE,
    ids=[f"{row[0]}-{at}" for at, row in enumerate(BORROWED_FROM_THE_PASSAGE)],
)
def test_a_figure_or_name_from_another_sentence_of_the_passage_is_supported(
    language, text, statement, cited, code
) -> None:
    """A passage that holds the figure or the name supports the fact that says it."""
    judged = Checker(passage(text, language=language)).atomic(statement, cited)

    assert judged.rejection_code != code, (judged.validation_error, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "section"),
    [
        (
            "en",
            "It is free of charge if at least 1,000 EUR is paid in each month.",
            "Current account",
        ),
        (
            "de",
            "Es ist kostenlos, wenn der Kunde jünger als 25 Jahre ist.",
            "Studentenkonto",
        ),
    ],
)
def test_it_before_a_condition_only_its_heading_names_is_still_refused(
    language, text, section
) -> None:
    """The heading names the account `it` is, and a reader of the fact sees none."""
    read = passage(text, language=language, section_path=section)

    judged = Checker(read).atomic(text, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )


def test_a_statement_with_no_finite_verb_is_refused(checker) -> None:
    """Naming something is not asserting anything about it."""
    naming = checker.atomic("The 4 kg device.")
    assert naming.rejection_code == Rejection.ASSERTS_NOTHING, naming.validation_error
    assert naming.statement_predicates == 0


@pytest.mark.parametrize(
    ("statement", "cited", "added"),
    [
        ("The device weighs 7 kg.", 0, "7"),
        ("The Bundesbank delivers the device in March 2026.", 1, "bundesbank"),
    ],
)
def test_a_unit_the_cited_text_does_not_carry_is_refused(
    checker, statement, cited, added
) -> None:
    """A number or a name the source never gave is an unsupported addition."""
    invented = checker.atomic(statement, cited)
    assert invented.rejection_code == Rejection.UNSUPPORTED_ADDITION, (
        invented.validation_error
    )
    assert added in invented.units_added, invented.units_added


@pytest.mark.parametrize(
    "statement",
    [
        "Das Umfeld des Finanzsektors ist geprägt von geopolitischen Umbrüchen.",
        "Die Digitalisierung schreitet fort.",
    ],
)
def test_neither_a_common_noun_nor_a_verb_is_a_unit(statement) -> None:
    """The two sides are parsed separately; only units are compared."""
    german = Checker(
        passage(
            "Das Umfeld des Finanzsektors ist geprägt von geopolitischen Umbrüchen "
            "und fortschreitender Digitalisierung. Die Bafin beobachtet das.",
            language="de",
        )
    )
    echoed = german.atomic(statement, 0)
    assert not echoed.units_added, (statement, echoed.units_added)


def test_a_statement_that_cannot_be_read_alone_is_refused(checker) -> None:
    """An unresolved pronoun cannot become a question."""
    dangling = checker.atomic("It arrives in March 2026.", 1)
    assert dangling.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        dangling.validation_error
    )
    assert "it" in dangling.unresolved_references, dangling.unresolved_references


@pytest.mark.parametrize(
    ("statement", "language"),
    [
        ("The card is blocked if it is reported stolen.", "en"),
        ("If the card is reported stolen, it is blocked.", "en"),
        ("The bank replaces the card when its chip fails.", "en"),
        ("The bank replaces its cards every year.", "en"),
        ("Die Bank ersetzt ihre Karten jedes Jahr.", "de"),
        ("Der Kredit wird gekündigt, wenn er nicht bedient wird.", "de"),
        (
            (
                "Ein Kunde erhält eine Ersatzkarte, sofern es die Bedingungen "
                "der Bank gestatten."
            ),
            "de",
        ),
        ("The account holder may use their card abroad.", "en"),
        ("A customer who moves must give their new address.", "en"),
        ("Die Rückgabe ist kostenlos, es sei denn, die Ware ist beschädigt.", "de"),
        ("It is easy to close the account online.", "en"),
        (
            "Die Filialen tragen Schilder, durch die sie sich voneinander unterscheiden.",
            "de",
        ),
    ],
)
def test_a_pronoun_its_own_statement_resolves_is_not_dangling(
    statement, language
) -> None:
    """`it` after `The card`, in the same statement, names the card.

    And it is not recorded at all: the table refuses a validated claim
    carrying an unresolved reference, so refusing nothing is not enough.
    """
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.validated, judged.validation_error
    assert not judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "language", "pointer"),
    [
        ("Er wird gekündigt, wenn der Kredit nicht bedient wird.", "de", "er"),
        ("Der Kredit wird gekündigt, wenn sie ihn nicht bedient.", "de", "sie"),
        ("The card is blocked if this is reported stolen.", "en", "this"),
        ("This is blocked if the card is reported stolen.", "en", "this"),
        ("The customer must return it within 14 days.", "en", "it"),
        ("At the branch, the customer must return it within 14 days.", "en", "it"),
        ("In der Filiale muss der Kunde sie zurückgeben.", "de", "sie"),
        ("Customers and staff are not allowed to use it.", "en", "it"),
        ("The customer has the right to return it within 14 days.", "en", "it"),
        ("Der Kunde hat das Recht, ihn zurückzugeben.", "de", "ihn"),
        ("The account holder must inform him within three days.", "en", "him"),
        ("Der Kunde muss ihn informieren.", "de", "ihn"),
        ("The customer must return hers.", "en", "hers"),
        ("The bank asks it to confirm the transfer.", "en", "it"),
        ("Der Kunde muss es zurückgeben, um eine Erstattung zu erhalten.", "de", "es"),
        (
            "Der Nutzer muss den Akku laden, bevor es den Ruhemodus verlässt.",
            "de",
            "es",
        ),
    ],
)
def test_a_pronoun_its_statement_does_not_resolve_is_still_refused(
    statement, language, pointer
) -> None:
    """Opening the statement, agreeing with nothing before it, or pointing.

    Or agreeing only with a noun of its own clause, which a personal pronoun
    never names - that takes a reflexive - so `it` in "The customer must
    return it" is something the passage named before, as it is after "At
    the branch".
    """
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )
    assert pointer in judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        (
            "The card issued by it is valid for three years.",
            "a participle opens no clause, so `it` sits in the card's own",
        ),
        (
            "To renew the card, the customer returns it to the bank.",
            "a to-infinitive opens no clause, so the card sits in `it`'s own",
        ),
    ],
)
def test_a_pronoun_beside_a_non_finite_clause_is_refused(statement, reason) -> None:
    """Refused, as the safe direction, whether or not a reader would resolve it.

    The second names the card plainly. Only a finite clause is read as one
    of its own, which is what refuses "The customer has the right to return
    it", and the price is a statement like this one refused as dangling: one
    fact lost, rather than one let through that cannot be read alone.
    """
    judged = Checker(passage(statement, language="en")).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, reason
    assert "it" in judged.unresolved_references, reason


@pytest.mark.parametrize(
    ("statement", "language", "pointer"),
    [
        (
            "These types of documentation typically form part of the test basis.",
            "en",
            "these",
        ),
        ("Diese Bibliotheken erben die Klassen der Kernbibliotheken.", "de", "diese"),
        ("Hierfür werden Testdaten benötigt.", "de", "hierfür"),
    ],
)
def test_a_statement_opening_on_a_demonstrative_is_refused(
    statement, language, pointer
) -> None:
    """`Diese Bibliotheken` names libraries the statement never introduced."""
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )
    assert pointer in judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "language", "pointer"),
    [
        ("Such a card is blocked after three wrong PIN entries.", "en", "such"),
        ("The following fees apply to transfers abroad.", "en", "following"),
        (
            "The aforementioned card is blocked after three wrong PIN entries.",
            "en",
            "aforementioned",
        ),
        (
            "Eine solche Karte wird nach drei falschen PIN-Eingaben gesperrt.",
            "de",
            "solche",
        ),
        ("Die folgenden Gebühren gelten für Auslandsüberweisungen.", "de", "folgenden"),
        (
            "Die vorgenannte Karte wird nach drei falschen PIN-Eingaben gesperrt.",
            "de",
            "vorgenannte",
        ),
    ],
)
def test_a_statement_opening_on_a_noun_its_modifier_points_away_from_is_refused(
    statement, language, pointer
) -> None:
    """`Eine solche Karte` and `the following fees` point as far as `Diese Karte`."""
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )
    assert pointer in judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "language"),
    [
        ("A replacement card is issued per account; such a card costs 5 EUR.", "en"),
        ("Fees such as transfer fees are charged monthly.", "en"),
        ("On the following day, the amount is credited to the account.", "en"),
        ("Am folgenden Bankarbeitstag wird der Betrag gutgeschrieben.", "de"),
        ("Der Betrag wird am folgenden Bankarbeitstag gutgeschrieben.", "de"),
        ("The following fees apply: 2 EUR per transfer and 5 EUR per month.", "en"),
        (
            "Folgende Gebühren fallen an: 2 EUR pro Überweisung und 5 EUR im Monat.",
            "de",
        ),
        ("For the following 12 months, the card is free.", "en"),
        ("In den folgenden zwölf Monaten ist die Karte kostenlos.", "de"),
    ],
)
def test_a_modifier_naming_its_noun_or_the_next_day_is_not_a_reference(
    statement, language
) -> None:
    """The card named first, an example list, the items after a colon, and a span to come."""
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert not judged.unresolved_references, judged.validation_error


@pytest.mark.parametrize(
    ("statement", "language"),
    [
        ("This syllabus defines adaptability as the ease of modification.", "en"),
        ("Each keyword in this training course syllabus is defined.", "en"),
        ("This section focuses on branch testing.", "en"),
        ("This chapter discusses black-box test techniques.", "en"),
        ("Extracts from this document may be copied for non-commercial use.", "en"),
        ("Dieser Lehrplan behandelt zwei Modelle.", "de"),
        ("Die Lernziele dieses Lehrplans enden mit einem Aktionsverb.", "de"),
        ("Dieser Abschnitt behandelt datengetriebenes Testen.", "de"),
        ("Die in diesem Kapitel behandelten Verfahren sind Black-Box-Verfahren.", "de"),
    ],
)
def test_a_demonstrative_naming_the_source_document_is_not_a_reference(
    statement, language
) -> None:
    """`Dieser Lehrplan` is the document the citation names."""
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.rejection_code != Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )
    assert not judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "cited"),
    [
        ("Ein zentrales Risiko ergibt sich aus Handelskonflikten.", 0),
        ("Es besteht Potenzial für plötzliche Marktkorrekturen.", 1),
    ],
)
def test_a_german_reflexive_or_expletive_is_not_a_reference(statement, cited) -> None:
    """A reflexive belongs to its verb and an expletive stands in for nothing."""
    german = Checker(
        passage(
            "Ein zentrales Risiko ergibt sich aus Handelskonflikten. "
            "Es besteht Potenzial für plötzliche Marktkorrekturen.",
            language="de",
        )
    )
    # Cited from the other sentence, so the copy check leaves it alone.
    judged = german.atomic(statement, 1 - cited)
    assert judged.rejection_code != Rejection.UNRESOLVED_REFERENCE, (
        f"{statement!r}: {judged.unresolved_references}"
    )


def test_two_cited_sentences_span_from_the_first_to_the_last(checker) -> None:
    """The evidence runs from the start of the first to the end of the last."""
    joined = checker.atomic("The device arrives in March 2026.", (0, 1))

    assert only(joined).sentence_ids == [0, 1]
    assert only(joined).start == 0
    assert only(joined).end == len(checker.passage.text)


def test_a_citation_naming_one_sentence_twice_resolves_once(checker) -> None:
    """A repeated index is one sentence, not a span of two."""
    repeated = checker.atomic("The device weighs 4 kg.", (0, 0))
    assert only(repeated).sentence_ids == [0]


@pytest.fixture(scope="module")
def spaced() -> Checker:
    """Three sentences, the middle one carrying a number of its own."""
    return Checker(
        passage(
            "The device weighs 4 kg. A spare part costs 99 euro. It arrives in March."
        )
    )


class TestSentencesWithAGapBetweenThem:
    """A claim citing 0 and 2 rests on two sentences, not on three.

    The span recorded covers all three, because that is what a reader sees
    highlighted. What the checks read is the two.
    """

    def test_the_span_still_covers_the_whole_range(self, spaced) -> None:
        """One offset pair per passage is what fact_passages holds."""
        cited = only(spaced.atomic("The device arrives in March.", (0, 2)))

        assert cited.sentence_ids == [0, 2]
        assert cited.start == 0
        assert cited.end == len(spaced.passage.text)

    def test_the_evidence_leaves_out_what_was_not_cited(self, spaced) -> None:
        """It is what the checks read, so it carries what was named."""
        drawn = spaced.atomic("The device arrives in March.", (0, 2))

        assert "99 euro" not in drawn.evidence_text
        assert "weighs 4 kg" in drawn.evidence_text
        assert "arrives in March" in drawn.evidence_text

    def test_a_unit_from_the_uncited_sentence_is_the_passages(self, spaced) -> None:
        """The passage gives the 99 though the claim never cited it.

        The evidence stored and shown stays the cited sentences; what counts
        as said is the passage.
        """
        borrowed = spaced.atomic("The device costs 99 euro.", (0, 2))

        assert borrowed.validated, borrowed.units_added


def test_a_deterministic_statement_is_judged_on_its_citation_alone(checker) -> None:
    """A statement composed from a grid is neither a sentence nor written."""
    composed = checker.composed("Device - Mass: 4 kg")
    assert composed.validated, (composed.rejection_code, composed.validation_error)


def test_a_deterministic_statement_faces_no_check_a_writer_faces(checker) -> None:
    """Every written check would refuse this; none of them is applied."""
    composed = checker.composed("Device - Mass: 7 kg - it")
    assert composed.validated, (composed.rejection_code, composed.validation_error)
    assert composed.units_added, "the reading is still recorded"


def test_a_deterministic_copy_of_its_evidence_is_still_refused(checker) -> None:
    """The one check a composed statement does face."""
    copied = checker.composed("The device weighs 4 kg and runs for 12 hours.")
    assert copied.rejection_code == Rejection.COPIED, copied.validation_error


class TestDigest:
    """A summary and an outline stand in for a whole passage."""

    def test_a_condensed_summary_of_the_passage_is_accepted(self, checker) -> None:
        """Shorter than its passage, asserting something, inventing nothing."""
        made = checker.summary("The device weighs 4 kg. It arrives in March 2026.")

        assert made.validated, (made.rejection_code, made.validation_error)
        assert made.kind == FactKind.SUMMARY
        assert made.evidence_text == checker.passage.text
        assert only(made).sentence_ids == [0, 1], "a digest cites its whole passage"

    def test_a_condensed_outline_of_the_passage_is_accepted(self, checker) -> None:
        """Two points, shorter than the passage, inventing nothing."""
        made = checker.outline("Weighs 4 kg", "Arrives in March 2026")

        assert made.validated, (made.rejection_code, made.validation_error)
        assert made.kind == FactKind.OUTLINE
        assert made.evidence_text == checker.passage.text

    def test_several_claims_are_what_a_summary_is_for(self, checker) -> None:
        """The atomicity check is not applied to a digest."""
        several = checker.summary("The device weighs 4 kg. It arrives in March 2026.")

        assert several.statement_predicates > 1, several.statement_predicates
        assert several.validated, several.rejection_code

    def test_a_dangling_pronoun_is_allowed_inside_a_summary(self, checker) -> None:
        """A summary stands in for its passage and may open on a pronoun."""
        referring = checker.summary("It weighs 4 kg. It arrives in March 2026.")

        assert referring.unresolved_references, "the pronoun is still recorded"
        assert referring.validated, referring.rejection_code

    def test_a_summary_referring_back_to_its_own_subject_records_nothing(
        self, checker
    ) -> None:
        """`It` after `The device`, in the same text, names the device."""
        referring = checker.summary("The device weighs 4 kg. It arrives in March 2026.")

        assert not referring.unresolved_references
        assert referring.validated, referring.rejection_code

    def test_a_digest_as_long_as_its_passage_is_refused(self, checker) -> None:
        """Something the length of what it replaces saves a reader nothing."""
        copied = checker.summary(checker.passage.text)

        assert copied.rejection_code == Rejection.NOT_CONDENSED, copied.validation_error
        assert "%" in (copied.validation_error or ""), "the measurement is reported"

    def test_a_digest_inventing_a_value_is_refused(self, checker) -> None:
        """Condensing a passage may not add to it."""
        invented = checker.summary("The device weighs 9 kg.")

        assert invented.rejection_code == Rejection.UNSUPPORTED_ADDITION
        assert "9" in invented.units_added, invented.units_added

    def test_bullets_are_read_as_one_statement(self, checker) -> None:
        """An outline is one fact whose statement is a list."""
        listed = checker.outline("Weighs 4 kg", "Runs for 12 hours")

        assert listed.validated, (listed.rejection_code, listed.validation_error)
        assert listed.statement == "- Weighs 4 kg\n- Runs for 12 hours"

    def test_a_bullet_written_as_a_fragment_is_not_asked_for_a_verb(
        self, checker
    ) -> None:
        """A fragment parses as having none, so no outline would ever pass."""
        from nlp.analysis import claim

        fragments = checker.outline("Weighs 4 kg", "Runs for 12 hours")

        assert claim(fragments.statement, "en").predicates == 0, (
            "the parse this check would have been read off"
        )
        assert fragments.validated, fragments.rejection_code

    def test_an_outline_that_lost_its_bullets_is_refused(self, checker) -> None:
        """The shape is what is checked, so the shape has to be there."""
        loose = checker.raw_outline("Weighs 4 kg\nRuns for 12 hours")
        assert loose.rejection_code == Rejection.NOT_LISTED, loose.validation_error

    def test_a_digest_of_a_passage_with_no_sentences_is_refused(self) -> None:
        """There is nothing to stand in for."""
        empty = Checker(passage("| a | b |", sentences=[]))
        assert empty.summary("Anything at all.").rejection_code == (
            Rejection.EVIDENCE_ABSENT
        )


@pytest.fixture(scope="module")
def offered():
    """Two passages of two documents, as a topic group offers them."""
    return group(
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    )


class TestBridge:
    """A bridge carries a claim no single passage states."""

    def test_a_claim_resting_on_both_passages_is_accepted(
        self, checker, offered
    ) -> None:
        """It records every passage it rests on, in the order shown."""
        bridged = checker.bridge(
            "Support response times are stated separately for standard and "
            "urgent requests.",
            offered,
        )

        assert bridged.validated, (bridged.rejection_code, bridged.validation_error)
        assert bridged.kind == FactKind.BRIDGE
        assert [one.passage_id for one in bridged.citations] == [11, 22]

    @pytest.mark.parametrize(
        ("language", "first", "second", "statement", "relation"),
        [
            (
                "de",
                "Rücksendungen sind innerhalb von 14 Tagen erlaubt.",
                "Geöffnete Software ist von der Rücksendung ausgeschlossen.",
                (
                    "Rücksendungen sind innerhalb von 14 Tagen erlaubt, aber geöffnete "
                    "Software ist von der Rücksendung ausgeschlossen."
                ),
                "contrast",
            ),
            (
                "en",
                "Returns are accepted within 14 days.",
                "Opened software cannot be returned.",
                (
                    "Returns are accepted within 14 days, but opened software cannot be "
                    "returned."
                ),
                "limits",
            ),
            (
                "en",
                "Clothing may be returned within 30 days.",
                "Opened software may not be returned.",
                (
                    "Clothing may be returned within 30 days, but opened software may not "
                    "be returned."
                ),
                "contrast",
            ),
        ],
    )
    def test_a_contrast_or_an_exception_may_state_both_sides(
        self, checker, language, first, second, statement, relation
    ) -> None:
        """A bridge whose relation is a contrast or a limit says a rule and its other side."""
        bridged = checker.bridge(
            statement, group(first, second, language=language), relation=relation
        )

        assert bridged.validated, (bridged.rejection_code, bridged.validation_error)

    def test_a_bridge_of_another_relation_is_still_held_to_one_claim(
        self, checker
    ) -> None:
        """Two independent rules joined by "and" are two facts, whichever the passages."""
        both = group(
            "Returns are accepted within 14 days.",
            "Refunds are paid within 5 days.",
        )
        statement = (
            "Returns are accepted within 14 days and refunds are paid within 5 days."
        )

        for relation in ("applies", "parallel", None):
            bridged = checker.bridge(statement, both, relation=relation)

            assert bridged.rejection_code == Rejection.NOT_ATOMIC, relation

    @pytest.mark.parametrize(
        ("language", "first", "second", "statement"),
        [
            (
                "de",
                "Rücksendungen sind innerhalb von 14 Tagen erlaubt.",
                "Rücksendungen sind innerhalb von 14 Tagen erlaubt.",
                "Rücksendungen sind innerhalb von 14 Tagen erlaubt.",
            ),
            (
                "en",
                "Orders over 50 EUR are shipped free of charge.",
                "Orders over 50 EUR are shipped free.",
                "Orders over 50 EUR are shipped free of charge.",
            ),
            (
                "en",
                "Summary: gift cards expire after 24 months.",
                "Gift cards expire after 24 months, counted from the purchase.",
                "Gift cards expire after 24 months.",
            ),
        ],
    )
    def test_a_bridge_one_passage_gives_whole_is_refused(
        self, checker, language, first, second, statement
    ) -> None:
        """A passage that gives the statement no word or figure the other lacks adds nothing."""
        bridged = checker.bridge(
            statement, group(first, second, language=language), relation="applies"
        )

        assert bridged.rejection_code == Rejection.NOT_BRIDGING, (
            bridged.validation_error
        )

    @pytest.mark.parametrize(
        ("language", "first", "second", "statement"),
        [
            (
                "en",
                "Standard orders ship within 5 days.",
                "Express orders ship within 1 day.",
                (
                    "Express orders are shipped within 1 day, while standard orders are shipped "
                    "within 5 days."
                ),
            ),
            (
                "de",
                "Standardbestellungen werden innerhalb von 5 Tagen versandt.",
                "Expressbestellungen werden innerhalb von 1 Tag versandt.",
                (
                    "Expressbestellungen werden innerhalb von 1 Tag versandt, "
                    "Standardbestellungen werden innerhalb von 5 Tagen versandt."
                ),
            ),
        ],
    )
    def test_a_bridge_each_passage_gives_a_part_of_is_accepted(
        self, checker, language, first, second, statement
    ) -> None:
        """Each passage owns a figure or a word the other lacks."""
        bridged = checker.bridge(
            statement, group(first, second, language=language), relation="contrast"
        )

        assert bridged.validated, (bridged.rejection_code, bridged.validation_error)

    def test_the_evidence_is_every_span_it_cited(self, checker, offered) -> None:
        """One line per passage, in the order the model was shown them."""
        bridged = checker.bridge("Two request kinds are named.", offered)

        by_id = {one.id: one for one in offered}
        assert bridged.evidence_text == "\n".join(
            by_id[one.passage_id].text[one.start : one.end] for one in bridged.citations
        )

    def test_every_citation_resolves_in_the_passage_it_names(
        self, checker, offered
    ) -> None:
        """A bridge is traceable in each half, not only in its anchor."""
        bridged = checker.bridge("Two request kinds are named.", offered)

        by_id = {one.id: one for one in offered}
        for one in bridged.citations:
            passage = by_id[one.passage_id]
            cited = [passage.sentences[index] for index in one.sentence_ids]
            assert one.start == cited[0].start
            assert one.end == cited[-1].end
            assert passage.text[one.start : one.end].strip()

    def test_a_citation_names_the_sentences_the_model_read(
        self, checker, offered
    ) -> None:
        """Not every sentence of the passage, which cites nothing in particular."""
        two = group(
            "Standard requests are answered within 48 hours. The clock starts "
            "at acknowledgement.",
            "Urgent requests are answered within 4 hours. They may be raised by phone.",
        )

        bridged = checker.bridge(
            "Two request kinds are answered on different times.",
            two,
            cites={0: (0,), 1: (0,)},
        )

        assert [one.sentence_ids for one in bridged.citations] == [[0], [0]]
        assert bridged.evidence_text == (
            f"{two[0].sentences[0].text}\n{two[1].sentences[0].text}"
        )

    def test_a_claim_citing_a_sentence_one_passage_lacks_rests_on_the_other(
        self, checker, offered
    ) -> None:
        """An unresolvable half leaves it resting on one passage, so refused."""
        bridged = checker.bridge(
            "Requests are answered within a stated time.",
            offered,
            cites={0: (0,), 1: (9,)},
        )

        assert bridged.rejection_code == Rejection.NOT_BRIDGING
        assert [one.passage_id for one in bridged.citations] == [11]

    @pytest.mark.parametrize("named", [(), (7,), (-1,)])
    def test_a_claim_naming_no_offered_passage_is_refused(
        self, checker, offered, named
    ) -> None:
        """Nothing resolves, so nothing supports it."""
        nowhere = checker.bridge("Anything at all happens.", offered, rests_on=named)
        assert nowhere.rejection_code == Rejection.EVIDENCE_ABSENT
        assert [one.passage_id for one in nowhere.citations] == [11, 22], (
            "the group it was read from, with no span in any of it"
        )
        assert not any(one.sentence_ids for one in nowhere.citations)

    def test_a_unit_from_the_second_passage_is_supported(
        self, checker, offered
    ) -> None:
        """The vocabulary checked against is the union of every passage."""
        across = checker.bridge(
            "Standard requests are answered within 48 hours, urgent requests within "
            "4 hours.",
            offered,
        )

        assert not across.units_added, across.units_added
        assert across.validated, across.rejection_code

    def test_a_computed_value_is_in_neither_passage(self, checker, offered) -> None:
        """Arithmetic is not reading, so a total nobody wrote is an addition."""
        summed = checker.bridge("The two times differ by 44 hours.", offered)

        assert summed.rejection_code == Rejection.UNSUPPORTED_ADDITION
        assert "44" in summed.units_added, summed.units_added

    def test_a_group_naming_the_positions_out_of_order_still_anchors_first(
        self, checker, offered
    ) -> None:
        """Position 0 is the anchor whichever order the model named them in."""
        reversed_order = checker.bridge(
            "Two request kinds are named.", offered, rests_on=(1, 0)
        )
        assert [one.passage_id for one in reversed_order.citations] == [11, 22]


def _under(language: str, *rows: tuple[str, str]):
    """Passages of two documents under the given heading trails."""
    from dataclasses import replace

    return [
        replace(
            passage(text, language=language, section_path=path),
            id=11 * (at + 1),
            doc_sha256=f"doc-{at}",
        )
        for at, (path, text) in enumerate(rows)
    ]


class TestBridgeReadsItsHeadings:
    """A bridge is checked against each passage's trail and title as an atomic fact is."""

    @pytest.mark.parametrize(
        ("language", "rows", "statement", "unit"),
        [
            (
                "en",
                (
                    (
                        "Fees 2026 > Dormant accounts",
                        "A dormant account is charged 10 EUR a year.",
                    ),
                    (
                        "Accounts > Dormancy",
                        "An account is dormant when its holder has made no payment for 24 months.",
                    ),
                ),
                "In 2026, an account whose holder has made no payment for 24 months is charged 10 EUR a year.",
                "2026",
            ),
            (
                "de",
                (
                    (
                        "Gebühren 2026 > Ruhende Konten",
                        "Für ein ruhendes Konto werden 10 EUR im Jahr berechnet.",
                    ),
                    (
                        "Konten > Ruhende Konten",
                        "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
                    ),
                ),
                "Im Jahr 2026 werden für ein Konto, dessen Inhaber 24 Monate lang keine Zahlung geleistet hat, 10 EUR im Jahr berechnet.",
                "2026",
            ),
            (
                "en",
                (
                    ("Aurora Card > Fees", "A replacement costs 5 EUR."),
                    ("Cards > Replacement", "A lost card is replaced within 3 days."),
                ),
                "A lost Aurora card is replaced within 3 days for 5 EUR.",
                "aurora",
            ),
            (
                "de",
                (
                    ("Aurora-Karte > Gebühren", "Der Ersatz kostet 5 EUR."),
                    (
                        "Karten > Ersatz",
                        "Eine verlorene Karte wird innerhalb von 3 Tagen ersetzt.",
                    ),
                ),
                "Eine verlorene Aurora-Karte wird innerhalb von 3 Tagen für 5 EUR ersetzt.",
                "aurora",
            ),
        ],
    )
    def test_a_unit_its_heading_carries_is_not_added(
        self, checker, language, rows, statement, unit
    ) -> None:
        """The trail names what a sentence under it leaves as 'the card'."""
        bridged = checker.bridge(statement, _under(language, *rows))

        assert bridged.validated, (
            bridged.rejection_code,
            bridged.validation_error,
            bridged.units_added,
        )

    @pytest.mark.parametrize(
        ("language", "first", "second", "statement"),
        [
            (
                "de",
                "Artikel können innerhalb von 30 Tagen zurückgesendet werden.",
                "Erstattungen erfolgen innerhalb von 14 Tagen.",
                "Artikel, die innerhalb von dreissig Tagen zurückgesendet werden, werden innerhalb von vierzehn Tagen erstattet.",
            ),
        ],
    )
    def test_a_number_spelled_otherwise_is_not_added(
        self, checker, language, first, second, statement
    ) -> None:
        """Numbers are read in any spelling, as for an atomic fact."""
        bridged = checker.bridge(statement, group(first, second, language=language))

        assert not bridged.units_added, bridged.units_added

    @pytest.mark.parametrize(
        ("language", "path", "text", "statement", "label"),
        [
            (
                "en",
                "Section 7 > Yearly fees",
                "A dormant account is charged a yearly fee of 10 EUR.",
                "Section 7 charges a dormant account a yearly fee of 10 EUR.",
                "Section 7",
            ),
            (
                "de",
                "Abschnitt 7 > Jahresgebühren",
                "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
                "Abschnitt 7 belastet ein ruhendes Konto mit einer Jahresgebühr von 10 EUR.",
                "Abschnitt 7",
            ),
        ],
    )
    def test_a_bridge_naming_its_passages_section_is_refused(
        self, checker, language, path, text, statement, label
    ) -> None:
        """Where the text sits is a claim about the document."""
        other = (
            "Accounts > Dormancy",
            "An account is dormant when its holder has made no payment for 24 months."
            if language == "en"
            else "Konten > Ruhe",
        )
        if language == "de":
            other = (
                "Konten > Ruhe",
                "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
            )
        bridged = checker.bridge(statement, _under(language, (path, text), other))

        assert bridged.rejection_code == Rejection.NOT_BRIDGING
        assert label in (bridged.validation_error or "")

    @pytest.mark.parametrize(
        ("language", "path", "text", "statement", "label"),
        [
            (
                "en",
                "Section 7 > Yearly fees",
                "A dormant account is charged a yearly fee of 10 EUR after 9 months.",
                "The yearly fee of 10 EUR after 9 months for a dormant account is set out in Sections 7 and 9.",
                "Section 7",
            ),
            (
                "en",
                "Section 7 > Yearly fees",
                "A dormant account is charged a yearly fee after 9 months.",
                "The fees in Sections 7 and 9 apply to dormant accounts after 9 months.",
                "Section 7",
            ),
            (
                "en",
                "Section 4 > Delivery",
                "An order is delivered within 5 days.",
                "The delivery of an order within 5 days is described in Sections 4 and 5.",
                "Section 4",
            ),
            (
                "de",
                "Abschnitt 7 > Jahresgebühren",
                "Für ein ruhendes Konto wird nach 9 Monaten eine Jahresgebühr von 10 EUR erhoben.",
                "Die Jahresgebühr von 10 EUR nach 9 Monaten für ein ruhendes Konto regeln die Abschnitte 7 und 9.",
                "Abschnitt 7",
            ),
        ],
    )
    def test_a_bridge_naming_its_passages_section_in_the_plural_is_refused(
        self, checker, language, path, text, statement, label
    ) -> None:
        """An inflected label word is the label word whatever its tag."""
        other = (
            (
                "Accounts > Dormancy",
                "An account is dormant after 24 months without payment.",
            )
            if language == "en"
            else ("Konten > Ruhe", "Ein Konto ruht nach 24 Monaten ohne Zahlung.")
        )
        bridged = checker.bridge(statement, _under(language, (path, text), other))

        assert bridged.rejection_code == Rejection.NOT_BRIDGING
        assert label in (bridged.validation_error or "")

    @pytest.mark.parametrize(
        ("language", "rows", "statement"),
        [
            (
                "en",
                (
                    (
                        "Section 7 > Yearly fees",
                        "A dormant account is charged a yearly fee of 10 EUR.",
                    ),
                    (
                        "Accounts > Dormancy",
                        "An account is dormant when its holder has made no payment for 24 months.",
                    ),
                ),
                "A dormant account whose holder has made no payment for 24 months is charged 10 EUR within 7 days under the fees section.",
            ),
            (
                "en",
                (
                    (
                        "Fees 2026 > Dormant accounts",
                        "A dormant account is charged 10 EUR a year.",
                    ),
                    (
                        "Accounts > Dormancy",
                        "An account is dormant when its holder has made no payment for 24 months.",
                    ),
                ),
                "An account whose holder has made no payment for 24 months is charged fees of 10 EUR a year.",
            ),
            (
                "de",
                (
                    (
                        "Abschnitt 7 > Jahresgebühren",
                        "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
                    ),
                    (
                        "Konten > Ruhe",
                        "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
                    ),
                ),
                "Für ein Konto, dessen Inhaber 24 Monate lang keine Zahlung geleistet hat, wird innerhalb von 7 Tagen im Abschnitt über Gebühren eine Jahresgebühr von 10 EUR erhoben.",
            ),
        ],
    )
    def test_a_label_word_and_number_apart_are_no_claim_about_the_document(
        self, checker, language, rows, statement
    ) -> None:
        """Only the word followed by the number names the heading."""
        bridged = checker.bridge(statement, _under(language, *rows))

        assert "names where" not in (bridged.validation_error or ""), (
            bridged.validation_error
        )

    def test_an_atomic_fact_naming_its_section_is_not_refused(self) -> None:
        """The label rule is the bridge's only."""
        read = passage(
            "A dormant account is charged a yearly fee of 10 EUR.",
            section_path="Section 7 > Yearly fees",
        )

        judged = Checker(read).atomic(
            "Section 7 charges a dormant account a yearly fee of 10 EUR.", 0
        )

        assert judged.rejection_code != Rejection.NOT_BRIDGING

    def test_a_bridge_naming_another_documents_section_is_not_refused(
        self, checker
    ) -> None:
        """No cited passage sits under 'Section 9'."""
        rows = (
            ("Fees > Yearly", "A dormant account is charged a yearly fee of 10 EUR."),
            (
                "Accounts > Dormancy",
                "An account is dormant when its holder has made no payment for 24 months.",
            ),
        )
        bridged = checker.bridge(
            "Section 9 charges a dormant account a yearly fee of 10 EUR.",
            _under("en", *rows),
        )

        assert "names where" not in (bridged.validation_error or "")


def test_each_failure_reaches_its_own_code(checker, offered) -> None:
    """Every rejection code the checks can emit, and no bucket shared."""
    codes = {
        checker.atomic("Anything.", 7).rejection_code,
        checker.atomic(checker.passage.text, (0, 1)).rejection_code,
        checker.atomic("The 4 kg device.").rejection_code,
        checker.atomic(
            "The device weighs 4 kg and it runs for 12 hours."
        ).rejection_code,
        checker.atomic("The device weighs 7 kg.").rejection_code,
        checker.atomic("It arrives in March 2026.", 1).rejection_code,
        checker.summary(checker.passage.text).rejection_code,
        checker.outline("Weighs 4 kg").rejection_code,
        checker.bridge(
            "Standard requests are answered within 48 hours.", offered, rests_on=(0,)
        ).rejection_code,
    }

    # Every code a CHECK emits. Two are not among them, and for the same
    # reason: the service refuses what the checks already passed, on
    # something no one fact can be read for. `over_cap` is the passage
    # yielding more atomic facts than EXTRACTION_MIN_OTHER_SHARE leaves room
    # for, and `duplicate` is the corpus already holding the statement.
    service_refuses = {Rejection.OVER_CAP, Rejection.DUPLICATE}
    assert codes == set(Rejection) - service_refuses, sorted(
        set(Rejection) - service_refuses - codes
    )


def test_one_passage_cited_twice_is_one_citation() -> None:
    """Two rows for one passage would collide in the link table."""
    offered = group(
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    )
    checker = Checker()

    bridged = checker.checker.check_bridge(
        offered,
        CandidateFact(
            "Requests are answered within a stated time.",
            (),
            kind=FactKind.BRIDGE,
            passages=(
                Cited(position=0, sentences=(0,)),
                Cited(position=0, sentences=(0,)),
            ),
        ),
    )

    assert [one.passage_id for one in bridged.citations] == [11]
    assert bridged.rejection_code == Rejection.NOT_BRIDGING


def test_a_name_the_section_path_carries_is_no_addition() -> None:
    """The heading trail is where a passage names what it is about."""
    read = passage(
        "The card is free for students.", section_path="Current account > Visa Debit"
    )

    judged = Checker(read).atomic("The Visa Debit card is free for students.", 0)

    assert judged.validated, judged.validation_error


def test_a_name_the_document_title_carries_is_no_addition() -> None:
    """A bank's terms name the bank in their title and say "the bank" after."""
    from dataclasses import replace

    read = replace(
        passage("The bank waives the fee for students."),
        title="Northbank Terms and Conditions",
    )

    judged = Checker(read).atomic("Northbank waives the fee for students.", 0)

    assert judged.validated, judged.validation_error


def test_a_name_from_an_uncited_sentence_of_the_passage_is_no_addition() -> None:
    """The passage says it: an atomic fact is supported by all of its passage."""
    read = passage(
        "The fee applies to all cards. Mastercard holders receive a monthly statement."
    )

    judged = Checker(read).atomic("The fee applies to Mastercard.", 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


def test_a_name_no_sentence_of_the_passage_gives_is_still_an_addition() -> None:
    """Support is the passage's, not the document's or the world's."""
    read = passage("The fee applies to all cards. Holders receive a statement.")

    judged = Checker(read).atomic("The fee applies to Mastercard.", 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION


def test_a_time_the_evidence_does_not_give_is_an_addition() -> None:
    """A time is a figure the statement states, though `like_num` misses it."""
    invented = Checker(passage("The branch opens at 09:00.")).atomic(
        "The branch opens at 08:00.", 0
    )
    stated = Checker(passage("The branch opens at 08:00.")).atomic(
        "The branch opens at 08:00.", 0
    )

    assert invented.rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert "08:00" in invented.units_added, invented.units_added
    assert stated.validated, stated.validation_error


@pytest.mark.parametrize(
    ("evidence", "statement"),
    [
        ("The branch opens at 8:00.", "The branch opens at 08:00."),
        ("The branch opens at 08:00.", "The branch opens at 8:00."),
    ],
)
def test_a_leading_zero_is_no_addition(evidence, statement) -> None:
    """`08:00` and `8:00` are one time: a figure's digits are read as numbers."""
    judged = Checker(passage(evidence)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


def test_a_count_written_as_digits_and_a_suffix_is_its_word() -> None:
    """`2-mal` is the `zweimal` it cites, in digits, and no figure added."""
    read = passage("Die Karte kann zweimal gesperrt werden.", language="de")

    judged = Checker(read).atomic("Die Karte kann 2-mal gesperrt werden.", 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("text", "statement", "language"),
    [
        (
            "Orders over EUR 50 are delivered free. Delivery to Austria takes two days.",
            "Orders over EUR 50 are delivered free to Austria.",
            "en",
        ),
        (
            "Für Rücksendungen gilt: Die Gebühr beträgt 5 EUR. Der Betrag wird erstattet.",
            "Für Rücksendungen beträgt die Gebühr 5 EUR.",
            "de",
        ),
        (
            "The terms set a fee of 12 EUR a month. Students pay no fee.",
            "Students pay no fee of 12 EUR a month.",
            "en",
        ),
    ],
)
def test_a_lead_in_figure_is_supported_by_the_passage(
    text, statement, language
) -> None:
    """A figure stated by the lead-in or a neighbouring sentence is the passage's."""
    read = passage(text, language=language)
    last = len(read.sentences) - 1

    alone = Checker(read).atomic(statement, last)

    assert alone.validated, (alone.rejection_code, alone.units_added)


def test_a_sub_number_of_the_passages_own_heading_is_no_support() -> None:
    """Under heading 3, a figure 3.2 the passage mentions elsewhere is no evidence."""
    from dataclasses import replace

    read = replace(
        passage("Refunds are paid in 14 days. See also clause 3.2 for fees."),
        section_path="Article 3",
    )

    judged = Checker(read).atomic("Refunds are paid in 14 days under 3.2.", 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert "3.2" in judged.units_added, judged.units_added


@pytest.mark.parametrize(
    ("text", "statement"),
    [
        (
            "Die Rückgabefrist beträgt 14 Tage.",
            "Die Rückgabe-frist beträgt 14 Tage.",
        ),
        (
            "Die Rückgabe-frist beträgt 14 Tage.",
            "Die Rückgabefrist beträgt 14 Tage.",
        ),
    ],
)
def test_a_hyphen_the_text_layer_split_or_dropped_is_no_addition(
    text, statement
) -> None:
    """One German compound, with or without the hyphen a line break left."""
    judged = Checker(passage(text, language="de")).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


def test_a_capitalised_list_opener_is_no_new_name_in_english() -> None:
    """A bullet's first word is written with a capital and is no name."""
    read = passage("The shop offers:\n- Refunds within 14 days.\n- Exchanges are free.")

    judged = Checker(read).atomic(
        "The shop offers refunds within 14 days.", len(read.sentences) - 1
    )

    assert judged.validated, (judged.rejection_code, judged.units_added)


def test_a_word_form_is_read_only_in_a_configured_language() -> None:
    """A Spanish passage (no pipeline named) gets no form rule."""
    read = passage("La tarifa es de 5 EUR.", language="es")

    judged = Checker(read).atomic("La tarifa es de 9 EUR.", 0)

    assert not judged.validated


@pytest.mark.parametrize(
    ("excerpt", "statement"),
    [
        (
            "The new tariff applies from 1 st July 2026.",
            "The new tariff applies from 1st July 2026.",
        ),
        (
            "Each player has a ten-second limit.",
            "Each player has a ten-second limit to restart.",
        ),
    ],
)
def test_a_number_written_another_way_is_no_addition(excerpt, statement) -> None:
    """An ordinal parsed apart from its number is the same number."""
    judged = Checker(passage(excerpt)).atomic(statement, 0)

    assert judged.validated, judged.validation_error


class TestBridgeKeepsItsReading:
    """A bridge records the relation it was written with and the question it was tested with."""

    @pytest.mark.parametrize(
        ("language", "texts", "statement", "probe"),
        [
            (
                "en",
                (
                    "A dormant account is charged a yearly fee of 10 EUR.",
                    "An account is dormant when its holder has made no payment for 24 months.",
                ),
                (
                    "An account whose holder has made no payment for 24 months is "
                    "charged a yearly fee of 10 EUR."
                ),
                (
                    (
                        "What yearly fee is charged on an account whose holder has "
                        "made no payment for 24 months?"
                    ),
                    "10 EUR",
                ),
            ),
            (
                "de",
                (
                    "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
                    "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
                ),
                (
                    "Für ein Konto, dessen Inhaber 24 Monate lang keine Zahlung "
                    "geleistet hat, wird eine Jahresgebühr von 10 EUR erhoben."
                ),
                (
                    (
                        "Welche Jahresgebühr wird für ein Konto erhoben, dessen "
                        "Inhaber 24 Monate lang keine Zahlung geleistet hat?"
                    ),
                    "10 EUR",
                ),
            ),
        ],
    )
    def test_check_bridge_carries_the_reading(
        self, checker, language, texts, statement, probe
    ) -> None:
        """Validated or not, the fact carries {relation, question, answer}."""
        offered = group(*texts, language=language)

        bridged = checker.bridge(statement, offered, relation="defines", probe=probe)

        assert bridged.bridge == {
            "relation": "defines",
            "question": probe[0],
            "answer": probe[1],
        }

    def test_a_refused_bridge_keeps_its_reading_too(self, checker, offered) -> None:
        """One citing a single passage is refused as not bridging and still keeps it."""
        probe = ("Which is answered sooner?", "an urgent request")

        refused = checker.bridge(
            "Urgent requests are answered within 4 hours.",
            offered,
            rests_on=(1,),
            relation="contrast",
            probe=probe,
        )

        assert not refused.validated
        assert refused.bridge == {
            "relation": "contrast",
            "question": probe[0],
            "answer": probe[1],
        }

    def test_an_absent_citation_keeps_its_reading(self, checker, offered) -> None:
        """The refusal that names no sentence still records what was asked."""
        absent = checker.bridge(
            "Anything.",
            offered,
            cites={0: (9,), 1: (9,)},
            relation="limits",
            probe=("q?", "a"),
        )

        assert absent.rejection_code == Rejection.EVIDENCE_ABSENT
        assert absent.bridge == {"relation": "limits", "question": "q?", "answer": "a"}

    def test_a_candidate_with_no_reading_carries_none(self, checker, offered) -> None:
        """A bridge from a prompt before 6 has neither relation nor probe."""
        assert checker.bridge("Two kinds are named.", offered).bridge is None


@pytest.mark.parametrize(
    ("language", "word", "text", "named"),
    [
        ("en", "section", "Sections 7", True),
        ("en", "section", "Sectional 7", False),
        ("en", "law", "Lawn 3", False),
        ("en", "part", "Party 3", False),
        ("de", "abschnitt", "Abschnitte 7", True),
        ("de", "abschnitt", "Abschnittes 7", True),
        ("de", "abschnitt", "Abschnitten 7", True),
        ("de", "ziffer", "Ziffern 3", True),
        ("de", "artikel", "Artikeln 3", True),
        ("de", "teil", "Teilen 3", True),
        ("de", "teil", "Teilnehmer 3", False),
    ],
)
def test_a_label_word_is_matched_through_an_inflection_of_its_language(
    language, word, text, named
) -> None:
    """Only a suffix the language inflects with, not any letters, is an inflection."""
    from types import SimpleNamespace as T

    from extraction.validation import label_word

    tokens = [T(text=w, lemma_=w) for w in text.split()]
    assert (label_word(tokens, 0, (word,), language) == word) is named


@pytest.mark.parametrize(
    ("language", "text", "statement", "line"),
    [
        (
            "en",
            "Accepted payments:\n- Cards are accepted\n- Cash is accepted\n- Vouchers are accepted",
            "Cash is accepted.",
            2,
        ),
        (
            "de",
            "Zahlungsarten:\n- Karten werden akzeptiert\n- Bargeld wird akzeptiert\n- Gutscheine werden akzeptiert",
            "Bargeld wird akzeptiert.",
            2,
        ),
        (
            "en",
            "Delivery options:\n- Standard delivery is free\n- Express delivery costs 5 EUR\n- Pickup is free",
            "Express delivery costs 5 EUR.",
            2,
        ),
    ],
)
def test_a_list_line_the_model_numbered_past_the_last_sentence_names_that_line(
    language, text, statement, line
) -> None:
    """A passage read as one sentence of several lines is cited by its lines."""
    read = passage(text, language=language)
    assert len(read.sentences) == 1, [one.text for one in read.sentences]

    judged = Checker(read).atomic(statement, line)

    assert judged.validated, (judged.rejection_code, judged.validation_error)
    (cite,) = judged.citations
    assert cite.sentence_ids == [0]
    assert read.text[cite.start : cite.end] == judged.evidence_text
    assert statement.rstrip(".") in judged.evidence_text
    assert "Cards are" not in judged.evidence_text


def test_an_index_beyond_the_lines_of_the_last_sentence_stays_refused() -> None:
    """Three lines are indices 0 to 2 at most; 9 names nothing."""
    read = passage("Options:\n- Cards are accepted\n- Cash is accepted", language="en")

    judged = Checker(read).atomic("Cash is accepted.", 9)

    assert judged.rejection_code == Rejection.EVIDENCE_ABSENT
