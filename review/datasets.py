"""The three datasets, as Argilla holds them.

One per thing a model decided and a person may disagree with:

    facts         is this statement true, and does the evidence support it?
    topic-labels  is this a good name for these terms, and is it a subject?
    questions     would somebody ask this, and is the answer right?

Each carries the machine's own verdict as metadata rather than hiding it.
A reviewer told nothing sees a wall of statements; a reviewer told "the
checker refused this one for unsupported_addition" is answering the
question the review is actually for, which is whether the checker is
right. The risk is anchoring, and it is the lesser one: a sample nobody
can interpret gets abandoned.

The database stays the source of truth. Argilla holds a copy of the rows
put in front of somebody and the answers they gave; `review-pull` brings
the answers back and the copy is disposable.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import argilla as rg

from review.config import Settings
from review.judged import UNJUDGED, Opinion
from review.records import FactRow, QuestionRow
from telemetry import pipeline

log = logging.getLogger(__name__)

#: What the CLI takes, and what the code branches on.
FACTS = "facts"
TOPIC_LABELS = "topic-labels"
QUESTIONS = "questions"
NAMES = (FACTS, TOPIC_LABELS, QUESTIONS)

#: Which stage produces each kind. What Argilla shows is numbered with the
#: stage's place in the pipeline, because Argilla sorts its datasets by
#: name and `facts, questions, topic-labels` is not the order they are
#: produced in. The number means what it means in Phoenix's projects and
#: Dagster's groups: the same step seen from another side.
STAGES = {
    FACTS: "extraction",
    TOPIC_LABELS: "topic_modelling",
    QUESTIONS: "question_generation",
}


def dataset_name(name: str) -> str:
    """What Argilla holds one kind under, numbered by its stage.

    Carries the database, because the workspace is one for every database
    and a pull by a bare name wrote another database's verdicts here.
    """
    return pipeline.scoped(pipeline.numbered(name, STAGES.get(name)))


#: The one question every verdict dataset asks. Two labels and no middle:
#: "unsure" is where a review goes to not happen, and a reviewer who
#: genuinely cannot tell should leave the record unanswered, which Argilla
#: already distinguishes from an answer.
_VERDICT = ["accepted", "rejected"]


def _judge_metadata() -> list[rg.TermsMetadataProperty]:
    """What the evaluation phase said, as the two terms it is filtered by.

    Two properties rather than one: `judge_verdict` is the verdict and is
    what a reviewer narrows by, and `judge_disagrees` is the pair worth a
    sitting of their own - the artefacts the pipeline kept and the judge
    refused.

    `judge_verdict` rather than `judge`, because the FIELD carrying the
    reasoning is called that and **Argilla requires every name in a
    dataset's settings to be unique across fields, questions and metadata
    together**. Two of them called `judge` is refused at dataset creation
    with `SettingsError`, which reaches a person as a push that will not
    run. See `tests/static/test_review_datasets.py`.

    A function and not a constant, like every other declaration in this
    module: building an `rg.` object reaches for the default client, so one
    at import time makes importing this module require a running Argilla.
    """
    return [
        rg.TermsMetadataProperty(name="judge_verdict", title="What the LLM judge said"),
        rg.TermsMetadataProperty(
            name="judge_disagrees", title="Judge disagrees with the pipeline"
        ),
    ]


def _judge_field() -> rg.TextField:
    """The field carrying the judge's reasoning.

    Not required: the phase may be off, or may not have reached this row,
    and a required field would make a record unpushable in both cases.
    """
    return rg.TextField(
        name="judge", title="What the LLM judge said, and why", required=False
    )


#: The paragraph added to every dataset's guidelines. One wording for all
#: three, because the thing it has to establish is the same in each: the
#: judge is not an answer key.
_JUDGE_GUIDELINE = (
    "\n\n"
    "The `judge` field is what an LLM judge said about this row, and the "
    "`judge_verdict` metadata is its verdict in one word. It is NOT the "
    "answer. It "
    "is a second machine opinion recorded beside the checker's, and it "
    "gates nothing. Where it says it disagrees with the pipeline, that pair "
    "is the reason this row is in front of you: one of the two is wrong and "
    "only you can say which."
)

#: Added after it. Argilla's job is the artefacts a person judges, and a
#: reviewer who needs the calls behind one has to be told where they are.
_WHERE_GUIDELINE = (
    "\n\n"
    "The number in this dataset's name is the stage that produced it: "
    "4 extraction, 5 topic modelling, 6 question generation. Argilla holds "
    "the artefacts and your verdicts on them, and nothing else. The calls "
    "that produced a row are in Phoenix under a project numbered the same "
    "way, every line the run wrote is in Grafana, and which run it was is "
    "in Dagster. The application's own pages show one artefact's whole "
    'chain under "How this was produced".'
)


def judge_metadata(opinion: Opinion) -> dict[str, str]:
    """The two metadata terms one artefact's verdict becomes."""
    return {
        "judge_verdict": opinion.verdict,
        "judge_disagrees": "yes" if opinion.disagrees else "no",
    }


