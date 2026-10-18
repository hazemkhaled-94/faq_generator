"""The paper's diversity metrics, against values worked out by hand.

Each expected value below was computed on paper first. The set `B` is
small enough to count its n-grams by eye: joined, it is thirteen words.
"""

from __future__ import annotations

import pytest

from assessment import run as cli
from assessment.diversity import (
    compression_ratio,
    ngram_diversity,
    self_repetition,
    subsamples,
)
from question_generation.export import workbook
from question_generation.models import StoredQuestion

B = ["a b c d e", "a b c d f", "x y z"]


def test_ngram_diversity_joins_the_questions() -> None:
    """Unique over total n-grams for n = 1..4, summed, across question ends.

    Joined, B has 13 words: 9 unique of 13 unigrams, 9 of 12 bigrams, 9 of
    11 trigrams and 9 of 10 fourgrams. Counted question by question it would
    be 2.856593, which is the reading this test rules out.
    """
    assert ngram_diversity(B) == pytest.approx(9 / 13 + 9 / 12 + 9 / 11 + 9 / 10)
    assert ngram_diversity(B) == pytest.approx(3.160490, abs=1e-6)


def test_ngram_diversity_of_one_repeated_word() -> None:
    """Five copies of one word have one distinct n-gram at every n."""
    assert ngram_diversity(["a a a a a"]) == pytest.approx(
        1 / 5 + 1 / 4 + 1 / 3 + 1 / 2
    )


def test_ngram_diversity_with_nothing_repeated_is_four() -> None:
    """Every n-gram distinct gives 1 at each of the four sizes."""
    assert ngram_diversity(["a b c d e f g h"]) == pytest.approx(4.0)


def test_self_repetition_is_the_share_of_questions_sharing_a_fourgram() -> None:
    """The first two share "a b c d"; the third shares nothing."""
    assert self_repetition(B) == pytest.approx(2 / 3)


def test_self_repetition_ignores_repeats_inside_one_question() -> None:
    """A question repeating itself is not repeating another question."""
    assert self_repetition(["a b c d a b c d", "w x y z"]) == 0.0


def test_self_repetition_of_questions_shorter_than_four_words() -> None:
    """Two identical three-word questions have no fourgram to share."""
    assert self_repetition(["a b c", "a b c"]) == 0.0


def test_compression_ratio_is_raw_bytes_over_gzip_bytes() -> None:
    """Short text grows under gzip; a long repeat shrinks a great deal.

    A bound rather than an exact value: zlib builds differ in the bytes they
    write, and the ratio is only ever compared within one machine's run.
    """
    assert compression_ratio(B) < 1
    assert compression_ratio(["a " * 500]) > 20


def test_compression_ratio_joins_with_one_space() -> None:
    """Two questions compress exactly as their space-joined text does."""
    assert compression_ratio(["ab", "cd"]) == compression_ratio(["ab cd"])


@pytest.mark.parametrize(
    "measure", [ngram_diversity, self_repetition, compression_ratio]
)
def test_an_empty_set_has_no_diversity(measure) -> None:
    """Nothing to measure is an error, not a zero a report would print."""
    with pytest.raises(ValueError):
        measure([])


def test_subsamples_are_drawn_without_replacement() -> None:
    """Fifty draws of eight distinct places out of ten."""
    drawn = subsamples(10, 8)
    assert len(drawn) == 50
    assert all(len(set(one.tolist())) == 8 for one in drawn)
    assert all(0 <= place < 10 for one in drawn for place in one.tolist())


def test_subsamples_are_the_same_for_the_same_seed() -> None:
    """A rerun draws what the first run drew; another seed draws otherwise."""
    first, again, other = (
        subsamples(10, 8),
        subsamples(10, 8),
        subsamples(10, 8, seed=1),
    )
    assert [one.tolist() for one in first] == [one.tolist() for one in again]
    assert [one.tolist() for one in first] != [one.tolist() for one in other]


def asked(id: int, text: str, language: str) -> StoredQuestion:
    """One accepted question, as the exporter is handed it."""
    return StoredQuestion(
        id=id,
        question_text=text,
        target_answer="48 hours",
        answer_explanation="A standard request is answered within 48 hours.",
        answerable=True,
        difficulty="easy",
        passage_scope="single_passage",
        document_scope="single_document",
        topic_scope="single_topic",
        answer_chars=8,
        language=language,
        status="accepted",
        rejected_reason=None,
        created_at="2026-10-18T12:00:00+00:00",
        facts=1,
        documents=["Service policy"],
        topics=["Support"],
        statements=["A standard request is answered in 48 hours."],
        evidence=["Requests are answered in 48 hours."],
    )


@pytest.fixture
def exported(tmp_path, monkeypatch):
    """B in German and one English question, as `make questions-export` writes them.

    Reading any setting fails the test: the report asks no model, so the
    phase being off, or no judge being named, must not stop it.
    """
    path = tmp_path / "questions.xlsx"
    path.write_bytes(
        workbook(
            [asked(i, text, "de") for i, text in enumerate(B, 1)]
            + [asked(4, "Wie lange dauert eine Antwort?", "en")]
        )
    )

    def unread():
        raise AssertionError("the diversity report read a setting")

    monkeypatch.setattr(cli, "snapshot", unread)
    return path


def report(capsys, *argv: str) -> list[list[str]]:
    """The report's rows below its heading, each split into its cells."""
    assert cli.main(["--diversity", *argv]) == 0
    heading, *rows = capsys.readouterr().out.strip().splitlines()
    assert heading.split() == ["language", "n", "NGD", "SR", "word-CR"]
    return [row.split() for row in rows]


def test_the_command_line_measures_a_workbook_per_language(exported, capsys) -> None:
    """One row a language, each set measured on its own."""
    rows = report(capsys, "--file", str(exported))
    assert [row[:4] for row in rows] == [
        ["de", "3", "3.160", "0.667"],
        ["en", "1", "4.000", "0.000"],
    ]


def test_the_command_line_measures_one_language(exported, capsys) -> None:
    """CODE= names it."""
    rows = report(capsys, "--file", str(exported), "--language", "en")
    assert [row[:2] for row in rows] == [["en", "1"]]


def test_a_size_draws_each_language_to_it(exported, capsys) -> None:
    """Equal sizes, or nothing: a smaller set is named and left out."""
    rows = report(capsys, "--file", str(exported), "--size", "2")
    assert rows[0][:2] == ["de", "2"]
    assert rows[1] == ["en", "1", "question,", "fewer", "than", "2"]
