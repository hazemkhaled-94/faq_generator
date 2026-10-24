"""Drawing a balanced release, against the table that stores it.

`choose` is covered over lists in tests/unit/questions/test_balance.py. What
is covered here is the round trip: which questions the catalogue offers, what
the draw writes, and that a second draw replaces the first rather than adding
to it.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, membership, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import QuestionFact
from question_generation.catalog import QuestionCatalog

pytestmark = pytest.mark.integration


BANDS = {"easy": 1, "medium": 1, "hard": 1}
TYPES = {"factoid": 1, "reason": 1}

#: An answer of the form each kind asks for, so the re-verify a draw runs
#: first keeps every row.
_ANSWERS = {"factoid": "4 kg", "reason": "because the frame is built to weigh 4 kg"}


@pytest.fixture
def written(engine, database):
    """Writes accepted questions of the bands and kinds a test asks for."""

    def write(rows: list[tuple[str, str, bool, str]]) -> list[int]:
        with Session(engine) as session:
            sha = digest("a")
            session.add(document(sha))
            held = fitted(0)
            session.add(held)
            session.flush()
            at = passage(sha, ordinal=1, text="The device weighs 4 kg.", language="en")
            session.add(at)
            session.flush()
            session.add(membership(at.id, held.id))
            drawn = fact(at.id, statement="The device weighs 4 kg.")
            session.add(drawn)
            session.flush()

            ids = []
            for band, kind, answerable, status in rows:
                asked = question(
                    question_text=f"A {band} {kind} question?",
                    target_answer=_ANSWERS[kind] if answerable else None,
                    answerable=answerable,
                    difficulty=band,
                    question_type=kind,
                    status=status,
                )
                session.add(asked)
                session.flush()
                session.add(QuestionFact(question_id=asked.id, fact_id=drawn.id))
                ids.append(asked.id)
            session.commit()
            return ids

    return write


def released(engine) -> int:
    """How many rows carry a release id."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM questions WHERE release_id IS NOT NULL")
        ).scalar_one()


def test_only_accepted_questions_are_offered(written) -> None:
    """A rejected question is drop-rate evidence, not benchmark material."""
    written(
        [
            ("easy", "factoid", True, "accepted"),
            ("easy", "factoid", True, "rejected"),
            ("easy", "factoid", True, "draft"),
        ]
    )

    assert len(QuestionCatalog().releasable()) == 1


def test_a_question_with_no_band_or_kind_is_not_offered(written, engine) -> None:
    """It would be chosen into a quota it cannot be counted against.

    The report would then disagree with the set it describes.
    """
    written([("easy", "factoid", True, "accepted")])
    with engine.begin() as connection:
        connection.execute(text("UPDATE questions SET difficulty = NULL"))

    assert QuestionCatalog().releasable() == []


def test_a_question_is_offered_with_its_language(written, engine) -> None:
    """The draw holds a share per language, so it has to know which one."""
    ids = written([("easy", "factoid", True, "accepted")] * 2)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE questions SET language = 'de' WHERE id = :id"), {"id": ids[0]}
        )

    offered = {one.id: one.language for one in QuestionCatalog().releasable()}

    assert offered == {ids[0]: "de", ids[1]: "en"}


def test_a_released_row_carries_its_categories(written, engine) -> None:
    """As labels, sorted, from the list of objects the store writes; none for NULL."""
    ids = written([("easy", "factoid", True, "accepted")] * 2)
    with engine.begin() as connection:
        connection.execute(
            text(
                'UPDATE questions SET categories = \'[{"categorization": "Premise", '
                '"category": "direct", "role": "question", "form": "question", '
                '"description": "asked without a premise."}, {"categorization": '
                '"Phrasing", "category": "verbose-and-natural", "description": '
                '"a relatively long question."}]\' WHERE id = :id'
            ),
            {"id": ids[0]},
        )

    offered = {one.id: one.categories for one in QuestionCatalog().releasable()}

    assert offered == {
        ids[0]: ("Phrasing=verbose-and-natural", "Premise=direct"),
        ids[1]: (),
    }


