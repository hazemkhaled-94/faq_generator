"""The topic map holds a document's words as data, never as markup.

The page is served on the api's origin (GET /topics/visualisation/{language})
and drawn by the frontend in an iframe that allows scripts and the parent's
origin, and its vocabulary is lemmas read out of uploaded documents.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from topic_modelling.models import TopicSpace
from topic_modelling.visualisation import render

#: What en_core_web_md and de_core_news_md both keep as one content lemma of
#: "The fee</script><script>alert(1)</script>applies." - nlp.analysis._lemmas
#: passes it, since it holds letters and sits outside any web address.
_CLOSING = "fee</script><script"


def _page(vocabulary: list[str]) -> str:
    """The figure of a two-topic model over the given words."""
    width = len(vocabulary)
    half = width // 2
    first = [2.0 if i < half else 1.0 for i in range(width)]
    second = [1.0 if i < half else 2.0 for i in range(width)]
    space = TopicSpace(
        topic_term=[[w / sum(first) for w in first], [w / sum(second) for w in second]],
        doc_topic=[[0.8, 0.2], [0.3, 0.7], [0.5, 0.5]],
        doc_lengths=[5, 6, 4],
        vocabulary=vocabulary,
        term_frequency=[3] * width,
    )
    return render(space, "en").decode("utf-8")


_BASE = ["gebühr", "konto", "karte", "versand", "lieferung", "rücksendung"]


def _closings(page: str) -> int:
    return page.lower().count("</script")


@given(
    st.lists(
        st.text(
            alphabet=st.characters(
                categories=("Ll", "Lu", "Nd"), include_characters="-'."
            ),
            min_size=2,
            max_size=12,
        ),
        min_size=1,
        max_size=4,
        unique=True,
    ).filter(lambda extra: not set(extra) & set(_BASE))
)
def test_ordinary_words_leave_the_pages_scripts_as_they_are(extra) -> None:
    """Letters, digits and hyphens in any script close nothing early."""
    assert _closings(_page(_BASE + extra)) == _closings(_page(_BASE))


def test_a_word_holding_a_closing_tag_closes_no_script() -> None:
    """The lemma reaches the page as data, escaped, and no script ends early."""
    page = _page([*_BASE, _CLOSING])

    assert _closings(page) == _closings(_page([*_BASE, "fee"]))
