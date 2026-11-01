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
        return {
            "runId": run["runId"],
            "status": run["status"],
            "startTime": 1.0,
            "endTime": None,
        }

    def _repository(self) -> dict:
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
        found = [
            r
            for r in reversed(self.runs)
            if statuses is None or r["status"] in statuses
        ]
        return {"__typename": "Runs", "results": [self._view(r) for r in found[:limit]]}

    def _State(self, limit, **_):
        return {
            "runsOrError": self._runs_or_error(limit),
            "repositoryOrError": self._repository(),
        }

    def _Runs(self, filter, limit=None):
        return {"runsOrError": self._runs_or_error(limit, filter.get("statuses"))}

    def _Triggers(self, **_):
        return {"repositoryOrError": self._repository()}

    def _Launch(self, params):
        run = {"runId": f"run-{len(self.runs)}", "status": "STARTED"}
        self.runs.append(run)
        return {"launchRun": {"__typename": "LaunchRunSuccess", "run": self._view(run)}}

    def _RunStatus(self, runId):
        run = next(r for r in self.runs if r["runId"] == runId)
        return {"runOrError": {"__typename": "Run", **run}}

    def _Terminate(self, runId, policy=None):
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
        self.status[kind] = "RUNNING" if on else "STOPPED"
        return {"x": {"__typename": "ScheduleStateResult"}}

    def _StartSensor(self, selector):
        return self._switch("sensor", True)

    def _StopSensor(self, id):
        return self._switch("sensor", False)

    def _StartSchedule(self, selector):
        return self._switch("schedule", True)

    def _StopSchedule(self, id):
        return self._switch("schedule", False)