def test_the_twins_are_the_pairs_of_accepted_questions_of_one_language(
    engine, database
) -> None:
    """Close enough, in one language, both accepted, and alike in answerability.

    Each side names what it cites, so the rule the duplicate gate applies can
    be read over the pair.
    """
    one = [1.0] + [0.0] * 1023
    with Session(engine) as session:
        session.add(document(digest("a")))
        session.flush()
        at = passage(digest("a"), ordinal=1, language="en")
        session.add(at)
        session.flush()
        drawn = fact(at.id, statement="The device weighs 4 kg.")
        session.add(drawn)
        session.flush()
        accepted = {"status": "accepted", "embedding": one}
        rows = [
            question(question_text="What does the device weigh?", **accepted),
            question(question_text="How heavy is the device?", **accepted),
            question(question_text="Wie schwer ist es?", language="de", **accepted),
            question(question_text="Is it heavy?", answerable=False, **accepted),
            question(
                question_text="What did it weigh?",
                embedding=one,
                status="rejected",
                rejected_reason="duplicate",
            ),
            question(
                question_text="Who built it?",
                status="accepted",
                embedding=[0.0] * 1023 + [1.0],
            ),
        ]
        session.add_all(rows)
        session.flush()
        session.add_all(
            QuestionFact(question_id=row.id, fact_id=drawn.id) for row in rows
        )
        session.commit()
        ids, fact_id, passage_id = [row.id for row in rows], drawn.id, at.id

    found = QuestionCatalog().twins(0.88)

    assert [(first.id, second.id) for first, second in found] == [(ids[0], ids[1])]
    first, second = found[0]
    assert second.similarity == pytest.approx(1.0, abs=1e-5)
    assert (first.question_text, first.language, first.answerable) == (
        "What does the device weigh?",
        "en",
        True,
    )
    assert first.fact_ids == second.fact_ids == {fact_id}
    assert first.passage_ids == second.passage_ids == {passage_id}


def test_the_twins_are_read_among_each_question_s_nearest_few(engine, database) -> None:
    """The probe is a nearest-k over the index, not every pair in the pool.

    The asked question has more close neighbours than are read for it, and
    the furthest of them has as many closer ones of its own, so neither side
    reads the other. Every pair a question's nearest few hold is still found,
    from either side.
    """
    from math import sqrt

    from question_generation.catalog import TWIN_NEIGHBOURS

    def at(alike: float, axis: int) -> list[float]:
        """A unit vector this alike to the first axis."""
        vector = [0.0] * 1024
        vector[0], vector[axis] = alike, sqrt(1.0 - alike * alike)
        return vector

    # Alike enough to the asked one to be twins, and not to each other.
    near = [0.89 + 0.01 * step for step in range(TWIN_NEIGHBOURS)]
    with Session(engine) as session:
        asked = question(
            question_text="Asked?", status="accepted", embedding=at(1.0, 1)
        )
        closer = [
            question(
                question_text=f"Closer {step}?",
                status="accepted",
                embedding=at(alike, 2 + step),
            )
            for step, alike in enumerate(near)
        ]
        # Further from the asked one than every closer one, and with a
        # cluster of its own nearer to it than the asked one is.
        beyond = [
            question(
                question_text=f"Beyond {step}?",
                status="accepted",
                embedding=at(0.885, 100),
            )
            for step in range(TWIN_NEIGHBOURS + 1)
        ]
        session.add_all([asked, *closer, *beyond])
        session.commit()
        asked_id = asked.id
        closer_ids = {row.id for row in closer}

    found = QuestionCatalog().twins(0.88)

    with_asked = {
        first.id if second.id == asked_id else second.id
        for first, second in found
        if asked_id in (first.id, second.id)
    }
    assert with_asked == closer_ids


