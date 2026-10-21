"""What a pull writes, over any mix of answers a dataset can hold.

`test_service.py` names the cases one at a time. The rule they add up to is
one sentence, and this states it over every mix of reviewers, drafts and
discarded answers Hypothesis can build: a row is written exactly when it has
a submitted answer and every submitted answer agrees, and it is written with
that answer.
"""

from __future__ import annotations

import pytest

pytest.importorskip("argilla", reason="the observability group is not installed")

from hypothesis import given
from hypothesis import strategies as st
from test_service import (
    ANSWERED,
    Client,
    Dataset,
    Facts,
    Questions,
    Record,
    Response,
    Topics,
)

from review import datasets
from review.config import Settings
from review.service import Catalogs, pull

SETTINGS = Settings(
    api_url="http://argilla:6900",
    api_key="key",
    workspace="qa_generator",
    sample=10,
)

#: One reviewer's answer to the verdict question: its status, then its value.
_ANSWER = st.tuples(
    st.sampled_from(["submitted", "draft", "discarded"]),
    st.sampled_from(["accepted", "rejected"]),
)

#: A dataset: distinct row ids, each with between none and four answers.
_HELD = st.dictionaries(
    st.integers(min_value=1, max_value=10_000),
    st.lists(_ANSWER, max_size=4),
    max_size=12,
)


def _records(held: dict, key: str) -> list[Record]:
    """The dataset as the pull reads it."""
    return [
        Record({key: row_id}, [Response("verdict", value, said) for said, value in got])
        for row_id, got in held.items()
    ]


def _agreed(held: dict) -> dict[int, str]:
    """The rule: the one value every submitted answer gives, where there is one."""
    agreed = {}
    for row_id, got in held.items():
        values = {value for said, value in got if said == "submitted"}
        if len(values) == 1:
            agreed[row_id] = values.pop()
    return agreed


def _pulled(name: str, key: str, held: dict) -> Catalogs:
    """Runs one pull over this dataset, timed as Argilla's listing times it."""
    records = _records(held, key)
    catalogs = Catalogs(facts=Facts(), questions=Questions(), topics=Topics())
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "review.service.connect", lambda settings: Client(Dataset(records))
        )
        # Only a record with a submitted answer has a time, as `_given_at` reads it.
        patch.setattr(
            "review.service._given_at",
            lambda client, dataset, key: {
                row_id: ANSWERED
                for row_id, got in held.items()
                if any(said == "submitted" for said, _ in got)
            },
        )
        written = pull(name, SETTINGS, catalogs)
    assert written == len(_agreed(held))
    return catalogs


@given(held=_HELD)
def test_a_fact_is_written_exactly_when_its_submitted_answers_agree(held) -> None:
    """With that answer, dated when it was given; a draft never counts."""
    catalogs = _pulled(datasets.FACTS, "fact_id", held)

    assert {row: verdict for row, verdict, _ in catalogs.facts.written} == _agreed(held)
    assert {at for _, _, at in catalogs.facts.written} <= {ANSWERED}


@given(held=_HELD)
def test_a_question_is_decided_exactly_when_its_submitted_answers_agree(
    held,
) -> None:
    """Through `decide`, which PATCH /questions/{id} also calls, and dated."""
    catalogs = _pulled(datasets.QUESTIONS, "question_id", held)

    assert dict(catalogs.questions.decided) == _agreed(held)
    assert {row for row, _ in catalogs.facts.dated} == set(_agreed(held))
