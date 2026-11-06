"""What must hold of a fact for any passage at all.

The example-based tests say what happens to the text this corpus holds.
These say what must hold for a document nobody has seen yet.
"""

from __future__ import annotations

import pytest
from drivers import DIGEST_SHARE, Checker, Extraction, group, passage
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from database.qa_generator import FactKind, Rejection
from extraction.links import linked
from extraction.models import BULLET, MIN_POINTS, CandidateFact, Cited, Twin
from extraction.validation import FactChecker
from nlp.analysis import claim

#: Passages of one topic, as (document, passage id).
TOPIC = st.lists(
    st.tuples(st.sampled_from("abcd"), st.integers(min_value=1, max_value=200)),
    min_size=0,
    max_size=24,
    unique_by=lambda one: one[1],
)


def _passages(rows):
    """Turns the generated pairs into the passages a group is formed from."""
    from dataclasses import replace

    template = passage()
    return [
        replace(
            template,
            id=passage_id,
            doc_sha256=document,
            section_path=f"Fees > Part {passage_id}",
        )
        for document, passage_id in rows
    ]


def grouped(passages, wanted, size):
    """The passages of each link one topic offers."""
    return [
        link.passages
        for link in linked(
            passages, passages, {one.id: 1 for one in passages}, wanted, size
        )
    ]


@given(rows=TOPIC, wanted=st.integers(1, 8), size=st.integers(2, 4))
@settings(deadline=None)
@pytest.mark.nlp
def test_a_group_holds_exactly_the_passages_asked_for(rows, wanted, size) -> None:
    """A short tail is dropped rather than offered as a smaller group."""
    for one in grouped(_passages(rows), wanted, size):
        assert len(one) == size


@given(rows=TOPIC, wanted=st.integers(1, 8), size=st.integers(2, 4))
@settings(deadline=None)
@pytest.mark.nlp
def test_a_passage_is_never_offered_twice_in_one_group(rows, wanted, size) -> None:
    """The same passage twice bridges nothing."""
    for one in grouped(_passages(rows), wanted, size):
        assert len({passage.id for passage in one}) == size


@given(rows=TOPIC, wanted=st.integers(1, 8), size=st.integers(2, 4))
@settings(deadline=None)
@pytest.mark.nlp
def test_no_more_groups_than_were_asked_for(rows, wanted, size) -> None:
    """The count multiplied by the topics is what a bridge run costs."""
    assert len(grouped(_passages(rows), wanted, size)) <= wanted


@given(rows=TOPIC, wanted=st.integers(1, 8), size=st.integers(2, 4))
@settings(deadline=None)
@pytest.mark.nlp
def test_a_topic_smaller_than_one_group_offers_none(rows, wanted, size) -> None:
    """There is no pair to put together."""
    passages = _passages(rows)
    if len(passages) < size:
        assert grouped(passages, wanted, size) == []


@given(
    statement=st.text(max_size=120),
    cited=st.lists(st.integers(-5, 5), max_size=4),
    kind=st.sampled_from([FactKind.ATOMIC, FactKind.SUMMARY, FactKind.OUTLINE]),
)
@settings(deadline=None)
@pytest.mark.nlp
def test_a_verdict_and_its_code_always_agree(statement, cited, kind) -> None:
    """The column's CHECK constraint refuses a row where they do not."""
    checked = FactChecker(DIGEST_SHARE).check(
        passage(), CandidateFact(statement, tuple(cited), kind=kind), "llm"
    )

    assert checked.validated == (checked.rejection_code is None)
    assert (checked.validation_error is None) == (checked.rejection_code is None)


