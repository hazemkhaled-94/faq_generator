"""What Phoenix, Argilla and the log stream hold is told apart by database.

Each is one server for every database on the stack, so a name that carried
no database let one database's wipe take another's traces and verdicts. The
scoping is fakes only here: Phoenix, Argilla, Elasticsearch and Dagster are
not in the integration fixtures.
"""

from __future__ import annotations

import json
import logging

import pytest

from telemetry import pipeline, projects
from telemetry.logs import JsonFormatter

#: Databases of a bank, a shop and a name with characters Argilla refuses.
DATABASES = ["qa_bank", "qa_shop", "qa_geschäft"]


def use(monkeypatch, database: str | None) -> None:
    """Runs the process against a database, or against none."""
    monkeypatch.delenv("APP_DB_NAME", raising=False)
    if database is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv(
            "DATABASE_URL", f"postgresql+psycopg://u:p@h:5432/{database}"
        )


@pytest.mark.parametrize("database", DATABASES)
def test_a_project_carries_the_database_that_filed_it(monkeypatch, database) -> None:
    """The same stage in two databases is two projects."""
    use(monkeypatch, database)
    named = pipeline.project("extraction")
    assert named.startswith("4-extraction") and pipeline.owned(named)
    use(monkeypatch, "qa_other")
    assert not pipeline.owned(named)


def test_a_name_is_left_alone_where_no_database_is_named(monkeypatch) -> None:
    """A process with no database - a bare tool - files as it always did."""
    use(monkeypatch, None)
    assert pipeline.project("extraction") == "4-extraction"
    assert not pipeline.owned("4-extraction")


def test_the_orchestrator_names_its_database_by_APP_DB_NAME(monkeypatch) -> None:
    """It has no URL of the application database."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_NAME", "qa_shop")
    assert pipeline.database() == "qa_shop"


class Phoenix:
    """A Phoenix holding projects of several databases."""

    def __init__(self, names: list[str]) -> None:
        """Holds the project names."""
        self.names = names
        self.deleted: list[str] = []

    def get(self, path: str, params: dict):
        """The listing, or a project's spans (none)."""

        class Answer:
            ok = True
            status_code = 200

            def __init__(self, body) -> None:
                self.body = body

            def raise_for_status(self) -> None:
                pass

            def json(self):
                return self.body

        if path == "/v1/projects":
            return Answer({"data": [{"id": n, "name": n} for n in self.names]})
        return Answer({"data": [{"name": "work"}]})

    def delete(self, path: str):
        """Records a deletion."""

        class Answer:
            ok = True
            status_code = 200

        self.deleted.append(path.rsplit("/", 1)[1])
        return Answer()


def test_a_purge_in_one_database_deletes_only_its_own_projects(monkeypatch) -> None:
    """Another database's, and one filed before names carried a database, stay."""
    use(monkeypatch, "qa_bank")
    mine = pipeline.project("extraction")
    use(monkeypatch, "qa_shop")
    theirs = pipeline.project("extraction")
    legacy = "4-extraction"
    client = Phoenix([mine, theirs, legacy, "default"])

    use(monkeypatch, "qa_bank")
    assert projects.prune(client, projects.held(client), everything=True) == 1
    assert client.deleted == [mine]


def test_every_database_is_purged_only_when_asked(monkeypatch) -> None:
    """ALL_DATABASES=1 is the old behaviour, bar `default`."""
    use(monkeypatch, "qa_bank")
    names = [pipeline.project("extraction"), "4-extraction", "default"]
    client = Phoenix(names)

    taken = projects.prune(
        client, projects.held(client), everything=True, every_database=True
    )
    assert taken == 2
    assert sorted(client.deleted) == sorted(names[:2])


def test_every_log_line_carries_its_database(monkeypatch) -> None:
    """What `make wipe` deletes the stream by."""
    use(monkeypatch, "qa_bank")
    record = logging.LogRecord("x", logging.INFO, "f.py", 1, "m", None, None)
    assert json.loads(JsonFormatter("api").format(record))["db"] == "qa_bank"
    use(monkeypatch, None)
    assert json.loads(JsonFormatter("api").format(record))["db"] == ""


@pytest.mark.parametrize(
    "password", ["plain", "ab/cd+ef==", "a#b", "a?b", "p@ss", "x/y?z#w@v"]
)
@pytest.mark.parametrize("database", ["qa_generator", "qa_kunden", "shop_orders"])
def test_a_password_holding_url_characters_leaks_into_no_name(
    monkeypatch, password, database
) -> None:
    """The database is the path of the URL, whatever the secret before the host holds."""
    monkeypatch.delenv("APP_DB_NAME", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL", f"postgresql+psycopg://app:{password}@h:5432/{database}"
    )

    assert pipeline.database() == database
    assert pipeline.scoped("6-questions") == f"6-questions__{database}"


def test_a_url_with_a_query_names_its_database_alone(monkeypatch) -> None:
    """Options after the path are not part of the name."""
    monkeypatch.delenv("APP_DB_NAME", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:a/b@h:5432/qa_one?sslrootcert=/ca/x.pem"
    )

    assert pipeline.database() == "qa_one"


def test_a_url_with_no_password_names_its_database(monkeypatch) -> None:
    """No `@` at all: the path after the host."""
    monkeypatch.delenv("APP_DB_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/qa_two")

    assert pipeline.database() == "qa_two"
