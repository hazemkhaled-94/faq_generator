"""Mending a word a converter broke at a line, wherever the break is found.

Parsing mends each string it reads, and the table and page joins mend the
string they make, so a second pass over what is already whole has to
change nothing.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st


@pytest.mark.parametrize(
    ("broken", "whole"),
    [
        (
            "monatlich, inklusive Kontofüh- rungsentgelt",
            "monatlich, inklusive Kontoführungsentgelt",
        ),
        ("Zoll- und Steuerrecht", "Zoll- und Steuerrecht"),
        ("pre- and post-trade", "pre- and post-trade"),
    ],
)
def test_a_broken_word_is_joined_and_a_shared_suffix_kept(broken, whole) -> None:
    """The joining words of every configured language complete a hyphen."""
    from nlp.text import rejoined

    assert rejoined(broken) == whole


def test_a_compound_the_document_prints_whole_keeps_its_hyphen() -> None:
    """A shop's terms print "third-party" on one line and break it on another."""
    from nlp.text import printed, rejoined

    whole = printed(["Payments through a third-party provider are refunded."])

    assert rejoined("sent with a third- party courier", whole) == (
        "sent with a third-party courier"
    )
    assert rejoined("inklusive Kontofüh- rungsentgelt", whole) == (
        "inklusive Kontoführungsentgelt"
    )


@given(
    text=st.text(alphabet="aäbKZ- \n", max_size=40),
    seen=st.text(alphabet="aäbKZ- ", max_size=20),
)
def test_mending_twice_is_mending_once(text: str, seen: str) -> None:
    """A join mends a string already mended, and must leave the rest alone."""
    from nlp.text import printed, rejoined

    whole = printed([seen])
    once = rejoined(text, whole)

    assert rejoined(once, whole) == once


def test_held_and_holders_read_a_quote_per_passage() -> None:
    """A quote is held by the passages that carry every piece of it unbroken."""
    from nlp.text import held, holders

    bank = [
        "A dormant account is charged a yearly fee of 10 EUR.",
        "An account is dormant when its holder has made no payment for 24 months.",
    ]
    assert held("charged a yearly fee of 10 EUR", bank)
    assert holders("charged a yearly fee of 10 EUR", bank) == {0}
    stitched = "a yearly fee of 10 EUR … no payment for 24 months"
    assert held(stitched, bank)
    assert holders(stitched, bank) == frozenset()
    german = [
        "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
        "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
    ]
    assert holders("eine Jahresgebühr von 10 EUR", german) == {0}
    assert holders("24 Monate lang keine Zahlung", german) == {1}


@pytest.mark.parametrize(
    ("broken", "whole"),
    [
        # A capital or a digit after the hyphen is a compound the page broke at
        # its own hyphen, which a join would corrupt.
        ("Ein Online- Händler", "Ein Online-Händler"),
        ("eine E- Mail", "eine E-Mail"),
        ("a 14- 30 day window", "a 14-30 day window"),
        ("a 2- year guarantee", "a 2-year guarantee"),
        ("a non- EU account", "a non-EU account"),
        ("dans les 14- 30 jours", "dans les 14-30 jours"),
        ("εντός 14- 30 ημερών", "εντός 14-30 ημερών"),
        # A lower-case continuation is a broken word, in any script with case.
        ("une carte ban- caire", "une carte bancaire"),
        ("ein prélè- vement", "ein prélèvement"),
        ("opła- ta i zał- ącznik", "opłata i załącznik"),
        ("the fran- çais", "the français"),
        ("pře- vod a plat- ba", "převod a platba"),
        # A slash or a comma after the hyphen closes a suspended hyphen.
        ("für Bau- /Renovierungsarbeiten", "für Bau-/Renovierungsarbeiten"),
        ("für Gas- , Strom- und Wasser", "für Gas-, Strom- und Wasser"),
        ("pour les travaux- /rénovation", "pour les travaux-/rénovation"),
        # A bracket after it opens a phrase, so the break stays.
        ("la carte- (voir plus bas)", "la carte- (voir plus bas)"),
    ],
)
def test_a_break_is_read_by_the_case_of_what_follows_in_any_language(
    broken, whole
) -> None:
    """Letters are read by their Unicode class, so no language lists its own."""
    from nlp.text import rejoined

    assert rejoined(broken) == whole


