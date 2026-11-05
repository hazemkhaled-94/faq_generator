"""The verdict a proposed fact is judged to.

A rejected fact's code is the quality signal this project reports, so each
failure must reach its own code rather than share a bucket with another.
"""

from __future__ import annotations

from dataclasses import replace

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
    ("statement", "language", "title"),
    [
        (
            "This syllabus defines adaptability as the ease of modification.",
            "en",
            "Syllabus for Test Analysts",
        ),
        (
            "Each keyword in this training course syllabus is defined.",
            "en",
            "Syllabus for Test Analysts",
        ),
        (
            "Extracts from this document may be copied for non-commercial use.",
            "en",
            "Document of Terms",
        ),
        ("Dieser Lehrplan behandelt zwei Modelle.", "de", "Lehrplan für Testanalysten"),
        (
            "Dieses Merkblatt gilt für alle Girokonten.",
            "de",
            "Merkblatt zum Girokonto",
        ),
        ("This brochure applies to all current accounts.", "en", "Account brochure"),
    ],
)
def test_a_demonstrative_naming_the_source_document_is_not_a_reference(
    statement, language, title
) -> None:
    """The document's own title says what it is: `Dieser Lehrplan` under a Lehrplan."""
    named = replace(passage(statement, language=language), title=title)
    judged = Checker(named).atomic(statement, 0)

    assert judged.rejection_code != Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )
    assert not judged.unresolved_references


