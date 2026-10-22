"""Reading the paper's categorizations out of QUESTIONS_CATEGORIZATIONS.

The setting holds the JSON of the paper's Figure 2, one object or a list of
them. What is refused here is refused before a worker starts, naming the
categorization at fault, rather than turning up as a prompt nobody meant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from question_generation.config import (
    DEFAULT_CATEGORIZATIONS,
    Settings,
    categorizations,
)
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


def test_the_default_bounds_its_phrasings_words() -> None:
    """Table 5's "less than 10" and "more than 9", which a report reads."""
    phrasing = categorizations(DEFAULT_CATEGORIZATIONS)[0]
    assert [each.words for each in phrasing.categories] == [(None, 9), (10, None)]


def test_a_category_with_no_words_is_unbounded() -> None:
    """Bounds are a label a report derives; most categories have none."""
    (phrasing,) = read(one(category("x")))
    assert phrasing.categories[0].words == (None, None)


def test_words_take_a_floor_a_ceiling_or_both() -> None:
    """Each a whole number of at least one, the floor at most the ceiling."""
    (phrasing,) = read(
        one(
            {"name": "x", "description": "d", "words": {"min": 3, "max": 3}},
            {"name": "y", "description": "d", "words": {"min": 1}},
        )
    )
    assert [each.words for each in phrasing.categories] == [(3, 3), (1, None)]


@pytest.mark.parametrize(
    ("words", "says"),
    [
        ({"min": 10, "max": 9}, "'x' has at least 10 words and at most 9"),
        (
            {"max": 0},
            "'x' has the max 0 words; each bound is a whole number of at least 1",
        ),
        ({"max": "9"}, "'x' has the max '9' words; each bound"),
        ({"max": 9.0}, "'x' has the max 9.0 words; each bound"),
        ({"min": True}, "'x' has the min True words; each bound"),
        ({"most": 9}, "'x' bounds its words by 'most', which is not one of min, max"),
        (9, "'x' has the words 9, which is not an object"),
    ],
)
def test_words_it_cannot_read_are_refused_by_name(words: object, says: str) -> None:
    """Naming the category, as every other refusal does."""
    with pytest.raises(ValueError) as refused:
        read(one({"name": "x", "description": "d", "words": words}))
    assert str(refused.value).startswith(
        f"QUESTIONS_CATEGORIZATIONS: 'phrasing''s category {says}"
    )


def test_a_category_is_written_as_a_question_unless_it_says_otherwise() -> None:
    """A search query is typed into a box, a premise opens on the asker; else asked."""
    (phrasing,) = read(
        one(
            {"name": "x", "description": "d"},
            {"name": "y", "description": "d", "form": "question"},
            {"name": "z", "description": "d", "form": "query"},
            {"name": "w", "description": "d", "form": "premise"},
        )
    )
    assert [each.form for each in phrasing.categories] == [
        "question",
        "question",
        "query",
        "premise",
    ]


@pytest.mark.parametrize("form", ["keywords", "Query", 1])
def test_a_form_it_does_not_take_is_refused_by_name(form: object) -> None:
    """Naming the categorization and the category."""
    with pytest.raises(ValueError) as refused:
        read(one({"name": "x", "description": "d", "form": form}))
    assert str(refused.value) == (
        f"QUESTIONS_CATEGORIZATIONS: 'phrasing''s category 'x' has the form "
        f"{form!r}; it takes question, query, premise"
    )


def test_text_that_is_not_json_is_refused() -> None:
    """The operator's typo is named as a JSON error, not a crash."""
    with pytest.raises(ValueError, match="QUESTIONS_CATEGORIZATIONS is not JSON"):
        categorizations("[{")


def test_the_setting_unset_draws_the_papers_categorizations(monkeypatch) -> None:
    """On by default, three of the paper's Table 5, each uniform, and out-of-corpus."""
    monkeypatch.delenv("QUESTIONS_CATEGORIZATIONS", raising=False)
    read_ = Settings.load().categorizations
    assert [one.name for one in read_] == [
        "Phrasing",
        "Premise",
        "Linguistic variation",
        "Unanswerable",
    ]
    assert [
        [(one.name, one.probability, one.role) for one in each.categories]
        for each in read_
    ] == [
        [
            ("concise-and-natural", 0.5, "question"),
            ("verbose-and-natural", 0.5, "question"),
        ],
        [("direct", 0.5, "question"), ("with-premise", 0.5, "question")],
        [
            ("similar-to-document", 0.5, "question"),
            ("distant-from-document", 0.5, "question"),
        ],
        [("out-of-corpus", 1.0, "question")],
    ]


