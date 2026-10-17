"""How every stage's queue claims its next row.

Two workers of one stage claim from the same table. Without SKIP LOCKED the
second waits on the first's row and then takes it too, so the same document
or topic is worked twice; the integration test proves this for parsing
only, and every other stage writes the same clause by hand.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize(
    "module",
    [
        "preprocessing.parsing.repository",
        "preprocessing.chunking.repository",
        "extraction.repository",
        "topic_modelling.repository",
        "question_generation.queue",
        "assessment.repository",
    ],
)
def test_every_stage_queue_claims_with_skip_locked(module: str) -> None:
    """Compiled as Postgres runs it, the claim skips a row another holds."""
    claim = importlib.import_module(module)._NEXT_PENDING

    assert "FOR UPDATE SKIP LOCKED" in str(claim.compile(dialect=postgresql.dialect()))
