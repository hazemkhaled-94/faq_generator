"""The export's command line, against the vocabularies its columns hold.

`GET /questions/export` refuses a value its Literal does not list with a
422. The command line reads the same filters, and a typo there is a
workbook of nothing written without a word, which reads as "no question
of that type" rather than "no such type".
"""

from __future__ import annotations

import pytest

from database.qa_generator import outcomes
from question_generation.export import parser

#: Each filter that offers choices, and the column vocabulary it narrows.
_CHOSEN = {
    "--status": outcomes.QuestionStatus,
    "--difficulty": outcomes.Difficulty,
    "--planned-difficulty": outcomes.Difficulty,
    "--cognitive-level": outcomes.CognitiveLevel,
    "--passage-scope": outcomes.PassageScope,
    "--document-scope": outcomes.DocumentScope,
    "--topic-scope": outcomes.TopicScope,
}


def _choices(flag: str) -> set[str]:
    """What one flag of the export accepts."""
    (action,) = [one for one in parser()._actions if flag in one.option_strings]
    return set(action.choices or ())


@pytest.mark.parametrize("flag", sorted(_CHOSEN))
def test_a_filter_offers_exactly_the_values_its_column_holds(flag) -> None:
    """None missing, so every stored value can be exported, and none extra."""
    assert _choices(flag) == {one.value for one in _CHOSEN[flag]}


@pytest.mark.parametrize(
    ("flag", "value"),
    [(flag, one.value) for flag, kind in _CHOSEN.items() for one in kind],
)
def test_every_value_a_column_holds_is_taken(flag, value) -> None:
    """Parsed as given."""
    parsed = parser().parse_args(["--out", "x.xlsx", flag, value])

    assert vars(parsed)[flag.removeprefix("--").replace("-", "_")] == value


@pytest.mark.parametrize(
    ("flag", "typo"),
    [("--question-type", "factiod"), ("--answer-form", "valeu")],
)
def test_a_type_or_form_that_is_not_one_is_refused(flag, typo) -> None:
    """As the route refuses it, rather than selecting nothing."""
    with pytest.raises(SystemExit):
        parser().parse_args(["--out", "x.xlsx", flag, typo])
