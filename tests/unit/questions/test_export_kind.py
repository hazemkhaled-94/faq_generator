"""frontend-review-4: the workbook names the kind a question was written as."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from question_generation.export import workbook
from question_generation.models import StoredQuestion


@pytest.mark.parametrize(
    "language,text,answer",
    [
        (
            "de",
            "Wie hoch ist die Gebühr, und bis wann muss ein Widerspruch eingehen?",
            "5 EUR; sechs Wochen",
        ),
        (
            "en",
            "What does the express parcel cost, and how long is the return window?",
            "9 EUR; 30 days",
        ),
    ],
)
def test_compound_kind_is_in_the_questions_sheet(language, text, answer) -> None:
    """The workbook holds the kind a question was written as."""
    q = StoredQuestion(
        id=7,
        question_text=text,
        target_answer=answer,
        answer_explanation=None,
        answerable=True,
        difficulty="medium",
        passage_scope="multi_passage",
        document_scope="single_document",
        topic_scope="single_topic",
        answer_chars=20,
        language=language,
        status="accepted",
        rejected_reason=None,
        created_at=None,
        facts=2,
        documents=["Preise"],
        topics=["Gebühren"],
        kind="compound",
    )
    sheet = pd.read_excel(io.BytesIO(workbook([q])), sheet_name="Questions")
    assert sheet["Kind"].tolist() == ["compound"], f"headers {list(sheet.columns)}"
