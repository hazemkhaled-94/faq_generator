"""Argilla's datasets are told apart by database.

The workspace is one for every database, so a name that carried none let a
pull write another database's verdicts here. Fakes only: Argilla is not in
the integration fixtures.
"""

from __future__ import annotations

import pytest

DATABASES = ["qa_bank", "qa_shop", "qa_geschäft"]


def use(monkeypatch, database: str) -> None:
    """Runs the process against a database."""
    monkeypatch.delenv("APP_DB_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:p@h:5432/{database}")


@pytest.mark.parametrize("database", DATABASES)
def test_a_dataset_name_carries_the_database_in_characters_argilla_takes(
    monkeypatch, database
) -> None:
    """Letters, digits, dash and underscore only."""
    from review import datasets

    use(monkeypatch, database)
    mine = datasets.dataset_name(datasets.QUESTIONS)
    assert mine.startswith("6-questions") and mine != "6-questions"
    assert set(mine) <= set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    use(monkeypatch, "qa_other")
    assert datasets.dataset_name(datasets.QUESTIONS) != mine


def test_a_pull_reads_only_its_own_database_dataset(monkeypatch) -> None:
    """The name asked of Argilla is this database's, never a bare one."""
    from review import datasets
    from review.service import pull

    asked: list[str] = []

    class Client:
        def datasets(self, name=None, workspace=None):
            asked.append(name)

    class Settings:
        workspace = "shared"

    monkeypatch.setattr("review.service.connect", lambda settings: Client())
    use(monkeypatch, "qa_bank")
    assert pull(datasets.FACTS, Settings(), object()) == 0
    use(monkeypatch, "qa_shop")
    pull(datasets.FACTS, Settings(), object())

    assert asked[0] != asked[1] and asked[0].endswith("qa_bank")
