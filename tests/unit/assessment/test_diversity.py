"""The paper's diversity metrics, against values worked out by hand.

Each expected value below was computed on paper first. The set `B` is
small enough to count its n-grams by eye: joined, it is thirteen words.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from assessment import run as cli
from assessment.diversity import (
    compression_ratio,
    factuality,
    few_documents,
    homogenization,
    ngram_diversity,
    p_value,
    self_repetition,
    subsamples,
    words,
)
from assessment.models import StoredAssessment, StoredMetric
from question_generation.export import workbook
from question_generation.models import Citation, StoredQuestion

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
    # Content words without a parse: the words of four letters or more.
    monkeypatch.setattr(
        cli,
        "_content",
        lambda text, language: frozenset(
            word.strip("?.,").lower() for word in text.split() if len(word) > 3
        ),
    )
    return path


def report(capsys, *argv: str) -> list[list[str]]:
    """The report's rows below its heading, each split into its cells."""
    assert cli.main(["--diversity", *argv]) == 0
    table, _ = capsys.readouterr().out.split("\n\n", 1)
    heading, *rows = table.strip().splitlines()
    assert heading.split() == [
        "language",
        "n",
        "NGD",
        "SR",
        "word-CR",
        "PoS-CR",
        "HS",
        "held",
    ]
    return [row.split() for row in rows]


def test_the_command_line_measures_a_workbook_per_language(exported, capsys) -> None:
    """One row a language, each set measured on its own."""
    rows = report(capsys, "--file", str(exported))
    tagged = f"{compression_ratio(['NOUN VERB'] * 3):.3f}"
    assert [row[:4] + row[5:] for row in rows] == [
        # B's one-letter words hold no content word, so nothing is read.
        ["de", "3", "3.160", "0.667", tagged, "0.333", "-"],
        [
            "en",
            "1",
            "4.000",
            "0.000",
            f"{compression_ratio(['NOUN VERB']):.3f}",
            "-",
            "0.000",
        ],
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


def test_identical_documents_give_a_flat_curve() -> None:
    """Every question tagged alike: each point is the same ratio, with no spread."""
    curve = few_documents(["a"] * 4 + ["b"] * 4, ["NOUN VERB"] * 8, [1, 2], 4, draws=3)
    flat = compression_ratio(["NOUN VERB"] * 4)
    assert [(k, round(mean, 9), sd) for k, mean, sd in curve] == [
        (1, round(flat, 9), 0.0),
        (2, round(flat, 9), 0.0),
    ]


def test_a_point_needing_more_documents_than_qualify_is_left_out() -> None:
    """Two documents cannot make a point of three."""
    assert few_documents(["a"] * 4 + ["b"] * 4, ["NOUN"] * 8, [3], 4, draws=3) == []


def test_a_document_too_small_for_its_share_is_not_drawn() -> None:
    """n=4 over k=1 needs one document of four; only `a` has four."""
    curve = few_documents(
        ["a"] * 4 + ["b"] * 2, ["NOUN"] * 4 + ["VERB"] * 2, [1], 4, draws=5
    )
    assert [(k, sd) for k, _, sd in curve] == [(1, 0.0)]
    assert curve[0][1] == pytest.approx(compression_ratio(["NOUN"] * 4))


def test_the_curve_is_the_same_twice() -> None:
    """Seeded: a rerun draws the same documents and questions."""
    units = [f"d{i % 6}" for i in range(60)]
    tags = [f"NOUN {'VERB ' * (i % 5)}PUNCT" for i in range(60)]
    assert few_documents(units, tags, [2, 4, 6], 12) == few_documents(
        units, tags, [2, 4, 6], 12
    )


def test_the_command_line_draws_the_curve_by_document(
    tmp_path, exported, capsys
) -> None:
    """Ten German questions over five documents: points at five documents and fewer."""
    path = tmp_path / "documents.xlsx"
    rows = [asked(i, f"Frage Nummer {i}?", "de") for i in range(1, 11)]
    cited = [
        Citation(
            question_id=i,
            fact_id=i,
            statement="s",
            evidence_text="e",
            validated=True,
            document=f"Seite {(i - 1) % 5}",
            doc_sha256="0" * 64,
            ordinal=1,
            page=1,
        )
        for i in range(1, 11)
    ]
    path.write_bytes(workbook(rows, cited))
    assert (
        cli.main(
            ["--diversity", "--file", str(path), "--by", "document", "--size", "10"]
        )
        == 0
    )
    table = capsys.readouterr().out.split("\n\n", 1)[0].splitlines()
    assert table[0].split() == ["language", "documents", "n", "PoS-CR", "sd"]
    assert [row.split()[:3] for row in table[1:]] == [["de", "5", "10"]]


def test_held_is_the_share_of_content_words_in_the_evidence(monkeypatch) -> None:
    """Every content word in the evidence is 1, none is 0, nothing to read is None."""
    monkeypatch.setattr(
        cli, "_content", lambda text, language: frozenset(text.lower().split())
    )
    assert cli._held("monthly fee", "the monthly fee", "en") == 1.0
    assert cli._held("monthly fee", "cards", "en") == 0.0
    assert cli._held("", "cards", "en") is None


def test_each_text_is_read_once(monkeypatch) -> None:
    """A question counted in several categories is parsed once, not once per category."""
    import nlp.analysis

    read: list[str] = []
    monkeypatch.setattr(
        nlp.analysis,
        "content",
        lambda text, language: read.append(text) or frozenset(text.split()),
    )
    cli._content.cache_clear()
    for _ in range(3):
        cli._held("monthly fee", "the monthly fee", "en")
    assert read == ["the monthly fee", "monthly fee"]
    cli._content.cache_clear()


def test_a_workbook_without_evidence_holds_nothing_to_read(tmp_path, capsys) -> None:
    """No evidence column, no reading: `held` prints a dash, the rest as before."""
    path = tmp_path / "bare.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(
            {"ID": [1, 2], "Question": ["a b c", "x y z"], "Language": ["de", "de"]}
        ).to_excel(writer, sheet_name="Questions", index=False)
    assert cli._evidence(path) == {}