def fact_settings() -> rg.Settings:
    """What a reviewer is shown about a fact, and what they are asked."""
    return rg.Settings(
        guidelines=(
            "Does the statement follow from the evidence beside it, and does "
            "it stand on its own?\n\n"
            "Accept when the evidence supports every part of the statement "
            "and the statement needs no surrounding context to be understood. "
            "Reject when it adds anything the evidence does not say, when it "
            "leaves a pronoun pointing outside itself, or when it is a "
            "paraphrase of the passage rather than a claim drawn from it.\n\n"
            "`rejection_code` is what the automatic checker decided. You are "
            "judging the statement, not agreeing with the checker - the "
            "disagreements are the point of the exercise."
            + _JUDGE_GUIDELINE
            + _WHERE_GUIDELINE
        ),
        fields=[
            rg.TextField(name="statement", title="The fact as written"),
            rg.TextField(name="evidence", title="The sentences it cites"),
            _judge_field(),
        ],
        questions=[
            rg.LabelQuestion(
                name="verdict",
                title="Does this fact hold?",
                labels=_VERDICT,
                required=True,
            ),
        ],
        metadata=[
            rg.TermsMetadataProperty(name="kind", title="Fact kind"),
            rg.TermsMetadataProperty(name="language", title="Language"),
            rg.TermsMetadataProperty(name="checker", title="What the checker said"),
            *_judge_metadata(),
            rg.IntegerMetadataProperty(name="fact_id", title="Fact id"),
        ],
    )


def topic_settings() -> rg.Settings:
    """What a reviewer is shown about a topic's name, and what they are asked."""
    return rg.Settings(
        guidelines=(
            "Is this a good name for these terms, and is it a subject the "
            "corpus should be asked about?\n\n"
            "Correct the label if it is wrong or vague; leave it alone if it "
            "is right. A topic that is an artefact of the fitting rather than "
            "a subject - boilerplate, page furniture, a mix of everything - "
            "should be marked out of coverage, which means no questions are "
            "written about it at all." + _JUDGE_GUIDELINE + _WHERE_GUIDELINE
        ),
        fields=[
            rg.TextField(name="terms", title="Its strongest terms"),
            rg.TextField(name="label", title="What the model named it"),
            _judge_field(),
        ],
        questions=[
            rg.TextQuestion(
                name="corrected_label",
                title="The name it should have",
                # Left empty, the name stays as it is and so does who gave it.
                required=False,
            ),
            rg.LabelQuestion(
                name="in_coverage",
                title="Is this a subject worth asking about?",
                labels=["yes", "no"],
                required=True,
            ),
        ],
        metadata=[
            rg.TermsMetadataProperty(name="language", title="Language"),
            rg.TermsMetadataProperty(name="labelled_by", title="Named by"),
            *_judge_metadata(),
            rg.IntegerMetadataProperty(name="topic_id", title="Topic id"),
            rg.IntegerMetadataProperty(name="passages", title="Passages held"),
        ],
    )


def question_settings() -> rg.Settings:
    """What a reviewer is shown about a question, and what they are asked."""
    return rg.Settings(
        guidelines=(
            "Would somebody actually ask this, and is the answer right?\n\n"
            "Accept when the question is one a person would put to a service "
            "desk, the answer follows from the facts beside it, and the "
            "question does not say where its own answer is. Reject a question "
            "that names its source, that asks two things at once, or whose "
            "answer is not recoverable from the facts shown.\n\n"
            "The exception is `kind` compound: a compound question asks two "
            "separate things on purpose, each answered by its own passage. "
            "Judge it one half at a time, and reject it if either half fails.\n\n"
            "A category whose form is a search query, marked `(query)` in "
            "`categories`, is judged as a query typed into a search box: "
            "keywords with no question mark and no verb are what it was "
            "written to be, not a malformed question. Judge whether somebody "
            "would search for that, and whether the answer fits it.\n\n"
            "A question with a `thread` is a follow-up: it leans on the turns "
            "listed there on purpose, so judge it after them and do not reject "
            "it for not standing alone.\n\n"
            "An unanswerable question is not automatically wrong: some are "
            "written deliberately, to check that a chatbot says it does not "
            "know. `answerable` says which kind this is.\n\n"
            "`facts` is what was written from, `evidence` is the sentences "
            "those facts cite, and `explanation` is why the writer says "
            "that is the answer. Judge the answer against the evidence: a "
            "fact can be a fair reading of a sentence that does not say "
            "what the answer claims." + _JUDGE_GUIDELINE + _WHERE_GUIDELINE
        ),
        fields=[
            rg.TextField(name="question", title="The question"),
            rg.TextField(name="answer", title="The answer it expects"),
            rg.TextField(name="facts", title="The facts it was written from"),
            rg.TextField(name="evidence", title="The sentences those facts cite"),
            rg.TextField(
                name="explanation", title="Why that is the answer, as the writer put it"
            ),
            rg.TextField(
                name="thread",
                title="The turns it follows, oldest first",
                required=False,
            ),
            rg.TextField(
                name="categories",
                title="What its writer was told it should be",
                required=False,
            ),
            _judge_field(),
        ],
        questions=[
            rg.LabelQuestion(
                name="verdict",
                title="Is this question good enough to keep?",
                labels=_VERDICT,
                required=True,
            ),
        ],
        metadata=[
            rg.TermsMetadataProperty(name="difficulty", title="Difficulty band"),
            rg.TermsMetadataProperty(name="question_type", title="Type"),
            rg.TermsMetadataProperty(name="kind", title="Kind"),
            rg.IntegerMetadataProperty(name="turn", title="Turn in its thread"),
            rg.TermsMetadataProperty(name="language", title="Language"),
            rg.TermsMetadataProperty(name="answerable", title="Answerable"),
            rg.TermsMetadataProperty(name="gate", title="What the gates said"),
            *_judge_metadata(),
            # A margin in [0, 1], so a reviewer can open the queue at the
            # questions that survived a gate by the least.
            rg.FloatMetadataProperty(
                name="confidence", title="Confidence", min=0.0, max=1.0
            ),
            rg.IntegerMetadataProperty(name="question_id", title="Question id"),
        ],
    )


