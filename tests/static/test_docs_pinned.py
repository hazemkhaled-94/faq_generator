"""What the documentation says about the code, pinned to the code.

Each test holds one claim an operator or a developer acts on: the doc says
it, and the code does it. A test fails when either side moves, so a change to
the behaviour comes with a change to the sentence describing it.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

#: A declaration, commented out or not, as the settings tests read one.
_DECLARED = re.compile(r"^[^\S\n]*#?[^\S\n]*([A-Z][A-Z0-9_]*)[^\S\n]*=", re.MULTILINE)

#: The five models a stage names for itself, in configs/env/backend.env.
_STAGE_MODELS = (
    "EXTRACTION_MODEL",
    "EXTRACTION_DIGEST_MODEL",
    "TOPIC_MODEL",
    "QUESTIONS_MODEL",
    "QUESTIONS_PHRASING_MODEL",
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def _flat(text: str) -> str:
    """The text with every run of whitespace read as one space."""
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """One section, from its heading to the next of the same depth or higher."""
    depth = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading)
    rest = text[start + len(heading) :]
    ends = [
        found.start()
        for found in re.finditer(r"^(#+) ", rest, re.MULTILINE)
        if len(found.group(1)) <= depth
    ]
    return heading + (rest[: ends[0]] if ends else rest)


def _function(relative: str, name: str) -> str:
    """The source of one function or method, found anywhere in a module."""
    source = _read(relative)
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
        ):
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{relative} defines no {name}")


def _row(text: str, setting: str) -> str:
    """The configuration table row a README gives one setting."""
    (row,) = [line for line in text.splitlines() if line.startswith(f"| `{setting}` |")]
    return row


def _help(name: str) -> str:
    """A setting's help as a page shows it."""
    from settings.catalog import BY_NAME

    return _flat(BY_NAME[name].help)


def _targets() -> set[str]:
    """Every target the Makefile defines."""
    return set(re.findall(r"^([a-z][a-z0-9-]*):", _read("Makefile"), re.MULTILINE))


# ── Where a setting comes from, and what a change to one stales ────────────


def test_a_command_line_value_reaches_host_commands_only() -> None:
    """A `make` command-line value never reaches a running container.

    The Makefile alone names QA_COMMAND_LINE, and nothing compose or the env
    files hand a container carries it, so configuration.md may promise only
    the host process.
    """
    makefile = _read("Makefile")
    setters = [line for line in makefile.splitlines() if "QA_COMMAND_LINE=" in line]
    assert len(setters) == 1 and setters[0].startswith("OVERRIDE ="), setters
    assert 'COMMAND_LINE = "QA_COMMAND_LINE"' in _read("backend/settings/store.py")

    for path in ["compose.yaml", ".env.example", *ROOT.glob("configs/env/*.env")]:
        text = (ROOT / path).read_text()
        assert "QA_COMMAND_LINE" not in text, f"{path} hands QA_COMMAND_LINE on"
        assert "MAKEOVERRIDES" not in text, f"{path} hands MAKEOVERRIDES on"

    assert "It never reaches a running container" in _flat(
        _read("docs/configuration.md")
    )


def test_every_rebuild_is_a_make_target() -> None:
    """A settings change prints its catalogue entry's rebuild as a command to run.

    So each one is a Makefile target, the bridge and recap settings carry
    theirs, and the commands configuration.md and the settings README give as
    examples are real ones.
    """
    from settings.catalog import BY_NAME, SETTINGS

    targets = _targets()
    for one in SETTINGS:
        if one.rebuild:
            command, _, target = one.rebuild.partition(" ")
            assert command == "make" and target in targets, (one.name, one.rebuild)
            # changes.py names a rebuild only for a setting that stales something.
            assert one.invalidates, f"{one.name}: a rebuild nothing prints"
        for named in re.findall(r"`make ([a-z][a-z0-9-]*)", one.help):
            assert named in targets, (one.name, named)
    assert BY_NAME["EXTRACTION_BRIDGES_PER_TOPIC"].rebuild == "make extract-bridge"
    assert BY_NAME["EXTRACTION_BRIDGE_PASSAGES"].rebuild == "make extract-bridge"
    assert BY_NAME["EXTRACTION_MIN_OTHER_SHARE"].rebuild == "make extract-recap"

    rebuilds = {one.rebuild for one in SETTINGS if one.rebuild}
    configuration = _flat(_read("docs/configuration.md"))
    for example in ("make extract-revalidate", "make questions-balance"):
        assert f"`{example}`" in configuration, example
        assert example in rebuilds, f"no catalogue entry names {example}"
    assert "Rerunning extraction leaves the bridges to `make extract-bridge`" in (
        configuration
    )

    assert "topics-rerun" not in targets
    assert "`make topics-discover` for topics, which has none" in _flat(
        _read("backend/settings/README.md")
    )


