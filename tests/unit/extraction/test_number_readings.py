"""How a fact's numbers are read: formats, words and pronouns (llm-nlp-7 ...)."""

import pytest
from drivers import Checker, passage

from nlp.analysis import figures, numbers


def ok(lang, text, fact=None):
    """The fact check's verdict on one statement against one passage."""
    f = Checker(passage(text, language=lang)).atomic(fact or text)
    return f.validated, f.rejection_code, f.validation_error


def must_validate(lang, text, fact=None):
    """Asserts the statement is accepted."""
    v, code, err = ok(lang, text, fact)
    assert v, f"refused {code}: {err} | {fact or text}"


def must_refuse(lang, text, fact):
    """Asserts the statement is refused."""
    v, _, _ = ok(lang, text, fact)
    assert not v, f"validated a changed figure: {fact}"


FORMATS = [
    (
        "en",
        "The daily withdrawal limit is 1,000 EUR.",
        "The daily withdrawal limit is 1000 EUR.",
    ),
    (
        "en",
        "The daily withdrawal limit is 1000 EUR.",
        "The daily withdrawal limit is 1,000 EUR.",
    ),
    ("en", "Shipping costs 5.00 EUR.", "Shipping costs 5 EUR."),
    ("en", "The fee is 2.50%.", "The fee is 2.5%."),
    (
        "de",
        "Das tägliche Abhebelimit beträgt 1.000 Euro.",
        "Das tägliche Abhebelimit beträgt 1000 Euro.",
    ),
    ("de", "Der Versand kostet 4,90 Euro.", "Der Versand kostet 4,9 Euro."),
]


@pytest.mark.parametrize(("lang", "text", "fact"), FORMATS)
def test_the_same_value_in_another_format_validates(lang, text, fact):
    """One value written another way adds nothing."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "The daily withdrawal limit is 1,000 EUR.",
            "The daily withdrawal limit is 1,500 EUR.",
        ),
        ("de", "Der Versand kostet 4,90 Euro.", "Der Versand kostet 4,99 Euro."),
        (
            "de",
            "Das tägliche Abhebelimit beträgt 1.000 Euro.",
            "Das tägliche Abhebelimit beträgt 1.500 Euro.",
        ),
        ("en", "Shipping costs 5.00 EUR.", "Shipping costs 5.50 EUR."),
    ],
)
def test_a_changed_value_is_still_refused(lang, text, fact):
    """A different value is an addition in any format."""
    must_refuse(lang, text, fact)


def test_the_dedup_reads_one_value_in_two_formats_as_one():
    """The dedup compares values, not spellings."""
    assert numbers("limit 1,000 EUR", "en") == numbers("limit 1000 EUR", "en")
    assert numbers("Versand 4,90 Euro", "de") == numbers("Versand 4,9 Euro", "de")
    assert numbers("limit 1,500 EUR", "en") != numbers("limit 1,000 EUR", "en")


WORDS = [
    (
        "en",
        "You can return items within thirty days of delivery.",
        "Items can be returned within 30 days of delivery.",
    ),
    (
        "en",
        "Items can be returned within 30 days of delivery.",
        "You can return items within thirty days of delivery.",
    ),
    (
        "en",
        "The limit is twenty thousand euros per day.",
        "The limit is 20000 euros per day.",
    ),
    (
        "en",
        "The account fee is twenty-five euros per year.",
        "The account fee is 25 euros per year.",
    ),
    (
        "en",
        "The shop sends one hundred twenty-five parcels a day.",
        "The shop sends 125 parcels a day.",
    ),
    (
        "de",
        "Sie können Waren innerhalb von dreißig Tagen zurückgeben.",
        "Waren können innerhalb von 30 Tagen zurückgegeben werden.",
    ),
    ("de", "Die Gebühr beträgt zwanzig Euro.", "Die Gebühr beträgt 20 Euro."),
    ("de", "Die Gebühr beträgt fünfundzwanzig Euro.", "Die Gebühr beträgt 25 Euro."),
    (
        "de",
        "Die Bank prüft zweihundert Konten pro Tag.",
        "Die Bank prüft 200 Konten pro Tag.",
    ),
]


@pytest.mark.parametrize(("lang", "text", "fact"), WORDS)
def test_a_count_in_words_above_twelve_validates(lang, text, fact):
    """A count past twelve written out is the count in digits."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "The account fee is twenty-five euros per year.",
            "The account fee is 35 euros per year.",
        ),
        (
            "de",
            "Die Gebühr beträgt fünfundzwanzig Euro.",
            "Die Gebühr beträgt 52 Euro.",
        ),
    ],
)
def test_a_wrong_count_past_twelve_is_still_refused(lang, text, fact):
    """A different number is an addition however it is written."""
    must_refuse(lang, text, fact)