@pytest.mark.parametrize(
    ("statement", "language"),
    [
        ("This section focuses on branch testing.", "en"),
        ("This clause focuses on branch testing.", "en"),
        ("This chapter discusses black-box test techniques.", "en"),
        ("This brochure applies to all current accounts.", "en"),
        ("This syllabus defines adaptability as the ease of modification.", "en"),
        ("Dieser Abschnitt behandelt datengetriebenes Testen.", "de"),
        ("Diese Ziffer behandelt datengetriebenes Testen.", "de"),
        ("Dieses Kapitel behandelt datengetriebenes Testen.", "de"),
        ("Dieses Merkblatt gilt für alle Girokonten.", "de"),
    ],
)
def test_a_demonstrative_before_any_noun_points_unless_the_title_names_it(
    statement, language
) -> None:
    """No noun is exempt by itself: a reader cannot tell which section, clause or brochure."""
    judged = Checker(passage(statement, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNRESOLVED_REFERENCE, (
        judged.validation_error
    )


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
        across = checker.bridge("An urgent request waits 4 hours.", offered)

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
                    ("Aurora Card > Fees", "The card costs 5 EUR a month."),
                    ("Cards > Replacement", "A lost card is replaced within 3 days."),
                ),
                "A lost Aurora card is replaced within 3 days.",
                "aurora",
            ),
            (
                "de",
                (
                    ("Aurora-Karte > Gebühren", "Die Karte kostet 5 EUR im Monat."),
                    (
                        "Karten > Ersatz",
                        "Eine verlorene Karte wird innerhalb von 3 Tagen ersetzt.",
                    ),
                ),
                "Eine verlorene Aurora-Karte wird innerhalb von 3 Tagen ersetzt.",
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


@pytest.mark.parametrize(
    ("text", "statement", "language", "cited", "swapped"),
    [
        (
            (
                "The current account costs EUR 5 per month. The savings account costs "
                "EUR 2 per month. A replacement card costs EUR 15."
            ),
            "The current account costs EUR 2 per month.",
            "en",
            0,
            "5",
        ),
        (
            (
                "Das Girokonto kostet 5 EUR im Monat. Das Sparkonto kostet 2 EUR im "
                "Monat. Eine Ersatzkarte kostet 15 EUR."
            ),
            "Das Girokonto kostet 2 EUR im Monat.",
            "de",
            0,
            "5",
        ),
        (
            "Der Sollzins beträgt 11,9 % p. a. Der Habenzins beträgt 0,5 % p. a.",
            "Der Sollzins beträgt 0,5 % p. a.",
            "de",
            0,
            "11,9",
        ),
        (
            (
                "Standard delivery costs 4.95 EUR and takes 3 days. Express delivery "
                "costs 9.95 EUR and takes 1 day."
            ),
            "Standard delivery costs 9.95 EUR.",
            "en",
            0,
            "4.95",
        ),
        (
            "Der Standardversand kostet 4,95 EUR. Der Expressversand kostet 9,95 EUR.",
            "Der Standardversand kostet 9,95 EUR.",
            "de",
            0,
            "4,95",
        ),
        (
            (
                "Clothing may be returned within 30 days. Electronics may be returned "
                "within 14 days."
            ),
            "Electronics may be returned within 30 days.",
            "en",
            1,
            "14",
        ),
        (
            (
                "Bestellungen bis 14 Uhr werden am selben Tag versandt. Bestellungen "
                "nach 18 Uhr werden am nächsten Tag versandt."
            ),
            "Bestellungen bis 18 Uhr werden am selben Tag versandt.",
            "de",
            0,
            "14",
        ),
    ],
)
def test_a_figure_of_the_same_kind_swapped_for_the_cited_one_is_refused(
    text, statement, language, cited, swapped
) -> None:
    """The passage states the figure elsewhere, but the cited sentence states another."""
    read = passage(text, language=language)

    judged = Checker(read).atomic(statement, cited)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert swapped in (judged.validation_error or ""), judged.validation_error


@pytest.mark.parametrize(
    ("text", "statement", "language"),
    [
        (
            "Bestellungen bis 14:00 Uhr werden am selben Tag versandt. Die Hotline ist bis 18:00 Uhr erreichbar.",
            "Bestellungen bis 18:00 Uhr werden am selben Tag versandt.",
            "de",
        ),
        (
            "Transfers received by 3:00 pm are booked the same day. Standing orders run at 6:00 pm.",
            "Transfers received by 6:00 pm are booked the same day.",
            "en",
        ),
        (
            "Der Standardversand dauert 2\u20134 Werktage. Der Versand ins Ausland dauert 2\u20137 Werktage.",
            "Der Standardversand dauert 2\u20137 Werktage.",
            "de",
        ),
        (
            "Standard delivery takes 2\u20134 working days. Delivery abroad takes 2\u20137 working days.",
            "Standard delivery takes 2\u20137 working days.",
            "en",
        ),
    ],
)
def test_a_swap_sharing_a_numeral_with_the_cited_figure_is_refused(
    text, statement, language
) -> None:
    """A time or a range sharing a digit group with the cited one is still another figure."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, (
        judged.validation_error
    )


@pytest.mark.parametrize(
    ("text", "statement", "language", "cited"),
    [
        (
            (
                "The current account costs EUR 5 per month. The savings account costs "
                "EUR 2 per month."
            ),
            "The current account costs EUR 5 per month.",
            "en",
            0,
        ),
        (
            "Standard delivery takes 3 days. Express delivery costs 9.95 EUR.",
            "Standard delivery costs 9.95 EUR.",
            "en",
            0,
        ),
        (
            "Der Standardversand dauert 3 Tage. Der Expressversand kostet 9,95 EUR.",
            "Der Standardversand kostet 9,95 EUR.",
            "de",
            0,
        ),
        (
            "Orders over EUR 50 are delivered free. Delivery to Austria takes two days.",
            "Orders over EUR 50 are delivered free to Austria.",
            "en",
            1,
        ),
        (
            "Orders must be placed by 23.59 CET. Late orders ship the day after 23:59 CET.",
            "Orders must be placed by 23:59 CET.",
            "en",
            0,
        ),
        (
            "Der Standardversand kostet 9,95 EUR. Der Expressversand kostet 12.50 EUR.",
            "Der Standardversand kostet 9.95 EUR.",
            "de",
            0,
        ),
    ],
)
def test_a_figure_of_another_kind_from_another_sentence_is_still_the_passages(
    text, statement, language, cited
) -> None:
    """Only a different figure of the same kind in the cited sentence is a swap."""
    read = passage(text, language=language)

    judged = Checker(read).atomic(statement, cited)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("text", "statement", "language", "cited"),
    [
        (
            "Orders over EUR 50 ship free. Below that, standard delivery costs EUR 4.95.",
            "Standard delivery costs EUR 4.95 for orders under EUR 50.",
            "en",
            1,
        ),
        (
            (
                "Ab einem Bestellwert von 50 EUR ist der Versand kostenlos. Darunter "
                "kostet der Standardversand 4,95 EUR."
            ),
            "Unter einem Bestellwert von 50 EUR kostet der Standardversand 4,95 EUR.",
            "de",
            1,
        ),
        (
            "The monthly account fee is EUR 5. Students pay EUR 2 instead.",
            "Students pay a monthly account fee of EUR 2 instead of EUR 5.",
            "en",
            1,
        ),
        (
            (
                "Für Überweisungen ab 50.000 EUR gilt eine Sonderregelung. Eine "
                "Online-Überweisung kostet dann 0,50 EUR."
            ),
            "Eine Online-Überweisung ab 50.000 EUR kostet 0,50 EUR.",
            "de",
            1,
        ),
        (
            (
                "Zamówienia powyżej 50 EUR są dostarczane bezpłatnie. Poniżej tej kwoty "
                "dostawa kosztuje 4,95 EUR."
            ),
            "Dostawa kosztuje 4,95 EUR przy zamówieniach poniżej 50 EUR.",
            "pl",
            1,
        ),
    ],
)
def test_a_cited_figure_the_statement_also_writes_is_no_swap(
    text, statement, language, cited
) -> None:
    """A fact that keeps the cited figure and adds one from elsewhere swaps nothing."""
    judged = Checker(passage(text, language=language)).atomic(statement, cited)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("text", "statement", "language", "swapped"),
    [
        (
            "Die Kontoführung kostet 5,00 € im Monat. Eine Ersatzkarte kostet 12 Euro.",
            "Die Kontoführung kostet 12 Euro im Monat.",
            "de",
            "5,00",
        ),
        (
            "Die Kontoführung kostet 5 EUR im Monat. Eine Ersatzkarte kostet 12 €.",
            "Die Kontoführung kostet 12 € im Monat.",
            "de",
            "5",
        ),
        (
            "The monthly fee is USD 5. A wire transfer costs $25.",
            "The monthly fee is $25.",
            "en",
            "5",
        ),
        (
            "Account maintenance costs five euros a month. A replacement card costs 15 euros.",
            "Account maintenance costs 15 euros a month.",
            "en",
            "5",
        ),
        (
            "Account maintenance costs EUR 5 a month. Two statements a month are free.",
            "Account maintenance costs two euros a month.",
            "en",
            "5",
        ),
        (
            "Die Kontoführung kostet 5 Euro im Monat. Zwei Kontoauszüge im Monat sind kostenlos.",
            "Die Kontoführung kostet zwei Euro im Monat.",
            "de",
            "5",
        ),
        (
            "The basic account costs 5 euros a month. There are four account models.",
            "The basic account costs four euros a month.",
            "en",
            "5",
        ),
        (
            "Das Basiskonto kostet 5 Euro im Monat. Es gibt vier Kontomodelle.",
            "Das Basiskonto kostet vier Euro im Monat.",
            "de",
            "5",
        ),
        (
            "Delivery takes 5 working days. See Section 3 for details.",
            "Delivery takes three working days.",
            "en",
            "5",
        ),
        (
            "Returns are accepted within fourteen days. Refunds are paid within 30 days.",
            "Returns are accepted within 30 days.",
            "en",
            "fourteen",
        ),
        (
            (
                "Die Rückgabe ist innerhalb von vierzehn Tagen möglich. Die Erstattung "
                "erfolgt binnen 30 Tagen."
            ),
            "Die Rückgabe ist innerhalb von 30 Tagen möglich.",
            "de",
            "vierzehn",
        ),
        (
            "Der Sollzins beträgt 11,9 Prozent. Der Habenzins beträgt 0,5 %.",
            "Der Sollzins beträgt 0,5 %.",
            "de",
            "11,9",
        ),
        (
            "The overdraft rate is 11.9 percent. Savings earn 0.5%.",
            "The overdraft rate is 0.5%.",
            "en",
            "11.9",
        ),
        (
            "Delivery takes 2 weeks. Returns are accepted within 30 days.",
            "Delivery takes 30 days.",
            "en",
            "2",
        ),
        (
            "Die Lieferung dauert 2 Wochen. Eine Rückgabe ist binnen 30 Tagen möglich.",
            "Die Lieferung dauert 30 Tage.",
            "de",
            "2",
        ),
        (
            "Prowadzenie konta kosztuje 5 PLN miesięcznie. Karta zastępcza kosztuje 25 PLN.",
            "Prowadzenie konta kosztuje 25 PLN miesięcznie.",
            "pl",
            "5",
        ),
    ],
)
def test_a_swap_in_words_or_another_spelling_of_its_kind_is_refused(
    text, statement, language, swapped
) -> None:
    """A figure in words, or a currency, share or span of time spelled another way, is of its kind."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert swapped in (judged.validation_error or ""), judged.validation_error


@pytest.mark.parametrize(
    ("text", "statement", "language"),
    [
        (
            "Die Kontoführung kostet 5,00 € im Monat. Eine Ersatzkarte kostet 12 Euro.",
            "Die Kontoführung kostet 5 € im Monat.",
            "de",
        ),
        (
            "Returns are accepted within fourteen days. Refunds are paid within 30 days.",
            "Returns are accepted within 14 days.",
            "en",
        ),
        (
            "Der Sollzins beträgt 11,9 Prozent. Der Habenzins beträgt 0,5 %.",
            "Der Sollzins beträgt 11,9 %.",
            "de",
        ),
        (
            "Delivery takes 2 weeks. A replacement card costs 5 euros.",
            "Delivery takes two weeks.",
            "en",
        ),
    ],
)
def test_one_figure_written_in_another_spelling_is_no_swap(
    text, statement, language
) -> None:
    """The same value in words, a symbol or a code is the cited figure."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("text", "statement", "language", "validated"),
    [
        (
            "Prowadzenie konta kosztuje 5 PLN miesięcznie. Karta zastępcza kosztuje 25 PLN.",
            "Prowadzenie konta kosztuje 25 PLN miesięcznie.",
            "pl",
            False,
        ),
        (
            (
                "Zwrot towaru jest możliwy w ciągu 14 dni. Zwrot pieniędzy następuje "
                "w ciągu 30 dni."
            ),
            "Zwrot towaru jest możliwy w ciągu 14 dni.",
            "pl",
            True,
        ),
    ],
)
def test_the_swapped_figure_guard_reads_words_only_where_the_language_is_configured(
    text, statement, language, validated
) -> None:
    """Polish has a finite verb the default parse finds but no number words: a digit is read, a word is not.

    A figure written out in a language no configuration names is no figure, so
    it is neither a swap nor an excuse for one; the digits are compared as
    in any language, and a correct fact stands.
    """
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated is validated, (
        judged.rejection_code,
        judged.validation_error,
    )


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


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Kontoführung kostet 5 EUR. Die neuen Entgelte gelten ab dem\n1. Januar 2026 für alle Privatkunden.",
            "Die neuen Entgelte gelten ab dem 1. Januar 2026 für alle Privatkunden.",
        ),
        (
            "en",
            "The account costs EUR 5. The new fees apply from\n1 January 2026 to every customer.",
            "The new fees apply from 1 January 2026 to every customer.",
        ),
        (
            "pl",
            "Prowadzenie konta kosztuje 5 EUR. Nowe opłaty obowiązują od\n1. stycznia 2026 dla wszystkich klientów.",
            "Nowe opłaty obowiązują od 1. stycznia 2026 dla wszystkich klientów.",
        ),
    ],
)
def test_a_wrapped_line_opening_with_a_date_is_no_list_line(
    language, text, statement
) -> None:
    """A lone number and its mark at a line start is a date or an ordinal, not a list."""
    read = passage(text, language=language)

    judged = Checker(read).atomic(statement, len(read.sentences))

    assert judged.rejection_code == Rejection.EVIDENCE_ABSENT, judged.validation_error


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "The bank charges a fee for each transfer.\nThe fee is charged at the end of the month and\nshown on the statement.",
            "The fee is shown on the statement.",
        ),
        (
            "de",
            "Die Bank erhebt für jede Überweisung eine Gebühr.\nDie Gebühr wird am Monatsende erhoben und\nauf dem Kontoauszug ausgewiesen.",
            "Die Gebühr wird auf dem Kontoauszug ausgewiesen.",
        ),
        (
            "pl",
            "Bank pobiera opłatę za każdy przelew.\nOpłata jest pobierana na koniec miesiąca i\nwykazana na wyciągu.",
            "Opłata jest wykazana na wyciągu.",
        ),
    ],
)
def test_an_index_past_a_wrapped_prose_sentence_names_nothing(
    language, text, statement
) -> None:
    """Only list lines are cited by their line: a wrapped line of prose is no fact's evidence."""
    read = passage(text, language=language)

    judged = Checker(read).atomic(statement, len(read.sentences))

    assert judged.rejection_code == Rejection.EVIDENCE_ABSENT


@pytest.mark.parametrize(
    ("language", "text", "statement", "section"),
    [
        (
            "en",
            "Each card costs EUR 4.95 per year. Cards can be ordered online.",
            "Cards ordered online cost EUR 4.95 per year.",
            "4 Card fees",
        ),
        (
            "de",
            "Jede Karte kostet 4.95 EUR im Jahr. Karten können online bestellt werden.",
            "Online bestellte Karten kosten 4.95 EUR im Jahr.",
            "4 Kartenentgelte",
        ),
        (
            "en",
            "Delivery takes 3.5 days. Orders can be placed online.",
            "Orders placed online are delivered in 3.5 days.",
            "3 Delivery",
        ),
    ],
)
def test_a_price_or_measure_is_no_sub_number_of_the_heading(
    language, text, statement, section
) -> None:
    """A figure beside a currency or a unit is a value, however the heading is numbered."""
    from dataclasses import replace

    read = replace(passage(text, language=language), section_path=section)

    judged = Checker(read).atomic(statement, 1)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        ("en", "The fee is EUR 12.30 a month.", "The fee is EUR 30 a month."),
        ("en", "The rate is 3.25% a year.", "The rate is 25% a year."),
        ("de", "Der Zins beträgt 3.25 % im Jahr.", "Der Zins beträgt 25 % im Jahr."),
        ("de", "Die Gebühr beträgt EUR 12.30 im Monat.", "Die Gebühr beträgt 30 EUR."),
    ],
)
def test_a_dotted_amount_or_rate_does_not_support_its_minute_part(
    language, evidence, statement
) -> None:
    """A dotted figure beside a currency or a percent is a value, never a clock time."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        (
            "de",
            "Das Privatkonto kostet CHF 1'250.50 pro Jahr.",
            "Das Privatkonto kostet CHF 250.50 pro Jahr.",
        ),
        (
            "de",
            "Das Privatkonto kostet CHF 1’250.50 pro Jahr.",
            "Das Privatkonto kostet CHF 250.50 pro Jahr.",
        ),
        (
            "de",
            "Das Limit beträgt CHF 1'000'000 pro Kunde.",
            "Das Limit beträgt CHF 1'000 pro Kunde.",
        ),
        (
            "en",
            "The private account costs CHF 1'250.50 a year.",
            "The private account costs CHF 250.50 a year.",
        ),
    ],
)
def test_a_fact_dropping_the_thousands_of_an_apostrophe_grouped_amount_is_refused(
    language, evidence, statement
) -> None:
    """The Swiss grouping is one figure: dropping its thousands changes the amount."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert not judged.validated, "a wrong amount was validated"


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        (
            "de",
            "Das Privatkonto kostet CHF 1'250.50 pro Jahr.",
            "Das Privatkonto kostet CHF 1250.50 pro Jahr.",
        ),
        (
            "en",
            "The private account costs CHF 1’250.50 a year.",
            "The private account costs CHF 1250.50 a year.",
        ),
        (
            "en",
            "The private account costs CHF 1250.50 a year.",
            "The private account costs CHF 1’250.50 a year.",
        ),
    ],
)
def test_an_apostrophe_grouped_amount_and_its_plain_spelling_support_each_other(
    language, evidence, statement
) -> None:
    """The same amount in another grouping is no addition, in any language."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        (
            "fr",
            "Le compte privé coûte CHF 1'250.50 par an.",
            "Le compte privé coûte CHF 250.50 par an.",
        ),
        (
            "el",
            "Ο λογαριασμός κοστίζει 1.250,50 EUR.",
            "Ο λογαριασμός κοστίζει 1.250,50 EUR.",
        ),
    ],
)
def test_a_language_no_pipeline_is_configured_for_is_refused_at_parse_not_read(
    language, evidence, statement
) -> None:
    """No predicate is read in such a language, so the amount is never judged."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.ASSERTS_NOTHING


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        (
            "en",
            "The promotional rate is 5 % for 12 months.",
            "The promotional rate is 12 % for 5 months.",
        ),
        (
            "de",
            "Der Aktionszins beträgt 5 % für 12 Monate.",
            "Der Aktionszins beträgt 12 % für 5 Monate.",
        ),
        (
            "en",
            "Returns are accepted within 30 days for a fee of 14 EUR.",
            "Returns are accepted within 14 days for a fee of 30 EUR.",
        ),
        (
            "de",
            "Rücksendungen sind innerhalb von 30 Tagen für 14 Euro möglich.",
            "Rücksendungen sind innerhalb von 14 Tagen für 30 Euro möglich.",
        ),
    ],
)
def test_two_figures_traded_between_their_kinds_are_refused(
    language, evidence, statement
) -> None:
    """Each figure is cited, but under the other's kind: the statement says another thing."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "evidence", "statement"),
    [
        (
            "en",
            "The promotional rate is 5 % for 12 months.",
            "For 12 months the promotional rate is 5 %.",
        ),
        (
            "de",
            "Der Aktionszins beträgt 5 % für 12 Monate.",
            "Für 12 Monate beträgt der Aktionszins 5 %.",
        ),
        (
            "en",
            "Returns are accepted within 30 days for a fee of 14 EUR.",
            "A fee of 14 EUR applies to returns within 30 days.",
        ),
    ],
)
def test_figures_keeping_their_kinds_in_another_order_are_validated(
    language, evidence, statement
) -> None:
    """Moving a figure within the sentence is no swap."""
    judged = Checker(passage(evidence, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "evidence", "statement", "faithful"),
    [
        (
            "fr",
            "Le taux promotionnel est de 5 % pendant 12 mois.",
            "Le taux promotionnel est de 12 % pendant 5 mois.",
            "Le taux promotionnel est de 5 % pendant 12 mois.",
        ),
        (
            "el",
            "Το επιτόκιο είναι 5 % για 12 μήνες.",
            "Το επιτόκιο είναι 12 % για 5 μήνες.",
            "Το επιτόκιο είναι 5 % για 12 μήνες.",
        ),
    ],
)
def test_a_language_no_pipeline_is_configured_for_never_reaches_the_swap_guard(
    language, evidence, statement, faithful
) -> None:
    """The traded pair and the faithful one get the same verdict: the guard is inert."""
    read = Checker(passage(evidence, language=language))

    assert (
        read.atomic(statement, 0).rejection_code
        == read.atomic(faithful, 0).rejection_code
    )


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "Since 2024 the account fee is 5 EUR a month. Until 2023 the account fee was 3 EUR a month.",
            "Since 2023 the account fee is 5 EUR a month.",
        ),
        (
            "de",
            "Seit 2024 beträgt die Kontogebühr 5 Euro im Monat. Bis 2023 betrug die Kontogebühr 3 Euro im Monat.",
            "Seit 2023 beträgt die Kontogebühr 5 Euro im Monat.",
        ),
        (
            "en",
            "The branch opens at 9:00. The branch closes at 17:00.",
            "The branch opens at 17:00.",
        ),
        (
            "de",
            "Die Filiale öffnet um 9:00 Uhr. Die Filiale schließt um 17:00 Uhr.",
            "Die Filiale öffnet um 17:00 Uhr.",
        ),
    ],
)
def test_a_year_or_time_lifted_from_an_uncited_sentence_is_a_swap(
    language, text, statement
) -> None:
    """A figure with no unit beside it still has a kind: its shape."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement", "cited"),
    [
        (
            "en",
            "Since 2024 the account fee is 5 EUR a month. Until 2023 the account fee was 3 EUR a month.",
            "Until 2023 the account fee was 3 EUR a month.",
            1,
        ),
        (
            "de",
            "Seit 2024 beträgt die Kontogebühr 5 Euro im Monat. Bis 2023 betrug die Kontogebühr 3 Euro im Monat.",
            "Bis 2023 betrug die Kontogebühr 3 Euro im Monat.",
            1,
        ),
        (
            "en",
            "The branch opens at 9:00. The branch closes at 17:00.",
            "The branch closes at 17:00.",
            1,
        ),
        (
            "en",
            "Orders 100 and 250 are shipped. Order 7 is held.",
            "Order 7 is held.",
            1,
        ),
    ],
)
def test_a_year_or_time_in_the_cited_sentence_is_supported(
    language, text, statement, cited
) -> None:
    """Citing the sentence that states the figure keeps the fact."""
    judged = Checker(passage(text, language=language)).atomic(statement, cited)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "fr",
            "Depuis 2024 les frais sont de 5 EUR par mois. Jusqu'en 2023 ils étaient de 3 EUR par mois.",
            "Depuis 2023 les frais sont de 5 EUR par mois.",
        ),
        (
            "el",
            "Από το 2024 η χρέωση είναι 5 EUR. Μέχρι το 2023 ήταν 3 EUR.",
            "Από το 2023 η χρέωση είναι 5 EUR.",
        ),
    ],
)
def test_a_year_in_a_language_no_pipeline_is_configured_for_is_refused_at_parse(
    language, text, statement
) -> None:
    """Such a language is read by the default pipeline's tags and refused whatever the shape rule does."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert not judged.validated


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die neuen Preise gelten ab dem 1. Januar 2026.",
            "Die neuen Preise gelten ab dem 1. Februar 2026.",
        ),
        (
            "de",
            "Der Antrag muss bis zum 31. März eingereicht werden.",
            "Der Antrag muss bis zum 31. Mai eingereicht werden.",
        ),
        (
            "de",
            "Die Filiale ist montags von 9 bis 18 Uhr geöffnet.",
            "Die Filiale ist dienstags von 9 bis 18 Uhr geöffnet.",
        ),
        (
            "de",
            "Die Abrechnung erfolgt am Montag.",
            "Die Abrechnung erfolgt am Freitag.",
        ),
        (
            "en",
            "The new prices apply from 1 January 2026.",
            "The new prices apply from 1 February 2026.",
        ),
        (
            "en",
            "The branch is open on Mondays from 9 am to 6 pm.",
            "The branch is open on Tuesdays from 9 am to 6 pm.",
        ),
    ],
)
def test_a_fact_moving_a_date_to_another_month_or_weekday_is_refused(
    language, text, statement
) -> None:
    """A month or a weekday is a name a writer reports, whatever the tagger calls it."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die neuen Preise gelten ab dem 1. Januar 2026.",
            "Die neuen Preise gelten ab dem 1. Januar 2026.",
        ),
        (
            "de",
            "Die Filiale ist montags von 9 bis 18 Uhr geöffnet.",
            "Die Filiale ist am Montag von 9 bis 18 Uhr geöffnet.",
        ),
        (
            "de",
            "Die Filiale ist am Montag von 9 bis 18 Uhr geöffnet.",
            "Die Filiale ist montags von 9 bis 18 Uhr geöffnet.",
        ),
        (
            "en",
            "The new prices apply from 1 January 2026.",
            "The new prices apply from 1 January 2026.",
        ),
    ],
)
def test_a_faithful_date_restatement_is_validated(language, text, statement) -> None:
    """The same month or weekday, in whichever of its forms, is no addition."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


def test_a_month_or_weekday_is_read_whatever_the_tagger_calls_it() -> None:
    """German tags `Mai` as a common noun; its row in the calendar table reads it."""
    from nlp.analysis import claim

    assert "mai" in claim("Der Bericht vom Mai ist fertig.", "de").calendar
    assert "montag" in claim("Die Filiale ist montags geöffnet.", "de").calendar
    assert "tuesday" in claim("The branch is closed on Tuesdays.", "en").calendar
    assert "march" in claim("Fees are due in March.", "en").calendar


def test_a_verb_spelled_like_a_month_is_no_month() -> None:
    """Only a token the tagger reads as a noun or a name is a month or a weekday."""
    from nlp.analysis import claim

    assert claim("The bank may close on Tuesdays.", "en").calendar == ("tuesday",)
    assert claim("Clients march to the branch.", "en").calendar == ()


def test_the_calendar_names_leave_the_units_the_question_gates_read_alone() -> None:
    """The fact check reads them from their own field."""
    from nlp.analysis import claim

    assert "februar" not in claim("Gültig ab dem 1. Februar.", "de").units


def test_a_month_read_both_as_a_unit_and_a_calendar_name_is_asserted_once() -> None:
    """English tags a month as a name, so it is a unit and a calendar name; it is asked for once."""
    from nlp.analysis import claim

    asserted = claim("The new prices apply from 1 June 2026.", "en").asserted

    assert asserted.count("june") == 1, asserted


@pytest.mark.parametrize(
    "text",
    [
        "Les prix s'appliquent à partir du 1 janvier 2026.",
        "Οι τιμές ισχύουν από την 1 Ιανουαρίου 2026.",
        "La sucursal cierra los lunes.",
    ],
)
def test_a_language_without_a_calendar_row_reads_no_month(text) -> None:
    """No row, no fold: French, Greek and Spanish names are left to their tags."""
    from nlp.analysis import claim

    assert claim(text, "fr").calendar == ()
    assert claim(text, "el").calendar == ()


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "The branch is closed on Mondays.",
            "The branch is closed on Tuesdays.",
        ),
        (
            "en",
            "Payments made on Saturdays are booked on Mondays.",
            "Payments made on Sundays are booked on Mondays.",
        ),
        (
            "en",
            "Fees are due in March.",
            "Fees are due in May.",
        ),
        (
            "de",
            "Die Filiale ist am Montagmorgen geschlossen.",
            "Die Filiale ist am Dienstag geschlossen.",
        ),
    ],
)
def test_a_fact_moving_a_weekday_or_month_is_refused_in_the_plural_and_across_tags(
    language, text, statement
) -> None:
    """The English plural weekday is a common noun to the tagger; the table reads it all the same."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Hotline ist Mo.–Fr. von 8 bis 20 Uhr erreichbar.",
            "Die Hotline ist Montag bis Freitag von 8 bis 20 Uhr erreichbar.",
        ),
        (
            "de",
            "Die Hotline ist Mo-Fr von 8 bis 20 Uhr erreichbar.",
            "Die Hotline ist montags bis freitags von 8 bis 20 Uhr erreichbar.",
        ),
        (
            "de",
            "Die Frist endet am 31. Dez. 2025.",
            "Die Frist endet am 31. Dezember 2025.",
        ),
        (
            "en",
            "The hotline is open Mon-Fri from 8 to 8.",
            "The hotline is open Monday to Friday from 8 to 8.",
        ),
        (
            "en",
            "The deadline is 31 Dec. 2025.",
            "The deadline is 31 December 2025.",
        ),
        (
            "en",
            "The bank may close on Tuesdays.",
            "The bank may close on Tuesdays.",
        ),
    ],
)
def test_an_abbreviated_date_in_the_evidence_supports_its_full_name(
    language, text, statement
) -> None:
    """An abbreviation can only add support to the cited text, never a refusal."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Hotline ist Mo.–Fr. von 8 bis 20 Uhr erreichbar.",
            "Die Hotline ist Samstag von 8 bis 20 Uhr erreichbar.",
        ),
        (
            "en",
            "The hotline is open Mon-Fri from 8 to 8.",
            "The hotline is open Saturday from 8 to 8.",
        ),
    ],
)
def test_a_weekday_the_abbreviated_evidence_does_not_name_is_refused(
    language, text, statement
) -> None:
    """The folded range names Monday and Friday only."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "Returns are accepted within 14 days. Refunds are paid within 2 weeks.",
            "Returns are accepted within 2 weeks.",
        ),
        (
            "en",
            "A transfer is credited within 8 seconds. A card block lasts 10 minutes.",
            "A transfer is credited within 10 minutes.",
        ),
        (
            "de",
            "Eine Überweisung wird innerhalb von 8 Sekunden gutgeschrieben. Eine Kartensperre dauert 10 Minuten.",
            "Eine Überweisung wird innerhalb von 10 Minuten gutgeschrieben.",
        ),
        (
            "en",
            "The legal guarantee lasts at least 2 years. A repair must be made within 6 months.",
            "The legal guarantee lasts at least 6 months.",
        ),
        (
            "de",
            "Die gesetzliche Gewährleistung beträgt mindestens 2 Jahre. Eine Reparatur muss binnen 6 Monaten erfolgen.",
            "Die gesetzliche Gewährleistung beträgt mindestens 6 Monate.",
        ),
        (
            "en",
            "A transfer arrives within 24 hours. A cheque clears within 3 days.",
            "A transfer arrives within 3 days.",
        ),
        (
            "de",
            "Eine Überweisung dauert 24 Stunden. Ein Scheck wird binnen 3 Tagen gutgeschrieben.",
            "Eine Überweisung dauert 3 Tage.",
        ),
    ],
)
def test_a_period_lifted_from_an_uncited_sentence_is_a_swap_across_every_unit_of_time(
    language, text, statement
) -> None:
    """Seconds, minutes, hours, days, weeks, months and years are one kind of figure."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement", "faithful"),
    [
        (
            "fr",
            "Un virement arrive sous 24 heures. Un chèque est crédité sous 3 jours.",
            "Un virement arrive sous 3 jours.",
            "Un virement arrive sous 24 heures.",
        ),
        (
            "el",
            "Η μεταφορά φτάνει σε 24 ώρες. Η επιταγή πιστώνεται σε 3 ημέρες.",
            "Η μεταφορά φτάνει σε 3 ημέρες.",
            "Η μεταφορά φτάνει σε 24 ώρες.",
        ),
    ],
)
def test_a_period_in_a_language_without_a_time_table_is_never_a_swap(
    language, text, statement, faithful
) -> None:
    """No row, no kind: the swapped pair and the faithful one get the same verdict."""
    read = Checker(passage(text, language=language))

    assert (
        read.atomic(statement, 0).rejection_code
        == read.atomic(faithful, 0).rejection_code
    )


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "A card costs EUR 2 a month. A text message costs 50 cents.",
            "A card costs 50 cents a month.",
        ),
        (
            "de",
            "Eine Karte kostet 2 Euro im Monat. Eine SMS kostet 50 Cent.",
            "Eine Karte kostet 50 Cent im Monat.",
        ),
        (
            "en",
            "The overdraft rate is 9.5 per cent. The savings rate is 2 per cent.",
            "The overdraft rate is 2 per cent.",
        ),
        (
            "en",
            "The rate rose by 2 percentage points. The fee is 9 %.",
            "The rate rose by 9 percentage points.",
        ),
        (
            "de",
            "Der Zins stieg um 2 Prozentpunkte. Die Gebühr beträgt 9 %.",
            "Der Zins stieg um 9 Prozentpunkte.",
        ),
    ],
)
def test_a_figure_swapped_across_a_minor_unit_or_a_share_spelling_is_refused(
    language, text, statement
) -> None:
    """A cent is money and a per cent is a share, however many words write it."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "The overdraft rate is 9.5 per cent a year.",
            "The overdraft rate is 9.5 per cent a year.",
        ),
        (
            "de",
            "Eine SMS kostet 50 Cent.",
            "Eine SMS kostet 50 Cent.",
        ),
    ],
)
def test_a_minor_unit_or_a_share_spelling_kept_is_validated(
    language, text, statement
) -> None:
    """The faithful restatement keeps its kind."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize("language", ["fr", "el"])
def test_a_minor_unit_in_a_language_without_a_row_names_no_kind(language) -> None:
    """No table row: `cent` is only a word there."""
    from extraction.validation import _named_kind

    assert _named_kind("cent", language) is None
    assert _named_kind("cents", language) is None


_UNIT_SWAPS = [
    ("de", "Die Lieferung dauert 3 Tage.", "Die Lieferung dauert 3 Wochen."),
    ("en", "Delivery takes 3 days.", "Delivery takes 3 weeks."),
    ("de", "Das Gerät wiegt 4 kg.", "Das Gerät wiegt 4 g."),
    ("en", "The device weighs 4 kg.", "The device weighs 4 g."),
    (
        "de",
        "Die Kündigungsfrist beträgt 3 Monate.",
        "Die Kündigungsfrist beträgt 3 Jahre.",
    ),
    ("en", "The notice period is 3 months.", "The notice period is 3 years."),
]


@pytest.mark.parametrize(("language", "text", "statement"), _UNIT_SWAPS)
def test_a_figure_that_keeps_its_digits_and_changes_its_unit_is_refused(
    language, text, statement
) -> None:
    """The digits are cited, but beside another unit: the statement says another thing."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text"), [(one[0], one[1]) for one in _UNIT_SWAPS]
)
def test_the_faithful_statement_keeps_its_unit_and_is_validated(language, text) -> None:
    """The control: the same figure and unit."""
    judged = Checker(passage(text, language=language)).atomic(text, 0)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        ("en", "Delivery takes 3 days.", "Delivery takes 3 working days."),
        ("en", "The fee is 3 EUR a month.", "The fee is 3 EUR per month."),
        ("de", "Die Lieferung dauert 3 Tage.", "Die Lieferung dauert 3 Tage lang."),
        ("en", "The bank serves 3 customers.", "The bank serves 3 customers today."),
    ],
)
def test_a_unit_written_with_a_modifier_or_a_neighbour_is_the_same_unit(
    language, text, statement
) -> None:
    """Only another unit lemma beside the same digits is a swap."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        ("fr", "La livraison prend 3 jours.", "La livraison prend 3 semaines."),
        ("el", "Η παράδοση διαρκεί 3 ημέρες.", "Η παράδοση διαρκεί 3 εβδομάδες."),
    ],
)
def test_a_unit_in_a_language_no_pipeline_is_configured_for_is_refused_at_parse(
    language, text, statement
) -> None:
    """No predicate is read, so the unit is never compared."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.ASSERTS_NOTHING


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "The daily card limit is 1500. Since 2024 the limit applies to all cards.",
            "The daily card limit of 1500 applies to all cards.",
        ),
        (
            "de",
            "Das tägliche Kartenlimit liegt bei 1500. Seit 2024 gilt das Limit für alle Karten.",
            "Das Limit von 1500 gilt für alle Karten.",
        ),
        (
            "en",
            "Orders up to 2500 ship free. From 2024 returns are free of charge.",
            "Returns of orders up to 2500 are free of charge.",
        ),
    ],
)
def test_a_bare_four_digit_figure_is_no_year(language, text, statement) -> None:
    """A limit, a count or an amount written bare is not compared with a cited year."""
    judged = Checker(passage(text, language=language)).atomic(statement, 1)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "In May 2024 the fee is 5 EUR. In June 2023 the fee was 3 EUR.",
            "In May 2023 the fee is 5 EUR.",
        ),
        (
            "de",
            "Im Mai 2024 beträgt die Gebühr 5 Euro. Im Juni 2023 betrug die Gebühr 3 Euro.",
            "Im Mai 2023 beträgt die Gebühr 5 Euro.",
        ),
        (
            "en",
            "Cards expire in 2026. Cards issued before 2020 expire in 2023.",
            "Cards expire in 2023.",
        ),
    ],
)
def test_a_year_after_a_month_or_a_year_preposition_is_still_a_swap(
    language, text, statement
) -> None:
    """The year context is a month name or a word of the language's year prepositions."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Hotline ist Montag–Freitag von 8 bis 20 Uhr erreichbar.",
            "Die Hotline ist Montag bis Freitag von 8 bis 20 Uhr erreichbar.",
        ),
        (
            "de",
            "Die Aktion läuft Januar–März.",
            "Die Aktion läuft von Januar bis März.",
        ),
        (
            "de",
            "Die Filiale ist an Sonn- und Feiertagen geschlossen.",
            "Die Filiale ist an Sonntagen und Feiertagen geschlossen.",
        ),
        (
            "de",
            "Die Filiale ist bis Montagabend geschlossen.",
            "Die Filiale ist bis Montag geschlossen.",
        ),
        (
            "de",
            "Die Filiale öffnet am Samstagvormittag.",
            "Die Filiale öffnet am Samstag.",
        ),
        (
            "en",
            "The hotline is open Monday–Friday from 8 to 8.",
            "The hotline is open Monday to Friday from 8 to 8.",
        ),
    ],
)
def test_a_name_inside_a_range_or_a_compound_of_the_cited_text_supports_the_plain_name(
    language, text, statement
) -> None:
    """The cited side reads Montag-Freitag, Samstagvormittag and Sonn- as the names they hold."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.validated, (judged.rejection_code, judged.units_added)


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Die Filiale ist montags geöffnet, so lange der Vorrat reicht.",
            "Die Filiale ist montags und sonntags geöffnet.",
        ),
        (
            "en",
            "The store is open on Mondays when the sun is out.",
            "The store is open on Sundays.",
        ),
    ],
)
def test_an_ordinary_word_spelled_like_an_abbreviation_supports_no_day(
    language, text, statement
) -> None:
    """An abbreviation counts only as the text writes one: capitalised, dotted or in a range."""
    judged = Checker(passage(text, language=language)).atomic(statement, 0)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, judged.units_added


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "de",
            "Kartenzahlungen sind ab 1000 möglich. Seit 2024 gilt das für alle Karten.",
            "Kartenzahlungen ab 1000 gelten für alle Karten.",
        ),
        (
            "en",
            "Card payments are possible from 1000. Since 2024 this applies to all cards.",
            "Card payments from 1000 apply to all cards.",
        ),
        (
            "de",
            "Überweisungen bis 2500 sind kostenlos. Seit 2023 gilt das auch online.",
            "Überweisungen bis 2500 sind auch online kostenlos.",
        ),
        (
            "en",
            "Transfers until 2500 are free. Since 2023 this also applies online.",
            "Transfers until 2500 are also free online.",
        ),
    ],
)
def test_a_limit_after_a_preposition_that_also_sets_limits_is_no_year(
    language, text, statement
) -> None:
    """From, until, ab and bis introduce an amount as often as a year."""
    judged = Checker(passage(text, language=language)).atomic(statement, 1)

    assert judged.validated, (judged.rejection_code, judged.units_added)