def test_every_stale_stage_has_a_command_that_rebuilds_it() -> None:
    """A stale stage's rerun is its -rerun target, bar topics, whose is topics-discover."""
    from settings.catalog import SETTINGS

    rebuilt_by = {
        "parsing": "parse-rerun",
        "chunking": "chunk-rerun",
        "extraction": "extract-rerun",
        "topics": "topics-discover",
        "questions": "questions-rerun",
    }
    targets = _targets()
    stale = {stage for one in SETTINGS for stage in one.invalidates}

    assert stale <= set(rebuilt_by), sorted(stale - set(rebuilt_by))
    for stage in stale:
        assert rebuilt_by[stage] in targets, f"{stage}: no {rebuilt_by[stage]}"
    assert "bar topics, which have none: `make topics-discover`" in _flat(
        _read("docs/configuration.md")
    )


def test_a_setting_that_only_shapes_the_next_run_stales_nothing() -> None:
    """These shape only what the next run is offered, so a change stales nothing.

    No reverify, recheck, rescore or release draw reads them, so a page
    calling the stored questions stale would send an operator to a rerun
    that changes nothing.
    """
    from settings.catalog import BY_NAME

    shaping = {
        "QUESTIONS_PARTY_DENSITY": "party_density",
        "QUESTIONS_MEETS_FLOOR": "meets_floor",
        "QUESTIONS_MEETS_SHARE": "meets_share",
        "QUESTIONS_BOILERPLATE_COSINE": "boilerplate_cosine",
        "QUESTIONS_FACT_SAMPLE": "sample_size",
    }
    stored = {
        name: _function("backend/question_generation/service.py", name)
        for name in ("reverify", "_recheck", "rescore", "balance")
    }

    assert not [name for name in shaping if BY_NAME[name].invalidates]
    for attribute in shaping.values():
        for name, source in stored.items():
            assert attribute not in source, f"{name} reads {attribute}"


def test_embedding_model_stales_every_stage_that_embeds() -> None:
    """A new embedding model stales every stage whose settings read it."""
    from settings.catalog import BY_NAME

    folders = {
        "preprocessing/parsing": "parsing",
        "preprocessing/chunking": "chunking",
        "extraction": "extraction",
        "topic_modelling": "topics",
        "question_generation": "questions",
    }
    reading = {
        stage
        for folder, stage in folders.items()
        if '"EMBEDDING_MODEL"' in _read(f"backend/{folder}/config.py")
    }

    assert reading == {"chunking", "extraction", "questions"}
    assert set(BY_NAME["EMBEDDING_MODEL"].invalidates) == reading
    assert "extraction embeds passages and facts" in _help("EMBEDDING_MODEL")


# ── Which model a call follows ─────────────────────────────────────────────


def test_container_model_pairs_are_the_ones_compose_sets() -> None:
    """The models given a container value are exactly the ones compose sets.

    The other five come from backend.env, which every model-calling
    container takes unchanged.
    """
    compose = yaml.safe_load(_read("compose.yaml"))
    compose_sets = {name for name in compose["x-model-env"] if name.endswith("_MODEL")}

    text = _read("docs/configuration.md")
    said = re.search(
        r"Three have a container value of their own, which compose sets over "
        r"the host's: (.*?), in the table above",
        _flat(text),
    )
    assert said, "the page no longer says which models a container is given"
    assert set(re.findall(r"`([A-Z_]+)`", said.group(1))) == compose_sets

    pairs = text.split("### The host and the container see different addresses")[
        1
    ].split("The model pairs are")[0]
    tabled = {
        name
        for row in pairs.splitlines()
        if row.startswith("| `")
        for name in re.findall(r"`([A-Z_]+)`", row.split("|")[1])
        if name.endswith("_MODEL")
    }
    assert tabled == compose_sets, tabled

    assert not compose_sets & set(_STAGE_MODELS)
    assert "configs/env/backend.env" in compose["x-model-env-files"]


def test_only_the_documented_model_settings_have_a_container_counterpart() -> None:
    """Compose overrides three model settings; the settings README says which."""
    overridden = {
        name
        for name in yaml.safe_load(_read("compose.yaml"))["x-model-env"]
        if name.endswith("_MODEL")
    }

    assert overridden == {
        "LLM_MODEL",
        "QUESTIONS_VERIFIER_MODEL",
        "ASSESSMENT_JUDGE_MODEL",
    }
    assert (
        "compose gives the containers their own `LLM_MODEL`, "
        "`QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`; the other five "
        "come from `backend.env` for both"
    ) in _flat(_read("backend/settings/README.md"))


