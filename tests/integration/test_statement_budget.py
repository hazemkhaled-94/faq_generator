"""What each page's route may ask of the database, however large the corpus.

A budget is a number of statements, not of seconds: it holds on a laptop and
on a build host, and it does not grow with the rows. Each route is read over a
corpus of a few hundred questions, so a statement per row would blow it.
"""

from __future__ import annotations

import pytest
from budget import counted
from seed import digest, document, fact, link, passage, question
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

#: Questions in the corpus, each resting on a fact of its own.
SIZE = 300

#: The statements a route may issue, by the request it answers.
BUDGET = {
    # What it costs today: a statement per spread, each re-evaluating the filter.
    "/questions/quality": 18,
    "/questions": 2,
    "/facts": 3,
    "/extraction/status": 1,
    "/questions/status": 1,
}


@pytest.fixture
def corpus(client, engine):
    """A few hundred questions, accepted and not, over one document."""
    sha = digest("budget")
    with Session(engine) as session:
        session.add(document(sha, language="en", chunk_status="chunked"))
        session.flush()
        held = passage(sha, ordinal=1, language="en")
        session.add(held)
        session.flush()
        for number in range(SIZE):
            drawn = fact(held.id, statement=f"Statement {number} is true.")
            session.add(drawn)
            session.flush()
            asked = question(
                question_text=f"Is statement {number} true?",
                status="accepted" if number % 3 else "rejected",
                rejected_reason=None if number % 3 else "duplicate",
                difficulty=("easy", "medium", "hard")[number % 3],
                categories=[{"categorization": "style", "category": f"s{number % 4}"}],
            )
            session.add(asked)
            session.flush()
            session.add(link(asked.id, drawn.id))
        session.commit()
    return client


@pytest.mark.parametrize("path", sorted(BUDGET))
def test_a_route_stays_within_its_statement_budget(corpus, path: str) -> None:
    """The questions page recomputed its filter eighteen times per redraw."""
    with counted() as spent:
        answered = corpus.get(path)

    assert answered.status_code == 200, answered.text
    assert len(spent) <= BUDGET[path], f"{len(spent)} statements:\n{spent.describe()}"
