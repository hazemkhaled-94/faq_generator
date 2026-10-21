"""The filters the API offers against the values the database holds.

A route spells its choices as a `Literal` so the OpenAPI document lists them
and the frontend's pickers cannot drift from what the backend will accept.
That is two copies of one vocabulary, and the copy in the route is the one
nothing else would notice going stale: adding a question type reaches the
enum, the CHECK constraint and the writer, and a listing that cannot filter
to the new kind still answers every request it is given.

Which is what happened. `implication` and `application` were written,
stored and constrained for a day before the route's list knew about them.
"""

from __future__ import annotations

from typing import get_args

import pytest

from database.qa_generator import (
    AnswerForm,
    CognitiveLevel,
    Difficulty,
    DocumentScope,
    PassageScope,
    QuestionType,
    TopicScope,
)

#: Each route alias beside the enum it has to agree with. The route is
#: imported lazily inside the test so this module stays cheap to collect.
PINNED = {
    "QuestionType": QuestionType,
    "CognitiveLevel": CognitiveLevel,
    "AnswerForm": AnswerForm,
    "PassageScope": PassageScope,
    "DocumentScope": DocumentScope,
    "TopicScope": TopicScope,
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_a_filter_offers_exactly_what_the_column_holds(name: str) -> None:
    """Neither more than the database accepts nor less than it stores."""
    from api.routes import questions

    offered = set(get_args(getattr(questions, name)))
    held = {str(one) for one in PINNED[name]}

    assert offered == held, (
        f"{name}: the route offers {sorted(offered - held)} that no column "
        f"holds, and is missing {sorted(held - offered)} that one does"
    )


def test_the_assessment_filter_offers_every_metric_a_verdict_carries() -> None:
    """`?metric=toxicity` answered 422 while toxicity was being judged."""
    from api.routes import assessment
    from database.qa_generator import JudgeMetric

    assert set(get_args(assessment.Metric)) == {str(one) for one in JudgeMetric}


def test_the_band_filter_offers_exactly_the_three_bands() -> None:
    """Spelled `Band` rather than after its enum, so it is checked by name."""
    from api.routes import questions

    assert set(get_args(questions.Band)) == {str(one) for one in Difficulty}


def test_the_settings_route_offers_exactly_the_services_the_catalogue_has() -> None:
    """The one vocabulary that was written out twice, and drifted.

    `settings.catalog.Service` is what a setting declares itself under and
    what the Configuration panel is drawn from; the route has a Literal of
    its own so the OpenAPI document lists the services and an unknown one
    is refused before it reaches the catalogue. Two lists, and nothing held
    them together.

    Adding the evaluation phase added a service to the catalogue and not to
    the route, so every setting of it was described, served read-only by
    nothing, and `GET /settings/assessment` answered 422 - which reaches a
    person as a Configuration panel that will not open on one page and
    works on the other six.
    """
    from api.routes import settings as route
    from settings.catalog import Service

    offered = set(get_args(route.Service))
    described = set(get_args(Service))

    assert offered == described, (
        f"the route offers {sorted(offered - described)} that the catalogue "
        f"does not describe, and is missing {sorted(described - offered)} "
        f"that it does"
    )


def test_every_service_the_catalogue_names_has_a_setting() -> None:
    """A service with nothing to configure draws an empty panel."""
    from settings.catalog import SETTINGS, Service

    described = {one.service for one in SETTINGS}

    assert set(get_args(Service)) == described


def test_a_pulled_topic_name_is_held_to_what_patch_topics_takes() -> None:
    """`review-pull` names a topic through the same write as PATCH /topics."""
    pytest.importorskip("argilla", reason="the observability group is not installed")
    from api.routes.topics import TopicDescription
    from review.service import LABEL_MAX

    (bound,) = [
        one.max_length for one in TopicDescription.model_fields["label"].metadata
    ]

    assert LABEL_MAX == bound