def test_each_model_setting_is_where_the_doc_says() -> None:
    """The deployment's models are in .env and a stage's own in backend.env.

    As configuration.md's 'Where to look' row says, and both the host and a
    model worker read backend.env.
    """
    example = set(_DECLARED.findall(_read(".env.example")))
    backend = set(_DECLARED.findall(_read("configs/env/backend.env")))

    for name in ("LLM_MODEL", "QUESTIONS_VERIFIER_MODEL", "ASSESSMENT_JUDGE_MODEL"):
        assert name in example and name not in backend, name
    # backend.env documents each stage model, unset; the go-live split that
    # sets them is the deployment's, in .env.example.
    live = set(
        re.findall(
            r"^([A-Z][A-Z0-9_]*)=", _read("configs/env/backend.env"), re.MULTILINE
        )
    )
    for name in _STAGE_MODELS:
        assert name in backend and name not in live and name in example, name
    assert "LOADENV = set -a && . ./configs/env/backend.env" in _read("Makefile")

    row = next(
        line
        for line in _read("docs/configuration.md").splitlines()
        if line.startswith("| Which model, and where it is served |")
    )
    assert "configs/env/backend.env" in row
    for name in _STAGE_MODELS:
        assert f"`{name}`" in row, name


def test_architecture_names_every_model_setting() -> None:
    """Section 6's model row names every model a call can follow.

    The per-stage models live in configs/env/backend.env, and the shipped
    file sets some of them, so those calls do not follow LLM_MODEL.
    """
    encoders = {"EMBEDDING_MODEL", "NLI_MODEL", "QA_MODEL"}
    stage_models = {
        name
        for name in re.findall(
            r"^#? ?([A-Z][A-Z0-9_]*_MODEL)=",
            _read("configs/env/backend.env"),
            re.MULTILINE,
        )
        if name not in encoders
    }
    row = next(
        line
        for line in _read("docs/architecture.md").splitlines()
        if line.startswith("| Which model, or which provider |")
    )

    assert stage_models, "configs/env/backend.env names no stage model"
    for name in {"LLM_MODEL", "LLM_CONTAINER_MODEL", *stage_models}:
        assert f"`{name}`" in row, f"the model row does not name {name}"


def test_llm_readme_names_the_stage_models_containers_inherit() -> None:
    """Every model compose does not override reaches the containers from backend.env.

    So the llm README's container section names each of them.
    """
    from settings.catalog import BY_NAME

    models = {
        name for name, one in BY_NAME.items() if name.endswith("_MODEL") and one.fixed
    }
    named = set(
        re.findall(
            r"^#?\s*([A-Z][A-Z0-9_]*_MODEL)=",
            _read("configs/env/backend.env"),
            re.MULTILINE,
        )
    )
    overridden = set(yaml.safe_load(_read("compose.yaml"))["x-model-env"])
    inherited = (named & models) - overridden
    section = _section(_read("backend/llm/README.md"), "### The containers call Ollama")

    assert inherited
    missing = sorted(name for name in inherited if f"`{name}`" not in section)
    assert not missing, f"the container section does not name {missing}"


# ── Where the stages run ───────────────────────────────────────────────────


def test_host_drains_are_not_said_to_be_kept_off() -> None:
    """Nothing keeps a host drain's rows out of the dataset, so no doc may say so.

    A host drain sources the same files and writes the same database as the
    workers; the Makefile's IDLE only checks that the stage's worker is
    stopped. A doc promising otherwise lets a developer build the dataset
    from a host run without knowing it.
    """
    docs = [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "backend").rglob("README.md")),
    ]
    saying = [
        str(path.relative_to(ROOT))
        for path in docs
        if re.search(
            r"kept off (the dataset|it)|runs off the dataset", _flat(path.read_text())
        )
    ]

    assert not saying, f"say host runs are kept off the dataset: {saying}"
    for relative in ("backend/llm/README.md", "backend/stages/README.md"):
        assert "Nothing keeps a host run out of the dataset" in _flat(
            _read(relative)
        ), relative
    (guard,) = re.findall(r"^IDLE = (.*)$", _read("Makefile"), re.MULTILINE)
    assert guard.startswith("! $(COMPOSE_CMD) ps -q $(1)"), guard


def test_a_setting_new_in_the_upgrade_table_loads_without_its_line() -> None:
    """A setting an upgrade table marks new loads from a backend.env without it.

    operations.md tells an operator that a copied file keeps working after an
    upgrade, so each such setting not marked required is read through
    `optional()` in its config module.
    """
    marked = set()
    for row in _read("docs/operations.md").splitlines():
        named = re.match(r"^\| `([A-Z][A-Z0-9_]*)` \|", row)
        last = row.rstrip(" |").rsplit("|", 1)[-1]
        if named and re.search(r"\bnew\b", last):
            if "required" in last and "required until" not in last:
                continue
            marked.add(named.group(1))
    readers = "\n".join(
        path.read_text() for path in sorted((ROOT / "backend").rglob("config.py"))
    )

    assert marked, "no upgrade table marks a setting new"
    for name in sorted(marked):
        assert f'optional("{name}"' in readers, f"{name} is required"