SETTINGS = {
    FACTS: fact_settings,
    TOPIC_LABELS: topic_settings,
    QUESTIONS: question_settings,
}


def fact_record(row: FactRow, judge: Opinion = UNJUDGED) -> rg.Record:
    """One fact as a record."""
    return rg.Record(
        # The database id, so a pulled answer finds its row again. Argilla
        # deduplicates on it too, so pushing a record twice updates rather
        # than doubling it.
        id=str(row.id),
        fields={
            "statement": row.statement,
            "evidence": row.evidence,
            "judge": judge.detail,
        },
        metadata={
            "kind": row.kind,
            "language": row.language or "unknown",
            "checker": row.rejection_code or "accepted",
            **judge_metadata(judge),
            "fact_id": row.id,
        },
    )


def topic_record(topic, judge: Opinion = UNJUDGED) -> rg.Record:
    """One topic as a record."""
    return rg.Record(
        id=str(topic.id),
        fields={
            "terms": ", ".join(topic.top_terms),
            "label": topic.label or "(the model named nothing)",
            "judge": judge.detail,
        },
        metadata={
            "language": topic.language or "unknown",
            "labelled_by": topic.labelled_by or "nobody",
            **judge_metadata(judge),
            "topic_id": topic.id,
            "passages": topic.passages,
        },
    )


def question_record(row: QuestionRow, judge: Opinion = UNJUDGED) -> rg.Record:
    """One question as a record."""
    return rg.Record(
        id=str(row.id),
        fields={
            "question": row.question_text,
            "answer": row.target_answer or "(deliberately unanswerable)",
            "facts": "\n".join(f"- {one}" for one in row.facts) or "(none recorded)",
            "evidence": "\n".join(f"- {one}" for one in row.evidence)
            or "(none recorded)",
            # A question written to have no answer explains nothing, which
            # is the ordinary case rather than a gap: the field says so
            # rather than arriving empty, which Argilla refuses.
            "explanation": row.answer_explanation or "(none written)",
            "judge": judge.detail,
            # Omitted on a root: a field of "(none)" would only be noise,
            # and this one is not required.
            **(
                {"thread": "\n".join(f"{n}. {t}" for n, t in enumerate(row.before, 1))}
                if row.before
                else {}
            ),
            **(
                {"categories": "\n".join(f"- {one}" for one in row.categories)}
                if row.categories
                else {}
            ),
        },
        metadata={
            "difficulty": row.difficulty or "unbanded",
            "question_type": row.question_type or "untyped",
            "kind": row.kind or "single",
            "turn": row.turn,
            "language": row.language,
            "answerable": str(row.answerable).lower(),
            "gate": row.rejected_reason or row.status,
            **judge_metadata(judge),
            "question_id": row.id,
            # What a reviewer sorts the queue by. Omitted rather than sent
            # as a sentinel where nothing measured it: a filter on a range
            # cannot tell -1 from a real reading, and a row with no
            # confidence is not a row with a bad one.
            **({} if row.confidence is None else {"confidence": row.confidence}),
        },
    )


# ── The Argilla adapter of `review.service.ReviewTool` ────────────────────
#
# Everything below is the one place the review package speaks Argilla's
# client: opening it, its datasets, its records and their responses.