#: (language, the cited sentence, a statement re-pairing the digit runs of its clock times or dates)
_REPAIRED = [
    (
        "de",
        "Die Filiale ist von 9:30 bis 13:00 Uhr geöffnet.",
        "Die Filiale ist von 13:30 bis 9:00 Uhr geöffnet.",
    ),
    (
        "en",
        "The branch is open from 9:30 to 13:00.",
        "The branch is open from 13:30 to 9:00.",
    ),
    (
        "de",
        "Der Kundenservice ist zwischen 8:15 und 18:00 Uhr erreichbar.",
        "Der Kundenservice ist zwischen 8:00 und 18:15 Uhr erreichbar.",
    ),
    (
        "en",
        "Customer service answers calls between 8:15 and 18:00.",
        "Customer service answers calls between 8:00 and 18:15.",
    ),
    (
        "de",
        "Die Preisänderung gilt ab dem 01/12/2026.",
        "Die Preisänderung gilt ab dem 12/01/2026.",
    ),
    (
        "en",
        "The price change takes effect on 2026-12-01.",
        "The price change takes effect on 2026-01-12.",
    ),
    (
        "el",
        "Το κατάστημα είναι ανοιχτό από 9:30 έως 13:00.",
        "Το κατάστημα είναι ανοιχτό από 13:30 έως 9:00.",
    ),
]