def test_the_dedup_reads_a_count_in_words_as_its_digits():
    """The dedup compares values, whether digits or words."""
    assert numbers("within thirty days", "en") == numbers("within 30 days", "en")
    assert numbers("dreißig Tage", "de") == numbers("30 Tage", "de")
    assert numbers("twenty thousand euros", "en") == numbers("20000 euros", "en")
    assert numbers("zweitausend Euro", "de") == numbers("2000 Euro", "de")
    assert numbers("das Jahrhundert", "de") == ()


PRONOUN = [
    (
        "Customers may withdraw at most 500 EUR per day.",
        "No one may withdraw more than 500 EUR per day.",
    ),
    (
        "The shop refunds the purchase price within 30 days.",
        "The one you bought can be returned within 30 days.",
    ),
    (
        "Customers may open a savings account for 12 months.",
        "No one may close a savings account within 12 months.",
    ),
]


@pytest.mark.parametrize(("text", "fact"), PRONOUN)
def test_one_as_a_pronoun_is_no_number(text, fact):
    """`one` of "no one" or "the one you bought" asserts no count."""
    _, code, err = ok("en", text, fact)
    assert "asserts one" not in str(err), f"{code}: {err}"


@pytest.mark.parametrize(
    ("text", "fact"),
    [
        ("Each account comes with 2 cards.", "Each account comes with one card."),
        ("Each account may hold 3 cards.", "Only one card per account is allowed."),
    ],
)
def test_one_as_a_number_is_still_checked(text, fact):
    """A numeral `one` is a count and a wrong one is refused."""
    must_refuse("en", text, fact)


def test_one_card_per_account_is_still_read_as_one():
    """The numeral reading of `one` survives."""
    must_validate("en", "Each account holds 1 card.", "Each account holds one card.")


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "de",
            "Ihr Geld ist bis zu 100 000 Euro geschützt.",
            "Ihr Geld ist bis zu 100.000 Euro geschützt.",
        ),
        (
            "en",
            "Deposits are protected up to EUR 100,000.",
            "Deposits are protected up to EUR 100 000.",
        ),
    ],
)
def test_a_space_grouped_amount_is_one_value_in_the_fact_check(lang, text, fact):
    """One amount written two ways adds nothing; `numbers` reads it as one."""
    must_validate(lang, text, fact)
    assert numbers(fact, lang) == numbers(text, lang)


