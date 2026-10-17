"""Every per-language word table holds every language NLP_MODELS configures.

A language missing from one is no error anywhere: the gate reading the table
treats it as it treats no language at all, which for a count, a polarity or
a purpose is a rule that never fires, and nothing logs it. So a language
added to NLP_MODELS without its rows fails here instead, naming the table.

The tables are found by reading the source, so one added later is held to
the same rule without being listed here: every module-level dict under
`backend/` with an ISO 639-1 code NLP_MODELS names as a literal key. One
built by a comprehension is not seen that way, so those are named.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _configured() -> frozenset[str]:
    """The languages NLP_MODELS names in the shipped backend.env."""
    text = (ROOT / "configs/env/backend.env").read_text()
    (value,) = re.findall(r"^NLP_MODELS=(.*)$", text, re.MULTILINE)
    return frozenset(
        pair.split(":")[0].strip().lower() for pair in value.split(",") if ":" in pair
    )


#: The tables built by a comprehension, which the source scan cannot key.
BUILT = ("nlp.analysis.CARDINALS", "nlp.analysis._NUMBER_WORDS")

#: Tables keyed by language that are right to miss one, and why.
EXEMPT = {
    #: Only a language with a correlate pronoun has one: English has none.
    "nlp.analysis._CORRELATES",
    #: A language missing here is named by its own ISO code in a prompt,
    #: which is still an instruction a model can follow.
    "nlp.models._NAMED",
}


def _keyed(languages: frozenset[str]) -> list[str]:
    """Every module-level dict in the backend with one of these as a literal key."""
    found = []
    for path in sorted(BACKEND.rglob("*.py")):
        module = ".".join(path.relative_to(BACKEND).with_suffix("").parts)
        for node in ast.parse(path.read_text()).body:
            target = node.target if isinstance(node, ast.AnnAssign) else None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            value = getattr(node, "value", None)
            if not isinstance(target, ast.Name) or not isinstance(value, ast.Dict):
                continue
            keys = {
                key.value
                for key in value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys & languages:
                found.append(f"{module}.{target.id}")
    return found


def _table(name: str) -> dict:
    """The table a dotted name points at."""
    module, _, attribute = name.rpartition(".")
    return getattr(importlib.import_module(module), attribute)


def test_the_scan_finds_the_tables_it_is_meant_to() -> None:
    """A scan finding nothing would pass every language."""
    found = set(_keyed(_configured()))

    assert {
        "question_generation.gates._ASKED_FOR",
        "question_generation.gates._ASKS_HOW_MANY",
        "question_generation.gates._POLARITY",
        "question_generation.gates._PURPOSE",
        "nlp.analysis._ORDINALS",
        "nlp.analysis._CONTRASTIVE",
        "nlp.analysis.DECIMAL_MARK",
        "nlp.text.JOINING",
    } <= found


@pytest.mark.parametrize(
    "name",
    sorted(
        {*_keyed(_configured()), *BUILT, "question_generation.gates._COUNTED"} - EXEMPT
    ),
)
def test_every_configured_language_has_its_rows(name: str) -> None:
    """Each language NLP_MODELS names is a key of the table."""
    missing = _configured() - set(_table(name))

    assert not missing, f"{name} holds no rows for {sorted(missing)}"