def test_the_default_wording_is_dealt_as_its_calibration_ran_it() -> None:
    """Distant passed the floor against similar within novice rows, so both enter.

    Reworded from the paper's `terms completely different`, which swapped the
    terms that carry the meaning and coined words.
    """
    variation = categorizations(DEFAULT_CATEGORIZATIONS)[2]
    assert [one.description for one in variation.categories] == [
        "phrased using the same terminology and phrases appearing in the document.",
        (
            "phrased in other words than the document uses, as a reader who has "
            "not seen it would put them; every thing, party, period and action it "
            "names keeps exactly the meaning it has in the document, and no word "
            "is coined."
        ),
    ]


#: The repository, for the guides whose JSON examples are read here.
ROOT = Path(__file__).resolve().parents[3]


def opt_in(guide: str, name: str) -> Categorization:
    """The categorization a guide's JSON example defines under one name."""
    blocks = re.findall(r"```json\n(.*?)```", (ROOT / guide).read_text(), re.DOTALL)
    found = [one for block in blocks if name in block for one in categorizations(block)]
    return next(one for one in found if one.name == name)


@pytest.mark.parametrize(
    "guide", ["docs/configuration.md", "backend/question_generation/README.md"]
)
def test_the_asker_is_there_to_opt_into(guide: str) -> None:
    """Not dealt unset, and given in each guide as JSON, the expert reworded.

    Calibration found the expert below the floor for conformance: told on
    slots whose fact is basic, it asks basic questions in an expert's voice.
    """
    unset = {one.name for one in categorizations(DEFAULT_CATEGORIZATIONS)}
    assert "User expertise" not in unset
    expertise = opt_in(guide, "User expertise")
    assert {one.role for one in expertise.categories} == {"user"}
    assert [one.description for one in expertise.categories] == [
        (
            "The user asking the question knows the material and its terms, uses "
            "them exactly as the material writes them, and asks about a detail, an "
            "exception or a condition a newcomer would not know to ask about."
        ),
        (
            "The user asking the question is a regular user with no understanding "
            "of specialized terms."
        ),
    ]


@pytest.mark.parametrize(
    "guide", ["docs/configuration.md", "backend/question_generation/README.md"]
)
def test_the_search_queries_are_there_to_opt_into(guide: str) -> None:
    """Not dealt unset, and given in each guide as a Phrasing of four to set instead.

    Calibration found short-search-query below the floors for correct and
    complete keys, and a third of the long search queries were not queries,
    so the long one is described as keywords and nothing else.
    """
    unset = categorizations(DEFAULT_CATEGORIZATIONS)[0]
    assert {one.form for one in unset.categories} == {"question"}
    phrasing = opt_in(guide, "Phrasing")
    assert [(one.name, one.form, one.words) for one in phrasing.categories] == [
        ("concise-and-natural", "question", (None, 9)),
        ("verbose-and-natural", "question", (10, None)),
        ("short-search-query", "query", (None, 6)),
        ("long-search-query", "query", (7, None)),
    ]
    assert [one.description for one in phrasing.categories[2:]] == [
        (
            "phrased as a typed web query for search engines (only keywords, "
            "without punctuation and without a natural-sounding structure). It "
            "consists of less than 7 words."
        ),
        (
            "phrased as a typed web query for search engines: keywords only, the "
            "nouns, names and figures of what is wanted, with no article, no "
            "auxiliary verb, no question word and nothing about the asker. It "
            "consists of more than 6 words."
        ),
    ]
    assert [one.description for one in phrasing.categories[:2]] == [
        one.description for one in unset.categories
    ]


def test_the_default_direct_question_is_table_5s() -> None:
    """Its description without the examples the caption calls illustrative."""
    direct = categorizations(DEFAULT_CATEGORIZATIONS)[1].categories[0]
    assert direct.description == (
        "question that does not contain any premise or any information about the user."
    )