@pytest.mark.nlp
def test_held_reads_content_lemmas_with_the_languages_pipeline() -> None:
    """The real reading: the question's nouns and adjectives against the evidence's."""
    question = "What is the monthly fee for a current account?"
    assert (
        cli._held(question, "The monthly fee for a current account is EUR 5.", "en")
        == 1.0
    )
    assert cli._held(question, "Cards are issued within a week.", "en") == 0.0
    assert cli._held("What is it?", "Cards are issued within a week.", "en") is None


def test_the_report_gives_how_much_the_evidence_holds(
    exported, tmp_path, capsys
) -> None:
    """The mean over a group's questions, a question with nothing to read left out."""
    path = tmp_path / "held.xlsx"
    path.write_bytes(
        workbook(
            [
                replace(
                    asked(1, "Monthly fee account?", "en"),
                    evidence=["Monthly fee account."],
                ),
                replace(
                    asked(2, "Overdraft limit students?", "en"),
                    evidence=["Cards issued."],
                ),
                replace(asked(3, "Is it so?", "en"), evidence=["Cards issued."]),
            ]
        )
    )
    rows = report(capsys, "--file", str(path))
    assert rows[0][0] == "en" and rows[0][-1] == "0.500"


def labelled_set(
    tmp_path: Path,
    rows: list[tuple[int, str, bool | None]],
    labels: list[dict],
    english: frozenset[int] = frozenset(),
) -> tuple[Path, Path]:
    """A workbook of (id, category, verdict) rows and its labels file.

    German but for the ids in `english`. A verdict of None leaves the
    question unjudged. The paper's judge is stored only for the questions it
    judged, as the exporter reads it.
    """
    path, file = tmp_path / "labelled.xlsx", tmp_path / "labels.jsonl"
    path.write_bytes(
        workbook(
            [
                asked(
                    id,
                    f"Frage {id}?",
                    "en" if id in english else "de",
                    (category,) if category else (),
                )
                for id, category, _ in rows
            ],
            judged={
                id: replace(judged(id, 1.0), approved=verdict)
                for id, _, verdict in rows
                if verdict is not None
            },
        )
    )
    file.write_text("\n".join(json.dumps(one) for one in labels))
    return path, file


def usable(ids: range, answers: list[int]) -> list[dict]:
    """One `usable` label per id."""
    return [
        {"id": i, "usable": "yes" if a else "no"}
        for i, a in zip(ids, answers, strict=True)
    ]


