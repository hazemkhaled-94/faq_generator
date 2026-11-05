"""Reading the language a passage is written in.

These documents carry a German report and its English summary in one file,
so the document's own label is not what a passage is read under.
"""

from __future__ import annotations

import pytest

GERMAN = (
    "Die Bundesanstalt für Finanzdienstleistungsaufsicht beaufsichtigt "
    "Institute und prüft deren Risikomanagement regelmäßig."
)
ENGLISH = (
    "The supervisory authority examines the risk management of the "
    "institutions it supervises on a regular basis."
)

#: An English list of links to a German site.
LINKS = (
    "1. [Risks arising from significant corrections on the international "
    "financial markets](https://www.bafin.de/EN/die-bafin/"
    "publikationen-daten/risiken-im-fokus/Fokusrisiken_2026/RIF1/rif_1.html)\n"
    "2. [Risks arising from corporate loan defaults](https://www.bafin.de/EN/"
    "die-bafin/publikationen-daten/risiken-im-fokus/Fokusrisiken_2026/RIF2/"
    "rif_2.html)"
)


@pytest.mark.parametrize(
    ("text", "expected"), [(GERMAN, "de"), (ENGLISH, "en"), (LINKS, "en")]
)
def test_prose_is_read_in_its_own_language(text: str, expected: str) -> None:
    """The addresses in a link do not decide the language of its text."""
    from nlp.language import detect

    assert detect(text) == expected, detect(text)


@pytest.mark.parametrize(
    "text",
    [
        "Risiko",
        "",
        "[Digitalisation](https://www.bafin.de/EN/die-bafin/x.html)",
    ],
)
def test_too_short_to_judge_is_not_guessed(text: str) -> None:
    """Nothing is returned, and the caller falls back to the document's."""
    from nlp.language import detect

    assert detect(text) is None


@pytest.mark.parametrize(
    ("code", "name"), [("de", "German"), ("EN", "English"), ("fr", "fr"), (None, "")]
)
def test_a_language_is_named_as_a_prompt_says_it(code: str | None, name: str) -> None:
    """A code it has no name for stays a code; no language is no sentence."""
    from nlp.models import named

    assert named(code) == name


FRENCH = (
    "Le consommateur dispose d'un délai de quatorze jours pour se rétracter "
    "d'un contrat conclu à distance, sans avoir à justifier sa décision."
)
SPANISH = (
    "El consumidor dispone de un plazo de catorce días para desistir de un "
    "contrato celebrado a distancia, sin tener que justificar su decisión."
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [(GERMAN, "de"), (ENGLISH, "en"), (FRENCH, "fr"), (SPANISH, "es")],
)
def test_a_document_is_read_in_any_language_not_only_the_configured(
    text: str, expected: str
) -> None:
    """The document's language is asked of every language, so French is French."""
    from nlp.language import document_language

    found = document_language(text)

    assert found is not None and found[0] == expected, found


def test_a_document_too_short_to_judge_has_no_language() -> None:
    """A few words are no evidence, as for a passage."""
    from nlp.language import document_language

    assert document_language("Bonjour") is None


def _price_list(heading: str, prose: str, header: str) -> str:
    """A table-heavy body: a short heading, one sentence, rows of figures."""
    rows = "\n".join(
        f"A-{n:04d} | {n % 9 + 1} | {n * 3 + 5}.90 EUR | {n % 4}.5 kg"
        for n in range(40)
    )
    return f"{heading}\n\n{prose}\n\n{header}\n{rows}"


ENGLISH_LIST = _price_list(
    "Price list for trade customers",
    "All prices are net and valid until the end of the quarter.",
    "SKU | Qty | Price | Weight",
)
GERMAN_LIST = _price_list(
    "Preisliste für Geschäftskunden",
    "Alle Preise sind Nettopreise und gelten bis zum Ende des Quartals.",
    "Art.-Nr. | Menge | Preis | Gew.",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [(ENGLISH_LIST, "en"), (GERMAN_LIST, "de")],
    ids=["english", "german"],
)
def test_a_rare_token_in_a_table_does_not_change_the_documents_language(
    text: str, expected: str
) -> None:
    """Abbreviations of a price list are not evidence of another language."""
    from nlp.language import document_language

    found = document_language(text + "\nQty")

    assert found is not None and found[0] == expected, found