def test_the_upgrade_rebuild_names_no_host_drain() -> None:
    """The upgrade guide rebuilds a stack through the workers, not host drains.

    A host drain refuses while `make up`'s worker for its stage runs, so the
    sentence that queues each stage names only targets without an IDLE
    guard. The sentence after it names the host drains on purpose.
    """
    makefile = _read("Makefile")
    guarded = {
        target
        for target, recipe in re.findall(
            r"^([a-z][a-z0-9-]*):[^\n]*\n((?:\t[^\n]*\n)*)", makefile, re.MULTILINE
        )
        if "$(call IDLE," in recipe
    }
    operations = _flat(_read("docs/operations.md"))
    queueing = re.findall(
        r"[^.]*queue each stage[^.]*`make questions-balance`\.", operations
    )

    assert queueing, "the upgrade rebuild sentence is gone"
    for sentence in queueing:
        for target in re.findall(r"`make ([a-z][a-z0-9-]*)", sentence):
            assert target not in guarded, f"{target} is a host drain"


# ── What the README promises ───────────────────────────────────────────────


def test_readme_says_whether_the_release_holds_unanswerables() -> None:
    """The opening promises unanswerable questions; it says what the release holds."""
    value = re.search(
        r"^QUESTIONS_RELEASE_UNANSWERABLE=(\S*)",
        _read("configs/env/backend.env"),
        re.MULTILINE,
    ).group(1)
    opening = _flat(_read("README.md").split("\n## ", 1)[0])

    if float(value) == 0:
        assert "`QUESTIONS_RELEASE_UNANSWERABLE` is 0" in opening
        assert "the release holds none of them" in opening
    else:
        assert f"`QUESTIONS_RELEASE_UNANSWERABLE` is {value}" in opening
        assert "the release holds none of them" not in opening


def test_readme_lists_what_corpus_runs() -> None:
    """README's stage-by-stage block is what `make corpus` runs, in its order."""
    recipe = _read("Makefile").split("\ncorpus:\n", 1)[1].split("\n\n", 1)[0]
    steps = [
        " ".join(line.replace(" $(CORPUS_PINS)", "").replace("$(MAKE)", "make").split())
        for line in recipe.splitlines()
        if "$(MAKE)" in line and "$(foreach" not in line
    ]
    readme = _read("README.md")
    block = readme.split("Stage by stage", 1)[1].split("```bash\n", 1)[1]
    listed = [
        " ".join(line.split("#", 1)[0].split())
        for line in block.split("```", 1)[0].splitlines()
    ]

    at = 0
    for step in steps:
        assert step in listed[at:], f"README's corpus block lacks {step!r} in order"
        at = listed.index(step, at) + 1


# ── Parsing ────────────────────────────────────────────────────────────────


def test_min_confidence_is_not_called_the_worst_page() -> None:
    """The floor is Docling's low score averaged over the pages, not the worst page."""
    step = _flat(
        _section(
            _read("backend/preprocessing/parsing/README.md"),
            "### Step 7 — Two refusals after the fact",
        )
    )
    said = _help("PARSING_MIN_CONFIDENCE")

    assert 'confidence_low=_score(result, "low_score")' in _read(
        "backend/preprocessing/parsing/pipelines/pdf.py"
    )
    assert "parsed.confidence_low" in _function(
        "backend/preprocessing/parsing/service.py", "_trustworthy"
    )
    assert "averaged over the pages" in step and "averaged over the pages" in said
    assert "worst of the document" not in step
    assert "worst" not in said


def test_parsing_readme_names_hidden_words() -> None:
    """Parsing removes words a clip hides, so Step 4 of its README says so."""
    pdf = _read("backend/preprocessing/parsing/pipelines/pdf.py")
    readme = _read("backend/preprocessing/parsing/README.md")
    (heading,) = re.findall(r"^### Step 4 — .*$", readme, re.MULTILINE)
    step = _flat(_section(readme, heading))

    assert "def _hidden(" in pdf and "_UNCLIPPED" in pdf
    assert "hidden" in heading, heading
    assert "clip" in step
    assert "invisible" in step and "OCR" in step


# ── Extraction ─────────────────────────────────────────────────────────────


def test_min_other_share_names_both_ends_and_its_recap() -> None:
    """0 and 1 both set no cap, and a new share is applied by the recap."""
    from extraction.config import atomic_cap
    from settings.catalog import BY_NAME

    said = _help("EXTRACTION_MIN_OTHER_SHARE")

    assert "0 or 1 turns the cap off" in said
    assert "no digest kind" in said
    assert atomic_cap(2, 0.0) is None and atomic_cap(2, 1.0) is None
    assert atomic_cap(0, 0.33) is None
    assert BY_NAME["EXTRACTION_MIN_OTHER_SHARE"].rebuild == "make extract-recap"


def test_duplicate_probe_is_judged_again_under_a_lock() -> None:
    """The duplicate probe reads only stored facts, and the store reads again.

    So the extraction README says two drains side by side are safe because the
    store judges the facts again under a lock per language and kind, which the
    operations guide scales on.
    """
    readme = _flat(_read("backend/extraction/README.md"))

    assert "every validated passage fact already stored in the corpus" in readme
    assert (
        "takes a lock for each language and kind among a passage's validated facts"
    ) in readme
    assert "Fact.validated" in _function(
        "backend/extraction/repository.py", "_nearest_fact"
    )
    assert "pg_advisory_xact_lock" in _function(
        "backend/extraction/repository.py", "store"
    )
    assert "--scale extract-worker" in _read("docs/operations.md")


