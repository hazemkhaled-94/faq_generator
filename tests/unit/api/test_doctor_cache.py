"""`make doctor` reads the Hugging Face cache a run with the Hub off loads from.

With HF_HUB_OFFLINE=1 a model not in the cache is not downloaded: the first
passage fails. The doctor says which model, and which pinned revision, is
missing or holds no weights, before a corpus pays for finding out: a failure
where the run reads the cache with the Hub off (HF_HUB_OFFLINE=1, or the
go-live HOST_RUNNER=1), a warning elsewhere. Tests use a scratch HF_HOME and
download nothing.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from api.doctor import cache_check, cache_problems

EMBEDDER = ("org-a/embedder", "1" * 40)
CLASSIFIER = ("org-b/classifier", "2" * 40)


def source(home: Path, **more: str) -> dict[str, str]:
    """The settings a doctor run reads, offline, with a scratch cache."""
    return {
        "HF_HUB_OFFLINE": "1",
        "HF_HOME": str(home),
        "EMBEDDING_MODEL": EMBEDDER[0],
        "EMBEDDING_MODEL_REVISION": EMBEDDER[1],
        "NLI_MODEL": CLASSIFIER[0],
        "NLI_MODEL_REVISION": CLASSIFIER[1],
        "QA_MODEL": "",
        "QA_MODEL_REVISION": "",
        "DOCLING_ARTIFACTS_PATH": "",
        **more,
    }


def cached(
    home: Path, repo: str, revision: str, files=("config.json", "model.safetensors")
) -> None:
    """Puts one snapshot where the Hub client puts it, holding `files`."""
    snapshot = (
        home / "hub" / f"models--{repo.replace('/', '--')}" / "snapshots" / revision
    )
    snapshot.mkdir(parents=True)
    for name in files:
        (snapshot / name).write_text("{}")


def fill(home: Path) -> None:
    """Every model the settings above name, and Docling's two."""
    cached(home, *EMBEDDER)
    cached(home, *CLASSIFIER)
    for repo in (
        "docling-project/docling-layout-heron",
        "docling-project/docling-models",
    ):
        cached(home, repo, "3" * 40)
        refs = home / "hub" / f"models--{repo.replace('/', '--')}" / "refs"
        refs.mkdir()
        (refs / "main").write_text("3" * 40)


def test_an_empty_cache_with_the_hub_off_names_each_missing_model(tmp_path) -> None:
    """The embedder and the NLI encoder, by name."""
    said = " ".join(cache_problems(source(tmp_path)))

    assert EMBEDDER[0] in said and CLASSIFIER[0] in said


def test_a_filled_cache_passes(tmp_path) -> None:
    """Nothing to report."""
    fill(tmp_path)

    assert cache_problems(source(tmp_path)) == []


def test_a_pinned_revision_that_is_not_cached_is_named(tmp_path) -> None:
    """The model is there, at another commit."""
    fill(tmp_path)
    moved = source(tmp_path, EMBEDDING_MODEL_REVISION="9" * 40)

    (said,) = cache_problems(moved)

    assert EMBEDDER[0] in said and "9" * 40 in said


def test_a_model_left_unset_is_not_checked(tmp_path) -> None:
    """QA_MODEL is empty by default, and an unset encoder is not a missing one."""
    fill(tmp_path)

    assert cache_problems(source(tmp_path, QA_MODEL="", QA_MODEL_REVISION="")) == []


def test_a_set_qa_model_is_checked_like_the_others(tmp_path) -> None:
    """Once somebody turns it on."""
    fill(tmp_path)

    (said,) = cache_problems(
        source(tmp_path, QA_MODEL="org-c/reader", QA_MODEL_REVISION="4" * 40)
    )

    assert "org-c/reader" in said


def test_with_the_hub_reachable_the_cache_is_still_read(tmp_path) -> None:
    """What is missing is said either way; whether it fails is the caller's."""
    said = " ".join(cache_problems(source(tmp_path, HF_HUB_OFFLINE="")))

    assert EMBEDDER[0] in said and CLASSIFIER[0] in said


@pytest.mark.parametrize(
    "files",
    [(), ("tokenizer.json", "tokenizer_config.json"), ("config.json",)],
    ids=["empty", "tokenizer-only", "no-weights"],
)
def test_a_snapshot_without_the_weights_is_incomplete(tmp_path, files) -> None:
    """What a tokenizer-only load leaves: an offline encoder load fails on it."""
    fill(tmp_path)
    folder = tmp_path / "hub" / f"models--{EMBEDDER[0].replace('/', '--')}"
    for one in (folder / "snapshots" / EMBEDDER[1]).iterdir():
        one.unlink()
    for name in files:
        (folder / "snapshots" / EMBEDDER[1] / name).write_text("{}")

    (said,) = cache_problems(source(tmp_path))

    assert EMBEDDER[0] in said and EMBEDDER[1] in said


@pytest.mark.parametrize(
    "weights",
    ["model.safetensors", "pytorch_model.bin", "model.safetensors.index.json"],
)
def test_each_weights_file_a_model_loads_from_counts(tmp_path, weights) -> None:
    """Safetensors, the older bin, or a sharded index."""
    fill(tmp_path)
    folder = tmp_path / "hub" / f"models--{EMBEDDER[0].replace('/', '--')}"
    (folder / "snapshots" / EMBEDDER[1] / "model.safetensors").unlink()
    (folder / "snapshots" / EMBEDDER[1] / weights).write_text("{}")

    assert cache_problems(source(tmp_path)) == []


