"""Opening Argilla makes what is missing and leaves what is there.

A workspace or a dataset that is not there yet is made on first use; one that
is there is reused, because a dataset holds every answer not yet pulled. A
dataset whose settings match the code's says nothing: the warning about a
stale one must stay rare enough to be read.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("argilla", reason="the observability group is not installed")

from test_service import Dataset

from review import datasets
from review.config import Settings

SETTINGS = Settings(
    api_url="http://argilla:6900", api_key="key", workspace="qa_generator", sample=10
)


def names(*held: str) -> list[SimpleNamespace]:
    """Fields or metadata, by name."""
    return [SimpleNamespace(name=one) for one in held]


def test_a_dataset_whose_settings_match_warns_nothing(monkeypatch, caplog) -> None:
    """Every field the code declares is there."""
    monkeypatch.setitem(
        datasets.SETTINGS,
        datasets.QUESTIONS,
        lambda: SimpleNamespace(fields=names("question", "judge"), metadata=[]),
    )
    found = Dataset([])
    found.name = "6-questions"
    found.settings = SimpleNamespace(fields=names("question", "judge"), metadata=[])

    with caplog.at_level(logging.WARNING):
        datasets._warn_if_stale(found, datasets.QUESTIONS)

    assert caplog.text == ""


class Workspaces:
    """Argilla's workspaces, holding those named."""

    def __init__(self, *held: str) -> None:
        """Holds these workspaces."""
        self.held, self.added = set(held), []

    def __call__(self, name: str):
        """The workspace by that name, or None."""
        return name if name in self.held else None

    def add(self, workspace) -> None:
        """Records a workspace made."""
        self.added.append(workspace.name)


@pytest.mark.parametrize(
    ("held", "made"), [((), ["qa_generator"]), (("qa_generator",), [])]
)
def test_the_workspace_is_made_only_when_missing(monkeypatch, held, made) -> None:
    """A second connect makes nothing."""
    workspaces = Workspaces(*held)
    monkeypatch.setattr(
        datasets.rg, "Argilla", lambda **_: SimpleNamespace(workspaces=workspaces)
    )

    monkeypatch.setattr(datasets.rg, "Workspace", SimpleNamespace)

    datasets.connect(SETTINGS)

    assert workspaces.added == made


def test_a_dataset_not_there_yet_is_created_under_the_codes_settings(
    monkeypatch,
) -> None:
    """Named for this database, in the deployment's workspace."""
    created: list[dict] = []

    class Made:
        def __init__(self, **given) -> None:
            """Keeps what the dataset was made with."""
            self.given = given

        def create(self):
            """Records the creation."""
            created.append(self.given)
            return self

    monkeypatch.setattr(datasets.rg, "Dataset", Made)
    monkeypatch.setitem(datasets.SETTINGS, datasets.QUESTIONS, lambda: "declared")
    client = SimpleNamespace(datasets=lambda name=None, workspace=None: None)

    datasets._dataset(client, SETTINGS, datasets.QUESTIONS)

    (made,) = created
    assert made["name"] == datasets.dataset_name(datasets.QUESTIONS)
    assert made["workspace"] == "qa_generator"
    assert made["settings"] == "declared"
