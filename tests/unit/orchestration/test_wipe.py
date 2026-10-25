"""Dagster's run history is one for every database, so a wipe takes its own runs."""

from __future__ import annotations

import pytest

pytest.importorskip("dagster", reason="the pipeline group is not installed")

from orchestration import corpus, wipe


class Run:
    """One run, by id."""

    def __init__(self, run_id: str, database: str | None) -> None:
        """Holds the id and the database tag."""
        self.run_id = run_id
        self.tags = {"database": database} if database else {}


class Instance:
    """Dagster's instance, filtering by tag as it does."""

    def __init__(self, runs: list[Run]) -> None:
        """Holds every run."""
        self.runs = runs
        self.deleted: list[str] = []

    def get_runs(self, filters):
        """The runs holding every tag asked for."""
        return [
            run
            for run in self.runs
            if all(run.tags.get(k) == v for k, v in filters.tags.items())
        ]

    def delete_run(self, run_id: str) -> None:
        """Records a deletion."""
        self.deleted.append(run_id)


def test_a_wipe_deletes_only_the_runs_tagged_with_its_database() -> None:
    """Another database's, and an untagged one, stay."""
    instance = Instance([Run("a", "qa_bank"), Run("b", "qa_shop"), Run("c", None)])

    assert wipe.wipe_runs(instance, "qa_bank") == 1
    assert instance.deleted == ["a"]


def test_the_corpus_job_tags_its_runs_with_the_database(monkeypatch) -> None:
    """Without the tag nothing is its database's to wipe."""
    import importlib

    import orchestration

    monkeypatch.setenv("APP_DB_NAME", "qa_shop")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reloaded = importlib.reload(orchestration)
    try:
        assert reloaded.corpus.tags == {"database": "qa_shop"}
    finally:
        monkeypatch.undo()
        importlib.reload(orchestration)
    assert corpus.name == "corpus"