def test_the_not_atomic_repair_is_described_as_it_runs() -> None:
    """Once per passage, only for `not_atomic`, and a failed call fails nothing.

    The behaviour is in the unit tests; this pins the README's sentence to
    the method that keeps it.
    """
    readme = _flat(_read("backend/extraction/README.md"))
    repaired = _function("backend/extraction/service.py", "_repaired")

    assert "is sent back to the same model once, in one more call" in readme
    assert (
        "a repair call that fails leaves the refusals standing and is logged "
        "rather than failing the passage"
    ) in readme
    assert "Rejection.NOT_ATOMIC" in repaired
    assert "except ExtractionFailed" in repaired


# ── The model client ───────────────────────────────────────────────────────


def test_retried_failures_are_the_ones_documented() -> None:
    """The help names a server error and a misshapen answer: the client retries both."""
    tree = ast.parse(_read("backend/llm/client.py"))
    (transient,) = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_TRANSIENT" for t in node.targets)
    ]
    retried = {ast.unparse(one).rsplit(".", 1)[-1] for one in transient.elts}
    said = _help("LLM_MAX_ATTEMPTS")

    assert {
        "InternalServerError",
        "ServiceUnavailableError",
        "InstructorRetryException",
    } <= retried
    assert "a server error" in said
    assert "an answer that does not fit" in said


# ── Language tables ────────────────────────────────────────────────────────


def test_nlp_readme_lists_every_word_table() -> None:
    """Adding a language means editing every per-language table and language set.

    So the nlp README's 'Adding a language' section names each one the code
    holds, the hyphen rejoin's letters included.
    """
    (value,) = re.findall(
        r"^NLP_MODELS=(.*)$", _read("configs/env/backend.env"), re.MULTILINE
    )
    languages = {
        pair.split(":")[0].strip().lower() for pair in value.split(",") if ":" in pair
    }
    keyed: set[str] = set()
    coded: set[str] = set()
    for path in sorted((ROOT / "backend").rglob("*.py")):
        for node in ast.parse(path.read_text()).body:
            target = node.target if isinstance(node, ast.AnnAssign) else None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            value_node = getattr(node, "value", None)
            if not isinstance(target, ast.Name):
                continue
            if (
                isinstance(value_node, ast.Dict)
                and {
                    key.value
                    for key in value_node.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                & languages
            ):
                keyed.add(target.id)
            if (
                isinstance(value_node, ast.Call)
                and getattr(value_node.func, "id", None) == "frozenset"
                and value_node.args
                and isinstance(value_node.args[0], ast.Set)
                and {
                    one.value
                    for one in value_node.args[0].elts
                    if isinstance(one, ast.Constant)
                }
                & languages
            ):
                coded.add(target.id)
    section = _section(_read("backend/nlp/README.md"), "## Adding a language")
    text = _read("backend/nlp/text.py")

    assert {"JOINING", "_DIVISIONS"} <= keyed
    assert "def _broken_word(" in text and "[A-Za-zÄÖÜäöüß]" in text
    wanted = keyed | coded | {"_broken_word"}
    missing = sorted(name for name in wanted if f"`{name}`" not in section)
    assert not missing, f"'Adding a language' does not name {missing}"


# ── Topic modelling ────────────────────────────────────────────────────────


def test_topic_count_names_fact_bearing_passages() -> None:
    """The topic count scales over the fact-bearing passages a fit reads."""
    repository = _read("backend/topic_modelling/repository.py")
    passages = _function("backend/topic_modelling/repository.py", "passages")
    fit = _function("backend/topic_modelling/topics.py", "fit")
    row = _row(_read("backend/topic_modelling/README.md"), "TOPIC_PASSAGES_PER_TOPIC")

    # One clause, `_BEARING`, says what a fact-bearing passage is, for the
    # corpus a fit reads and the stale check alike.
    bearing = repository.split("_BEARING = (", 1)[1].split("\n)\n", 1)[0]
    assert "Fact.validated" in bearing and "query.where(_BEARING)" in passages
    assert "self._count(counted)" in fit
    assert "carry a validated fact" in _help("TOPIC_PASSAGES_PER_TOPIC")
    assert "counting the passages that carry a validated fact" in row


# ── Question generation ────────────────────────────────────────────────────


def test_fact_sample_floor_is_one_per_passage() -> None:
    """The deal offers at least one fact from each passage of a sample."""
    readme = _flat(_read("backend/question_generation/README.md"))

    assert "max(1, self._size // len(passages))" in _function(
        "backend/question_generation/selection.py", "_group"
    )
    assert "never fewer than one from each" in readme


def test_the_list_ceiling_is_the_one_the_readme_names() -> None:
    """A reading type takes a list whole up to the ceiling the README names."""
    tree = ast.parse(_read("backend/question_generation/selection.py"))
    (ceiling,) = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and [getattr(one, "id", None) for one in node.targets] == ["_GROUP_CEILING"]
    ]
    readme = _flat(_read("backend/question_generation/README.md"))
    given = [
        *re.findall(r"up to (\d+) facts in the whole sample", readme),
        *re.findall(r"took a list whole, up to (\d+)", readme),
        *re.findall(r"the rest of a chosen fact's list, up to (\d+)", readme),
    ]

    assert len(given) == 3, given
    assert {int(one) for one in given} == {ceiling}


