"""In-memory stand-ins for the components behind a port, shared by the contract suites.

Each fake keeps to the port's own words, so a suite written against the port
runs unchanged against it and against today's adapter. `FakeS3Client` is the
one that is not a port's fake: it stands in for boto3's client, so the real
`S3Store` can be run without a container.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from botocore.exceptions import ClientError

from blob_store.store import Entry


class FakeObjectStore:
    """The `ObjectStore` port over a dict.

    `buckets` is what the store holds; a bucket that is not in it is absent.
    The port has no account-wide bucket list, so nothing here offers one.
    """

    def __init__(
        self, buckets: Mapping[str, Mapping[str, bytes]] | None = None
    ) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {
            name: dict(held) for name, held in (buckets or {}).items()
        }
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self._clock = datetime(2026, 1, 1, tzinfo=UTC)
        self._written: dict[tuple[str, str], datetime] = {}

    def _held(self, bucket: str) -> dict[str, bytes]:
        """Held."""
        if bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "Op")
        return self.buckets[bucket]

    def _stamp(self, bucket: str, key: str) -> None:
        """Stamp."""
        self._clock += timedelta(seconds=1)
        self._written[(bucket, key)] = self._clock

    def put(self, bucket, key, data, *, content_type, metadata=None) -> None:
        """See `ObjectStore.put`."""
        self._held(bucket)[key] = data
        self.metadata[(bucket, key)] = dict(metadata or {})
        self._stamp(bucket, key)

    def get(self, bucket, key):
        """See `ObjectStore.get`."""
        return self._held(bucket).get(key)

    def exists(self, bucket, key) -> bool:
        """See `ObjectStore.exists`."""
        return key in self._held(bucket)

    def delete(self, bucket, key) -> None:
        """See `ObjectStore.delete`."""
        self._held(bucket).pop(key, None)

    def copy(self, bucket, key, to_bucket, to_key) -> bool:
        """See `ObjectStore.copy`."""
        data = self._held(bucket).get(key)
        if data is None:
            return False
        self._held(to_bucket)[to_key] = data
        self._stamp(to_bucket, to_key)
        return True

    def listed(self, bucket, prefix=""):
        """See `ObjectStore.listed`."""
        return [
            Entry(key, len(data), self._written.get((bucket, key), self._clock))
            for key, data in sorted(self._held(bucket).items())
            if key.startswith(prefix)
        ]

    def delete_many(self, bucket, keys) -> None:
        """See `ObjectStore.delete_many`."""
        for key in keys:
            self._held(bucket).pop(key, None)

    def has_bucket(self, bucket) -> bool:
        """See `ObjectStore.has_bucket`."""
        return bucket in self.buckets


class FakeS3Client:
    """The part of boto3's S3 client `S3Store` calls, over a dict.

    `list_buckets` is refused, as it is to a credential scoped to one bucket,
    so a caller that lists the account's buckets fails here as it does there.
    """

    def __init__(
        self, buckets: Mapping[str, Mapping[str, bytes]] | None = None
    ) -> None:
        self._inner = FakeObjectStore(buckets)

    @staticmethod
    def _error(code: str, operation: str) -> ClientError:
        """Error."""
        return ClientError({"Error": {"Code": code}}, operation)

    def list_buckets(self):
        """See `ObjectStore.list_buckets`."""
        raise self._error("AccessDenied", "ListBuckets")

    def head_bucket(self, Bucket):
        """See `ObjectStore.head_bucket`."""
        if not self._inner.has_bucket(Bucket):
            raise self._error("404", "HeadBucket")

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        """See `ObjectStore.put_object`."""
        self._inner.put(Bucket, Key, Body, content_type=ContentType, metadata=Metadata)

    def get_object(self, Bucket, Key):
        """See `ObjectStore.get_object`."""
        data = self._inner.get(Bucket, Key)
        if data is None:
            raise self._error("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(data)}

    def head_object(self, Bucket, Key):
        """See `ObjectStore.head_object`."""
        if not self._inner.exists(Bucket, Key):
            raise self._error("404", "HeadObject")

    def delete_object(self, Bucket, Key):
        """See `ObjectStore.delete_object`."""
        self._inner.delete(Bucket, Key)

    def copy_object(self, Bucket, Key, CopySource):
        """See `ObjectStore.copy_object`."""
        if not self._inner.copy(CopySource["Bucket"], CopySource["Key"], Bucket, Key):
            raise self._error("NoSuchKey", "CopyObject")

    def delete_objects(self, Bucket, Delete):
        """See `ObjectStore.delete_objects`."""
        self._inner.delete_many(Bucket, [one["Key"] for one in Delete["Objects"]])
        return {}

    def get_paginator(self, name):
        """See `ObjectStore.get_paginator`."""
        assert name == "list_objects_v2"
        inner = self._inner

        class Pages:
            """Pages."""

            def paginate(self, Bucket, Prefix=""):
                """See `ObjectStore.paginate`."""
                entries = inner.listed(Bucket, Prefix)
                half = max(1, len(entries) // 2)
                for start in range(0, max(len(entries), 1), half):
                    yield {
                        "Contents": [
                            {"Key": e.key, "Size": e.size, "LastModified": e.modified}
                            for e in entries[start : start + half]
                        ]
                    }

        return Pages()


class FakeOrchestrator:
    """The `Orchestrator` port over a list of runs."""

    def __init__(self) -> None:
        """Starts with no runs and both triggers off."""
        from api.orchestrator import Automation

        self.held: list = []
        self.automation = Automation(available=True)

    def state(self):
        """What it is doing."""
        from api.orchestrator import Orchestration

        return Orchestration(
            available=True,
            running=next((r for r in self.held if r.live), None),
            recent=list(reversed(self.held))[:5],
            automation=self.automation,
        )

    def runs(self, *, limit: int = 20):
        """Newest first."""
        return list(reversed(self.held))[:limit]

    def live(self):
        """The unfinished ones."""
        return [r for r in self.runs() if r.live]

    def launch(self):
        """A started run."""
        from api.orchestrator import Run

        run = Run(f"run-{len(self.held)}", "STARTED", 1.0)
        self.held.append(run)
        return run

    def terminate(self, run_id: str) -> bool:
        """True when it was live."""
        from dataclasses import replace

        for index, run in enumerate(self.held):
            if run.id == run_id:
                if not run.live:
                    return False
                self.held[index] = replace(run, status="CANCELED")
                return True
        raise KeyError(run_id)

    def automate(self, *, on_arrival, nightly):
        """Moves what is given."""
        from dataclasses import replace

        self.automation = replace(
            self.automation,
            on_arrival=self.automation.on_arrival if on_arrival is None else on_arrival,
            nightly=self.automation.nightly if nightly is None else nightly,
        )
        return self.automation


class FakeDagsterSession:
    """A requests session that answers Dagster's GraphQL from a state, as the webserver does.

    It reads the operation's name out of the document, so a document renamed
    in the adapter is a document this does not know, and the contract suite
    fails on it.
    """

    def __init__(self) -> None:
        """Starts with no runs and both triggers stopped."""
        self.runs: list[dict] = []
        self.status = {"sensor": "STOPPED", "schedule": "STOPPED"}
        self.posts = 0

    def post(self, url: str, json: dict, timeout):
        """Answers one document."""
        import re

        self.posts += 1
        name = re.search(r"(?:query|mutation)\s+(\w+)", json["query"]).group(1)  # type: ignore[union-attr]
        data = getattr(self, f"_{name}")(**json["variables"])
        return type(
            "Reply", (), {"status_code": 200, "json": lambda _: {"data": data}}
        )()

    def _view(self, run: dict) -> dict:
        """View."""
        return {
            "runId": run["runId"],
            "status": run["status"],
            "startTime": 1.0,
            "endTime": None,
        }

    def _repository(self) -> dict:
        """Repository."""
        return {
            "__typename": "Repository",
            "sensors": [
                {
                    "name": "arrivals",
                    "sensorState": {"id": "s", "status": self.status["sensor"]},
                }
            ],
            "schedules": [
                {
                    "name": "nightly_corpus",
                    "scheduleState": {"id": "n", "status": self.status["schedule"]},
                }
            ],
        }

    def _runs_or_error(self, limit=None, statuses=None) -> dict:
        """Runs or error."""
        found = [
            r
            for r in reversed(self.runs)
            if statuses is None or r["status"] in statuses
        ]
        return {"__typename": "Runs", "results": [self._view(r) for r in found[:limit]]}

    def _State(self, limit, **_):
        """State."""
        return {
            "runsOrError": self._runs_or_error(limit),
            "repositoryOrError": self._repository(),
        }

    def _Runs(self, filter, limit=None):
        """Runs."""
        return {"runsOrError": self._runs_or_error(limit, filter.get("statuses"))}

    def _Triggers(self, **_):
        """Triggers."""
        return {"repositoryOrError": self._repository()}

    def _Launch(self, params):
        """Launch."""
        run = {"runId": f"run-{len(self.runs)}", "status": "STARTED"}
        self.runs.append(run)
        return {"launchRun": {"__typename": "LaunchRunSuccess", "run": self._view(run)}}

    def _RunStatus(self, runId):
        """Runstatus."""
        run = next(r for r in self.runs if r["runId"] == runId)
        return {"runOrError": {"__typename": "Run", **run}}

    def _Terminate(self, runId, policy=None):
        """Terminate."""
        run = next(r for r in self.runs if r["runId"] == runId)
        if run["status"] in ("SUCCESS", "FAILURE", "CANCELED"):
            one = {
                "__typename": "TerminateRunFailure",
                "message": f"Run {runId} could not be terminated due to having status {run['status']}.",
            }
        else:
            run["status"] = "CANCELED"
            one = {"__typename": "TerminateRunSuccess"}
        return {
            "terminateRuns": {
                "__typename": "TerminateRunsResult",
                "terminateRunResults": [one],
            }
        }

    def _switch(self, kind: str, on: bool) -> dict:
        """Switch."""
        self.status[kind] = "RUNNING" if on else "STOPPED"
        return {"x": {"__typename": "ScheduleStateResult"}}

    def _StartSensor(self, selector):
        """Startsensor."""
        return self._switch("sensor", True)

    def _StopSensor(self, id):
        """Stopsensor."""
        return self._switch("sensor", False)

    def _StartSchedule(self, selector):
        """Startschedule."""
        return self._switch("schedule", True)

    def _StopSchedule(self, id):
        """Stopschedule."""
        return self._switch("schedule", False)


class FakeTraceStore:
    """The `TraceStore` port over lists, with the observable state the contract suite reads."""

    def __init__(self) -> None:
        """Starts empty."""
        from telemetry.projects import Project

        self.annotated: list[dict] = []
        self.prompts: dict[str, dict] = {}
        self.held = [
            Project("p1", "1-extraction-a", 1, work=False, whole=True),
            Project("p2", "2-parsing-b", 3, work=True, whole=True),
        ]
        self.golden = [
            {"id": "d1", "name": "golden-a"},
            {"id": "d2", "name": "golden-b"},
        ]
        self.retention: int | None = None
        self.uploaded: dict[str, list] = {}

    def annotate(self, annotations) -> None:
        """Keeps them."""
        self.annotated.extend(annotations)

    def publish_prompt(
        self, name, description, call, version_description, provider
    ) -> None:
        """Keeps the latest version by name."""
        self.prompts[name] = {
            "call": call,
            "provider": provider,
            "description": description,
        }

    def projects(self):
        """What is held."""
        return list(self.held)

    def delete_project(self, project_id) -> bool:
        """True when it was there."""
        before = len(self.held)
        self.held = [p for p in self.held if p.id != project_id]
        return len(self.held) < before

    def datasets(self):
        """What is held."""
        return list(self.golden)

    def delete_dataset(self, dataset_id) -> bool:
        """True when it was there."""
        before = len(self.golden)
        self.golden = [d for d in self.golden if d["id"] != dataset_id]
        return len(self.golden) < before

    def set_retention(self, days) -> None:
        """Remembers it."""
        self.retention = days

    def create_dataset(self, name, inputs, outputs, description) -> str:
        """Remembers it, and returns an id."""
        self.uploaded[name] = list(zip(inputs, outputs, strict=True))
        return f"id-{name}"

    def run_experiment(
        self, dataset, task, evaluators, name, description, metadata
    ) -> str:
        """Runs the task over what was uploaded and returns an address."""
        for inputs, _ in self.uploaded.get(dataset, []):
            task(inputs)
        return f"http://traces.invalid/{dataset}/{name}"


class FakePhoenixHttp:
    """Phoenix's REST API as a `requests` session sees it: projects, spans, datasets and the retention mutation."""

    def __init__(self) -> None:
        """Seeds two projects and two datasets, and a retention policy that was never set."""
        self.projects = {
            "p1": {"name": "1-extraction-a", "spans": [{"name": "completion"}]},
            "p2": {
                "name": "2-parsing-b",
                "spans": [{"name": "parse"}, {"name": "completion"}],
            },
        }
        self.datasets = {"d1": "golden-a", "d2": "golden-b"}
        self.retention: int | None = None
        self.refuse_retention = False

    class _Answer:
        """_Answer."""

        def __init__(self, body: dict | None = None, ok: bool = True) -> None:
            self._body, self.ok, self.status_code = body or {}, ok, 200 if ok else 404

        def json(self) -> dict:
            """The port's json."""
            return self._body

        def raise_for_status(self) -> None:
            """The port's raise for status."""
            if not self.ok:
                raise RuntimeError(self.status_code)

    def get(self, path: str, params=None):
        """Lists, or reads a project's spans."""
        if path == "/v1/projects":
            data = [{"id": i, "name": p["name"]} for i, p in self.projects.items()]
        elif path == "/v1/datasets":
            data = [{"id": i, "name": n} for i, n in self.datasets.items()]
        elif path.endswith("/spans"):
            data = self.projects[path.split("/")[3]]["spans"]
        else:
            return self._Answer(ok=False)
        return self._Answer({"data": data, "next_cursor": None})

    def delete(self, path: str):
        """Deletes a project or a dataset."""
        _, _, kind, key = path.split("/")
        held = self.projects if kind == "projects" else self.datasets
        return self._Answer(ok=held.pop(key, None) is not None)

    def post(self, path: str, json: dict):
        """Takes the retention mutation."""
        assert path == "/graphql"
        if self.refuse_retention:
            return self._Answer({"errors": [{"message": "not allowed"}]})
        self.retention = json["variables"]["input"]["rule"]["maxDays"]["maxDays"]
        return self._Answer({"data": {}})