def test_each_released_question_is_paired_with_its_nearest_released_one(
    engine, database
) -> None:
    """Rank and not a bar: the twin judge is asked about the nearest, however far.

    Among the ids given only, in one language and one answerability, each
    pair once.
    """

    def axis(*weights: float) -> list[float]:
        """A unit vector with these first components."""
        vector = [0.0] * 1024
        norm = sum(one * one for one in weights) ** 0.5
        for at, one in enumerate(weights):
            vector[at] = one / norm
        return vector

    with Session(engine) as session:
        rows = [
            question(question_text="A?", target_answer="4 kg", embedding=axis(1, 0)),
            question(question_text="B?", target_answer="5 kg", embedding=axis(1, 0.3)),
            question(question_text="C?", target_answer="6 kg", embedding=axis(0, 1)),
            question(question_text="D?", target_answer="7 kg", embedding=axis(1, 0.1)),
            question(
                question_text="E?",
                language="de",
                target_answer="8 kg",
                embedding=axis(1, 0),
            ),
        ]
        session.add_all(rows)
        session.commit()
        a, b, c, _, e = (row.id for row in rows)

    found = QuestionCatalog().closest_among([a, b, c, e])

    pairs = {(first.id, second.id) for first, second in found}
    assert pairs == {(min(a, b), max(a, b)), (min(b, c), max(b, c))}, pairs
    assert all(first.question_text and first.target_answer for first, _ in found)


def test_the_draw_writes_one_id_on_what_it_chose(written, engine) -> None:
    """A release is a column on the rows already there."""
    ids = written([("easy", "factoid", True, "accepted")] * 3)
    catalog = QuestionCatalog()

    drawn, count = catalog.release(ids[:2])

    assert count == 2
    assert released(engine) == 2
    with engine.connect() as connection:
        held = (
            connection.execute(
                text(
                    "SELECT DISTINCT release_id FROM questions "
                    "WHERE release_id IS NOT NULL"
                )
            )
            .scalars()
            .all()
        )
    assert held == [drawn]


def test_a_second_draw_replaces_the_first(written, engine) -> None:
    """One release at a time, because the column holds one id.

    The question a report answers is what would ship today, and a previous
    draw is not history worth keeping here: every question it held is still
    in the table.
    """
    ids = written([("easy", "factoid", True, "accepted")] * 4)
    catalog = QuestionCatalog()

    first, _ = catalog.release(ids[:3])
    second, count = catalog.release(ids[3:])

    assert first != second
    assert count == 1
    assert released(engine) == 1


def test_drawing_nothing_clears_the_last_release(written, engine) -> None:
    """Rather than leaving a stale set that no settings produced."""
    ids = written([("easy", "factoid", True, "accepted")] * 2)
    catalog = QuestionCatalog()
    catalog.release(ids)

    catalog.release([])

    assert released(engine) == 0


def test_a_question_that_leaves_accepted_leaves_the_release(written, engine) -> None:
    """Whether a person or a re-check moves it; an accepted row keeps its mark."""
    ids = written([("easy", "factoid", True, "accepted")] * 5)
    catalog = QuestionCatalog()
    catalog.release(ids)

    catalog.decide(ids[0], "rejected")
    catalog.decide(ids[1], "draft")
    catalog.reject([(ids[2], "malformed")])
    catalog.decide(ids[3], "accepted")

    with engine.connect() as connection:
        held = (
            connection.execute(
                text(
                    "SELECT id FROM questions WHERE release_id IS NOT NULL ORDER BY id"
                )
            )
            .scalars()
            .all()
        )
    assert held == ids[3:]


def test_released_narrows_every_read_of_the_listing_to_the_draw(written) -> None:
    """The rows, the figures and the citations, and false is the rest."""
    ids = written([("easy", "factoid", True, "accepted")] * 3)
    catalog = QuestionCatalog()
    catalog.release(ids[:2])

    total, inside = catalog.page(released=True)
    outside = catalog.page(released=False)[1]

    assert total == 2
    assert [one.id for one in inside] == ids[:2]
    assert all(one.released for one in inside)
    assert [(one.id, one.released) for one in outside] == [(ids[2], False)]
    assert catalog.quality(released=True).total == 2
    assert {one.question_id for one in catalog.citations(released=True)} == set(ids[:2])


