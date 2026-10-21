"""The Topics page's search and filters, which run in the page and not the API.

`/topics` answers every topic at once, so the words, the column and the two
filters are applied by `views/topics.py` itself. Every other listing hands
them to a route whose tests say what they select; nothing said it here.
"""

from __future__ import annotations

import pytest
from pages import TOPIC, changed

pytestmark = pytest.mark.frontend

VIEW = "topics"

#: Two languages, one named by a person and out of coverage, one unnamed.
SHIPPING = changed(TOPIC, label="Lieferung und Versand", include_in_coverage=False)
ACCOUNT = changed(
    TOPIC,
    id=2,
    language="en",
    topic_index=0,
    top_terms=["account", "fee", "overdraft"],
    label=None,
)


def listed(drawn) -> list[str]:
    """The topics the table lists, by language and number."""
    tables = [
        one.value
        for one in drawn.app.dataframe
        if "Top terms" in getattr(one.value, "columns", ())
    ]
    if not tables:
        return []
    (table,) = tables
    return [
        f"{lang} #{index}"
        for lang, index in zip(table["Language"], table["#"], strict=True)
    ]


@pytest.fixture
def both(page):
    """The page over the two topics."""
    return page(topics=[SHIPPING, ACCOUNT])


@pytest.mark.parametrize(
    ("words", "column", "found"),
    [
        ("LIEFERUNG", "Label and terms", ["de #0"]),
        ("versand", "Label", ["de #0"]),
        ("overdraft", "Terms", ["en #0"]),
        ("overdraft", "Label", []),
        ("transport", "Label and terms", ["de #0"]),
        ("e", "Label and terms", ["de #0", "en #0"]),
    ],
)
def test_the_words_are_looked_for_in_the_chosen_column(
    both, words, column, found
) -> None:
    """A case-insensitive substring of the label, the terms, or either."""
    drawn = both.choose("topics-field", column).type_in("topics-search", words)

    assert drawn.raised == []
    assert listed(drawn) == found


def test_the_filters_narrow_to_one_language_and_one_coverage(both) -> None:
    """Each filter alone, then the two together, which leave nothing."""
    # One app underneath, so each listing is read before the next choice.
    assert listed(both.choose("topics-language", "en")) == ["en #0"]
    assert listed(
        both.choose("topics-language", "All languages").choose(
            "topics-coverage", "excluded"
        )
    ) == ["de #0"]
    assert listed(both.choose("topics-language", "en")) == []


@pytest.mark.xfail(
    strict=True,
    reason="The Topics table shows a topic's terms joined by ', ' and the "
    "search looks in them joined by ' ', so terms typed as the table shows "
    "them find nothing",
)
def test_terms_typed_as_the_table_shows_them_find_the_topic(both) -> None:
    """`lieferung, versand` is what the Top terms cell reads."""
    shown = ", ".join(TOPIC["top_terms"][:2])
    drawn = both.choose("topics-field", "Terms").type_in("topics-search", shown)

    assert listed(drawn) == ["de #0"]