class FakePhoenixSdk:
    """The part of Phoenix's client the adapter calls."""

    def __init__(self) -> None:
        """Starts with nothing filed."""
        self.annotated: list[dict] = []
        self.prompt_calls: list[dict] = []
        self.uploaded: dict[str, list] = {}
        self.spans = self
        self.prompts = self
        self.datasets = self
        self.experiments = self

    def log_span_annotations(self, span_annotations) -> None:
        """Files them."""
        self.annotated.extend(span_annotations)

    def create(self, name, prompt_description, version) -> None:
        """Files one prompt."""
        self.prompt_calls.append(
            {"name": name, "description": prompt_description, "version": version}
        )

    def create_dataset(self, name, inputs, outputs, dataset_description):
        """Files a dataset."""
        self.uploaded[name] = list(zip(inputs, outputs, strict=True))
        return type("Dataset", (), {"id": f"id-{name}", "name": name})()

    def get_dataset(self, dataset):
        """Reads it back."""
        return type("Dataset", (), {"id": f"id-{dataset}", "name": dataset})()

    def run_experiment(
        self,
        dataset,
        task,
        evaluators,
        experiment_name,
        experiment_description,
        experiment_metadata,
    ):
        """Runs the task over the dataset."""
        for inputs, _ in self.uploaded.get(dataset.name, []):
            task(inputs)
        return {"id": experiment_name}

    def get_experiment_url(self, dataset_id, experiment_id) -> str:
        """Where it is read."""
        return f"http://traces.invalid/{dataset_id}/{experiment_id}"