@given(
    statement=st.text(max_size=120),
    cited=st.lists(st.integers(0, 1), min_size=1, max_size=2, unique=True),
)
@settings(deadline=None)
@pytest.mark.nlp
def test_an_evidence_span_always_resolves_in_its_passage(statement, cited) -> None:
    """The invariant every reader of fact_passages relies on."""
    under = passage()
    checked = FactChecker(DIGEST_SHARE).check(
        under, CandidateFact(statement, tuple(cited)), "llm"
    )

    assert [one.passage_id for one in checked.citations] == [under.id]
    for one in checked.citations:
        if one.sentence_ids is None:
            assert one.start is None and one.end is None
        else:
            assert 0 <= one.start <= one.end <= len(under.text)
    assert checked.evidence_text == "\n".join(
        under.text[one.start : one.end]
        for one in checked.citations
        if one.sentence_ids is not None
    )


@given(
    statement=st.text(max_size=120),
    rests_on=st.lists(
        st.tuples(st.integers(-3, 3), st.lists(st.integers(-3, 3), max_size=3)),
        max_size=4,
    ),
)
@settings(deadline=None)
@pytest.mark.nlp
def test_a_bridge_records_only_passages_it_was_offered(statement, rests_on) -> None:
    """A position or a sentence outside the group resolves to nothing."""
    offered = group("Requests are answered within 48 hours.", "Urgent: 4 hours.")
    checked = FactChecker(DIGEST_SHARE).check_bridge(
        offered,
        CandidateFact(
            statement,
            (),
            kind=FactKind.BRIDGE,
            passages=tuple(
                Cited(position=position, sentences=tuple(sentences))
                for position, sentences in rests_on
            ),
        ),
    )
    held = {one.id for one in offered}

    rested = [one.passage_id for one in checked.citations]
    assert set(rested) <= held
    assert len(rested) == len(set(rested))
    by_id = {one.id: one for one in offered}
    assert checked.evidence_text == "\n".join(
        by_id[one.passage_id].text[one.start : one.end]
        for one in checked.citations
        if one.sentence_ids is not None
    )
    # Never validated, rather than always `not_bridging`: an empty statement
    # resting on one passage is refused by `asserts_nothing` first, and which
    # check fires first is the order, not the invariant.
    if len(rested) < 2:
        assert not checked.validated


@given(points=st.lists(st.text(max_size=20), max_size=6))
@settings(deadline=None)
@pytest.mark.nlp
def test_an_outline_is_refused_on_its_shape_before_anything_else(points) -> None:
    """A bullet is a fragment, so nothing can be read off its grammar."""
    checker = Checker(share=DIGEST_SHARE)
    written = "\n".join(f"{BULLET}{point}" for point in points if point.strip())

    checked = checker.raw_outline(written)
    if written.count(BULLET) < MIN_POINTS:
        assert checked.rejection_code == Rejection.NOT_LISTED


