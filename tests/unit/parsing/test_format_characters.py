"""Bidi marks and C1 controls in a text layer do not survive the mend."""

from __future__ import annotations

import unicodedata

import pytest

from preprocessing.parsing.pipelines.pdf import _mend


@pytest.mark.parametrize(
    ("raw", "copyable"),
    [
        ("IBAN:\u200e DE12 3456 7890", "IBAN: DE12 3456 7890"),
        ("Hotline \u202a+49 30 1234567\u202c", "Hotline +49 30 1234567"),
        ("Retoure\u2066n\u2069 sind kostenlos", "Retouren sind kostenlos"),
        ("Mo\x96Fr 8\x9618 Uhr", "Mo–Fr 8–18 Uhr"),
        ("Opening hours: Mon\x96Fri 9\x965", "Opening hours: Mon–Fri 9–5"),
    ],
)
def test_no_format_or_c1_control_character_survives_the_mend(raw, copyable) -> None:
    """A character a model cannot reproduce is one no quote of it can match."""
    mended = _mend(raw)

    assert not [c for c in mended if unicodedata.category(c) in ("Cf", "Cc")], [
        f"U+{ord(c):04X}" for c in mended
    ]
    # A cp1252 dash read as U+0096 may come back as either dash.
    assert mended.replace("-", "–") == copyable
