"""BL-B21: `make diversity BY=kind` gives each kind its factoid and open-ended shares.

`BY=category` prints them (with word bounds) in `_conformance`; `BY=kind`
prints only the diversity table and the judge's means. Word bounds belong to
a category, so a kind has none; the factoid / open-ended split is read off
the stored answer form and holds for a kind as well as for a category.
"""

from __future__ import annotations

import pytest

from assessment import run as cli
from question_generation.export import workbook
from question_generation.models import StoredQuestion


def _asked(id: int, text: str, language: str, kind: str, form: str) -> StoredQuestion:
    return StoredQuestion(
        categories=[],
        answer_form=form,
        kind=kind,
        id=id,
        question_text=text,
        target_answer="Within 14 days.",
        answer_explanation="A return is refunded within 14 days of receipt.",
        answerable=True,
        difficulty="easy",
        passage_scope="single_passage",
        document_scope="single_document",
        topic_scope="single_topic",
        answer_chars=15,
        language=language,
        status="accepted",
        rejected_reason=None,
        created_at="2026-10-21T12:00:00+00:00",
        facts=1,
        documents=["Returns policy"],
        topics=["Returns"],
        statements=["A return is refunded within 14 days of receipt."],
        evidence=["Returns are refunded within 14 days of receipt."],
    )


@pytest.fixture
def kinded(tmp_path, monkeypatch):
    """A workbook of four kinded questions, the language models stubbed."""
    path = tmp_path / "kinded.xlsx"
    path.write_bytes(
        workbook(
            [
                _asked(
                    1, "Wann wird eine Rücksendung erstattet?", "de", "single", "value"
                ),
                _asked(
                    2,
                    "Warum verlangt die Bank eine zweite Unterschrift?",
                    "de",
                    "single",
                    "explanation",
                ),
                _asked(
                    3,
                    "Wie lange dauert die Erstattung, und wer trägt das Porto?",
                    "de",
                    "compound",
                    "list",
                ),
                _asked(
                    4, "When is a card refund credited?", "en", "needs_both", "value"
                ),
            ]
        )
    )
    monkeypatch.setattr(cli, "snapshot", lambda: ({}, "test"))
    monkeypatch.setattr(
        cli, "_tags", lambda texts, language: (["NOUN VERB"] * len(texts), "stub 1.0")
    )
    monkeypatch.setattr(cli, "_vectors", lambda texts: [[1.0, 0.0] for _ in texts])
    return path


def test_by_kind_gives_each_kind_its_factoid_and_open_ended_shares(
    kinded, capsys
) -> None:
    """The per-kind report carries the shares and no word-bounds column."""
    assert cli.main(["--diversity", "--file", str(kinded), "--by", "kind"]) == 0
    out = capsys.readouterr().out
    assert "factoid" in out and "open-ended" in out, out
    assert "in bounds" not in out