def test_a_reference_and_a_figure_are_not_one_grouped_number():
    """A heading number and a figure after it stay two."""
    assert numbers("Artikel 3 Absatz 12 gilt.", "de") == ("12", "3")


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "Under Section 3 100 customers were refunded.",
            "Under Section 3, 100 customers were refunded.",
        ),
        (
            "de",
            "Laut Abschnitt 2 300 Euro werden erstattet.",
            "Laut Abschnitt 2 werden 300 Euro erstattet.",
        ),
    ],
)
def test_a_reference_then_a_figure_still_validates(lang, text, fact):
    """A reference label before a space-grouped run keeps its two numbers."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("Fees by tier: 100 200 300 GBP.", "en", [100.0, 200.0, 300.0]),
        ("Gebühren je Stufe 10 250 500 Euro.", "de", [10.0, 250.0, 500.0]),
        ("Rufen Sie 030 123 456 an.", "de", [30.0, 123.0, 456.0]),
        ("Deposits up to 1 299,99 EUR.", "en", [1299.99]),
    ],
)
def test_a_row_of_figures_is_not_one_grouped_number(text, lang, expected):
    """A flattened table row or a phone number is not thousands."""
    assert sorted(figures(text, lang)) == sorted(expected)


def test_a_language_without_amount_words_reads_no_grouped_number():
    """`fr` is read by the English model, and still groups nothing."""
    assert numbers("Codes 100 200 300 EUR", "fr") == ("100", "200", "300")


# C-020: an atomic fact rests on its passage, so a spelled count another sentence
# of the passage gives is supported, unless the cited sentence gives another count
# of the same kind: that is a swap, refused (test_fact_checker.py).
@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "de",
            "Es gibt vier Kontomodelle. Das Basiskonto kostet 5 Euro im Monat.",
            "Das Basiskonto kostet 5 Euro im Monat bei vier Kontomodellen.",
        ),
        (
            "en",
            "There are four account models. The basic account costs 5 euros a month.",
            "The basic account costs 5 euros a month across four account models.",
        ),
        (
            "en",
            "Parcels are sent in three boxes. Delivery takes 5 working days.",
            "Delivery of three boxes takes 5 working days.",
        ),
    ],
)
def test_a_spelled_count_another_sentence_of_the_passage_gives_is_supported(
    lang, text, fact
):
    """A count in words is read against the passage, as every figure is."""
    f = Checker(passage(text, language=lang)).atomic(fact, 1)
    assert f.validated, f"refused a count the passage gives: {fact!r}"


# VAR-one-same-price: a bare 'one' that is a count.
@pytest.mark.parametrize(
    ("text", "fact"),
    [
        (
            "Each customer may hold at most two cards.",
            "Each customer may hold at most one.",
        ),
        ("Only two are allowed per household.", "Only one is allowed per household."),
        ("The limit is three per customer.", "The limit is one per customer."),
    ],
)
def test_a_wrong_bare_one_is_still_refused(text, fact):
    """A bare `one` that is a count is still checked."""
    v, _, _ = ok("en", text, fact)
    assert not v, f"validated a changed count: {fact!r}"


# Lead replay ids 11368, 11962 (0defee49): German count words newly read as units.
def test_a_german_count_restating_a_multiplicative_adverb_validates():
    """`zwei Mahnungen` restates `zweimal gemahnt` (shape of fact 11368)."""
    v, code, err = ok(
        "de",
        "Ein Kunde, der zweimal gemahnt wird, zahlt eine Gebühr.",
        "Ein Kunde mit zwei Mahnungen zahlt eine Gebühr.",
    )
    assert v, f"refused {code}: {err}"


def test_a_german_ordinal_stated_earlier_in_the_passage_validates():
    """`ersten fünf` is stated in the uncited sentence before (shape of fact 11962)."""
    f = Checker(
        passage(
            "Die ersten fünf Bestellungen sind versandkostenfrei. Danach darf der Kunde die Versandart ändern.",
            language="de",
        )
    ).atomic(
        "Nach den ersten fünf Bestellungen darf der Kunde die Versandart ändern.", 1
    )
    v, code, err = f.validated, f.rejection_code, f.validation_error
    assert v, f"refused {code}: {err}"


def test_a_german_amount_closing_a_sentence_is_one_number():
    """`EUR 2 500.` ends a sentence: the tokenizer keeps `500.`, so the merge misses it."""
    text = "Die Gebühr beträgt EUR 2 500."
    assert numbers(text, "de") == ("2500",)
    assert figures(text, "de") == [2500.0]


def test_a_german_amount_closing_a_sentence_restated_with_a_mark_validates():
    """`EUR 2 500.` and `EUR 2.500.` are one amount."""
    f = Checker(passage("Die Gebühr beträgt EUR 2 500.", language="de")).atomic(
        "Die Gebühr beträgt EUR 2.500."
    )
    assert f.validated, f"refused {f.rejection_code}: {f.validation_error}"


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "The savings account pays 2½ % interest a year.",
            "The savings account pays 2¼ % interest a year.",
        ),
        (
            "de",
            "Das Sparkonto bringt 2½ % Zinsen pro Jahr.",
            "Das Sparkonto bringt 2¼ % Zinsen pro Jahr.",
        ),
        (
            "en",
            "Express delivery takes 1½ days.",
            "Express delivery takes 1¾ days.",
        ),
    ],
)
def test_another_fraction_is_refused(lang, text, fact):
    """The fraction is part of the figure the passage states."""
    must_refuse(lang, text, fact)


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "The savings account pays 2½ % interest a year."),
        ("de", "Das Sparkonto bringt 2½ % Zinsen pro Jahr."),
    ],
)
def test_a_statement_keeping_its_fraction_validates(lang, text):
    """The restated figure is the cited one."""
    must_validate(lang, text)


@pytest.mark.parametrize(
    ("lang", "text", "twin"),
    [
        ("en", "Express delivery takes 1½ days.", "Express delivery takes 1¾ days."),
        ("de", "Die Lieferung dauert 1½ Tage.", "Die Lieferung dauert 1¾ Tage."),
        ("fr", "La livraison prend 1½ jours.", "La livraison prend 1¾ jours."),
        ("el", "Η παράδοση διαρκεί 1½ ημέρες.", "Η παράδοση διαρκεί 1¾ ημέρες."),
    ],
)
def test_another_fraction_is_another_number_for_the_dedup_gate(lang, text, twin):
    """The two fractions are two numbers, so the statements are no twins."""
    from extraction.service import _counted_alike

    assert not _counted_alike(text, twin, lang)


#: Two statements that give one figure another unit, month, weekday or place.
_DIFFERENT_FIGURES = [
    (
        "de",
        "Die neuen Kontogebühren gelten ab dem 1. Januar 2026.",
        "Die neuen Kontogebühren gelten ab dem 1. Juli 2026.",
    ),
    (
        "en",
        "The new account fees apply from 1 January 2026.",
        "The new account fees apply from 1 July 2026.",
    ),
    (
        "de",
        "Das Bürgeramt ist montags geöffnet.",
        "Das Bürgeramt ist dienstags geöffnet.",
    ),
    ("en", "The office opens on Mondays.", "The office opens on Tuesdays."),
    (
        "de",
        "Die Rückgabefrist beträgt 14 Tage.",
        "Die Rückgabefrist beträgt 14 Wochen.",
    ),
    ("en", "The return period is 14 days.", "The return period is 14 weeks."),
    (
        "de",
        "Der Antrag wird innerhalb von 3 Wochen bearbeitet.",
        "Der Antrag wird innerhalb von 3 Monaten bearbeitet.",
    ),
    (
        "en",
        "The application is processed within 3 weeks.",
        "The application is processed within 3 months.",
    ),
    ("de", "Ein Paket darf bis zu 2 kg wiegen.", "Ein Paket darf bis zu 2 g wiegen."),
    (
        "en",
        "A parcel may weigh up to 2 kg.",
        "A parcel may weigh up to 2 g.",
    ),
    (
        "de",
        "Der Zinssatz beträgt 3 % für 12 Monate.",
        "Der Zinssatz beträgt 12 % für 3 Monate.",
    ),
    (
        "en",
        "The interest rate is 3 % for 12 months.",
        "The interest rate is 12 % for 3 months.",
    ),
    (
        "de",
        "Die Verwaltungsgebühr beträgt 2 %.",
        "Die Verwaltungsgebühr beträgt 2 Euro.",
    ),
    ("en", "The administration fee is 2 %.", "The administration fee is 2 euros."),
]


@pytest.mark.parametrize(("lang", "text", "twin"), _DIFFERENT_FIGURES)
def test_a_figure_of_another_unit_month_or_place_is_no_twin_for_the_dedup_gate(
    lang, text, twin
):
    """The unit, the month and the pairing a figure is written with are part of it."""
    from extraction.service import _counted_alike

    assert not _counted_alike(text, twin, lang)
    assert not _counted_alike(twin, text, lang)


@pytest.mark.parametrize(
    ("lang", "text", "twin"), [_DIFFERENT_FIGURES[i] for i in (0, 1, 4, 5, 10, 11)]
)
def test_the_probed_twin_of_another_figure_is_dropped(lang, text, twin):
    """Through `_closest`, a near fact of another figure is no twin at any cosine."""
    from database.qa_generator import FactKind
    from extraction.models import Twin
    from extraction.service import _closest

    probed = Twin(fact_id=7, statement=twin, similarity=0.999)
    assert _closest(text, FactKind.ATOMIC, lang, [1.0, 0.0], probed, []) is None
    kept = [(twin, FactKind.ATOMIC, [1.0, 0.0], 8)]
    assert _closest(text, FactKind.ATOMIC, lang, [1.0, 0.0], None, kept) is None


#: Two statements that write one figure in another spelling.
_RESTATEMENTS = [
    ("de", "Die Gebühr beträgt 5 Euro.", "Die Gebühr beträgt 5 €."),
    ("en", "The fee is EUR 5.", "The fee is 5 euros."),
    ("de", "Die Gebühr beträgt EUR 5.", "Die Gebühr beträgt 5 Euro."),
    ("de", "Der Zuschlag beträgt 3 Prozent.", "Der Zuschlag beträgt 3 %."),
    ("en", "The surcharge is 3 percent.", "The surcharge is 3 %."),
    (
        "de",
        "Eine Rückgabe ist innerhalb von 14 Tagen möglich.",
        "Eine Rückgabe ist innerhalb von 14 Kalendertagen möglich.",
    ),
    (
        "de",
        "Ein Antrag wird innerhalb von 14 Tagen bearbeitet.",
        "Ein Antrag wird innerhalb von vierzehn Tagen bearbeitet.",
    ),
    (
        "en",
        "The loan runs for 12 months.",
        "The loan runs for a 12-month term.",
    ),
    (
        "en",
        "Returns are accepted within 30 days.",
        "A 30-day return window applies.",
    ),
    (
        "de",
        "Ein Paket wiegt höchstens 2 kg.",
        "Ein Paket wiegt höchstens 2 Kilogramm.",
    ),
    (
        "en",
        "A parcel weighs at most 2 kg.",
        "A parcel weighs at most 2 kilograms.",
    ),
    (
        "en",
        "The interest rate is 3 % for 12 months.",
        "For 12 months the interest rate is 3 %.",
    ),
    (
        "de",
        "Die Gebühren gelten ab dem 1. Januar 2026.",
        "Ab 1. Januar 2026 gelten die Gebühren.",
    ),
    ("en", "Fees apply from 1 January 2026.", "Fees apply from January 1, 2026."),
    (
        "de",
        "Das Bürgeramt ist montags geöffnet.",
        "Das Bürgeramt hat am Montag geöffnet.",
    ),
    ("en", "The office opens on Mondays.", "The office opens on Monday."),
    (
        "de",
        "Die neuen Kontogebühren gelten ab Montag, dem 1. Juni 2026.",
        "Die neuen Kontogebühren gelten ab dem 1. Juni 2026.",
    ),
    (
        "de",
        "Der Antrag auf Wohngeld muss bis Freitag, den 31. Juli 2026, eingereicht werden.",
        "Der Antrag auf Wohngeld muss bis zum 31. Juli 2026 eingereicht werden.",
    ),
    (
        "de",
        "Die Filiale ist von Montag bis Freitag von 9 bis 18 Uhr geöffnet.",
        "Die Filiale ist von Montag, Dienstag, Mittwoch, Donnerstag und Freitag von 9 bis 18 Uhr geöffnet.",
    ),
    (
        "de",
        "Die Gebühr gilt von Januar bis März 2026.",
        "Die Gebühr gilt im Januar, Februar und März 2026.",
    ),
    (
        "en",
        "The new account fees apply from Monday, 1 June 2026.",
        "The new account fees apply from 1 June 2026.",
    ),
    (
        "en",
        "The tax return is due by Friday 31 July 2026.",
        "The tax return is due by 31 July 2026.",
    ),
    (
        "en",
        "The branch is open Monday to Friday from 9 to 18.",
        "The branch is open Monday, Tuesday, Wednesday, Thursday and Friday from 9 to 18.",
    ),
    (
        "en",
        "The fee applies from January to March 2026.",
        "The fee applies in January, February and March 2026.",
    ),
    (
        "en",
        "The branch is open from 9:30 to 13:00.",
        "The branch is open from 9:30 until 13:00.",
    ),
    (
        "en",
        "The bank capped the waiting list at 25 applicants again.",
        "The bank capped the waiting list at 25 again.",
    ),
]


@pytest.mark.parametrize(("lang", "text", "twin"), _RESTATEMENTS)
def test_a_figure_written_another_way_stays_a_twin_for_the_dedup_gate(lang, text, twin):
    """A reading the other side lacks, or an open noun, never tells two figures apart."""
    from extraction.service import _counted_alike

    assert _counted_alike(text, twin, lang)
    assert _counted_alike(twin, text, lang)


@pytest.mark.parametrize(
    ("lang", "text", "twin"),
    [
        (
            "fr",
            "Les nouveaux frais s'appliquent à partir du 1er janvier 2026.",
            "Les nouveaux frais s'appliquent à partir du 1er juillet 2026.",
        ),
        (
            "fr",
            "Le délai de retour est de 14 jours.",
            "Le délai de retour est de 14 semaines.",
        ),
        (
            "fr",
            "Le taux d'intérêt est de 3 % pour 12 mois.",
            "Le taux d'intérêt est de 12 % pour 3 mois.",
        ),
        (
            "pl",
            "Termin zwrotu wynosi 14 dni.",
            "Termin zwrotu wynosi 14 tygodni.",
        ),
        (
            "pl",
            "Nowe opłaty obowiązują od 1 stycznia 2026.",
            "Nowe opłaty obowiązują od 1 lipca 2026.",
        ),
        (
            "el",
            "Τα νέα τέλη ισχύουν από την 1η Ιανουαρίου 2026.",
            "Τα νέα τέλη ισχύουν από την 1η Ιουλίου 2026.",
        ),
        (
            "el",
            "Η προθεσμία επιστροφής είναι 14 ημέρες.",
            "Η προθεσμία επιστροφής είναι 14 εβδομάδες.",
        ),
    ],
)
def test_a_language_without_month_and_unit_words_reads_as_before(lang, text, twin):
    """No table names a month or a time unit there, so the cosine decides alone, as it did."""
    from extraction.service import _counted_alike

    assert _counted_alike(text, twin, lang)


#: Restatements whose figure the language writes before another noun, as a range or with a
#: sign, so that the one side reads a period and the other only a unit of time.
_WRITTEN_ANOTHER_WAY = [
    ("de", "Sie haben 14 Tage Rückgaberecht.", "Das Rückgaberecht beträgt 14 Tage."),
    (
        "de",
        "Auf alle Geräte gibt es 24 Monate Garantie.",
        "Die Garantie auf alle Geräte beträgt 24 Monate.",
    ),
    (
        "de",
        "Der Kredit hat 48 Monate Laufzeit.",
        "Die Laufzeit des Kredits beträgt 48 Monate.",
    ),
    ("de", "Es gilt ein Zahlungsziel von 30 Tagen.", "Sie haben 30 Tage Zahlungsziel."),
    ("de", "Die Lieferzeit beträgt 6 Wochen.", "Rechnen Sie mit 6 Wochen Lieferzeit."),
    ("de", "Die Lieferung dauert 3 bis 5 Tage.", "Die Lieferung dauert 3–5 Tage."),
    ("de", "Pakete bis 1 bis 2 kg kosten 5 Euro.", "Pakete von 1–2 kg kosten 5 Euro."),
    (
        "de",
        "Die Bearbeitung dauert etwa 3 Wochen.",
        "Die Bearbeitung dauert ~3 Wochen.",
    ),
    (
        "en",
        "You get 24 months warranty on all devices.",
        "The warranty on all devices is 24 months.",
    ),
    ("en", "You have 14 days return right.", "The right of return is 14 days."),
    ("en", "Delivery takes 3-5 days.", "Delivery takes 3–5 days."),
    ("en", "Processing takes 4 to 6 weeks.", "Processing takes 4–6 weeks."),
    ("en", "The loan has a 48 months term.", "The term of the loan is 48 months."),
    ("en", "Parcels of 1-2 kg cost EUR 5.", "Parcels of 1–2 kg cost EUR 5."),
    (
        "de",
        "Ein Kredit über 10.000 Euro hat 12 Monate Laufzeit.",
        "Ein Kredit von 10.000 Euro läuft 12 Monate.",
    ),
    (
        "de",
        "Auf alle Geräte gibt es 2 Jahre Garantie.",
        "Die Garantie auf alle Geräte beträgt 2 Jahre.",
    ),
    (
        "de",
        "Der Vertrag hat 24 Monate Mindestlaufzeit.",
        "Die Mindestlaufzeit des Vertrags beträgt 24 Monate.",
    ),
    (
        "de",
        "Für Neukunden gelten 6 Monate Zinsgarantie.",
        "Neukunden erhalten eine Zinsgarantie für 6 Monate.",
    ),
    (
        "de",
        "Der Antrag hat 3 Wochen Bearbeitungszeit.",
        "Die Bearbeitung des Antrags dauert 3 Wochen.",
    ),
    (
        "de",
        "Es gilt eine Frist von 30 Tagen ab Zugang.",
        "Die Frist beträgt 30 Tage ab Zugang.",
    ),
    (
        "en",
        "We offer 30 days money-back guarantee.",
        "Our money-back guarantee lasts 30 days.",
    ),
    (
        "en",
        "All devices come with 2 years warranty.",
        "The warranty on all devices is 2 years.",
    ),
    (
        "en",
        "Standard delivery takes 3 days.",
        "Standard delivery has 3 days lead time.",
    ),
    (
        "en",
        "The account has 12 months notice period.",
        "The notice period of the account is 12 months.",
    ),
    (
        "en",
        "Applications need 4 weeks processing time.",
        "Processing an application takes 4 weeks.",
    ),
    ("en", "Passports take 6 weeks processing.", "Passport processing takes 6 weeks."),
    (
        "en",
        "The loan of 5,000 euros has 12 months term.",
        "The loan of 5,000 euros runs for 12 months.",
    ),
    ("en", "Shipping costs 5 euros per parcel.", "Shipping costs 5 euros."),
    ("de", "Der Versand kostet 5 Euro pro Paket.", "Der Versand kostet 5 Euro."),
    ("en", "The fee is 2 % per transaction.", "Each transaction costs a 2 % fee."),
    (
        "de",
        "Ein Paket mit 2 kg Gewicht kostet 5 Euro.",
        "Ein Paket von 2 kg kostet 5 Euro.",
    ),
    ("en", "A 2 kg parcel costs 5 euros.", "A parcel of 2 kg weight costs 5 euros."),
    ("de", "Passbilder müssen 45 mm Höhe haben.", "Passbilder müssen 45 mm hoch sein."),
]


@pytest.mark.parametrize(("lang", "text", "twin"), _WRITTEN_ANOTHER_WAY)
def test_a_period_written_before_another_noun_or_as_a_range_stays_a_twin(
    lang, text, twin
):
    """A reading one side lacks, a kind as well as a unit, tells nothing."""
    from extraction.service import _counted_alike

    assert _counted_alike(text, twin, lang)
    assert _counted_alike(twin, text, lang)
