"""Reading the paper's categorizations out of QUESTIONS_CATEGORIZATIONS.

The setting holds the JSON of the paper's Figure 2, one object or a list of
them. What is refused here is refused before a worker starts, naming the
categorization at fault, rather than turning up as a prompt nobody meant.
"""

from __future__ import annotations

import json

import pytest

from question_generation.config import Settings, categorizations
from question_generation.models import Categorization, Category

#: The paper's Figure 2, verbatim.
FIGURE_2 = {
    "categorization": {
        "categorization_name": "question-factuality",
        "description": "This categorization distinguishes between factoid and "
        "non-factoid questions.",
        "categories": [
            {
                "name": "factoid",
                "probability": 0.25,
                "description": "a question seeking a specific, concise piece of "
                "information or a short fact about a particular subject, such as "
                "a name, date, or number.",
            },
            {
                "name": "non-factoid-experience",
                "probability": 0.75,
                "description": "A question to get advice or recommendations on a "
                "particular topic.",
            },
        ],
    }
}

#: The paper's Figure 3, verbatim: a categorization of the person asking.
FIGURE_3 = {
    "categorization": {
        "categorization_name": "user-expertise-categorization",
        "description": "This categorization defines the level of expertise of "
        "end-users.",
        "categories": [
            {
                "name": "expert",
                "probability": 0.5,
                "description": "a specialized user with deep understanding of "
                "the corpus.",
            },
            {
                "name": "novice",
                "probability": 0.5,
                "description": "a regular user with no understanding of "
                "specialized terms.",
            },
        ],
    }
}


def asking(role: object) -> dict:
    """Figure 3 with a role, which the paper's JSON leaves to its reader."""
    return {"categorization": {**FIGURE_3["categorization"], "role": role}}


def one(*categories: dict, name: str = "phrasing") -> dict:
    """A bare categorization holding these categories."""
    return {"categorization_name": name, "categories": list(categories)}


def category(name: str, probability: float | None = None) -> dict:
    """A category described by its own name, with a probability if given."""
    read: dict = {"name": name, "description": f"a {name} question"}
    if probability is not None:
        read["probability"] = probability
    return read


def read(value: object) -> tuple[Categorization, ...]:
    """The categorizations a value of the setting holds."""
    return categorizations(json.dumps(value))


def test_the_papers_figure_reads_as_it_is_printed() -> None:
    """The wrapper object, the description and both probabilities."""
    (factuality,) = read(FIGURE_2)
    assert factuality.name == "question-factuality"
    assert [one.name for one in factuality.categories] == [
        "factoid",
        "non-factoid-experience",
    ]
    assert [one.probability for one in factuality.categories] == [0.25, 0.75]
    assert factuality.categories[1].description == (
        "A question to get advice or recommendations on a particular topic."
    )


def test_a_list_keeps_its_order() -> None:
    """Bare objects and wrapped ones mix; the order is the operator's."""
    read_ = read([one(category("x"), name="b"), FIGURE_2, one(category("y"), name="a")])
    assert [each.name for each in read_] == ["b", "question-factuality", "a"]


def test_absent_probabilities_are_uniform() -> None:
    """The paper prints Table 5 without probabilities; each is then even."""
    (phrasing,) = read(one(category("x"), category("y"), category("z")))
    assert [each.probability for each in phrasing.categories] == pytest.approx(
        [1 / 3, 1 / 3, 1 / 3]
    )


def test_one_category_is_certain() -> None:
    """The paper's Table 1 holds categorizations of a single category."""
    (phrasing,) = read(one(category("concise")))
    assert phrasing.categories == (
        Category("phrasing", "concise", "a concise question", 1.0),
    )


def test_a_description_is_one_line() -> None:
    """Each category is one bullet line of the writer's prompt."""
    (phrasing,) = read(one({"name": "x", "description": "  a  question\nthat\tasks  "}))
    assert phrasing.categories[0].description == "a question that asks"


def test_a_category_is_labelled_by_its_categorization() -> None:
    """The name a filter, the workbook and a report give it."""
    (factuality,) = read(FIGURE_2)
    assert factuality.categories[0].label == "question-factuality=factoid"


