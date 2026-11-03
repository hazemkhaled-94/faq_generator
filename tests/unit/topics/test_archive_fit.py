"""The figure and the model of a language whose topics went are archived by one function.

The command, the route and a fit that left a language behind all name the
pair, and each used to carry its own copy of the loop.
"""

from __future__ import annotations

import pytest
from fakes import FakeObjectStore

from api.routes import topics as route
from blob_store import store
from blob_store.s3 import ArchiveBucket, ExportBucket, ModelsBucket
from topic_modelling import run, service
from topic_modelling.models import TopicRemoval
from topic_modelling.repository import archive_fit

#: A configured language, one no configuration names (Latin script) and one in another script.
LANGUAGES = ["de", "en", "fr", "el"]


@pytest.fixture
def held(monkeypatch):
    """The three buckets over one fake store, holding a figure and a model per language."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/qa_a")
    fake = FakeObjectStore(
        {b.name: {} for b in (ExportBucket, ModelsBucket, ArchiveBucket)}
    )
    monkeypatch.setattr(store, "object_store", lambda: fake)
    for language in LANGUAGES:
        ExportBucket().put(
            ExportBucket.topic_visualisation_key(language),
            b"<p>figure</p>",
            content_type="text/html",
        )
        ModelsBucket().put(
            ModelsBucket.topic_model_key(language),
            b"model",
            content_type="application/octet-stream",
        )
    return fake


def archived(held) -> set[str]:
    """The port's archived."""
    return {one.key for one in held.listed(ArchiveBucket.name)}


def test_every_language_gives_up_its_figure_and_its_model(held) -> None:
    """Every language gives up its figure and its model."""
    figures, models = archive_fit(
        LANGUAGES,
        export=ExportBucket(),
        models=ModelsBucket(),
        archive=ArchiveBucket(),
    )

    assert (figures, models) == (4, 4)
    assert len(archived(held)) == 8
    assert held.listed(ExportBucket.name) == []
    assert held.listed(ModelsBucket.name) == []


def test_a_language_with_nothing_stored_counts_for_nothing(held) -> None:
    """A language with nothing stored counts for nothing."""
    figures, models = archive_fit(
        ["pl"],
        export=ExportBucket(),
        models=ModelsBucket(),
        archive=ArchiveBucket(),
    )

    assert (figures, models) == (0, 0)


def test_the_route_archives_the_same_keys(held, monkeypatch) -> None:
    """The route archives the same keys."""

    class Catalog:
        """Catalog."""

        def delete_all(self):
            """The port's delete all."""
            return TopicRemoval(
                topics=4, memberships=9, labels=0, languages=["de", "en"]
            )

    monkeypatch.setattr(route, "topic_catalog", Catalog())
    monkeypatch.setattr(route, "export_bucket", ExportBucket())
    monkeypatch.setattr(route, "models_bucket", ModelsBucket())
    monkeypatch.setattr(route, "archive_bucket", ArchiveBucket())

    route.delete(confirm=True)

    assert len(archived(held)) == 4
    assert {one.key.split("/")[1] for one in held.listed(ArchiveBucket.name)} == {
        ExportBucket.name,
        ModelsBucket.name,
    }


def test_a_fit_that_left_a_language_behind_archives_it_and_logs_a_refusal(
    held, monkeypatch, caplog
) -> None:
    """A fit that left a language behind archives it and logs a refusal."""
    fitted = service.TopicModellingService.__new__(service.TopicModellingService)
    fitted._export, fitted._models, fitted._archive = (
        ExportBucket(),
        ModelsBucket(),
        ArchiveBucket(),
    )
    real = ArchiveBucket.take

    def refuse_el(self, origin, key):
        """The port's refuse el."""
        if "/el." in key:
            raise OSError("store unreachable")
        return real(self, origin, key)

    monkeypatch.setattr(ArchiveBucket, "take", refuse_el)

    fitted._release(["de", "el", "en"])

    assert len(archived(held)) == 4
    assert "could not archive the el" in caplog.text


def test_the_command_calls_the_same_function() -> None:
    """The command calls the same function."""
    assert run.archive_fit is archive_fit