@pytest.mark.parametrize(
    "kept",
    [
        "Kredit- und Debitkarten",
        "Kredit- respektive Debitkarten",
        "Kredit- ebenso wie Debitkarten",
        "Kredit- oder auch Debitkarten",
        "first- through third-year students",
        "short- but not long-term loans",
        "pre- as well as post-trial",
        "small- to medium-sized firms",
        "1- und 2-Zimmer-Wohnungen",
        "from 1- to 3-year loans",
    ],
)
def test_a_hanging_hyphen_before_a_coordinator_keeps_its_words_apart(kept) -> None:
    """The coordinators of a configured language complete a hanging hyphen."""
    from nlp.text import rejoined

    assert rejoined(kept) == kept


#: Hanging hyphens in languages no configuration names, in sentences long
#: enough for the language to be told.
HANGING = [
    "Wynajmujemy mieszkania 2- i 3-pokojowe oraz domy pół- i całodniowe w mieście.",
    "Nous proposons des cartes de crédit- et de débit pour tous nos clients ici.",
    "Προσφέρουμε οικονομικο- και κοινωνικο- υποστήριξη σε όλους τους πελάτες μας.",
    "Мы предлагаем кредитно- и дебетовые карты для всех наших клиентов сегодня.",
]


@pytest.mark.parametrize("text", HANGING)
def test_a_text_in_a_language_no_configuration_names_is_left_alone(text: str) -> None:
    """A hanging hyphen before a space and a conjunction stays in every language."""
    from nlp.text import rejoined

    assert rejoined(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "pół- i całodniowe",
        "mieszkania 2- i 3-pokojowe",
        "ενδο- και εξωτερικός",
        "οικονομικο- και κοινωνικο-",
        "кредитно- и дебетовой",
        "ο λογα- ριασμός",
    ],
)
def test_a_short_greek_cyrillic_or_one_letter_continuation_is_not_joined(
    text: str,
) -> None:
    """Only Latin letters are joined, and a half of one letter is no half."""
    from nlp.text import rejoined

    assert rejoined(text) == text


@pytest.mark.parametrize(
    ("broken", "whole"),
    [
        ("a big break- through in the market", "a big breakthrough in the market"),
        ("an der Werk- statt", "an der Werkstatt"),
        ("im Zweifel den- noch", "im Zweifel dennoch"),
    ],
)
def test_a_coordinator_that_completes_a_word_the_document_prints_is_that_word(
    broken: str, whole: str
) -> None:
    """The document's own spelling says a joining word is a half of a word."""
    from nlp.text import printed, rejoined

    printing = printed(
        ["Das war ein breakthrough.", "Die Werkstatt ist offen.", "Dennoch geht es."]
    )

    assert rejoined(broken) == broken
    assert rejoined(broken, printing) == whole


@pytest.mark.parametrize(
    ("broken", "mended"),
    [
        ("INTERNA- TIONAL REGULATIONS", "INTERNATIONAL REGULATIONS"),
        ("ALLGEMEINE GESCHÄFTS- BEDINGUNGEN", "ALLGEMEINE GESCHÄFTSBEDINGUNGEN"),
        ("CONDITIONS GÉNÉ- RALES DE VENTE", "CONDITIONS GÉNÉRALES DE VENTE"),
        ("ΓΕΝΙΚΟΙ ΟΡΟ- ΙΤΕΣ", "ΓΕΝΙΚΟΙ ΟΡΟ- ΙΤΕΣ"),
        ("die UEFA- Administration", "die UEFA-Administration"),
        ("per E- Mail", "per E-Mail"),
        ("pre- And Post-Trial", "pre- And Post-Trial"),
    ],
)
def test_the_halves_of_a_word_of_capitals_are_joined(broken: str, mended: str) -> None:
    """A word of capitals breaks at a syllable like any other, a name and a letter do not."""
    from nlp.text import rejoined

    assert rejoined(broken) == mended