#: A statement with two counts in it, per language, and how each language
#: spells the counts from two up, which both grammars put before a plural.
_COUNTED = {
    "en": "The parcel holds {} boxes and {} bags.",
    "de": "Das Paket enthält {} Kisten und {} Beutel.",
}
_SPELLED = {
    "en": {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"},
    "de": {2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs"},
}


@st.composite
def _counts(draw, language: str) -> tuple[tuple[int, int], str]:
    """Two counts, and the statement naming them as digits or as words."""
    values = draw(st.tuples(st.integers(0, 6), st.integers(0, 6)))
    written = [
        draw(st.sampled_from((str(value), _SPELLED[language].get(value, str(value)))))
        for value in values
    ]
    return values, _COUNTED[language].format(*written)


@given(data=st.data(), language=st.sampled_from(sorted(_COUNTED)))
@settings(deadline=None)
@pytest.mark.nlp
def test_statements_naming_different_numbers_are_never_duplicates(
    data, language
) -> None:
    """However close their vectors, a different count is a different claim."""
    values, statement = data.draw(_counts(language))
    others, twin = data.draw(_counts(language))
    assume(sorted(values) != sorted(others))
    read = passage(statement, language=language)
    cited = [one.index for one in read.sentences]
    run = Extraction(
        read,
        facts={"facts": [{"sentences": cited, "statement": statement}]},
        duplicate_cosine=0.9,
    )
    run.queue.twin = Twin(fact_id=7, statement=twin, similarity=1.0)
    run.next()

    (stored,) = run.queue.stored[1]
    assert stored.validated, (statement, twin, stored.validation_error)


# ── A date or a clock time, re-paired ────────────────────────────────────

#: A sentence of each domain naming one date, by configured language: `{}`
#: is the date.
_DATED = {
    "de": (
        "Die neuen Kontogebühren gelten ab dem {}.",
        "Das Amt nimmt Anträge bis zum {} entgegen.",
        "Der Sommerschlussverkauf endet am {}.",
    ),
    "en": (
        "The new account fees apply from {}.",
        "The office accepts applications until {}.",
        "The summer sale ends on {}.",
    ),
}


#: The same in French, Polish and Greek, which no `NLP_MODELS` row names.
_UNREAD_DATED = {
    "fr": ("Les nouveaux frais s'appliquent à partir du {}.",),
    "pl": ("Nowe opłaty obowiązują od {}.",),
    "el": ("Οι νέες χρεώσεις ισχύουν από {}.",),
}


def _dated(day: int, month: int, year: int, form: str) -> str:
    """A date with its year at one end, its runs joined by `/` or `-`."""
    mark = form[-1]
    if form.startswith("y"):
        return f"{year}{mark}{month:02d}{mark}{day:02d}"
    return f"{day:02d}{mark}{month:02d}{mark}{year}"


def _citing_all(text: str, language: str, statement: str):
    """The verdict on a statement citing every sentence of a one-rule passage.

    Every one, because the splitter may cut `ab | dem 01/09/2030.` (T2-06),
    and what is asked here is how the date is read, not where the rule is cut.
    """
    read = passage(text, language=language)
    return Checker(read).atomic(statement, tuple(range(len(read.sentences))))


@st.composite
def _dates(draw, frames=_DATED):
    """A language, a sentence, a date whose day and month differ, both 12 or less, and its form."""
    language = draw(st.sampled_from(sorted(frames)))
    day, month = draw(st.permutations(range(1, 13)))[:2]
    return (
        language,
        draw(st.sampled_from(frames[language])),
        day,
        month,
        draw(st.integers(2020, 2035)),
        draw(st.sampled_from(["d/", "d-", "y-", "y/"])),
    )


@given(case=_dates())
@pytest.mark.nlp
def test_a_date_with_its_day_and_month_swapped_is_refused(case) -> None:
    """`12-01-2026` for a cited `01-12-2026` moves the date by eleven months."""
    language, frame, day, month, year, form = case
    cited = frame.format(_dated(day, month, year, form))
    swapped = frame.format(_dated(month, day, year, form))

    judged = _citing_all(cited, language, swapped)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, (cited, swapped)


@given(case=_dates(_UNREAD_DATED))
@pytest.mark.nlp
def test_a_date_swapped_in_a_language_with_no_pipeline_is_never_validated(
    case,
) -> None:
    """Refused for whatever the default parse makes of it, never passed."""
    language, frame, day, month, year, form = case
    cited = frame.format(_dated(day, month, year, form))
    swapped = frame.format(_dated(month, day, year, form))

    assert not _citing_all(cited, language, swapped).validated, (cited, swapped)


@given(case=_dates())
@pytest.mark.nlp
def test_a_date_restated_as_the_cited_text_writes_it_is_validated(case) -> None:
    """The guard above is no refusal of every date: the cited date is no addition.

    Not a German date of dashes, day first, whose year the German parse may
    tag a finite verb (`endet am 01-11-2030.`): T2-06's.
    """
    language, frame, day, month, year, form = case
    assume(not (language == "de" and form == "d-"))
    cited = frame.format(_dated(day, month, year, form))

    judged = _citing_all(cited, language, cited)

    assert judged.validated, (cited, judged.validation_error)


#: Opening hours of each domain, by language: `{}` and `{}` are the times.
_OPEN = {
    "de": (
        "Die Filiale ist von {} bis {} Uhr geöffnet.",
        "Das Bürgeramt ist von {} bis {} Uhr erreichbar.",
    ),
    "en": (
        "The branch is open from {} to {}.",
        "The citizens' office answers calls from {} to {}.",
    ),
}


@st.composite
def _hours(draw):
    """A language, a sentence and two times whose hours and minutes all differ, even read on a 12-hour clock."""
    language = draw(st.sampled_from(sorted(_OPEN)))
    opens = draw(st.integers(6, 11))
    closes = draw(st.integers(12, 20).filter(lambda hour: hour % 12 != opens))
    early, late = draw(st.permutations([0, 15, 30, 45]))[:2]
    return language, draw(st.sampled_from(_OPEN[language])), opens, closes, early, late


@given(case=_hours())
@pytest.mark.nlp
def test_opening_hours_with_their_minutes_re_paired_are_refused(case) -> None:
    """`13:30 to 9:00` is not what a cited `9:30 to 13:00` says."""
    language, frame, opens, closes, early, late = case
    cited = frame.format(f"{opens}:{early:02d}", f"{closes}:{late:02d}")
    re_paired = frame.format(f"{opens}:{late:02d}", f"{closes}:{early:02d}")

    judged = _citing_all(cited, language, re_paired)

    assert judged.rejection_code == Rejection.UNSUPPORTED_ADDITION, (cited, re_paired)


# ── Two statements, one figure, read apart by its unit or its month ──────

#: A statement of each domain counting a period or a measure, by configured
#: language: `{}` is the figure and its unit. The units are the inflected
#: forms a writer puts after a count above one.
_PERIODS = {
    "de": (
        "Die Kündigungsfrist für das Girokonto beträgt {}.",
        "Die Rücksendung ist innerhalb von {} möglich.",
        "Das Amt bearbeitet den Antrag binnen {}.",
    ),
    "en": (
        "The notice period for the current account is {}.",
        "Returns are accepted within {}.",
        "The office decides on the application within {}.",
    ),
}
#: The same in French, Polish and Greek, which no `NLP_MODELS` row names and
#: whose units the default parse may not tag as one: there a unit tells
#: nothing, and only the figures read apart.
_MEASURED = {
    "fr": ("Le colis pèse au plus {}.", "La carte mesure {} de large."),
    "pl": ("Paczka waży najwyżej {}.", "Karta ma szerokość {}."),
    "el": ("Το δέμα ζυγίζει έως {}.", "Η κάρτα έχει πλάτος {}."),
}
_PERIOD_UNITS = {
    "de": ("Stunden", "Tage", "Wochen", "Monate", "Jahre"),
    "en": ("hours", "days", "weeks", "months", "years"),
}
_MEASURE_UNITS = ("g", "kg", "mm", "cm", "m", "km", "ml", "l")


@st.composite
def _twin_units(draw):
    """A language, a sentence, a count, and two different units of one closed set."""
    language = draw(st.sampled_from(sorted(_PERIODS)))
    units = draw(st.sampled_from([_PERIOD_UNITS[language], _MEASURE_UNITS]))
    first, second = draw(st.permutations(units))[:2]
    return (
        language,
        draw(st.sampled_from(_PERIODS[language])),
        draw(st.integers(2, 500)),
        first,
        second,
    )


@given(case=_twin_units())
@pytest.mark.nlp
def test_one_figure_beside_two_units_of_time_or_measure_names_two_values(
    case,
) -> None:
    """`14 Tage` and `14 Wochen`, `5 kg` and `5 g`, are two facts however alike their words."""
    from extraction.service import _counted_alike

    language, frame, count, unit, other = case
    statement, twin = frame.format(f"{count} {unit}"), frame.format(f"{count} {other}")

    assert not _counted_alike(statement, twin, language), (statement, twin)
    assert not _counted_alike(twin, statement, language), (twin, statement)


@given(case=_twin_units())
@pytest.mark.nlp
def test_one_figure_beside_one_unit_names_one_value(case) -> None:
    """The guard above refuses nothing it should keep: a statement is counted alike with itself."""
    from extraction.service import _counted_alike

    language, frame, count, unit, _ = case
    statement = frame.format(f"{count} {unit}")

    assert _counted_alike(statement, statement, language), statement


@given(
    language=st.sampled_from(sorted(_MEASURED)),
    frame=st.integers(0, 1),
    counts=st.permutations(range(1, 200)),
    unit=st.sampled_from(_MEASURE_UNITS),
)
@pytest.mark.nlp
def test_two_counts_in_a_language_with_no_pipeline_name_two_values(
    language, frame, counts, unit
) -> None:
    """Inert, not misread: `2 kg` and `3 kg` stay two in French, Polish and Greek."""
    from extraction.service import _counted_alike

    written = _MEASURED[language][frame]
    statement = written.format(f"{counts[0]} {unit}")
    twin = written.format(f"{counts[1]} {unit}")

    assert not _counted_alike(statement, twin, language), (statement, twin)
    assert _counted_alike(statement, statement, language), statement


#: A statement of each domain naming a day of a month, by configured language.
_DAYS = {
    "de": (
        "Die neuen Gebühren gelten ab dem {}. {}.",
        "Der Schlussverkauf beginnt am {}. {}.",
        "Anträge sind bis zum {}. {} einzureichen.",
    ),
    "en": (
        "The new fees apply from {} {}.",
        "The sale starts on {} {}.",
        "Applications are due by {} {}.",
    ),
}
_MONTHS = {
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
    "en": "January February March April May June July August September October November December",
}


@given(
    language=st.sampled_from(sorted(_DAYS)),
    frame=st.integers(0, 2),
    day=st.integers(1, 28),
    months=st.permutations(range(12)),
)
@pytest.mark.nlp
def test_one_day_of_two_different_months_names_two_dates(
    language, frame, day, months
) -> None:
    """`ab dem 1. Januar` and `ab dem 1. Juli` are two facts; `1. Januar` twice is one."""
    from extraction.service import _counted_alike

    names = _MONTHS[language].split()
    written = _DAYS[language][frame]
    statement = written.format(day, names[months[0]])
    twin = written.format(day, names[months[1]])

    assert not _counted_alike(statement, twin, language), (statement, twin)
    assert _counted_alike(statement, statement, language), statement


# ── One claim, whatever figure or reference it holds ─────────────────────

#: A one-claim rule of each domain, by configured language: `{}` is a figure
#: or a reference.
_ONE_CLAIM = {
    "de": (
        "Die Gebühr für die Ersatzkarte beträgt {}.",
        "Der Versand kostet {} pro Bestellung.",
        "Das Amt erhebt für den Antrag {}.",
    ),
    "en": (
        "The fee for a replacement card is {}.",
        "Shipping costs {} per order.",
        "The office charges {} for the application.",
    ),
}
_CITED = {
    "de": ("Gemäß {} gilt die Frist.", ("§ {} Abs. 2", "Artikel {}", "Ziff. {}.1")),
    "en": (
        "Under {} the period applies.",
        ("Article {}(2)", "Section {}.1", "clause {}"),
    ),
}


@st.composite
def _one_claims(draw):
    """A language and a one-claim rule holding an amount, a rate, a period or a reference."""
    language = draw(st.sampled_from(sorted(_ONE_CLAIM)))
    thousands, decimal = (".", ",") if language == "de" else (",", ".")
    whole, cents = draw(st.integers(1, 9_999_999)), draw(st.integers(0, 99))
    number = draw(st.integers(1, 30))
    amounts = [
        f"{whole:,}".replace(",", thousands) + f"{decimal}{cents:02d} EUR",
        f"{whole}{decimal}{cents:02d} EUR",
        f"{whole % 100}{decimal}5 %",
    ]
    if draw(st.booleans()):
        frame, written = _CITED[language]
        return language, frame.format(draw(st.sampled_from(written)).format(number))
    return language, draw(st.sampled_from(_ONE_CLAIM[language])).format(
        draw(st.sampled_from(amounts))
    )


@given(case=_one_claims())
@pytest.mark.nlp
def test_a_rule_of_one_claim_is_one_claim_whatever_figure_or_reference_it_holds(
    case,
) -> None:
    """`Die Gebühr beträgt 1.234,56 EUR.` makes one claim, as `... 5 EUR.` does.

    In German and English: in a language no `NLP_MODELS` row names the count
    is the default parse's, which N-146 says is unreliable.
    """
    language, text = case

    assert claim(text, language).predicates == 1, text


# ── A figure taken from the uncited sentence ─────────────────────────────

#: Two rules of one kind side by side, by language: a bank's fees, a shop's
#: periods, an office's rates. A fact cites the first. French, Polish and
#: Greek name no `NLP_MODELS` row.
_SIDE_BY_SIDE = {
    "de": (
        ("Die Ersatzkarte kostet {} EUR.", "Die Zusatzkarte kostet {} EUR."),
        (
            "Die Rücksendung ist binnen {} Tagen möglich.",
            "Der Umtausch ist binnen {} Tagen möglich.",
        ),
        ("Der Antrag kostet {} EUR.", "Der Widerspruch kostet {} EUR."),
    ),
    "en": (
        ("A replacement card costs {} EUR.", "An additional card costs {} EUR."),
        (
            "Returns are accepted within {} days.",
            "Exchanges are accepted within {} days.",
        ),
        ("An application costs {} EUR.", "An appeal costs {} EUR."),
    ),
    "fr": (
        (
            "Une carte de remplacement coûte {} EUR.",
            "Une carte supplémentaire coûte {} EUR.",
        ),
    ),
    "pl": (("Karta zastępcza kosztuje {} EUR.", "Karta dodatkowa kosztuje {} EUR."),),
    "el": (
        (
            "Η κάρτα αντικατάστασης κοστίζει {} EUR.",
            "Η πρόσθετη κάρτα κοστίζει {} EUR.",
        ),
    ),
}


@st.composite
def _side_by_side(draw, languages):
    """A language, a passage of two rules of one kind, the cited rule and that rule with the other's figure."""
    language = draw(st.sampled_from(languages))
    cited, other = draw(st.sampled_from(_SIDE_BY_SIDE[language]))
    own, theirs = draw(st.permutations(range(2, 500)))[:2]
    return (
        language,
        f"{cited.format(own)} {other.format(theirs)}",
        cited.format(own),
        cited.format(theirs),
    )


@given(case=_side_by_side(["de", "en"]))
@pytest.mark.nlp
def test_a_rule_given_the_figure_of_the_rule_beside_it_is_refused(case) -> None:
    """`The replacement card costs 7 EUR` for a cited 5 EUR is a swap, the faithful 5 EUR is not."""
    language, text, faithful, swapped = case
    read = Checker(passage(text, language=language))

    assert read.atomic(swapped, 0).rejection_code == Rejection.UNSUPPORTED_ADDITION
    assert read.atomic(faithful, 0).validated, faithful


@given(case=_side_by_side(["fr", "pl", "el"]))
@pytest.mark.nlp
def test_a_faithful_rule_is_never_refused_as_a_swap_in_a_language_with_no_pipeline(
    case,
) -> None:
    """The currency code is read in any language, so the swap may be refused; the faithful rule never is."""
    language, text, faithful, _ = case
    read = Checker(passage(text, language=language))

    assert read.atomic(faithful, 0).rejection_code != Rejection.UNSUPPORTED_ADDITION