def test_a_sum_close_to_one_is_scaled_to_one() -> None:
    """Rounded by hand, as 0.33 three times is, the share is kept."""
    (phrasing,) = read(
        one(category("x", 0.33), category("y", 0.33), category("z", 0.33))
    )
    assert [each.probability for each in phrasing.categories] == pytest.approx(
        [1 / 3, 1 / 3, 1 / 3]
    )


@pytest.mark.parametrize(
    ("value", "says"),
    [
        (one(category("x", 0.5), category("y", 0.3)), "'phrasing'.*0.8"),
        (one(category("x", 0.5), category("y")), "'phrasing'.*every category or none"),
        (one(category("x", 1.5), category("y", -0.5)), "'phrasing'.*between 0 and 1"),
        (one(category("x", 0), category("y", 0)), "'phrasing'.*summing to 0,"),
        (one(category("x"), category("x")), "'phrasing'.*'x' twice"),
        (one(category("x"), name="a=b"), "'a=b'.*an ="),
        (one(category("x"), name="a, b"), "'a, b'.*a comma"),
        (one(category("x=y")), "'x=y'.*an ="),
        ([one(category("x")), one(category("y"))], "'phrasing' twice"),
        (one(), "'phrasing'.*no categories"),
        ({"categories": [category("x")]}, "categorization_name"),
        (one({"name": "x", "description": "  "}), "'phrasing'.*'x'.*description"),
        (one({"name": "x", "description": "d", "probabilty": 1}), "'probabilty'"),
        ({**one(category("x")), "rolle": "user"}, "'rolle'"),
        ("not a list", "categorization"),
    ],
)
def test_a_mistake_is_refused_by_name(value: object, says: str) -> None:
    """Each refusal names the categorization, or the key, that is wrong."""
    with pytest.raises(ValueError, match=f"QUESTIONS_CATEGORIZATIONS.*({says})"):
        read(value)


def test_figure_3_reads_as_a_user_categorization() -> None:
    """Its role on the categorization, given to every category of it."""
    (expertise,) = read(asking("user"))
    assert [
        (each.name, each.role, each.probability) for each in expertise.categories
    ] == [
        ("expert", "user", 0.5),
        ("novice", "user", 0.5),
    ]


def test_a_categorization_with_no_role_describes_the_question() -> None:
    """The paper's Figure 2 as printed, and every value written before roles."""
    (factuality,) = read(FIGURE_2)
    assert {each.role for each in factuality.categories} == {"question"}
    (expertise,) = read(FIGURE_3)
    assert {each.role for each in expertise.categories} == {"question"}


@pytest.mark.parametrize("role", ["kind", "User", 1])
def test_a_role_it_does_not_take_is_refused_by_name(role: object) -> None:
    """Never read off a name: a role is one of two, or the value is wrong."""
    with pytest.raises(ValueError) as refused:
        read(asking(role))
    assert str(refused.value) == (
        "QUESTIONS_CATEGORIZATIONS: categorization 'user-expertise-categorization' "
        f"has the role {role!r}; it takes question, user"
    )


def test_text_that_is_not_json_is_refused() -> None:
    """The operator's typo is named as a JSON error, not a crash."""
    with pytest.raises(ValueError, match="QUESTIONS_CATEGORIZATIONS is not JSON"):
        categorizations("[{")


def test_the_setting_unset_draws_the_papers_two_natural_phrasings(
    monkeypatch,
) -> None:
    """On by default, with the descriptions of the paper's Table 5."""
    monkeypatch.delenv("QUESTIONS_CATEGORIZATIONS", raising=False)
    (phrasing,) = Settings.load().categorizations
    assert phrasing.name == "Phrasing"
    assert [(one.name, one.probability) for one in phrasing.categories] == [
        ("concise-and-natural", 0.5),
        ("verbose-and-natural", 0.5),
    ]


def test_an_empty_list_draws_no_categories(monkeypatch) -> None:
    """How an operator turns them off."""
    monkeypatch.setenv("QUESTIONS_CATEGORIZATIONS", "[]")
    assert Settings.load().categorizations == ()


def test_the_setting_is_read_into_the_settings(monkeypatch) -> None:
    """The settings carry what the setting holds."""
    monkeypatch.setenv("QUESTIONS_CATEGORIZATIONS", json.dumps(FIGURE_2))
    assert Settings.load().categorizations == read(FIGURE_2)