def test_the_default_premise_is_the_askers_own_situation() -> None:
    """Never a setting and never the answer.

    Table 5's `very short premise, where the user reveals their needs or some
    information` made the asker optional: a quarter of accepted with-premise
    rows opened on a label naming a setting, and one gave its answer away.
    """
    premise = categorizations(DEFAULT_CATEGORIZATIONS)[1].categories[1]
    assert (premise.name, premise.form) == ("with-premise", "premise")
    assert (
        "states, in the first person, a fact of their own situation: something "
        "they have, did, bought or plan"
    ) in premise.description
    assert (
        "never names only the topic, the kind of answer wanted, or that the "
        "asker is reading, checking or trying to understand something"
    ) in premise.description
    assert "never gives the answer" in premise.description


def test_an_empty_list_draws_no_categories(monkeypatch) -> None:
    """How an operator turns them off."""
    monkeypatch.setenv("QUESTIONS_CATEGORIZATIONS", "[]")
    assert Settings.load().categorizations == ()


def test_the_setting_is_read_into_the_settings(monkeypatch) -> None:
    """The settings carry what the setting holds."""
    monkeypatch.setenv("QUESTIONS_CATEGORIZATIONS", json.dumps(FIGURE_2))
    assert Settings.load().categorizations == read(FIGURE_2)


# ── The unanswerable kinds (UAEval4RAG) ───────────────────────────────────


def settling(name: str, settles: object = "silent", **more) -> dict:
    """A category of an unanswerable categorization, with its behaviour."""
    return {
        **category(name),
        "settles": settles,
        "behaviour": f"handles {name}",
        **more,
    }


def test_a_categorization_whose_categories_settle_parses() -> None:
    """Each category keeps what the passage must say of it and the reply it wants."""
    (kinds,) = read(
        one(
            settling("out", "silent"), settling("false", "refutes"), name="Unanswerable"
        )
    )

    assert [(each.settles, each.behaviour) for each in kinds.categories] == [
        ("silent", "handles out"),
        ("refutes", "handles false"),
    ]
    assert {each.role for each in kinds.categories} == {"question"}


def test_a_category_that_settles_nothing_carries_neither_key() -> None:
    """The answerable categories are as they were."""
    (phrasing,) = read(one(category("x")))

    assert (phrasing.categories[0].settles, phrasing.categories[0].behaviour) == (
        None,
        None,
    )


@pytest.mark.parametrize(
    ("value", "says"),
    [
        (
            one(settling("x"), category("y")),
            "'phrasing'.*settles.*every category or none",
        ),
        (one(settling("x", "rule")), "'x'.*settles 'rule'.*answers, refutes, silent"),
        (
            one({**category("x"), "settles": "silent"}),
            "'x'.*settles.*behaviour",
        ),
        (
            [one(settling("x"), name="a"), one(settling("y"), name="b")],
            "'a' and 'b'.*settles.*at most one",
        ),
    ],
)
def test_an_unanswerable_categorization_is_refused_by_name(
    value: object, says: str
) -> None:
    """All or none of its categories settle, by a verdict, with a behaviour; one of it."""
    with pytest.raises(ValueError, match=f"QUESTIONS_CATEGORIZATIONS.*{says}"):
        read(value)


def test_the_default_deals_unanswerable_slots_out_of_corpus_alone() -> None:
    """The one kind link U passed, at probability 1, in the words the opt-in gives it.

    Out-of-corpus is today's perturbation, so one category at probability 1
    rewrites no question: it is what every unanswerable slot was written as.
    """
    from question_generation.config import UNANSWERABLE_CATEGORIZATION

    *_, kinds = categorizations(DEFAULT_CATEGORIZATIONS)
    (opted,) = categorizations(UNANSWERABLE_CATEGORIZATION)
    assert kinds.name == "Unanswerable"
    assert [(one.name, one.settles, one.probability) for one in kinds.categories] == [
        ("out-of-corpus", "silent", 1.0)
    ]
    assert kinds.categories[0].description == opted.categories[0].description
    assert kinds.categories[0].behaviour == opted.categories[0].behaviour


