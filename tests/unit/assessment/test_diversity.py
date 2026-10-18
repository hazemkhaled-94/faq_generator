"""The paper's diversity metrics, against values worked out by hand.

Each expected value below was computed on paper first. The set `B` is
small enough to count its n-grams by eye: joined, it is thirteen words.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from assessment import run as cli
from assessment.diversity import (
    compression_ratio,
    factuality,
    homogenization,
    ngram_diversity,
    p_value,
    self_repetition,
    subsamples,
    words,
)
from assessment.models import StoredAssessment, StoredMetric
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
@pytest.mark.parametrize("texts", [[], ["   "], ["", ""]])
def test_an_empty_set_has_no_diversity(measure, texts) -> None:
    """Nothing to measure is an error, not a zero a report would print."""
    with pytest.raises(ValueError):
        measure(texts)


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


def test_p_value_is_welchs() -> None:
    """Checked by hand: t = -1.8974 on 5.882 degrees of freedom."""
    assert p_value([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(0.1075, abs=1e-4)


def test_p_value_is_undefined_where_neither_list_varies() -> None:
    """Equal constants are no evidence either way, and no warning is raised."""
    assert np.isnan(p_value([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]))


def test_homogenization_is_the_mean_cosine_over_ordered_pairs() -> None:
    """Of the six ordered pairs, only the two between the copies of (1, 0) are alike."""
    assert homogenization(np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])) == (
        pytest.approx(1 / 3)
    )


def test_homogenization_equals_the_pairwise_loop() -> None:
    """The sum identity gives what averaging every pair one by one gives."""
    vectors = np.random.default_rng(0).normal(size=(50, 8))
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    pairs = [unit[i] @ unit[j] for i in range(50) for j in range(50) if i != j]
    assert homogenization(vectors) == pytest.approx(np.mean(pairs), abs=1e-9)


def test_homogenization_ignores_length() -> None:
    """Cosine, so a vector and its double are the same direction."""
    assert homogenization(np.array([[1.0, 0.0], [2.0, 0.0]])) == pytest.approx(1.0)


def test_homogenization_of_orthogonal_vectors_is_zero() -> None:
    """No two directions alike."""
    assert homogenization(np.eye(3)) == pytest.approx(0.0)


def test_homogenization_needs_two_questions() -> None:
    """One question has no pair to compare."""
    with pytest.raises(ValueError):
        homogenization(np.array([[1.0, 0.0]]))


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("What's the fee for using my card abroad?", 8),
        ("Wie hoch ist die Kontoführungsgebühr?", 5),
        ("Darf ich eine Online-Bestellung innerhalb von 14 Tagen widerrufen?", 9),
        ("Can I return an e-mail voucher?", 6),
        ("refund damaged parcel", 3),
        ("customer_service", 2),
        ("", 0),
    ],
)
def test_words_are_counted_as_a_reader_counts_them(text: str, count: int) -> None:
    """A hyphen or an apostrophe inside a word joins it; punctuation is no word."""
    assert words(text) == count


@pytest.mark.parametrize(
    ("form", "kind"),
    [
        ("value", "factoid"),
        ("list", "factoid"),
        ("explanation", "open-ended"),
        (None, None),
    ],
)
def test_factuality_is_read_off_the_answer_form(
    form: str | None, kind: str | None
) -> None:
    """The paper's factoid and open-ended, from the shape the answer took."""
    assert factuality(form) == kind