#: ARES-1's fixture 1: eight rows only the judge saw, four it also had labelled.
UNLABELLED = [(i, "", bool(v)) for i, v in enumerate([1, 1, 0, 1, 1, 0, 1, 1], 1)]
LABELLED = [(i, "", bool(v)) for i, v in enumerate([1, 0, 1, 1], 9)]


def corrected_rows(capsys) -> list[list[str]]:
    """The corrected table's rows, each split into its cells."""
    out = capsys.readouterr().out.split("Labelled shares corrected", 1)[1]
    _, heading, *rows = out.split("\n\n", 1)[0].splitlines()
    assert heading.split()[-9:] == [
        "label",
        "n",
        "N",
        "judge",
        "labels",
        "corrected",
        "95%",
        "interval",
        "weight",
    ]
    return [row.split() for row in rows]


def test_labels_are_read_from_jsonl(tmp_path) -> None:
    """Yes and true are 1, no and false 0 in any case, na and null no label."""
    file = tmp_path / "labels.jsonl"
    file.write_text(
        '{"id": 1, "usable": "yes", "key_complete": "na"}\n'
        '{"id": 2, "usable": "No", "key_complete": false, "question": "Q?"}\n'
    )
    assert cli._labels(file) == (
        {1: {"usable": 1}, 2: {"usable": 0, "key_complete": 0}},
        {2: "Q?"},
    )


@pytest.mark.parametrize(
    "text",
    [
        '{"id": 1, "usable": "partly"}',
        '{"id": 1, "question": "Q?"}',
        '{"usable": "yes"}',
    ],
    ids=["not-yes-or-no", "no-labels", "no-id"],
)
def test_a_labels_file_that_cannot_be_read_is_refused(tmp_path, text) -> None:
    """A label that is not yes or no, no label at all and no id are each refused."""
    file = tmp_path / "labels.jsonl"
    file.write_text(text)
    with pytest.raises(SystemExit) as refused:
        cli._labels(file)
    assert refused.value.code == 2


def test_the_report_corrects_a_labelled_share(exported, tmp_path, capsys) -> None:
    """Judge 0.750 over twelve; labels 0.500 over four; weight 0.407 on the judge."""
    path, file = labelled_set(
        tmp_path, UNLABELLED + LABELLED, usable(range(9, 13), [1, 0, 0, 1])
    )
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    cells = ["usable", "4", "8", "0.750", "0.500", "0.500", "[0.067,", "0.933]"]
    assert corrected_rows(capsys) == [
        ["de", *cells, "0.407"],
        ["all", *cells, "-"],
    ]


def test_labels_from_another_database_are_refused(exported, tmp_path, capsys) -> None:
    """Two databases share ids; a question that differs is not the row labelled."""
    path, file = labelled_set(
        tmp_path,
        UNLABELLED + LABELLED,
        [
            {**one, "question": "Frage 9?" if one["id"] == 9 else "Other?"}
            for one in usable(range(9, 13), [1, 0, 0, 1])
        ],
    )
    with pytest.raises(SystemExit) as refused:
        cli.main(["--diversity", "--file", str(path), "--labels", str(file)])
    assert refused.value.code == 2
    assert "10" in capsys.readouterr().err


def test_unjudged_rows_are_left_out(exported, tmp_path, capsys) -> None:
    """A labelled row nobody judged says nothing about the judge; it is counted."""
    path, file = labelled_set(
        tmp_path,
        UNLABELLED + LABELLED + [(13, "", None)],
        usable(range(9, 14), [1, 0, 0, 1, 1]),
    )
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    out = capsys.readouterr().out
    assert "1 labelled row was not judged" in out
    table = out.split("Labelled shares corrected", 1)[1].splitlines()
    assert [row.split()[2] for row in table if row.startswith("de")] == ["4"]


