"""Pushing rows out for review, and pulling the verdicts back.

Two directions and one rule: the database decides. Argilla holds a copy of
what was put in front of somebody and the answers they gave, and `pull`
brings the answers home. Delete the Argilla dataset and nothing in the
pipeline is lost; delete the rows and the copy is meaningless.

A pull takes only submitted answers. Argilla keeps a draft the moment a
reviewer touches a record, and a draft is somebody part-way through
thinking rather than a decision.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import argilla as rg

from review import datasets
from review.config import Settings
from review.judged import UNJUDGED, opinions
from review.records import ReviewRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Catalogs:
    """Where each kind of verdict is read from and written back to.

    The existing catalogues, not new queries. A topic renamed here and a
    topic renamed on the Topics page have to be the same write, or the
    provenance the two record drifts apart - `describe` is what sets
    labelled_by to `person`, and a second path that forgot to would leave
    a human label looking like the model's.
    """

    #: Facts: the sample, and the only verdict with no route of its own.
    facts: ReviewRepository
    #: Questions: `decide`, which PATCH /questions/{id} also calls.
    questions: Any
    #: Topics: `describe`, which PATCH /topics/{id} also calls.
    topics: Any
    #: What the LLM judge said about each row, attached to the record so a
    #: reviewer sees both machine verdicts. None reads as "nobody judged
    #: anything", which is the honest answer for a deployment with the
    #: evaluation phase switched off - and is what keeps a push working
    #: without one.
    judge: Any = None


def connect(settings: Settings) -> rg.Argilla:
    """Opens the client and makes sure the workspace is there."""
    client = rg.Argilla(api_url=settings.api_url, api_key=settings.api_key)
    if client.workspaces(settings.workspace) is None:
        log.info("creating workspace %s", settings.workspace)
        client.workspaces.add(rg.Workspace(name=settings.workspace))
    return client


def _warn_if_stale(found: rg.Dataset, name: str) -> None:
    """Says so when a dataset predates something the records now carry.

    Argilla drops a field or a metadata term a record sets and the dataset
    does not declare. It does not refuse the push and it does not warn: the
    records arrive, and the part the dataset never heard of is simply not
    there.

    That is how the judge's verdict went missing the first time it was
    pushed. The datasets had been created before the evaluation phase
    existed, `_dataset` reuses what it finds rather than recreating it -
    deliberately, because recreating throws away every answer not yet
    pulled - and the push reported 38 records written with nothing on them.

    Warned rather than fixed automatically, for the same reason: what to do
    about it depends on whether anybody has answered. The warning counts
    the submitted answers the dataset holds and names the pull to run
    before deleting it in Argilla.
    """
    try:
        declared = {one.name for one in found.settings.fields} | {
            one.name for one in found.settings.metadata
        }
        wanted = {one.name for one in datasets.SETTINGS[name]().fields} | {
            one.name for one in datasets.SETTINGS[name]().metadata
        }
        missing = sorted(wanted - declared)
        waiting = len(answered(found)) if missing else 0
    except Exception as unreadable:  # noqa: BLE001 - any of them means quiet
        # Best-effort, like every other diagnostic in this repository: a
        # warning that cannot be worked out must not fail the push it was
        # only ever commenting on.
        log.debug("could not compare %s against its settings: %s", name, unreadable)
        return
    if not missing:
        return
    log.warning(
        "the Argilla dataset %s was created before %s existed, so Argilla "
        "will DROP %s from every record this push writes. It holds %d "
        "submitted answer(s), and deleting it loses every one not yet "
        "pulled: run `make review-pull-%s` first, then delete the dataset "
        "in Argilla and push again.",
        found.name,
        ", ".join(missing),
        ", ".join(missing),
        waiting,
        "topics" if name == datasets.TOPIC_LABELS else name,
    )


def _dataset(client: rg.Argilla, settings: Settings, name: str) -> rg.Dataset:
    """The dataset by that name, created on first push.

    Not recreated if it is there: a dataset holds the answers given so far,
    and a push that dropped it would throw away every verdict not yet
    pulled. What that costs when the settings have moved on is
    :func:`_warn_if_stale`.
    """
    held = datasets.dataset_name(name)
    found = client.datasets(name=held, workspace=settings.workspace)
    if found is not None:
        _warn_if_stale(found, name)
        return found
    log.info("creating dataset %s in %s", held, settings.workspace)
    return rg.Dataset(
        name=held,
        workspace=settings.workspace,
        settings=datasets.SETTINGS[name](),
        client=client,
    ).create()


def push(
    name: str,
    settings: Settings,
    catalogs: Catalogs,
    ids: Sequence[int] | None = None,
    everything: bool = False,
) -> int:
    """Puts one kind of row in front of a reviewer.

    `ids` names exactly which questions to push instead of sampling, which
    is how a queue built elsewhere - `evaluation.second_opinion`'s
    disagreements - reaches a reviewer. Questions only; the other two sets
    have no such queue behind them.

    `everything` pushes the corpus rather than a draw from it. The two
    answer different questions and both are worth having: a sample is
    "is the checker right", small enough that somebody finishes it; the
    whole set is "where is the artefact I am looking for", which a draw
    cannot answer because the row wanted may not be in it. One dataset per
    kind either way, so the two never mix in one place.

    Returns:
        How many records were written.
    """
    client = connect(settings)
    dataset = _dataset(client, settings, name)
    draw = None if everything else settings.sample

    if name == datasets.FACTS:
        rows = catalogs.facts.facts(draw)
        said = opinions(catalogs.judge, "fact", [one.id for one in rows])
        records = [
            datasets.fact_record(one, said.get(one.id, UNJUDGED)) for one in rows
        ]
    elif name == datasets.QUESTIONS:
        # What says a sample has nothing left to ask about this row. Read
        # off Argilla rather than off `questions.reviewed_verdict`, which
        # exists now and is not the same set: a verdict submitted in the UI
        # and not yet pulled is in Argilla and not in the column, and
        # pushing that row again asks somebody to judge it twice.
        # Never for an explicit queue: naming an id asks for that row.
        judged = set() if ids else answered(dataset)
        rows = [
            one
            for one in catalogs.facts.questions(draw, ids)
            if str(one.id) not in judged
        ]
        said = opinions(catalogs.judge, "question", [one.id for one in rows])
        records = [
            datasets.question_record(one, said.get(one.id, UNJUDGED)) for one in rows
        ]
    else:
        # Every topic, not a sample. A corpus has dozens, not thousands,
        # and a topic left unreviewed is one whose name nobody checked.
        rows = catalogs.topics.topics()
        said = opinions(catalogs.judge, "topic", [one.id for one in rows])
        records = [
            datasets.topic_record(one, said.get(one.id, UNJUDGED)) for one in rows
        ]

    if not records:
        log.info("%s: nothing left to review", name)
        return 0
    dataset.records.log(records)
    log.info("%s: %d record(s) pushed to %s", name, len(records), settings.api_url)
    return len(records)


def drop(settings: Settings) -> int:
    """Deletes every dataset in the workspace, and says how many went.

    The opposite decision from :func:`_dataset`, which reuses what it finds
    precisely so a push never throws away an answer nobody has pulled. This
    throws them away on purpose: `make wipe` deletes the corpus, and a
    dataset of facts that no longer exist is a reviewer being asked about
    rows nothing can apply their verdict to.

    Pull before wiping if the verdicts matter. Nothing here warns about
    that, because `wipe` already says what it is about to do and waits.

    Returns:
        How many datasets were deleted.
    """
    client = connect(settings)
    deleted = 0
    for name in datasets.NAMES:
        held = datasets.dataset_name(name)
        found = client.datasets(name=held, workspace=settings.workspace)
        if found is None:
            continue
        log.info("deleting dataset %s", held)
        found.delete()
        deleted += 1
    return deleted


def pull(name: str, settings: Settings, catalogs: Catalogs) -> int:
    """Brings submitted verdicts back into the database.

    Returns:
        How many rows were written.
    """
    client = connect(settings)
    dataset = client.datasets(
        name=datasets.dataset_name(name), workspace=settings.workspace
    )
    if dataset is None:
        log.info("%s: no such dataset; nothing has been pushed yet", name)
        return 0

    key, text = _KEYS[name]
    given = _given_at(client, dataset, key)
    submitted = [
        record
        for record in dataset.records(with_responses=True)
        if int(record.metadata[key]) in given
    ]
    rows = catalogs.facts.held(name, [int(one.metadata[key]) for one in submitted])
    answered, moved, later, disputed = [], 0, 0, []
    for record in submitted:
        row_id = int(record.metadata[key])
        row, at = rows.get(row_id), given[row_id]
        if row is None or row.text != record.fields[text]:
            moved += 1
        elif row.decided is not None and row.decided >= at:
            later += 1
        elif _disagreed(record):
            disputed.append(row_id)
        else:
            answered.append((row_id, record, at))
    if moved:
        log.warning(
            "%s: %d answer(s) skipped because the row with that id no longer "
            "reads as the record does, so the answer is about another row",
            name,
            moved,
        )
    if later:
        log.info(
            "%s: %d answer(s) skipped because the row was decided at or after "
            "the answer was given: pulled already, or decided since",
            name,
            later,
        )
    if disputed:
        log.warning(
            "%s: %d record(s) skipped because their reviewers disagree; both "
            "answers stay in Argilla for a person to settle: %s",
            name,
            len(disputed),
            ", ".join(map(str, disputed)),
        )

    if name == datasets.FACTS:
        written = catalogs.facts.review_facts(
            [
                (row_id, verdict, at)
                for row_id, record, at in answered
                if (verdict := _answer(record, "verdict")) is not None
            ]
        )
    elif name == datasets.QUESTIONS:
        dated = [
            (row_id, at)
            for row_id, record, at in answered
            if (verdict := _answer(record, "verdict")) is not None
            and catalogs.questions.decide(row_id, verdict)
        ]
        catalogs.facts.date_questions(dated)
        written = len(dated)
    else:
        written = sum(
            bool(
                catalogs.topics.describe(
                    row_id,
                    label=_answer(record, "corrected_label"),
                    # Absent means unanswered, and an unanswered coverage
                    # question must not read as "take it out of coverage".
                    include_in_coverage=_answer(record, "in_coverage") != "no",
                )
            )
            for row_id, record, _ in answered
            if _answer(record, "corrected_label") is not None
            or _answer(record, "in_coverage") is not None
        )

    log.info("%s: %d verdict(s) written", name, written)
    return written


#: How Argilla spells a response somebody has finished giving.
_SUBMITTED = ("submitted", "ResponseStatus.submitted")

#: Each dataset's id metadata, and the field holding the text a reviewer read.
_KEYS = {
    datasets.FACTS: ("fact_id", "statement"),
    datasets.QUESTIONS: ("question_id", "question"),
    datasets.TOPIC_LABELS: ("topic_id", "terms"),
}

#: How many records one page of Argilla's listing asks for.
_PAGE = 256


def _given_at(client: rg.Argilla, dataset: rg.Dataset, key: str) -> dict[int, datetime]:
    """When each row's latest submitted answer was given, by the row's id.

    Read off Argilla's REST listing: the SDK drops a response's timestamps.
    A pull applies an answer only where every submitted one agrees, so the
    latest is when the applied answer was last given.
    """
    # ponytail: a second read of the dataset beside the SDK's, so a response
    # submitted between the two reads can be applied with the time before
    # it. Upgrade: read answers and times from this one listing.
    given: dict[int, datetime] = {}
    offset = 0
    while True:
        page = client.http_client.get(
            f"/api/v1/datasets/{dataset.id}/records",
            params={"offset": offset, "limit": _PAGE, "include": ["responses"]},
        )
        page.raise_for_status()
        items = page.json()["items"]
        for item in items:
            times = [
                datetime.fromisoformat(one["updated_at"])
                for one in item.get("responses") or ()
                if one["status"] == "submitted"
            ]
            if times:
                # Argilla writes UTC without an offset.
                given[int(item["metadata"][key])] = max(
                    one if one.tzinfo else one.replace(tzinfo=UTC) for one in times
                )
        if len(items) < _PAGE:
            return given
        offset += len(items)


def answered(dataset) -> set[str]:
    """The records of one dataset that already carry a submitted answer."""
    return {
        str(record.id)
        for record in dataset.records(with_responses=True)
        if any(str(one.status) in _SUBMITTED for one in record.responses)
    }


def _disagreed(record) -> bool:
    """Whether two submitted answers to one question differ."""
    said: dict[str, set] = {}
    for response in record.responses:
        if str(response.status) in _SUBMITTED:
            said.setdefault(response.question_name, set()).add(response.value)
    return any(len(values) > 1 for values in said.values())


def _answer(record, question: str) -> str | None:
    """What a reviewer submitted for one question, or None.

    Drafts are skipped. Argilla saves one the moment a record is touched,
    so a draft is somebody part-way through rather than a decision, and
    writing it back would record an opinion nobody has finished having.
    """
    for response in record.responses:
        if response.question_name == question and str(response.status) in _SUBMITTED:
            return response.value
    return None