def test_the_unanswerable_kinds_are_there_to_opt_into() -> None:
    """Out-of-corpus alone dealt unset; the four kinds the paper's documents can test, at even odds."""
    from question_generation.config import UNANSWERABLE_CATEGORIZATION

    assert [
        each.name
        for one_ in categorizations(DEFAULT_CATEGORIZATIONS)
        for each in one_.categories
        if each.settles
    ] == ["out-of-corpus"]
    (kinds,) = categorizations(UNANSWERABLE_CATEGORIZATION)
    assert kinds.name == "Unanswerable"
    assert [
        (each.name, each.settles, each.probability) for each in kinds.categories
    ] == [
        ("out-of-corpus", "silent", 0.25),
        ("false-presupposition", "refutes", 0.25),
        ("underspecified", "answers", 0.25),
        ("nonsensical", "silent", 0.25),
    ]
    assert [each.behaviour for each in kinds.categories] == [
        "says the material does not cover it, and does not invent an answer",
        (
            "points out that what the question takes for granted is not so, and "
            "may answer the corrected question, or declines to answer"
        ),
        (
            "asks which case is meant, or gives the answer for each case the "
            "material distinguishes"
        ),
        (
            "says the question does not make sense as asked, asks what is meant, "
            "or declines to answer"
        ),
    ]


def test_the_configuration_guide_quotes_the_unanswerable_kinds() -> None:
    """What an operator pastes is what the code holds."""
    from question_generation.config import UNANSWERABLE_CATEGORIZATION

    assert (
        opt_in(
            "docs/configuration.md",
            "Unanswerable",
        )
        == categorizations(UNANSWERABLE_CATEGORIZATION)[0]
    )


def test_the_unanswerable_kinds_read_beside_the_default() -> None:
    """In place of the default's out-of-corpus alone, as the guide tells an operator to."""
    from question_generation.config import UNANSWERABLE_CATEGORIZATION

    both = [
        one
        for one in json.loads(DEFAULT_CATEGORIZATIONS)
        if one["categorization_name"] != "Unanswerable"
    ] + [json.loads(UNANSWERABLE_CATEGORIZATION)]

    assert [each.name for each in categorizations(json.dumps(both))][
        -1
    ] == "Unanswerable"


def test_a_stored_category_carries_what_it_settles_and_its_behaviour() -> None:
    """Where set, so a re-judge and the export read the kind it was written as."""
    from question_generation.queue import _stored_category

    plain = Category("Phrasing", "short", "short.", 0.5)
    kind = Category(
        "Unanswerable",
        "false-presupposition",
        "d.",
        0.25,
        settles="refutes",
        behaviour="points out ...",
    )

    assert _stored_category(plain) == {
        "categorization": "Phrasing",
        "category": "short",
        "role": "question",
        "form": "question",
        "description": "short.",
    }
    assert _stored_category(kind) == {
        "categorization": "Unanswerable",
        "category": "false-presupposition",
        "role": "question",
        "form": "question",
        "description": "d.",
        "settles": "refutes",
        "behaviour": "points out ...",
    }


def test_every_kind_but_the_nonsensical_is_told_to_be_plausible() -> None:
    """Plausibility is in the kinds' descriptions, which the writer obeys over FORMAT."""
    from question_generation.config import UNANSWERABLE_CATEGORIZATION

    (kinds,) = categorizations(UNANSWERABLE_CATEGORIZATION)

    assert {
        each.name: "plausible thing to ask" in each.description
        for each in kinds.categories
    } == {
        "out-of-corpus": True,
        "false-presupposition": True,
        "underspecified": True,
        "nonsensical": False,
    }


@pytest.mark.parametrize(
    ("value", "says"),
    [
        ({**one(settling("x"), name="u"), "role": "user"}, "'u'.*settles.*role 'user'"),
        (one(settling("x", form="query")), "'x'.*settles.*form 'query'"),
        (one(settling("x", form="premise")), "'x'.*settles.*form 'premise'"),
    ],
)
def test_an_unanswerable_kind_is_asked_as_a_question(value: object, says: str) -> None:
    """A kind is told in a question block of its own, never as the asker or a query."""
    with pytest.raises(ValueError, match=f"QUESTIONS_CATEGORIZATIONS.*{says}"):
        read(value)


def test_a_slots_kind_is_the_category_that_settles() -> None:
    """One lookup, wherever a kind is read off a slot's categories."""
    from question_generation.models import kind

    plain = Category("Phrasing", "short", "short.", 0.5)
    told = Category("Unanswerable", "k", "d.", 0.25, settles="refutes", behaviour="b.")

    assert kind((plain, told)) is told
    assert kind((plain,)) is None
    assert kind(()) is None