@pytest.mark.parametrize(
    ("offline", "host_runner", "failed"),
    [("1", "", 1), ("", "1", 1), ("true", "true", 1), ("", "", 0), ("0", "no", 0)],
)
def test_a_missing_model_fails_where_the_run_reads_with_the_hub_off(
    tmp_path, caplog, offline, host_runner, failed
) -> None:
    """HF_HUB_OFFLINE=1 or the go-live profile fails; development warns."""
    with caplog.at_level(logging.WARNING):
        code = cache_check(
            source(tmp_path, HF_HUB_OFFLINE=offline, HOST_RUNNER=host_runner)
        )

    assert code == failed
    levels = {r.levelno for r in caplog.records if EMBEDDER[0] in r.getMessage()}
    assert levels == {logging.ERROR if failed else logging.WARNING}


def test_a_filled_cache_says_nothing(tmp_path, caplog) -> None:
    """On either profile."""
    fill(tmp_path)

    with caplog.at_level(logging.WARNING):
        assert cache_check(source(tmp_path, HOST_RUNNER="1")) == 0

    assert caplog.records == []


def test_the_hosted_run_s_preflight_reads_the_cache_with_the_hub_off(
    tmp_path, monkeypatch, caplog
) -> None:
    """The hosted run refuses before it detaches, not at its first drain."""
    from api import doctor

    for name, value in source(tmp_path, HF_HUB_OFFLINE="").items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("llm.config.check_split", lambda source=None: None)
    monkeypatch.delenv("APP_DB_PASSWORD", raising=False)

    with caplog.at_level(logging.ERROR):
        assert doctor.preflight() == 1

    assert EMBEDDER[0] in caplog.text


def test_docling_artifacts_named_but_missing_are_reported(tmp_path) -> None:
    """DOCLING_ARTIFACTS_PATH replaces the cache for the converter."""
    fill(tmp_path)

    (said,) = cache_problems(
        source(tmp_path, DOCLING_ARTIFACTS_PATH=str(tmp_path / "nowhere"))
    )

    assert "DOCLING_ARTIFACTS_PATH" in said


def test_docling_artifacts_that_exist_pass(tmp_path) -> None:
    """A directory holding something."""
    fill(tmp_path)
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "model.bin").write_text("x")

    assert cache_problems(source(tmp_path, DOCLING_ARTIFACTS_PATH=str(weights))) == []


def test_the_scratch_cache_is_what_is_read_not_the_real_one(tmp_path) -> None:
    """HF_HOME in the source, whatever the process has."""
    assert cache_problems(source(tmp_path))


@pytest.mark.parametrize("value", ["", "  "])
def test_a_set_but_empty_artifacts_path_is_refused_at_load(value) -> None:
    """Docling reads an empty path as the working directory."""
    from preprocessing.parsing.config import Settings

    env = {
        "PARSING_OCR_CHAR_THRESHOLD": "10",
        "PARSING_MIN_CONFIDENCE": "0.5",
        "PARSING_TABLE_MODE": "accurate",
        "PARSING_HEADING_HIERARCHY": "true",
        "PARSING_TIMEOUT_SECONDS": "60",
        "DOCLING_ARTIFACTS_PATH": value,
    }

    with pytest.raises(ValueError, match="DOCLING_ARTIFACTS_PATH"):
        Settings.load(env)


def test_an_absent_artifacts_path_still_loads() -> None:
    """Absent lets Docling use the cache."""
    from preprocessing.parsing.config import Settings

    env = {
        "PARSING_OCR_CHAR_THRESHOLD": "10",
        "PARSING_MIN_CONFIDENCE": "0.5",
        "PARSING_TABLE_MODE": "accurate",
        "PARSING_HEADING_HIERARCHY": "true",
        "PARSING_TIMEOUT_SECONDS": "60",
        "PARSING_MAX_PAGES": "180",
    }

    assert Settings.load(env).artifacts_path is None


def test_a_docling_repository_cached_at_a_tag_passes(tmp_path) -> None:
    """Docling pins its own revision, a tag and not `main`, so any snapshot counts."""
    fill(tmp_path)
    folder = tmp_path / "hub" / "models--docling-project--docling-models"
    (folder / "refs" / "main").unlink()
    (folder / "refs" / "v2.3.0").write_text("3" * 40)

    assert cache_problems(source(tmp_path)) == []


def test_a_docling_repository_with_no_snapshot_is_named(tmp_path) -> None:
    """Present as a folder, holding nothing."""
    fill(tmp_path)
    folder = tmp_path / "hub" / "models--docling-project--docling-models"
    for one in (folder / "snapshots" / ("3" * 40)).iterdir():
        one.unlink()
    (folder / "snapshots" / ("3" * 40)).rmdir()

    (said,) = cache_problems(source(tmp_path))

    assert "docling-models" in said


# ── What fills the cache this check reads ─────────────────────────────────


def test_missing_docling_weights_name_the_host_fetch(tmp_path) -> None:
    """The plain target fills the containers' volume, not the host cache read here."""
    cached(tmp_path, *EMBEDDER)
    cached(tmp_path, *CLASSIFIER)

    said = cache_problems(source(tmp_path))

    assert len(said) == 2
    assert all("make docling-weights HOST=1" in one for one in said), said


def test_a_missing_encoder_names_the_command_that_fetches_its_commit(tmp_path) -> None:
    """The repository at the pinned commit, into the cache this check reads."""
    (said,) = [one for one in cache_problems(source(tmp_path)) if EMBEDDER[0] in one]

    assert f"hf download {EMBEDDER[0]} --revision {EMBEDDER[1]}" in said