def test_the_balance_command_holds_every_share(written, engine) -> None:
    """The whole round trip, over a pool that can fill the quota exactly."""
    from question_generation.service import balance

    rows = []
    for band in ("easy", "medium", "hard"):
        for kind in ("factoid", "reason"):
            rows += [(band, kind, True, "accepted")] * 6
    rows += [("easy", "factoid", False, "accepted")] * 6
    written(rows)

    count = balance(QuestionCatalog(), _settings())

    with engine.connect() as connection:
        got = dict(
            connection.execute(
                text(
                    "SELECT difficulty, count(*) FROM questions "
                    "WHERE release_id IS NOT NULL GROUP BY 1"
                )
            ).all()
        )
        unanswerable = connection.execute(
            text(
                "SELECT count(*) FROM questions "
                "WHERE release_id IS NOT NULL AND NOT answerable"
            )
        ).scalar_one()

    assert count == released(engine)
    # Within two of each other: a size that does not divide by three has to
    # give one band the remainder, largest-remainder is what decides which,
    # TOLERANCE lets a band come one place short of its quota, and a
    # thread's turns are counted only after its root is drawn, so they can
    # overdraw a band (B26).
    assert max(got.values()) - min(got.values()) <= 2
    assert set(got) == set(BANDS)
    assert unanswerable <= count * 0.1 + 1


def _settings(**overrides):
    """Release settings aiming at a third per band and a tenth unanswerable."""
    from question_generation.config import Settings

    return Settings(
        **{
            "per_topic": 4,
            "sample_size": 4,
            "samples_per_passage": 1,
            "fact_kinds": ("atomic",),
            "type_mix": TYPES,
            "difficulty_mix": {"easy": 1},
            "followup_types": ("condition",),
            "explanation_chars": (150, 900),
            "boilerplate_cosine": 0.0,
            "unanswerable_share": 0.1,
            "followup_share": 0.5,
            "max_followups": 2,
            "retries": 0,
            "answer_chars": {
                "value": (1, 80),
                "list": (3, 300),
                "explanation": (20, 600),
            },
            "answer_coverage": 0.0,
            "party_density": 0.0,
            "meets_floor": 0.0,
            "answer_overlap": 0.6,
            "off_topic_overlap": 0.3,
            "elsewhere_passages": 0,
            "long_answer_chars": 60,
            "duplicate_cosine": 0.93,
            "duplicate_floor": 0.75,
            "release_size": 0,
            "release_unanswerable": 0.1,
            "release_difficulty": BANDS,
            "embedding_model": "stub",
            "model": None,
            "max_tokens": 512,
            "verifier_model": "ollama/verifier",
            **overrides,
        }
    )


def test_the_earlier_turns_of_a_follow_up_are_walked_through_follows_id(
    written, engine
) -> None:
    """A thread of three, asked about its last turn alone: both turns before it come back."""
    ids = written([("easy", "factoid", True, "accepted")])
    with Session(engine) as session:
        previous = ids[0]
        for turn in (2, 3):
            follow = question(
                question_text=f"Turn {turn}?",
                target_answer=f"Answer {turn}" if turn == 2 else None,
                answerable=True,
                difficulty="easy",
                question_type="factoid",
                status="accepted",
                follows_id=previous,
                thread_position=turn,
            )
            session.add(follow)
            session.flush()
            ids.append(follow.id)
            previous = follow.id
        session.commit()
    catalog = QuestionCatalog()
    everyone = {one.id: one for one in catalog.page(limit=None)[1]}

    walked = catalog.earlier([everyone[ids[2]], everyone[ids[0]]])

    assert walked == {
        ids[2]: [("A easy factoid question?", "4 kg"), ("Turn 2?", "Answer 2")]
    }


def test_a_citation_carries_the_section_its_passage_sits_under(written, engine) -> None:
    """With its pages, which a tester needs to find the source by hand."""
    ids = written([("easy", "factoid", True, "accepted")])
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE passages SET section_path = 'Terms > Returns', "
                "page_from = 3, page_to = 4"
            )
        )

    (cited,) = QuestionCatalog().citations(released=None)

    assert cited.question_id == ids[0]
    assert cited.section_path == "Terms > Returns"
    assert cited.page == "3–4"