class FakeReviewTool:
    """The `ReviewTool` port over dicts, with a reviewer who can `submit`."""

    #: Which field holds the text a reviewer read, per dataset.
    TEXT: ClassVar[dict[str, str]] = {
        "facts": "statement",
        "questions": "question_text",
        "topic-labels": "label",
    }

    def __init__(self) -> None:
        """Starts with no dataset pushed."""
        self.shown: dict[str, dict[int, tuple[str, object]]] = {}
        self.given: dict[str, dict[int, list[tuple[str, str | None, str]]]] = {}
        self.checked = 0

    def check(self) -> None:
        """Counts the ask."""
        self.checked += 1

    def push(self, name, rows) -> int:
        """Shows the rows, once each by id."""
        held = self.shown.setdefault(name, {})
        for row, opinion in rows:
            held[row.id] = (getattr(row, self.TEXT[name], ""), opinion)
        return len(list(rows))

    def submit(
        self, name: str, row_id: int, answers: dict[str, str], status: str = "submitted"
    ) -> None:
        """A reviewer answers."""
        self.given.setdefault(name, {}).setdefault(row_id, []).extend(
            (question, value, status) for question, value in answers.items()
        )

    def answered(self, name) -> set[str]:
        """The rows with a submitted answer."""
        return {
            str(row_id)
            for row_id, given in self.given.get(name, {}).items()
            if any(status == "submitted" for *_, status in given)
        }

    def pull(self, name):
        """Every submitted answer, or None when nothing was pushed."""
        from datetime import UTC, datetime

        from review.service import Answer

        if name not in self.shown:
            return None
        found = []
        for row_id, given in self.given.get(name, {}).items():
            submitted = [(q, v) for q, v, status in given if status == "submitted"]
            if not submitted:
                continue
            values: dict[str, str | None] = {}
            disputed = False
            for question, value in submitted:
                if question in values and values[question] != value:
                    disputed = True
                values.setdefault(question, value)
            found.append(
                Answer(
                    row_id,
                    self.shown[name][row_id][0],
                    datetime(2026, 1, 1, tzinfo=UTC),
                    disputed,
                    values,
                )
            )
        return found

    def drop(self) -> int:
        """Deletes everything pushed."""
        count = len(self.shown)
        self.shown.clear()
        self.given.clear()
        return count


