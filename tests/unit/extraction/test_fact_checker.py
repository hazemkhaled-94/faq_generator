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
    """Evidence that is already one claim is the fact; restating two is not."""
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
    assert restated.rejection_code == Rejection.COPIED, restated.validation_error


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
        "Customers may return goods within 30 days, but refunds are paid only to "
        "the original card.",
        "Customers may return goods within 30 days, but refunds are only paid to "
        "the original card.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        "Kunden können Waren innerhalb von 30 Tagen zurückgeben, aber die "
        "Erstattung erfolgt nur auf die ursprüngliche Karte.",
        "Kunden können Waren binnen 30 Tagen zurückgeben, aber die Erstattung "
        "erfolgt nur auf die ursprüngliche Karte.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        "The card is free in the first year, but a fee of 30 EUR is charged from "
        "the second year.",
        "The card is free of charge in the first year, but a fee of 30 EUR is "
        "charged from the second year.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        "Die Karte ist im ersten Jahr kostenlos, jedoch wird ab dem zweiten Jahr "
        "eine Gebühr von 30 EUR berechnet.",
        "Die Karte ist im ersten Jahr gebührenfrei, jedoch wird ab dem zweiten "
        "Jahr eine Gebühr von 30 EUR berechnet.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        "If the card is lost, the bank blocks it and the customer is liable for up "
        "to 50 EUR.",
        "If the card is lost, the bank blocks the card and the customer is liable "
        "for up to 50 EUR.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "de",
        "Die Bank erstattet die Gebühr, wenn die Beschwerde berechtigt ist, und "
        "kündigt das Konto.",
        "Die Bank erstattet die Gebühr, wenn die Beschwerde berechtigt ist, und "
        "kündigt das Konto des Kunden.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    (
        "en",
        "The current account costs 5 EUR a month. It is free if at least 1,000 EUR "
        "is paid in each month.",
        "It is free of charge if at least 1,000 EUR is paid in each month.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "de",
        "Das Girokonto kostet 5 EUR im Monat. Es ist kostenlos, wenn monatlich "
        "mindestens 1.000 EUR eingehen.",
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
        "Das Geschenkpaket wird separat verkauft. Es ist kostenlos, wenn die "
        "Bestellung über 50 EUR liegt.",
        "Es ist gratis, wenn die Bestellung über 50 EUR liegt.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "en",
        "Credit cards have a daily limit of 1,000 EUR. Debit cards can be blocked "
        "abroad.",
        "Debit cards with a daily limit of 1,000 EUR can be blocked abroad.",
        1,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "de",
        "Für Kreditkarten gilt ein Tageslimit von 1.000 EUR. Debitkarten können im "
        "Ausland gesperrt werden.",
        "Debitkarten mit einem Tageslimit von 1.000 EUR können im Ausland gesperrt "
        "werden.",
        1,
        Rejection.UNSUPPORTED_ADDITION,
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


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "Payments are checked daily. It is an offence if the PIN is shared.",
            "It is an offence if the PIN is shared.",
        ),
        (
            "de",
            "Zahlungen werden täglich geprüft. Es ist ein Verstoß, wenn die PIN "
            "weitergegeben wird.",
            "Es ist ein Verstoß, wenn die PIN weitergegeben wird.",
        ),
    ],
)
def test_it_standing_for_the_condition_after_it_is_no_reference(
    language, text, statement
) -> None:
    """Nothing the passage said before agrees with `it`: the condition is the offence."""
    judged = Checker(passage(text, language=language)).atomic(statement, 1)

    assert judged.validated, judged.validation_error
    assert not judged.unresolved_references


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
        ("The card is blocked if this is reported stolen.", "en"),
        ("Geht die Karte verloren, sperrt die Bank sie sofort.", "de"),
        ("The card is replaced free of charge for a customer losing it abroad.", "en"),
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

    def test_a_unit_from_the_uncited_sentence_is_an_addition(self, spaced) -> None:
        """The defect this is all for.

        `unsupported_addition` is what says nothing was invented. Judged
        against the covering range it would accept 99 from a sentence the
        claim never cited.
        """
        borrowed = spaced.atomic("The device costs 99 euro.", (0, 2))

        assert borrowed.rejection_code == Rejection.UNSUPPORTED_ADDITION
        assert "99" in borrowed.units_added


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


def test_each_failure_reaches_its_own_code(checker, offered) -> None:
    """Every rejection code the checks can emit, and no bucket shared."""
    codes = {
        checker.atomic("Anything.", 7).rejection_code,
        checker.atomic("The device weighs 4 kg and runs for 12 hours.").rejection_code,
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


@pytest.mark.parametrize(
    ("language", "text", "statement"),
    [
        (
            "en",
            "Visa Debit cards are issued to students. The card is free of charge.",
            "The Visa Debit card is free of charge.",
        ),
        (
            "de",
            "Die Nordbank führt Girokonten für Studenten. Die Kontoführung ist "
            "kostenlos.",
            "Bei der Nordbank ist die Kontoführung kostenlos.",
        ),
    ],
)
def test_a_name_the_sentence_before_carries_is_no_addition(
    language, text, statement
) -> None:
    """The sentence before names what the cited one calls "the card"."""
    judged = Checker(passage(text, language=language)).atomic(statement, 1)

    assert judged.validated, (judged.validation_error, judged.units_added)


def test_a_name_from_an_uncited_sentence_is_still_an_addition() -> None:
    """Named in a sentence after the one cited is not said by it."""
    read = passage(
        "The fee applies to all cards. Mastercard holders receive a monthly statement."
    )

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


def test_a_lead_in_figure_is_supported_only_when_cited() -> None:
    """A figure restated from a lead-in is the lead-in's to support."""
    read = passage(
        "Orders over EUR 50 are delivered free. Delivery to Austria takes two days."
    )
    statement = "Orders over EUR 50 are delivered free to Austria."

    alone = Checker(read).atomic(statement, 1)
    with_lead_in = Checker(read).atomic(statement, (0, 1))

    assert alone.rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert with_lead_in.validated, with_lead_in.validation_error


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
