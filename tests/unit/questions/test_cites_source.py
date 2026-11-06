"""What `cites_source` settles from a question's parse: a source named, in German and in English alike."""

from __future__ import annotations

import pytest

from question_generation.gates import cites_source

pytestmark = pytest.mark.nlp


# N-027: a product or tariff named with its year is no author and year.
@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Wie hoch ist die Jahresgebühr der Mastercard Gold 2025?", "de"),
        ("Gilt die Garantie auch für das Modell Berlin 2024?", "de"),
        ("What does the Mastercard Gold 2025 cost per year?", "en"),
        ("Which countries does the Euro 2024 travel insurance cover?", "en"),
        ("Is the Galaxy 2024 battery replaceable?", "en"),
        ("Que comprend le forfait Premium 2024?", "fr"),
        ("Τι περιλαμβάνει το πακέτο Premium 2024;", "el"),
    ],
)
def test_a_product_named_with_its_year_is_not_a_citation(question, language):
    """A proper noun and a bare year cite a source only where the noun is a person or an organisation."""
    assert cites_source(question, language) is not True


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Was schreibt Beck 2003 über Reviews?", "de"),
        ("What does Beck 2003 say about reviews?", "en"),
    ],
)
def test_an_author_and_year_is_still_one(question, language):
    """The control."""
    assert cites_source(question, language) is True


# Known limits of the author-and-year rule: it follows the tagger's entities.
def test_a_surname_the_german_tagger_gives_no_entity_is_left_to_the_judge():
    """No person or organisation entity, no citation here: the phrasing judge reads it."""
    assert cites_source("Was schlägt Müller 2003 vor?", "de") is None


def test_a_product_led_by_a_brand_the_english_tagger_calls_an_organisation_still_cites():
    """A product the tagger reads as an organisation is read as an author."""
    assert cites_source("What is the price of the Samsung Galaxy 2024?", "en") is True


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Was verlangt die Richtlinie 2019/1937 von einer Bank?", "de"),
        ("What does Regulation 2016/679 require of a shop?", "en"),
        ("Was fordert die Norm 20246 von einem Review?", "de"),
        ("Was regelt die Richtlinie 3b für Banken?", "de"),
        ("Was regelt das Rundschreiben 4a zur Meldung?", "de"),
        ("What does Regulation 2a require?", "en"),
        ("Was beschreibt die Norm 29119-4?", "de"),
        ("What does Standard 29119-4 describe?", "en"),
        ("What does Directive 2011/83/EU require of online traders?", "en"),
    ],
)
def test_a_numbered_standard_is_still_a_source(question, language):
    """The controls: an identifier after a document noun."""
    assert cites_source(question, language) is True


# N-047: `laut` is an attribution as a preposition and no other word.
@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Wie laut ist der Staubsauger X5 im Eco-Modus?", "de"),
        ("Wie laut ist die Wärmepumpe WP 300 im Nachtbetrieb?", "de"),
        ("Wie laut ist das Modell 2024 bei voller Leistung?", "de"),
        ("Wie laut darf Musik ab 22 Uhr sein?", "de"),
        ("Wie laut im Vergleich zu X4 ist der Staubsauger X5?", "de"),
        ("How loud is the X5 vacuum cleaner in eco mode?", "en"),
        ("Quel est le niveau sonore de l'aspirateur X5?", "fr"),
        ("Πόσο θορυβώδης είναι η ηλεκτρική σκούπα X5;", "el"),
    ],
)
def test_a_question_about_loudness_cites_no_source(question, language):
    """The adjective `laut` attributes to nothing."""
    assert cites_source(question, language) is not True


def test_the_preposition_still_attributes():
    """The control."""
    assert (
        cites_source("Was kostet die Karte laut Preisverzeichnis 2026?", "de") is True
    )


# N-054: the tables of documents and attributions hold both languages alike.
_PAIRS = [
    (
        "Was verlangt die Richtlinie 2011/83/EU von Online-Händlern?",
        "What does Directive 2011/83/EU require of online traders?",
    ),
    (
        "Was sagt diese Richtlinie über Rückgaben?",
        "What does this directive say about returns?",
    ),
    (
        "Was empfiehlt dieser Leitfaden für die Rückgabe von Waren?",
        "What does this guide recommend for returning goods?",
    ),
    (
        "Was regelt diese Spezifikation für die Schnittstelle?",
        "What does this specification define for the interface?",
    ),
    (
        "Wie lang ist gemäß der Vereinbarung die Kündigungsfrist?",
        "In accordance with the agreement, how long is the notice period?",
    ),
    (
        "Wie lange gilt laut dem Handbuch die gesetzliche Gewährleistung?",
        "According to the manual, how long does the legal guarantee last?",
    ),
]


@pytest.mark.parametrize(("german", "english"), _PAIRS)
def test_a_question_cites_its_source_alike_in_german_and_english(german, english):
    """A word a document is named by has its counterpart in the other language's table."""
    assert cites_source(german, "de") == cites_source(english, "en")


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Que prévoit la directive 2011/83/UE pour les vendeurs en ligne ?", "fr"),
        ("Τι απαιτεί η οδηγία 2011/83/ΕΕ από τους εμπόρους;", "el"),
    ],
)
def test_an_unconfigured_language_stays_inert(question, language):
    """No table row, no reading."""
    assert cites_source(question, language) is None


@pytest.mark.parametrize(
    ("question", "language"), [("Gebühren Kapitel 5", "de"), ("fees chapter 5", "en")]
)
def test_a_numbered_division_closing_a_search_query_is_a_citation(question, language):
    """With no question mark after it, the number is the query's last token."""
    assert cites_source(question, language) is True


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Wie hoch ist laut Northbank die Gebühr?", "de"),
        ("What is the fee according to Northbank?", "en"),
    ],
)
def test_an_attribution_to_the_name_right_after_it_is_a_citation(question, language):
    """`laut Northbank`: the name is the very next token, and it is attributed to."""
    assert cites_source(question, language) is True


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Welche Frist nennt der Text des Artikels 5?", "de"),
        ("Which deadline does Article 5 set?", "en"),
    ],
)
def test_a_numbered_rule_in_any_case_is_what_the_question_is_about(question, language):
    """`des Artikels 5` is the genitive of `Artikel`: read by its lemma, it is a subject."""
    assert cites_source(question, language) is False


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("How often must staff report 2 or more failed logins?", "en"),
        ("Must the branch report 5 suspicious transfers to the police?", "en"),
        ("Wann muss die Filiale 3 Vorfälle melden?", "de"),
        ("Quelle commission fixe la directive 2015/2366 ?", "fr"),
        ("Ποια χρέωση ορίζει η οδηγία 2015/2366;", "el"),
    ],
)
def test_a_lower_case_verb_spelled_like_a_document_settles_nothing(question, language):
    """`report 2 or more` is an action with a count, not a report numbered 2."""
    assert cites_source(question, language) is None