def test_reverify_names_the_gates_it_reruns() -> None:
    """The release draw re-checks through _recheck, and the README names its gates."""
    recheck = _function("backend/question_generation/service.py", "_recheck")
    called = {
        node.func.id
        for node in ast.walk(ast.parse(recheck))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    readme = _flat(_read("backend/question_generation/README.md"))
    start = readme.index("The draw re-checks first")
    paragraph = readme[start : readme.index("Beyond that,", start)]

    assert {"structural", "typed", "near_verdict"} <= called
    assert not called & {
        "on_topic",
        "explains",
        "cites_source",
        "moves_on",
        "same_material",
    }
    assert "titles" not in recheck
    for said in (
        "`source_changed`",
        "structural gates other than the document-title check",
        "its type's rules",
        "duplicate probe",
        "on its facts alone",
    ):
        assert said in paragraph, said
    for gate in (
        "off_topic",
        "explanation_unusable",
        "leaks_source",
        "asks_nothing_new",
        "off_thread",
    ):
        assert f"`{gate}`" in paragraph, gate
    assert "are not run again" in paragraph


def test_the_boilerplate_twin_is_of_the_same_language() -> None:
    """Only a passage of the same language in another document is a furniture twin.

    The catalogue help and the question README both say so, and the README
    no longer says a translation reads as furniture.
    """
    readme = _read("backend/question_generation/README.md")
    flat = _flat(readme)

    assert "twin.language == Passage.language" in _function(
        "backend/question_generation/queue.py", "repeated_across_documents"
    )
    assert "of its own language" in _help("QUESTIONS_BOILERPLATE_COSINE")
    assert "in another document of its own language" in flat
    assert "in another document of its own language" in _row(
        readme, "QUESTIONS_BOILERPLATE_COSINE"
    )
    assert "A language held by one document gets no boilerplate filtering" in flat
    assert "A translation can read as furniture" not in flat


def test_boilerplate_names_its_abstentions() -> None:
    """Furniture is never read in a language one document holds or without a vector."""
    predicate = _function(
        "backend/question_generation/queue.py", "repeated_across_documents"
    )
    said = _help("QUESTIONS_BOILERPLATE_COSINE")

    assert "twin.doc_sha256 != Passage.doc_sha256" in predicate
    assert "Passage.embedding.is_not(None)" in predicate
    assert "a language held by one document" in said
    assert "a passage with no embedding" in said


# ── The evaluation phase ───────────────────────────────────────────────────


def test_assess_enrol_is_never_called_a_preview() -> None:
    """assess-enrol writes the rows a start judges, so no doc offers it as a free look.

    Every command line in the docs that runs it says it is not a dry run.
    """
    run = [
        line
        for relative in ("README.md", "docs/make.md", "backend/assessment/README.md")
        for line in _read(relative).splitlines()
        if line.startswith("make assess-enrol ")
    ]

    assert len(run) >= 3, run
    assert all("not a dry run" in line for line in run), run
    assert "Enrol without queuing. Not a dry run: it writes" in _flat(_read("Makefile"))


# ── docs/make.md and make help ─────────────────────────────────────────────


def _make(*arguments: str) -> list[str]:
    """What make prints for the arguments, one line per entry."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    return subprocess.run(
        ["make", "--no-print-directory", *arguments],
        cwd=ROOT,
        env=inherited,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def _help_lines() -> dict[str, tuple[str, str]]:
    """Each target `make help` lists, as (its group, its description)."""
    listed: dict[str, tuple[str, str]] = {}
    group = ""
    for line in _make("help"):
        if line and not line.startswith(" "):
            group = line.strip()
        elif shown := re.match(r"^  ([a-z][a-zA-Z0-9_-]*) +(.*)$", line):
            listed[shown[1]] = (group, shown[2])
    return listed


def _comment_above(target: str) -> str:
    """The comment lines directly above a target in the Makefile, as one line."""
    lines = _read("Makefile").splitlines()
    at = lines.index(f"{target}:")
    above: list[str] = []
    while at > 0 and lines[at - 1].startswith("#"):
        at -= 1
        above.insert(0, lines[at].lstrip("# "))
    return _flat(" ".join(above))


def _make_md_section(heading: str) -> str:
    """One `## ` section of docs/make.md, its subsections included."""
    (section,) = [
        part
        for part in re.split(r"^## ", _read("docs/make.md"), flags=re.MULTILINE)
        if part.startswith(f"{heading}\n")
    ]
    return _flat(section)


def _make_md_rows(target: str) -> list[str]:
    """Every table row of docs/make.md whose first cell is `target`."""
    return [
        line
        for line in _read("docs/make.md").splitlines()
        if line.startswith(f"| `{target}` |")
    ]


def test_help_lists_every_documented_target(tmp_path: Path) -> None:
    """make.md says help lists a target only under a comment directly above it.

    So a line between the two, an assignment or a blank, drops the target
    from `make help` without a word, which is how one went missing.
    """
    said = _flat(_read("docs/make.md"))
    assert "the first sentence of the comment directly above it" in said
    assert "A target with no comment directly above it is not listed" in said

    extra = tmp_path / "extra.mk"
    extra.write_text(
        "# Described directly above. And more.\n"
        "pin-described:\n\t@true\n\n"
        "# Described, then a gap.\n\n"
        "pin-undescribed:\n\t@true\n"
    )
    shown = "\n".join(_make("-f", "Makefile", "-f", str(extra), "help"))

    described = r"^  pin-described +Described directly above\.$"
    assert re.search(described, shown, re.MULTILINE), shown
    assert "pin-undescribed" not in shown


def test_help_lists_every_target_make_md_documents() -> None:
    """Every target docs/make.md's tables name is one `make help` lists.

    help drops a target whose comment is not directly above it, so a line
    in between, as `OUT ?=` was above questions-export, hides it quietly.
    """
    targets = set(
        re.findall(r"^([a-z][a-z0-9-]*):(?!=)", _read("Makefile"), re.MULTILINE)
    )
    documented: set[str] = set()
    for line in _read("docs/make.md").splitlines():
        if not line.startswith("|"):
            continue
        for quoted in re.findall(r"`([^`]+)`", line):
            words = quoted.split()
            if words[0] == "make" and len(words) > 1:
                documented.add(words[1])
            elif len(words) == 1 and words[0] in targets:
                documented.add(words[0])
    listed = set(_help_lines())

    assert len(documented) > 100, len(documented)
    assert sorted(documented - listed) == []


def test_every_help_line_describes_its_own_target() -> None:
    """A help line is the first sentence of the comment directly above it.

    A section's opening paragraph or another target's wording landed there
    instead, and the cost targets were listed under the evaluation phase.
    """
    listed = _help_lines()

    assert listed["phoenix-projects"][1] == "What Phoenix holds, changing nothing."
    assert listed["lint"][1].startswith("ruff check and format check")
    assert "baseline" not in listed["typecheck"][1], listed["typecheck"]
    assert listed["spend-by-shape"][1].startswith("What the models have cost")
    assert listed["assess-status"][1].startswith("Report the queue by artefact state")
    assert "what the judge has said" not in listed["assess-status"][1]
    for target in ("questions-runs", "questions-diff", "spend-by-shape", "spend"):
        assert listed[target][0] != "The evaluation phase", (target, listed[target])


def test_the_corpus_row_names_the_workers_to_stop() -> None:
    """Each drain `make corpus` runs refuses while its container worker runs.

    `make up` and `make dev` start every one, so the row has to name them all
    or a developer meets them one refusal at a time.
    """
    guarded = set(re.findall(r"ps -q (\S+-worker) ", "\n".join(_make("-n", "corpus"))))
    (row,) = _make_md_rows("make corpus")

    assert len(guarded) >= 5, guarded
    assert [worker for worker in sorted(guarded) if f"`{worker}`" not in row] == []


def test_the_corpus_comment_names_the_verifier_the_balance_calls() -> None:
    """The release draw `make corpus` runs again each time asks the verifier.

    `--balance` builds a Verifier and proves it first, and its twin verdicts
    are not stored, so the comment above `corpus:` cannot say the draw runs
    with no model.
    """
    drawn = [line for line in _make("-n", "corpus") if "run --balance" in line]
    called = {
        getattr(node.func, "id", None)
        for node in ast.walk(
            ast.parse(_function("backend/question_generation/run.py", "balanced"))
        )
        if isinstance(node, ast.Call)
    }
    comment = _comment_above("corpus")

    assert drawn, "make corpus does not draw the release"
    assert {"Verifier", "before_work"} <= called, called
    assert "no model" not in comment
    assert "asks the verifier" in comment
    assert "three rounds" in comment
    assert "not stored" in comment


def test_dev_installs_first() -> None:
    """`make dev` installs first, which needs the network, and both rows say so."""
    (prerequisites,) = re.findall(r"^dev:(.*)$", _read("Makefile"), re.MULTILINE)
    rows = _make_md_rows("make dev")

    assert "install" in prerequisites.split(), prerequisites
    assert len(rows) == 2, rows
    assert all("`make install` first" in row for row in rows), rows


def test_no_doc_says_a_question_rerun_replaces() -> None:
    """A question rerun only inserts, so make.md cannot say it replaced a run.

    `questions-diff` reads both runs live; the archive answers only for rows a
    deletion or a re-chunk took.
    """
    tree = ast.parse(_read("backend/question_generation/queue.py"))
    (store,) = [
        node
        for queue in ast.walk(tree)
        if isinstance(queue, ast.ClassDef) and queue.name == "QuestionQueue"
        for node in queue.body
        if isinstance(node, ast.FunctionDef) and node.name == "store"
    ]
    called = {
        getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for node in ast.walk(store)
        if isinstance(node, ast.Call)
    }
    said = _flat(_read("docs/make.md"))

    assert "insert" in called and "delete" not in called, called
    assert "A rerun appends" in said
    assert not re.search(r"`questions-rerun` (replace|delete)", said)


def test_make_md_names_the_container_model_variables() -> None:
    """compose.yaml gives the containers their model under names of their own.

    `.env`'s LLM_MODEL, QUESTIONS_VERIFIER_MODEL and ASSESSMENT_JUDGE_MODEL
    never reach a container, so make.md names the three it reads instead.
    """
    compose = yaml.safe_load(_read("compose.yaml"))
    mapped = " ".join(str(value) for value in compose["x-model-env"].values())
    written = _read("docs/make.md")

    for name in (
        "LLM_CONTAINER_MODEL",
        "QUESTIONS_VERIFIER_CONTAINER_MODEL",
        "ASSESSMENT_JUDGE_CONTAINER_MODEL",
    ):
        assert "${" + name in mapped, name
        assert f"`{name}`" in written, name


def test_make_md_says_a_command_line_value_beats_a_stored_setting() -> None:
    """A command-line value beats a stored setting, which settings-unset removes.

    The Makefile names the given values so the store gives way, and make.md's
    configuration section says both.
    """
    lines = _make("-n", "topics-discover", "TOPIC_PASSES=20")
    section = _make_md_section("Configuration and the container engine")

    assert any('QA_COMMAND_LINE="TOPIC_PASSES"' in line for line in lines), lines
    assert "until `make settings-unset` removes it" in section
    assert "beats them all, the stored setting included" in section


def test_make_md_docker_example_sets_container() -> None:
    """`doctor`, `prune` and `lock` run $(CONTAINER), not compose.

    A Docker example setting COMPOSE alone leaves them calling podman.
    """
    makefile = _read("Makefile")
    for target in ("doctor", "prune", "lock"):
        recipe = re.search(rf"^{target}:.*\n((?:\t.*\n)+)", makefile, re.MULTILINE)
        assert recipe and "$(CONTAINER)" in recipe[1], target

    examples = [
        line
        for line in (
            *_read("docs/make.md").splitlines(),
            *_read("README.md").splitlines(),
            *makefile.splitlines(),
        )
        if re.match(
            r"(# Override for Docker: )?make .*COMPOSE=\"docker compose\"", line
        )
    ]
    assert len(examples) >= 3, examples
    assert all("CONTAINER=docker" in line for line in examples), examples


def test_the_documents_section_points_at_the_archive() -> None:
    """A deletion is archived and `make restore-documents` puts it back.

    So the Documents section names the restore and calls none of its targets
    irreversible; only what wipe takes outside the database is final.
    """
    section = _make_md_section("Documents")

    assert 'os.environ.get("SINCE")' in _read("backend/archive/restore.py")
    assert "`make restore-documents SINCE=<time>`" in section
    assert "irreversible" not in section.lower()


def test_the_delete_row_names_the_extract_worker_refusal() -> None:
    """`make delete` refuses before deleting while extract-worker runs.

    And a deletion through the API or the UI runs no dedup replay, so the
    rows say what to stop first and what to run after.
    """
    lines = _make("-n", "delete", "SHA=abc")
    guards = [at for at, line in enumerate(lines) if "ps -q extract-worker " in line]
    deleting = [at for at, line in enumerate(lines) if "ingestion.run --delete" in line]
    (delete,) = _make_md_rows("make delete SHA=<sha256>")
    (derived,) = _make_md_rows("make delete-derived SHA=<sha256>")

    assert guards and deleting and guards[0] < deleting[0], lines
    assert "`extract-worker`" in delete and "`extract-worker`" in derived
    assert "through the API or the UI runs no replay" in delete


def test_the_pipeline_paragraph_names_what_the_job_skips() -> None:
    """The corpus job is not `make corpus` run elsewhere.

    Its Definitions hold no bridge asset and no release draw, and its workers
    call the containers' model, so make.md's Orchestration section and the
    comment above `pipeline:` say what it leaves out.
    """
    tree = ast.parse(_read("orchestration/__init__.py"))
    (definitions,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Definitions"
    ]
    (assets,) = [one.value for one in definitions.keywords if one.arg == "assets"]
    named = [ast.unparse(one) for one in getattr(assets, "elts", [])]
    section = _make_md_section("Orchestration")

    assert named and not [one for one in named if "bridge" in one], named
    assert "`make extract-bridge MISSING=1`" in section
    assert "`LLM_CONTAINER_MODEL`" in section
    assert "without the bridge pass or the release draw" in _comment_above("pipeline")