def asked(
    id: int,
    text: str,
    language: str,
    categories: tuple[str, ...] = (),
    answer_form: str | None = None,
    kind: str = "single",
) -> StoredQuestion:
    """One accepted question, as the exporter is handed it."""
    return StoredQuestion(
        categories=list(categories),
        answer_form=answer_form,
        kind=kind,
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
    # No spaCy model and no 2 GB encoder in a unit test: every question is a
    # noun and a verb, and B's vectors are the homogenization fixture's.
    monkeypatch.setattr(
        cli, "_tags", lambda texts, language: (["NOUN VERB"] * len(texts), "stub 1.0")
    )
    directions = {B[0]: [1.0, 0.0], B[1]: [0.0, 1.0], B[2]: [1.0, 0.0]}
    monkeypatch.setattr(
        cli,
        "_vectors",
        lambda texts: [directions.get(text, [0.6, 0.8]) for text in texts],
    )
    return path


def report(capsys, *argv: str) -> list[list[str]]:
    """The report's rows below its heading, each split into its cells."""
    assert cli.main(["--diversity", *argv]) == 0
    table, _ = capsys.readouterr().out.split("\n\n", 1)
    heading, *rows = table.strip().splitlines()
    assert heading.split() == ["language", "n", "NGD", "SR", "word-CR", "PoS-CR", "HS"]
    return [row.split() for row in rows]


def test_the_command_line_measures_a_workbook_per_language(exported, capsys) -> None:
    """One row a language, each set measured on its own."""
    rows = report(capsys, "--file", str(exported))
    tagged = f"{compression_ratio(['NOUN VERB'] * 3):.3f}"
    assert [row[:4] + row[5:] for row in rows] == [
        ["de", "3", "3.160", "0.667", tagged, "0.333"],
        ["en", "1", "4.000", "0.000", f"{compression_ratio(['NOUN VERB']):.3f}", "-"],
    ]


def test_the_report_names_what_tagged_and_embedded(exported, capsys) -> None:
    """PoS-CR moves with the tagset and HS with the model, so both are named."""
    assert cli.main(["--diversity", "--file", str(exported)]) == 0
    _, notes = capsys.readouterr().out.split("\n\n", 1)
    assert "de: UPOS tags from stub 1.0" in notes
    assert "not on the paper's MiniLM scale" in notes


def test_the_command_line_measures_one_language(exported, capsys) -> None:
    """CODE= names it."""
    rows = report(capsys, "--file", str(exported), "--language", "en")
    assert [row[:2] for row in rows] == [["en", "1"]]


def test_a_size_draws_each_language_to_it(exported, capsys) -> None:
    """Equal sizes, or nothing: a smaller set is named and left out."""
    rows = report(capsys, "--file", str(exported), "--size", "2")
    assert rows[0][:2] == ["de", "2"]
    assert rows[1] == ["en", "1", "question,", "fewer", "than", "2"]


def test_the_flag_is_read_wherever_it_stands(exported, capsys) -> None:
    """Not only first: anywhere else it would reach the queue's parser."""
    assert cli.main(["--file", str(exported), "--diversity"]) == 0
    assert "language" in capsys.readouterr().out


@pytest.mark.parametrize("size", ["0", "-1"])
def test_a_size_is_at_least_one(exported, size) -> None:
    """Zero would quietly measure everything, and below it nothing can be drawn."""
    with pytest.raises(SystemExit) as refused:
        cli.main(["--diversity", "--file", str(exported), "--size", size])
    assert refused.value.code == 2


def test_the_report_runs_as_make_runs_it() -> None:
    """`python -m assessment.run`, which imports the module as __main__.

    Asked for its usage, so the subprocess loads no tagger and no encoder:
    what this proves is that the flag reaches the report at all.
    """
    backend = Path(__file__).parents[3] / "backend"
    ran = subprocess.run(
        [sys.executable, "-m", "assessment.run", "--diversity", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(backend)},
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    assert "--file" in ran.stdout


def numbered(path: Path, count: int, words: str) -> Path:
    """A workbook of `count` German questions, each told apart by its number."""
    path.write_bytes(
        workbook([asked(i, f"{words} {i}?", "de") for i in range(1, count + 1)])
    )
    return path


def test_two_sets_are_compared_at_the_same_size(
    tmp_path, exported, capsys, monkeypatch
) -> None:
    """Each side drawn fifty times to 80% of the smaller set: 48 of 100 and of 60."""
    import assessment.diversity

    drawn = []
    real = assessment.diversity.subsamples

    def counting(n, size, draws=50, seed=0):
        drawn.append((n, size, draws))
        return real(n, size, draws, seed)

    monkeypatch.setattr(assessment.diversity, "subsamples", counting)
    larger = numbered(tmp_path / "a.xlsx", 100, "Wie hoch ist die Gebühr für Karte")
    smaller = numbered(tmp_path / "b.xlsx", 60, "Was kostet die Überweisung Nummer")

    assert (
        cli.main(["--diversity", "--file", str(larger), "--against", str(smaller)]) == 0
    )

    assert sorted(drawn) == [(60, 48, 50), (100, 48, 50)]
    table = capsys.readouterr().out.split("\n\n", 1)[0].splitlines()
    assert table[0].split() == [
        "language",
        "metric",
        "file",
        "against",
        "difference",
        "p",
    ]
    assert [row.split()[:2] for row in table[1:]] == [
        ["de", "NGD"],
        ["de", "SR"],
        ["de", "word-CR"],
        ["de", "PoS-CR"],
        ["de", "HS"],
    ]


def test_a_language_in_one_workbook_only_is_named(tmp_path, exported, capsys) -> None:
    """English is in the first workbook and not the second."""
    other = numbered(tmp_path / "b.xlsx", 5, "Was kostet die Überweisung Nummer")
    assert (
        cli.main(["--diversity", "--file", str(exported), "--against", str(other)]) == 0
    )
    assert "en: in one workbook only" in capsys.readouterr().out


def test_a_comparison_takes_no_size(tmp_path, exported) -> None:
    """It draws 80% of the smaller set; a size of its own would contradict that."""
    with pytest.raises(SystemExit) as refused:
        cli.main(
            [
                "--diversity",
                "--file",
                str(exported),
                "--against",
                str(exported),
                "--size",
                "2",
            ]
        )
    assert refused.value.code == 2


CONCISE = "Phrasing=concise-and-natural"
VERBOSE = "Phrasing=verbose-and-natural"


def judged(question: int, fluency: float) -> StoredAssessment:
    """What the paper's judge said of one question's fluency, as stored."""
    return StoredAssessment(
        id=question,
        kind="question",
        artifact_id=question,
        status="assessed",
        approved=True,
        judge_model="azure/gpt-4.1",
        prompt_version="3",
        run_id=None,
        trace_id=None,
        span_id=None,
        assessed_at=None,
        error=None,
        metrics=[StoredMetric("rubric_fluency", "3", fluency, True, "")],
    )


@pytest.fixture
def configured(monkeypatch):
    """The settings the report reads, as the snapshot holds them: none, at first."""
    stored: dict[str, str] = {}
    monkeypatch.setattr(cli, "snapshot", lambda: (stored, "test"))
    return stored


@pytest.fixture
def categorized(tmp_path, exported, configured):
    """B in German, two concise and one verbose, one English concise, two judged."""
    path = tmp_path / "categorized.xlsx"
    path.write_bytes(
        workbook(
            [
                asked(1, B[0], "de", (CONCISE,), "value"),
                asked(2, B[1], "de", (CONCISE,), "explanation"),
                asked(3, B[2], "de", (VERBOSE,), "list"),
                asked(4, "Wie lange dauert eine Antwort?", "en", (CONCISE,)),
            ],
            judged={1: judged(1, 1.0), 2: judged(2, 0.5)},
        )
    )
    return path


def test_the_report_splits_by_category(categorized, capsys) -> None:
    """One row per language and category, a question counted in each of its labels."""
    assert (
        cli.main(["--diversity", "--file", str(categorized), "--by", "category"]) == 0
    )
    table = capsys.readouterr().out.split("\n\n", 1)[0].splitlines()
    assert table[0].split()[:3] == ["language", "category", "n"]
    assert [row.split()[:3] for row in table[1:]] == [
        ["de", CONCISE, "2"],
        ["de", VERBOSE, "1"],
        ["en", CONCISE, "1"],
    ]


def test_the_report_gives_the_papers_judge_means(categorized, capsys) -> None:
    """The mean stored score, which is the paper's normalised mean; per category too."""
    assert (
        cli.main(["--diversity", "--file", str(categorized), "--by", "category"]) == 0
    )
    judge = capsys.readouterr().out.split("The paper's judge", 1)[1].splitlines()
    rows = [row.split() for row in judge if row.startswith(("de", "en"))]
    assert rows == [["de", CONCISE, "2", "0.750"]]


@pytest.fixture
def kinded(tmp_path, exported):
    """B in German, two single and one compound, one English needs_both, two judged."""
    path = tmp_path / "kinded.xlsx"
    path.write_bytes(
        workbook(
            [
                asked(1, B[0], "de"),
                asked(2, B[1], "de", kind="compound"),
                asked(3, B[2], "de"),
                asked(4, "Wie lange dauert eine Antwort?", "en", kind="needs_both"),
            ],
            judged={1: judged(1, 1.0), 2: judged(2, 0.5)},
        )
    )
    return path


def test_the_report_splits_by_kind(kinded, capsys) -> None:
    """One row per language and kind, read off the workbook's Kind column."""
    assert cli.main(["--diversity", "--file", str(kinded), "--by", "kind"]) == 0
    table = capsys.readouterr().out.split("\n\n", 1)[0].splitlines()
    assert table[0].split()[:3] == ["language", "kind", "n"]
    assert [row.split()[:3] for row in table[1:]] == [
        ["de", "compound", "1"],
        ["de", "single", "2"],
        ["en", "needs_both", "1"],
    ]


def test_the_report_gives_the_papers_judge_means_per_kind(kinded, capsys) -> None:
    """A compound question reaches the judge untold of its kind; read apart, it shows."""
    assert cli.main(["--diversity", "--file", str(kinded), "--by", "kind"]) == 0
    out = capsys.readouterr().out
    judge = out.split("The paper's judge", 1)[1].splitlines()
    assert judge[1].split()[:3] == ["language", "kind", "n"]
    rows = [row.split() for row in judge if row.startswith(("de", "en"))]
    assert rows == [["de", "compound", "1", "0.500"], ["de", "single", "1", "1.000"]]


def test_a_workbook_without_categories_cannot_be_split(exported) -> None:
    """A workbook written before categories has nothing to split by."""
    with pytest.raises(SystemExit) as refused:
        cli.main(["--diversity", "--file", str(exported), "--by", "category"])
    assert refused.value.code == 2


def conformance(capsys, path: Path) -> tuple[str, list[list[str]]]:
    """The conformance section's heading and its rows, each split into cells."""
    assert cli.main(["--diversity", "--file", str(path), "--by", "category"]) == 0
    section = capsys.readouterr().out.split("Word bounds", 1)[1]
    section = section.split("\n\n", 1)[0]
    heading, *rows = section.splitlines()
    return heading, [row.split() for row in rows if row.startswith(("de", "en"))]


def test_the_report_gives_each_category_its_conformance(categorized, capsys) -> None:
    """In bounds by today's settings; factoid and open-ended by the answer form.

    Unset, the bounds are the default's: at most 9 words for concise and at
    least 10 for verbose, so the five-word concise questions are in and the
    three-word verbose one out. The English question has no answer form.
    """
    heading, rows = conformance(capsys, categorized)

    assert "today" in heading
    assert rows == [
        ["de", CONCISE, "2", "1.000", "0.500", "0.500"],
        ["de", VERBOSE, "1", "0.000", "1.000", "0.000"],
        ["en", CONCISE, "1", "1.000", "0.000", "0.000"],
    ]


def test_the_bounds_are_the_ones_configured_now(
    categorized, configured, capsys
) -> None:
    """Read through the setting as the stages read it, so a change moves them."""
    configured["QUESTIONS_CATEGORIZATIONS"] = json.dumps(
        {
            "categorization_name": "Phrasing",
            "categories": [
                {
                    "name": "concise-and-natural",
                    "description": "d",
                    "words": {"max": 4},
                },
                {"name": "verbose-and-natural", "description": "d"},
            ],
        }
    )

    _, rows = conformance(capsys, categorized)

    assert [row[:4] for row in rows] == [
        ["de", CONCISE, "2", "0.000"],
        ["de", VERBOSE, "1", "-"],
        ["en", CONCISE, "1", "0.000"],
    ]