def test_a_body_of_figures_and_abbreviations_is_not_another_language() -> None:
    """With almost no words, the document is never refused as a third language."""
    from preprocessing.parsing.analysis import DocumentAnalyser

    body = "\n".join(
        f"SKU {n} | Qty {n % 7} | {n}.5 kg | EUR {n * 2}" for n in range(60)
    )

    DocumentAnalyser._configured(body)


#: A sentence of each language a deployment configured for German and English
#: does not name: Latin script, one that shares a script with them in common
#: words, and Greek.
OTHER = {
    "fr": "Les frais de tenue de compte s'élèvent à cinq euros par mois pour tous les clients de la banque.",
    "pl": "Opłata za prowadzenie konta wynosi pięć złotych miesięcznie dla wszystkich klientów banku.",
    "sv": "Kontoavgiften är fem euro per månad för alla kunder i banken och betalas varje månad.",
    "nl": "De rekeningkosten bedragen vijf euro per maand voor alle klanten van de bank en worden maandelijks afgeschreven.",
    "el": "Το τέλος τήρησης λογαριασμού είναι πέντε ευρώ το μήνα για όλους τους πελάτες της τράπεζας.",
}

#: A row of a price list: figures, units and a few words.
PRICES = "Adult 12.50 EUR | Child 6.00 EUR | Family 30.00 EUR | Pass 90 EUR"


@pytest.mark.parametrize(("text", "expected"), [(GERMAN, "de"), (ENGLISH, "en")])
def test_a_configured_passage_keeps_its_language(text: str, expected: str) -> None:
    """The reading is the configured one, and the fallback is not used."""
    from nlp.language import passage_language

    assert passage_language(text, "fr") == expected


@pytest.mark.parametrize("code", sorted(OTHER))
@pytest.mark.parametrize("fallback", ["de", "en", None])
def test_a_passage_in_a_language_no_pipeline_is_configured_for_reads_none(
    code: str, fallback: str | None
) -> None:
    """A guest passage is not labelled German or English by the detector's two-way pick."""
    from nlp.language import passage_language

    assert passage_language(OTHER[code], fallback) is None


@pytest.mark.parametrize(
    ("text", "fallback"),
    [("Risiko", "de"), ("", "en"), (PRICES, "en"), (PRICES, "de")],
)
def test_what_cannot_be_told_takes_the_documents_language(
    text: str, fallback: str
) -> None:
    """A heading or a row of figures says nothing against the document's language."""
    from nlp.language import detect, passage_language

    assert passage_language(text, fallback) == (detect(text) or fallback)


SIGNATURES = {
    "de": "Anna Kowalska Vorsitzende Peter Brandt Schriftführer Hamburg, 29. Juli 2026",
    "en": "Anna Kowalska Chair Peter Brandt Secretary General Leeds, 29 July 2026",
    "fr": "Anna Kowalska Présidente Pierre Brandt Secrétaire Général Lyon, 29 juillet 2026",
    "el": "Άννα Κοβάλσκα Πρόεδρος Πέτρος Μπραντ Γραμματέας Αθήνα, 29 Ιουλίου 2026",
}


@pytest.mark.parametrize("signature", sorted(SIGNATURES))
@pytest.mark.parametrize(("text", "expected"), [(GERMAN, "de"), (ENGLISH, "en")])
def test_a_passage_is_read_by_its_prose_not_by_its_names(
    signature: str, text: str, expected: str
) -> None:
    """A signature under a sentence is names, and says nothing against its language."""
    from nlp.language import outside, passage_language

    assert not outside(SIGNATURES[signature])
    assert not outside(f"{text}\n{SIGNATURES[signature]}")
    assert passage_language(f"{text}\n{SIGNATURES[signature]}", expected) is not None
    assert passage_language(SIGNATURES[signature], expected) is not None


def test_a_contents_table_is_not_a_language_of_its_own() -> None:
    """Rows of terms and page numbers read as no language, so they are not outside."""
    from nlp.language import outside

    assert not outside(
        "| Glossary                         |   194 |\n| Index           |  201 |"
    )