class FakeArgilla:
    """Argilla's client as the adapter calls it: workspaces, datasets of records, and the REST listing."""

    def __init__(self) -> None:
        """Starts with a workspace and no dataset."""
        self.held: dict[str, FakeArgilla.Dataset] = {}
        self.http_client = self
        self.deleted: list[str] = []

    class Workspaces:
        """Workspaces."""

        def __call__(self, name):
            """A workspace, whatever is asked for."""
            return object()

    workspaces = Workspaces()

    class Dataset:
        """Dataset."""

        def __init__(self, owner: FakeArgilla, name: str) -> None:
            self.owner, self.name, self.id = owner, name, f"id-{name}"
            self.logged: dict[str, Any] = {}
            self.responses: dict[str, list] = {}
            self.settings = type("S", (), {"fields": [], "metadata": []})()
            self.records = self

        def log(self, records) -> None:
            """Keeps the records by id."""
            """The port's log."""
            for one in records:
                self.logged[str(one.id)] = one

        def __call__(self, with_responses: bool = False):
            """The records, each with its responses."""
            from types import SimpleNamespace

            return iter(
                SimpleNamespace(
                    id=key,
                    metadata=dict(one.metadata),
                    fields=dict(one.fields),
                    responses=self.responses.get(key, []),
                )
                for key, one in self.logged.items()
            )

        def delete(self) -> None:
            """The port's delete."""
            self.owner.deleted.append(self.name)
            del self.owner.held[self.name]

    def datasets(self, name: str = "", workspace=None):
        """The dataset, or None."""
        return self.held.get(name)

    def make(self, name: str) -> FakeArgilla.Dataset:
        """Creates a dataset, as the operator's first push would."""
        return self.held.setdefault(name, FakeArgilla.Dataset(self, name))

    def get(self, path: str, params=None):
        """The records listing, with each response's time."""
        from types import SimpleNamespace

        dataset = next(d for d in self.held.values() if d.id == path.split("/")[4])
        items = []
        for key, one in dataset.logged.items():
            items.append(
                {
                    "metadata": dict(one.metadata),
                    "responses": [
                        {"status": r.status, "updated_at": "2026-01-01T00:00:00"}
                        for r in dataset.responses.get(key, [])
                    ],
                }
            )
        return SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"items": items}
        )