def test_the_correction_splits_by_category(
    exported, configured, tmp_path, capsys
) -> None:
    """Each category is corrected on its own, with its own weight, which may be negative."""
    b = [(i, "B", bool(v)) for i, v in enumerate([1, 0, 1, 0], 13)] + [
        (i, "B", bool(v)) for i, v in enumerate([1, 1, 0, 0, 1, 0], 17)
    ]
    path, file = labelled_set(
        tmp_path,
        [(i, "A", v) for i, _, v in UNLABELLED + LABELLED] + b,
        usable(range(9, 13), [1, 0, 0, 1]) + usable(range(17, 23), [0, 0, 1, 1, 0, 1]),
    )
    argv = ["--diversity", "--file", str(path), "--labels", str(file)]
    assert cli.main([*argv, "--by", "category"]) == 0
    rows = corrected_rows(capsys)
    assert [row[:2] + row[3:5] + row[7:] for row in rows if row[0] == "de"] == [
        ["de", "A", "4", "8", "0.500", "[0.067,", "0.933]", "0.407"],
        ["de", "B", "6", "4", "0.500", "[0.189,", "0.811]", "-0.360"],
    ]


def test_a_language_not_measured_leaves_nothing_pooled(
    exported, tmp_path, capsys
) -> None:
    """An `all` row over the German rows alone would pass for both languages."""
    english = [(i, "", bool(v)) for i, v in enumerate([1, 1, 0, 1], 101)]
    path, file = labelled_set(
        tmp_path,
        UNLABELLED + LABELLED + english,
        usable(range(9, 13), [1, 0, 0, 1]) + usable(range(101, 102), [1]),
        english=frozenset(range(101, 105)),
    )
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    out = capsys.readouterr().out
    rows = [row.split() for row in out.split("Labelled shares", 1)[1].splitlines()]
    assert not [row for row in rows if row[:1] == ["all"] and "0.500" in row]
    assert "usable not pooled: en not measured" in out


def test_a_group_labelled_whole_is_read_on_its_labels(
    exported, tmp_path, capsys
) -> None:
    """Every judged row labelled: the labels' own share, the judge given no weight."""
    path, file = labelled_set(tmp_path, LABELLED, usable(range(9, 13), [1, 0, 1, 1]))
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    row = corrected_rows(capsys)[0]
    assert row[:7] + row[-1:] == [
        "de",
        "usable",
        "4",
        "0",
        "0.750",
        "0.750",
        "0.750",
        "0.000",
    ]


def test_a_blank_judge_cell_is_not_judged(exported, tmp_path, capsys) -> None:
    """Only approved and refused are verdicts; a blank cell is not a refusal."""
    path, file = labelled_set(
        tmp_path, UNLABELLED + LABELLED, usable(range(9, 13), [1, 0, 0, 1])
    )
    frame = pd.read_excel(path, sheet_name=None, keep_default_na=False)
    frame["Questions"].loc[frame["Questions"]["ID"] <= 2, "Judge"] = ""
    with pd.ExcelWriter(path) as writer:
        for name, sheet in frame.items():
            sheet.to_excel(writer, sheet_name=name, index=False)
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    assert corrected_rows(capsys)[0][3] == "6"


def test_the_question_check_ignores_spacing_and_nulls(
    exported, tmp_path, capsys
) -> None:
    """A trailing space or a null question is not another question."""
    labels = usable(range(9, 13), [1, 0, 0, 1])
    labels[0]["question"], labels[1]["question"] = "Frage 9? ", None
    path, file = labelled_set(tmp_path, UNLABELLED + LABELLED, labels)
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0


def test_labels_that_all_agree_have_no_spread(exported, tmp_path, capsys) -> None:
    """Two yes labels give a zero standard error; no interval is printed for it."""
    path, file = labelled_set(
        tmp_path, UNLABELLED + LABELLED[:2], usable(range(9, 11), [1, 1])
    )
    assert cli.main(["--diversity", "--file", str(path), "--labels", str(file)]) == 0
    assert "no spread" in " ".join(corrected_rows(capsys)[0])


@pytest.mark.parametrize("other", [["--against", "{}"], ["--by", "document"]])
def test_labels_take_no_against_and_no_document_curve(
    exported, tmp_path, other
) -> None:
    """The correction is of one workbook's shares, not a comparison or a curve."""
    file = tmp_path / "labels.jsonl"
    file.write_text('{"id": 1, "usable": "yes"}')
    argv = ["--diversity", "--file", str(exported), "--labels", str(file)]
    with pytest.raises(SystemExit) as refused:
        cli.main([*argv, *(one.format(exported) for one in other)])
    assert refused.value.code == 2