@pytest.mark.parametrize(("lang", "text", "statement"), _REPAIRED)
def test_a_time_or_date_written_with_the_runs_of_cited_ones_in_another_order_is_refused(
    lang, text, statement
) -> None:
    """13:30 is not a time "from 9:30 to 13:00" writes: each figure is read whole."""
    fact = Checker(passage(text, language=lang)).atomic(statement, 0)
    assert fact.rejection_code == Rejection.UNSUPPORTED_ADDITION, fact.validation_error


def test_a_french_re_pairing_stays_refused() -> None:
    """A language no pipeline names is refused for its verb, as before."""
    fact = Checker(
        passage("L'agence est ouverte de 9:30 à 13:00.", language="fr")
    ).atomic("L'agence est ouverte de 13:30 à 9:00.", 0)
    assert not fact.validated


#: (language, the cited sentence, a statement writing its figures as they are, or one of them alone)
_KEPT = [
    ("de", "Die Filiale öffnet um 08:30 Uhr.", "Die Filiale öffnet um 8:30 Uhr."),
    ("en", "The shop opens at 08:30.", "The shop opens at 8:30."),
    (
        "de",
        "Das Bürgeramt ist von 9 bis 13:00 Uhr geöffnet.",
        "Das Bürgeramt öffnet um 9:00 Uhr.",
    ),
    (
        "en",
        "The office is open from 9 to 13:00.",
        "The office opens at 9:00.",
    ),
    (
        "de",
        "Das Bürgeramt ist montags bis freitags von 9:30 bis 13:00 Uhr geöffnet.",
        "Das Bürgeramt ist Mo–Fr 9:30–13:00 Uhr geöffnet.",
    ),
    (
        "en",
        "The shop is open on weekdays from 9:30 to 13:00.",
        "The shop is open 9:30-13:00 on weekdays.",
    ),
    (
        "en",
        "The shop is open on weekdays and opens at 9:30.",
        "The shop opens at 9:30.",
    ),
    (
        "de",
        "Die Filiale ist von 9:00–12:00 und 13:00–18:00 Uhr geöffnet.",
        "Die Mittagspause dauert von 12:00 bis 13:00 Uhr.",
    ),
    (
        "en",
        "The branch is open from 9:00–12:00 and 13:00–18:00.",
        "The branch closes for lunch from 12:00 to 13:00.",
    ),
    (
        "de",
        "Der Zeitraum läuft vom 01/03/2026 bis 31/03/2026.",
        "Der Zeitraum endet am 31/03/2026.",
    ),
    (
        "en",
        "The period runs from 01/03/2026 to 31/03/2026.",
        "The period ends on 31/03/2026.",
    ),
    (
        "de",
        "Die Hotline erreichen Sie unter 030-1234-5678.",
        "Die Hotline ist unter 030-1234-5678 erreichbar.",
    ),
    (
        "en",
        "Call our hotline on 030-1234-5678.",
        "The hotline number is 030-1234-5678.",
    ),
    (
        "de",
        "Das Paket ist zwischen 68 cm und 70 cm lang.",
        "Das Paket ist 68-70 cm lang.",
    ),
    (
        "en",
        "The parcel is between 68 cm and 70 cm long.",
        "The parcel is 68-70 cm long.",
    ),
    (
        "en",
        "The mix ratio of the paint is 2:1.",
        "The paint is mixed at a ratio of 2:1.",
    ),
    (
        "de",
        "Das Mischverhältnis beträgt 2:1.",
        "Das Mischverhältnis der Farbe beträgt 2:1.",
    ),
    (
        "de",
        "Die Gebühr ist in Abschnitt 3-2 geregelt.",
        "Abschnitt 3-2 regelt die Gebühr.",
    ),
    (
        "en",
        "The fee is set out in section 3-2.",
        "Section 3-2 sets out the fee.",
    ),
    (
        "en",
        "The portal is open from 9:30 to 13:00 and from 14:00 to 17:00.",
        "The portal is open from 14:00 to 17:00.",
    ),
]


@pytest.mark.parametrize(("lang", "text", "statement"), _KEPT)
def test_a_time_or_date_the_cited_text_writes_in_another_form_or_alone_validates(
    lang, text, statement
) -> None:
    """Padding, a shape the cited text lacks and a figure kept whole are no re-pairing."""
    fact = Checker(passage(text, language=lang)).atomic(statement, 0)
    assert fact.validated, (fact.rejection_code, fact.validation_error)