def connect(settings: Settings) -> rg.Argilla:
    """Opens the client and makes sure the workspace is there."""
    client = rg.Argilla(api_url=settings.api_url, api_key=settings.api_key)
    if client.workspaces(settings.workspace) is None:
        log.info("creating workspace %s", settings.workspace)
        client.workspaces.add(rg.Workspace(name=settings.workspace))
    return client


def check(settings: Settings) -> None:
    """Opens the client and asks Argilla who it is, creating nothing.

    Raises:
        Exception: Whatever the client raises when the address is wrong or the
            key is refused, which is what a preflight is for.
    """
    _ = rg.Argilla(api_url=settings.api_url, api_key=settings.api_key).me


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
    pulled - and the push reported its records written with nothing on them.

    Warned rather than fixed automatically, for the same reason: what to do
    about it depends on whether anybody has answered. The warning counts
    the submitted answers the dataset holds and names the pull to run
    before deleting it in Argilla.
    """
    try:
        declared = {one.name for one in found.settings.fields} | {
            one.name for one in found.settings.metadata
        }
        wanted = {one.name for one in SETTINGS[name]().fields} | {
            one.name for one in SETTINGS[name]().metadata
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
        "topics" if name == TOPIC_LABELS else name,
    )


def _dataset(client: rg.Argilla, settings: Settings, name: str) -> rg.Dataset:
    """The dataset by that name, created on first push.

    Not recreated if it is there: a dataset holds the answers given so far,
    and a push that dropped it would throw away every verdict not yet
    pulled. What that costs when the settings have moved on is
    :func:`_warn_if_stale`.
    """
    held = dataset_name(name)
    found = client.datasets(name=held, workspace=settings.workspace)
    if found is not None:
        _warn_if_stale(found, name)
        return found
    log.info("creating dataset %s in %s", held, settings.workspace)
    return rg.Dataset(
        name=held,
        workspace=settings.workspace,
        settings=SETTINGS[name](),
        client=client,
    ).create()


#: How Argilla spells a response somebody has finished giving.
_SUBMITTED = ("submitted", "ResponseStatus.submitted")

#: Each dataset's id metadata, and the field holding the text a reviewer read.
_KEYS = {
    FACTS: ("fact_id", "statement"),
    QUESTIONS: ("question_id", "question"),
    TOPIC_LABELS: ("topic_id", "terms"),
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


#: Which function turns a row into a record, per dataset.
_BUILDERS = {
    FACTS: fact_record,
    QUESTIONS: question_record,
    TOPIC_LABELS: topic_record,
}


class ArgillaTool:
    """The `ReviewTool` over Argilla, from the host.

    Redis is Argilla's own and nothing here speaks it.
    """

    def __init__(self, settings: Settings) -> None:
        """Binds to Argilla's address and key. Nothing is opened until asked."""
        self._settings = settings
        self._opened: rg.Argilla | None = None

    def _client(self) -> rg.Argilla:
        """The client, opened once, with the workspace made."""
        if self._opened is None:
            self._opened = connect(self._settings)
        return self._opened

    def check(self) -> None:
        """See `ReviewTool.check`."""
        check(self._settings)

    def answered(self, name: str) -> set[str]:
        """See `ReviewTool.answered`."""
        return answered(_dataset(self._client(), self._settings, name))

    def push(self, name: str, rows) -> int:
        """See `ReviewTool.push`."""
        dataset = _dataset(self._client(), self._settings, name)
        records = [_BUILDERS[name](row, opinion) for row, opinion in rows]
        if not records:
            return 0
        dataset.records.log(records)
        log.info(
            "%s: %d record(s) pushed to %s", name, len(records), self._settings.api_url
        )
        return len(records)

    def pull(self, name: str):
        """See `ReviewTool.pull`."""
        from review.service import Answer

        client = self._client()
        dataset = client.datasets(
            name=dataset_name(name), workspace=self._settings.workspace
        )
        if dataset is None:
            return None
        key, text = _KEYS[name]
        given = _given_at(client, dataset, key)
        found = []
        for record in dataset.records(with_responses=True):
            row_id = int(record.metadata[key])
            if row_id not in given:
                continue
            values = {
                one.question_name: _answer(record, one.question_name)
                for one in record.responses
            }
            found.append(
                Answer(
                    row_id=row_id,
                    shown=str(record.fields[text]),
                    at=given[row_id],
                    disputed=_disagreed(record),
                    values=values,
                )
            )
        return found

    def drop(self) -> int:
        """See `ReviewTool.drop`."""
        client = self._client()
        deleted = 0
        for name in NAMES:
            held = dataset_name(name)
            found = client.datasets(name=held, workspace=self._settings.workspace)
            if found is None:
                continue
            log.info("deleting dataset %s", held)
            found.delete()
            deleted += 1
        return deleted
