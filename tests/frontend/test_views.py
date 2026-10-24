"""The rules every page keeps, checked on every page.

The pages differ in what they list and which stage they run. Everything else
about them is deliberately the same, and that sameness is what these cover:
one service per page, one row of figures, nothing below the table until a
row is picked, and no page reaching into another page's stage.
"""

from __future__ import annotations

import html
import re

import pytest
import requests
from pages import (
    DOCUMENT,
    LISTING,
    OWNED,
    PASSAGE_DETAIL,
    QUESTION,
    QUESTION_QUALITY,
    QUESTION_SOURCE,
    SHA,
    Answers,
    answers,
    changed,
    status,
)

pytestmark = pytest.mark.frontend

#: Every page, including the two that list nothing.
EVERY = (*LISTING, "upload", "health")

#: A question the gates have not judged, so Accept is live on it.
QUESTION_DRAFT = changed(QUESTION, status="draft", rejected_reason=None)

#: The one panel on any page that is not a stage's, by the page carrying it.
#:
#: Documents holds the whole-pipeline controls, drawn between the figures and
#: the stage this page runs because it is the broader of the two: it asks the
#: orchestrator to run every stage in order, and the panel under it runs
#: parsing. It is not a page reaching into another page's stage - the rule
#: these tests exist for - because it reaches no stage at all. See
#: `frontend/lib/pipeline.py`.
BEYOND_THE_STAGE = {"documents": "Pipeline"}

#: The fold that panel adds, beside the two every page has.
AUTOMATION_FOLD = "Run it without being asked"

#: What a page's own explainer fold is called, whichever service it covers.
EXPLAINER_FOLD = "How "


def _stage_panels(name: str, drawn: list[str]) -> list[str]:
    """The panels every page has, with that one exception taken out."""
    return [one for one in drawn if one != BEYOND_THE_STAGE.get(name)]


# ── Every page ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", EVERY)
def test_a_page_renders(open_view, name) -> None:
    """Top to bottom, without raising."""
    assert open_view(name).raised == []


@pytest.mark.parametrize("name", EVERY)
def test_a_page_draws_no_progress_bar(open_view, name) -> None:
    """A queue's depth is a number and a spinner, never a filling bar."""
    assert open_view(name).progress_bars() == []


@pytest.mark.parametrize("name", LISTING)
def test_a_page_opens_an_analysis_fold_rather_than_spilling_it(open_view, name) -> None:
    """Everything beyond the headline figures is folded away on arrival.

    Two folds on most pages: the analysis, and the configuration of the one
    service this page runs. Neither is what anybody arrives to do, and a
    page that opened with forty numbers on it is a page nobody reads.

    Documents has a third, for the same reason and from the panel above:
    switching the pipeline to unattended is a decision made once.

    Questions has a third of its own, `EXPLAINER_FOLD`: what the service
    does, what its gates are, and how to read the numbers it stores. ONE
    fold holding three tabs rather than three folds, because the ceiling
    this test defends is the count a page opens with, and a page is no more
    readable for having its reference split across five headings than for
    having it spilled.
    """
    folded = [
        one
        for one in open_view(name).folds()
        if not one.startswith((AUTOMATION_FOLD, EXPLAINER_FOLD))
    ]

    assert folded == ["Analysis", "Configuration"]


@pytest.mark.parametrize("name", LISTING)
def test_a_page_adds_at_most_one_fold_of_its_own(open_view, name) -> None:
    """The ceiling the rule above is really about.

    A page may explain itself, and no page may do it in more than one
    place: three collapsed sections is what the minimal-page rule was
    written against, and a reference is as capable of flooding a page as a
    figure is.
    """
    explainers = [
        one for one in open_view(name).folds() if one.startswith(EXPLAINER_FOLD)
    ]

    assert len(explainers) <= 1


@pytest.mark.parametrize("name", LISTING)
def test_every_page_is_laid_out_the_same_way(open_view, name) -> None:
    """Overview, the service, search and filters, the table. In that order.

    Topics carries a fifth: its deletion is over the whole model rather
    than over a row, so the box is on the page and not in a selection.
    Documents carries one more again, which `BEYOND_THE_STAGE` names.
    """
    drawn = _stage_panels(name, open_view(name).panels())

    assert [drawn[0], drawn[2]] == ["Overview", "Search and filters"], drawn
    assert drawn[3].lower().startswith(name), drawn
    assert drawn[4:] in ([], ["Delete"]), drawn


@pytest.mark.parametrize("name", LISTING)
def test_a_page_names_its_service_between_the_figures_and_the_search(
    open_view, name
) -> None:
    """So a reader finds the controls in the same place on every page."""
    drawn = _stage_panels(name, open_view(name).panels())

    assert drawn[1].lower().startswith(OWNED[name][:5]), drawn


def test_only_documents_carries_a_control_that_is_not_a_stage_s(open_view) -> None:
    """The exception above is one page and one panel, and stays that way.

    Every other page holds exactly the stage that produced what it lists.
    A second page growing a whole-pipeline control would be two places to
    press Run, disagreeing the first time one of them changed.
    """
    carrying = {name for name in LISTING if "Pipeline" in open_view(name).panels()}

    assert carrying == {"documents"}


def test_the_pipeline_panel_sits_above_the_stage_the_page_runs(open_view) -> None:
    """Broadest first: every stage, then the one this page owns."""
    drawn = open_view("documents").panels()

    assert drawn[:3] == ["Overview", "Pipeline", "Parsing"], drawn


@pytest.mark.parametrize("name", LISTING)
def test_a_page_shows_a_handful_of_figures_and_no_more(open_view, name) -> None:
    """The first section carries what is worth seeing, not everything."""
    assert len(open_view(name).stats()) <= 5


@pytest.mark.parametrize("name", LISTING)
def test_every_figure_says_what_it_counts(open_view, name) -> None:
    """A figure cannot reach the page without a line saying what it is."""
    unexplained = [
        label for label, text in open_view(name).explanations().items() if not text
    ]

    assert not unexplained


@pytest.mark.parametrize("name", EVERY)
def test_a_page_reports_an_unreachable_backend_rather_than_raising(
    open_view, name
) -> None:
    """Streamlit would otherwise replace the page with a stack trace."""
    down = requests.exceptions.ConnectionError("backend is down")
    page = open_view(
        name,
        client=Answers(**dict.fromkeys(answers(), down)),
        upload_api=Answers(counts=down),
        health_api=Answers(reachable=(False, "down"), components={}, services=[]),
    )

    assert page.raised == []
    assert "Failed to load" in page.text() or "unreachable" in page.text().lower()


# ── One service per page ──────────────────────────────────────────────────


@pytest.mark.parametrize("name", LISTING)
def test_a_page_runs_its_own_stage_and_no_other(open_view, name) -> None:
    """The rule the whole layout is built on.

    Read off the controls themselves: every queue button is keyed with the
    stage it moves, so a page carrying a control for somebody else's stage
    says so in its own keys.
    """
    page = open_view(name)
    verbs = ("start", "stop", "retry", "rerun", "discover")

    moved = {
        key.split("-")[1]
        for key in page.control_keys()
        if key and key.split("-")[0] in verbs
    }

    assert moved == {OWNED[name]}, page.control_keys()


@pytest.mark.parametrize("name", LISTING)
def test_a_page_can_run_its_stage_over_everything_at_once(open_view, name) -> None:
    """Each service is startable for the whole corpus, not row by row."""
    page = open_view(name)

    assert page.button("Start all") or page.button("Fit all"), sorted(page.buttons())


@pytest.mark.parametrize("name", ("documents", "passages", "facts", "questions"))
def test_a_stage_that_queues_rows_offers_the_four_verbs(open_view, name) -> None:
    """Start, Stop, Retry and Redo, whichever page the stage is on."""
    offered = set(open_view(name).buttons())

    assert {"Start all", "Stop", "Retry", "Redo all"} <= offered


def test_the_topics_page_offers_a_fit_rather_than_a_start(open_view) -> None:
    """A fit is all-or-nothing, so it has no per-topic form and no redo."""
    page = open_view("topics")

    assert page.button("Fit all")
    assert page.button("Redo all") is None


# ── Search, filters and the table ─────────────────────────────────────────


@pytest.mark.parametrize("name", LISTING)
def test_searching_is_a_separate_control_from_filtering(open_view, name) -> None:
    """Typing words is one thing; narrowing to a value another."""
    keys = open_view(name).widget_keys()

    assert f"{name}-search" in keys
    assert {key for key in keys if key.startswith(f"{name}-")} - {
        f"{name}-search",
        f"{name}-field",
        f"{name}-page",
    }, keys


def _holding_q_to(bound: int, rows: dict):
    """A listing that refuses a longer search, as every listing route does."""

    class Unprocessable:
        @staticmethod
        def json() -> dict:
            return {
                "detail": [{"msg": f"String should have at most {bound} characters"}]
            }

    def answer(**asked):
        if len(asked.get("q") or "") > bound:
            refused = requests.HTTPError("422 Client Error: Unprocessable Entity")
            refused.response = Unprocessable()  # type: ignore[assignment]
            raise refused
        return rows

    return answer


@pytest.mark.parametrize(
    "pasted",
    [
        (
            "Ein Entgelt von 5,00 EUR wird für jede Rücklastschrift erhoben, die der "
            "Kunde zu vertreten hat; die Bank belastet das Entgelt dem Konto, von dem "
            "die Lastschrift eingelöst werden sollte, und teilt dem Kunden die "
            "Rückgabe unverzüglich mit."
        ),
        (
            "Items bought online may be returned within 30 days of delivery for a "
            "full refund to the original payment method, provided they are unused, "
            "in their original packaging and accompanied by the receipt or order "
            "number."
        ),
    ],
)
def test_a_pasted_sentence_does_not_take_the_page_down(open_view, pasted) -> None:
    """The box holds no more than the listing routes take, 200 characters."""
    assert len(pasted) > 200
    listed = _holding_q_to(200, {"total": 0, "passages": []})
    client = Answers(**answers(passages=listed))

    after = open_view("passages", client).type_in("passages-search", pasted)

    assert after.errors() == []
    assert [len(one[2]["q"]) for one in client.calls("passages")][-1] == 200


@pytest.mark.parametrize("name", LISTING)
def test_every_search_box_takes_no_more_than_the_api_does(open_view, name) -> None:
    """The one box every listing draws, held to the routes' own bound."""
    assert open_view(name).max_chars(f"{name}-search") == 200


def test_the_search_and_filters_wrap_only_once_a_row_is_full() -> None:
    """Questions' eleven controls take two rows; Facts' six take one."""
    from lib.catalog import _COLUMN, _FILTER, _PAGER, _WORDS, wrapped

    assert len(wrapped([_WORDS, _COLUMN, *[_FILTER] * 8, _PAGER])) == 2
    assert len(wrapped([_WORDS, _COLUMN, *[_FILTER] * 3, _PAGER])) == 1


@pytest.mark.parametrize("size", ["0", "600"])
def test_a_page_size_the_api_refuses_stops_the_frontend(monkeypatch, size) -> None:
    """Every listing asked for that many rows and got an unnamed 422 back."""
    import runpy

    from lib import config

    monkeypatch.setenv("PAGE_SIZE", size)

    with pytest.raises(RuntimeError, match="PAGE_SIZE"):
        runpy.run_path(config.__file__)


def test_a_page_the_corpus_shrank_under_goes_back_to_the_first(open_view) -> None:
    """Page 2 answering no rows is read again as page 1."""
    held = {"total": 30}

    def documents(**asked) -> dict:
        """One row a page, until the offset passes the total."""
        rows = [DOCUMENT] if asked["offset"] < held["total"] else []
        return {"total": held["total"], "documents": rows}

    client = Answers(**answers(documents=documents))
    opened = open_view("documents", client)
    held["total"] = 3
    opened.numbers()["Page of 2"].set_value(2)

    after = opened.rerun()

    assert [one[2]["offset"] for one in client.calls("documents")][-2:] == [25, 0]
    assert after.numbers()["Page of 1"].value == 1
    assert "report.pdf" in after.tables()


@pytest.mark.parametrize("name", LISTING)
def test_nothing_about_an_item_is_shown_until_one_is_picked(open_view, name) -> None:
    """A page opens as a list, and stays one until a row is clicked."""
    page = open_view(name)

    assert "Field" not in page.tables()


@pytest.mark.parametrize("name", LISTING)
def test_picking_a_row_opens_everything_held_about_it(open_view, name) -> None:
    """One table of every field, rather than a second row of figures."""
    page = open_view(name).select(0)

    assert page.raised == []
    assert "Field" in page.tables()


@pytest.mark.parametrize("name", LISTING)
def test_picking_a_row_adds_no_figures(open_view, name) -> None:
    """Below the table everything is a table. No boxes."""
    before = open_view(name)
    after = before.select(0)

    assert set(after.stats()) == set(before.stats())


@pytest.mark.parametrize("name", LISTING)
def test_a_page_with_nothing_on_it_says_so(open_view, name) -> None:
    """An empty corpus is a sentence, not a stack trace or a blank."""
    page = open_view(
        name,
        documents={"total": 0, "documents": []},
        passages={"total": 0, "passages": []},
        facts={"total": 0, "facts": []},
        questions={"total": 0, "questions": []},
        assessments={"total": 0, "assessments": []},
        topics=[],
        stage_status=lambda *a, **k: status(),
    )

    assert page.raised == []
    assert "matches" in page.text() or "Fit the model" in page.text()


# ── Stored text, drawn as written ─────────────────────────────────────────


def literal(said: str) -> str:
    """What Markdown draws of it: each backslash escape as the mark it escapes."""
    return re.sub(r"\\(.)", r"\1", said)


def formatting(said: str) -> list[str]:
    """The marks in it Markdown would read as formatting rather than draw."""
    return re.findall(r"(?<!\\)[$*_`\[\]~]", said)


@pytest.mark.parametrize(
    "filename", ["Konditionen <Entwurf> & Preise.pdf", "Fees <draft> & charges.pdf"]
)
def test_a_documents_panel_is_headed_with_its_name_as_uploaded(
    open_view, filename
) -> None:
    """`st.html` drops an element it does not know, so `<Entwurf>` went."""
    named = changed(DOCUMENT, filename=filename)
    client = Answers(
        **answers(
            documents={"total": 1, "documents": [named]},
            document_names=[{"sha256": SHA, "filename": filename}],
        )
    )

    opened = open_view("documents", client).select(0)

    assert html.escape(filename, quote=False) in opened.panels()


@pytest.mark.parametrize(
    "filename", ["Preisliste_2026_*Entwurf*.pdf", "returns_policy_*final*.pdf"]
)
def test_the_delete_question_names_the_file_as_it_was_uploaded(
    open_view, filename
) -> None:
    """Drawn as Markdown, `*Entwurf*` was a name no document has, in italics."""
    named = changed(DOCUMENT, filename=filename)
    client = Answers(**answers(documents={"total": 1, "documents": [named]}))

    (asked,) = (
        open_view("documents", client).select(0).press("Delete document").warnings()
    )

    assert literal(asked).startswith(f"Delete {filename} and everything")
    assert formatting(asked) == []


@pytest.mark.parametrize(
    "filename", ["Preisliste_2026_*Entwurf*.pdf", "returns_policy_*final*.pdf"]
)
def test_an_upload_names_the_file_as_it_was_chosen(open_view, filename) -> None:
    """The message after an upload is Markdown too."""
    page = open_view("upload")
    page.uploader()[0].upload(filename, b"%PDF-1.4", "application/pdf")

    (said,) = page.press("Upload all").successes()

    assert literal(said) == f"{filename}: stored."
    assert formatting(said) == []


# ── Deletion ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ("passages", "facts", "questions"))
def test_a_page_whose_rows_cannot_be_deleted_offers_no_deletion(
    open_view, name
) -> None:
    """A passage belongs to its document; a rejected question is evidence."""
    page = open_view(name).select(0)

    assert not [key for key in page.control_keys() if key and key.startswith("danger-")]


@pytest.mark.parametrize(
    ("name", "label"),
    (("documents", "Delete document"), ("topics", "Delete all topics")),
)
def test_a_deletion_asks_before_it_does_anything(open_view, name, label) -> None:
    """The first click arms it; a second, separately labelled one acts."""
    page = open_view(name).select(0)
    assert page.button("Yes, delete") is None

    armed = page.press(label)

    assert armed.button("Yes, delete")
    assert armed.button("Cancel")


def test_cancelling_a_deletion_removes_nothing(open_view) -> None:
    """Nothing is asked of the backend until the second click."""
    client = Answers(**answers())
    page = open_view("documents", client).select(0)

    page.press("Delete document").press("Cancel")

    assert not client.calls("delete")


def test_confirming_a_deletion_deletes(open_view) -> None:
    """And says what went."""
    client = Answers(**answers())
    page = open_view("documents", client).select(0)

    page.press("Delete document").press("Yes, delete")

    assert client.calls("delete")


def test_deleting_the_derived_data_keeps_the_document(open_view) -> None:
    """The two deletions are different operations, not one with a flag."""
    client = Answers(**answers())
    page = open_view("documents", client).select(0)

    page.press("Delete passages and facts").press("Yes, delete")

    assert [one for one in client.calls("delete") if one[2].get("derived_only")]


def test_the_deletion_says_only_what_the_api_removed(open_view, monkeypatch) -> None:
    """A file that was not there is not reported as removed."""
    import streamlit as st

    said: list[str] = []
    monkeypatch.setattr(st, "toast", lambda body, **_: said.append(str(body)))
    removed = {"sha256": SHA, "document": True, "passages": 10, "file": False}
    client = Answers(**answers(delete={**removed, "parsed": True}))

    open_view("documents", client).select(0).press("Delete document").press(
        "Yes, delete"
    )

    assert "The file was not there" in said[-1]
    assert "The parsed form was removed" in said[-1]


@pytest.mark.parametrize("label", ("Delete passages and facts", "Delete document"))
def test_a_document_deletion_names_the_questions_and_bridges_it_takes(
    open_view, label
) -> None:
    """They go with the facts, so the confirmation says so."""
    armed = open_view("documents").select(0).press(label)
    said = " ".join(armed.warnings())

    assert "person-reviewed and released" in said
    assert "bridge" in said
    assert "this document only" not in armed.html()


# ── Redo ──────────────────────────────────────────────────────────────────

#: The pages whose Redo deletes what was built on the work, by what the
#: confirmation has to name.
REDO_WARNS = {
    "passages": "person-reviewed and released",
    "facts": "person-reviewed and released",
    "assessment": "verdict",
    "documents": "stored parse",
    "questions": "asked again",
}


def _reruns(client: Answers) -> list:
    """Every rerun the page asked for."""
    return [one for one in client.calls("stage_action") if one[1][1] == "rerun"]


@pytest.mark.parametrize("name", REDO_WARNS)
def test_redo_all_asks_before_it_sends_anything(open_view, name) -> None:
    """The first press arms it and says what goes; the second sends it."""
    client = Answers(**answers())

    armed = open_view(name, client).press("Redo all")

    assert not _reruns(client)
    assert REDO_WARNS[name] in " ".join(armed.warnings())

    armed.press("Yes, redo")

    assert _reruns(client)


@pytest.mark.parametrize(
    ("name", "scope"),
    (
        ("documents", ("document", SHA)),
        ("passages", ("document", SHA)),
        ("facts", ("passage", "11")),
    ),
)
def test_redo_on_one_item_asks_before_it_sends_anything(open_view, name, scope) -> None:
    """The same two presses for the Redo drawn under a picked row."""
    client = Answers(**answers())

    armed = open_view(name, client).select(0).press("Redo")

    assert not _reruns(client)

    armed.press("Yes, redo")

    assert ("stage_action", (OWNED[name], "rerun", scope), {}) in client.asked


def test_cancelling_a_redo_sends_nothing(open_view) -> None:
    """Cancel disarms it."""
    client = Answers(**answers())

    cancelled = open_view("facts", client).press("Redo all").press("Cancel")

    assert not _reruns(client)
    assert cancelled.button("Yes, redo") is None


# ── After an action ───────────────────────────────────────────────────────

#: One action per page, as the presses that send it with a row picked.
ACTIONS = {
    "documents": ("Delete passages and facts", "Yes, delete"),
    "passages": ("Redo", "Yes, redo"),
    "facts": ("Redo", "Yes, redo"),
    "topics": ("Save",),
    "assessment": ("Start all",),
}


@pytest.mark.parametrize("name", ACTIONS)
def test_an_action_unpicks_the_row_so_the_detail_cannot_slide(open_view, name) -> None:
    """A pick is a position, and the action may have moved the rows under it."""
    page = open_view(name, stage_status=lambda *a, **k: status(new=2)).select(0)
    assert "Field" in page.tables()

    for label in ACTIONS[name]:
        page = page.press(label)

    assert page.raised == []
    assert "Field" not in page.tables()


# ── The pages outside the catalogue ───────────────────────────────────────


def test_the_upload_page_offers_a_file_picker(open_view) -> None:
    """The one page whose service runs in the request rather than a worker."""
    assert open_view("upload").uploader()


def test_the_upload_page_uploads_every_chosen_file_at_once(open_view) -> None:
    """Its all-at-once is the picker taking several files."""
    assert open_view("upload").uploader()[0].proto.multiple_files


def test_the_upload_page_counts_what_it_just_uploaded(open_view) -> None:
    """The figures are read after the uploads, not before them."""
    held = {"documents": 3, "upload_attempts": 5}

    def added(filename: str, data: bytes) -> dict:
        """Stores the file, so the counts move."""
        held.update(documents=4, upload_attempts=6)
        return {"outcome": "stored"}

    page = open_view(
        "upload", upload_api=Answers(counts=lambda: dict(held), add_document=added)
    )
    page.uploader()[0].upload("report.pdf", b"%PDF-1.4", "application/pdf")

    done = page.press("Upload all")

    assert done.raised == []
    assert done.stats()["Documents"] == "4"


def _many(page, names: list[str], size: int = 8):
    """A picker holding one small file under each name."""
    picker = page.uploader()[0]
    for name in names:
        picker.upload(name, b"%PDF-1.4" + b"x" * size, "application/pdf")
    return page


def test_the_upload_page_refuses_a_selection_above_the_file_cap(open_view) -> None:
    """Held whole in the browser session and sent one request at a time."""
    from lib import config

    sent: list[str] = []

    def added(filename: str, data: bytes) -> dict:
        """Would store it."""
        sent.append(filename)
        return {"outcome": "stored"}

    names = [f"Bericht {n}.pdf" for n in range(config.UPLOAD_MAX_FILES // 2 + 1)]
    names += [f"report-{n}.pdf" for n in range(config.UPLOAD_MAX_FILES // 2 + 1)]
    page = open_view("upload", upload_api=Answers(counts=dict, add_document=added))

    done = _many(page, names).press("Upload all")

    assert sent == []
    assert done.raised == []
    refusal = " ".join(done.errors() + done.warnings())
    assert "make ingest DIR=" in refusal
    assert str(config.UPLOAD_MAX_FILES) in refusal


def test_the_upload_page_refuses_a_selection_above_the_byte_cap(
    open_view, monkeypatch
) -> None:
    """The total, because three files under the per-file limit can still be a lot."""
    from lib import config

    monkeypatch.setattr(config, "UPLOAD_MAX_BYTES", 40)
    sent: list[str] = []

    def added(filename: str, data: bytes) -> dict:
        """Would store it."""
        sent.append(filename)
        return {"outcome": "stored"}

    page = open_view("upload", upload_api=Answers(counts=dict, add_document=added))

    done = _many(page, ["a.pdf", "b.pdf", "c.pdf"], size=20).press("Upload all")

    assert sent == []
    assert "make ingest DIR=" in " ".join(done.errors() + done.warnings())


def test_the_upload_page_keeps_each_files_outcome_in_a_table(open_view) -> None:
    """Where it can still be read after the page redraws."""

    def added(filename: str, data: bytes) -> dict:
        """The second file is a copy."""
        return {"outcome": "duplicate_bytes" if "Kopie" in filename else "stored"}

    page = open_view("upload", upload_api=Answers(counts=dict, add_document=added))

    done = _many(page, ["Gebühren.pdf", "Gebühren Kopie.pdf"]).press("Upload all")

    table = done.table("Outcome")
    assert list(table["File"]) == ["Gebühren.pdf", "Gebühren Kopie.pdf"]
    assert list(table["Outcome"]) == ["stored", "duplicate bytes"]


def test_the_upload_page_calls_a_timeout_unknown_and_points_at_the_list(
    open_view,
) -> None:
    """The api may have stored the file whose answer never came."""

    def added(filename: str, data: bytes) -> dict:
        """Waits past the client's timeout."""
        raise requests.exceptions.ReadTimeout("read timed out")

    page = open_view(
        "upload",
        upload_api=Answers(counts=dict, add_document=added),
    )
    page.uploader()[0].upload("rapport.pdf", b"%PDF-1.4", "application/pdf")

    done = page.press("Upload all")

    assert done.raised == []
    assert any("unknown" in one and "Documents" in one for one in done.errors())


def test_the_health_page_lists_every_component_the_backend_reports(open_view) -> None:
    """A component appears without a change here."""
    page = open_view("health")

    assert "Ingestion" in page.tables()
    assert "Database" in page.tables()


def test_the_health_page_shows_a_component_s_figures_when_it_is_picked(
    open_view,
) -> None:
    """Its own numbers, and what each counts."""
    picked = open_view("health").select(2)

    assert "Upload Attempts" in picked.tables()
    assert "accepted and refused" in picked.tables()


def test_the_health_page_lists_every_service_with_a_link_to_it(open_view) -> None:
    """The whole of compose, not the browsable half.

    A page called System health that listed only what has a web page could
    not answer "is Redis up", which is the question somebody has when a
    stage stops claiming rows.
    """
    page = open_view("health")

    assert "argilla" in page.tables()
    assert "redis" in page.tables()
    assert "http://localhost:6900" in page.tables()


def test_the_health_page_says_a_worker_is_neither_up_nor_down(open_view) -> None:
    """It reads a queue and serves no port, so a red mark would be a lie."""
    page = open_view("health")

    assert "no port" in page.tables()


def test_the_health_page_names_what_is_not_answering(open_view) -> None:
    """A table of twenty-three rows buries one failure."""
    page = open_view("health")

    assert "redis" in page.text()


def test_the_health_page_survives_a_backend_that_is_down(open_view) -> None:
    """A failed backend card makes every other card unknowable."""
    page = open_view(
        "health",
        health_api=Answers(reachable=(False, "refused"), components={}, services=[]),
    )

    assert page.raised == []
    assert "unreachable" in page.text()


# ── What each listing page put in its table ───────────────────────────────


def test_the_documents_page_lists_what_the_backend_returns(open_view) -> None:
    """The row, as a reader recognises it."""
    tables = open_view("documents").tables()

    assert "report.pdf" in tables
    assert "Risks in focus" in tables


def test_the_documents_page_can_narrow_to_one_parse_state(open_view) -> None:
    """Which is the filter the parsing page has."""
    client = Answers(**answers())
    page = open_view("documents", client)

    page.choose("documents-parse_status", "failed")

    assert [
        one
        for one in client.calls("documents")
        if one[2].get("parse_status") == "failed"
    ]


def test_the_passages_page_numbers_the_sentences_a_fact_would_cite(open_view) -> None:
    """The number in the first column is what a citation refers to."""
    sentences = [
        {"i": 4, "start": 0, "end": 30, "predicates": 1},
        {"i": 5, "start": 31, "end": 62, "predicates": 1},
    ]
    client = Answers(**answers(passage=changed(PASSAGE_DETAIL, sentences=sentences)))

    drawn = open_view("passages", client).select(0)

    assert list(drawn.table("Claims")["#"]) == [4, 5]


def test_the_passages_page_runs_chunking_over_the_document_it_belongs_to(
    open_view,
) -> None:
    """Chunking queues over a document and replaces all of its passages."""
    page = open_view("passages").select(0)

    assert f"start-chunking-document-{SHA}" in page.control_keys()


def test_the_facts_page_runs_extraction_over_the_passage_it_came_from(
    open_view,
) -> None:
    """Extraction reads a passage and writes all of its facts together."""
    page = open_view("facts").select(0)

    assert "start-extraction-passage-11" in page.control_keys()


def test_the_questions_page_lists_what_the_backend_returns(open_view) -> None:
    """The question and the answer it is scored against."""
    tables = open_view("questions").tables()

    assert "48 hours" in tables


def test_a_question_with_no_scope_recorded_does_not_read_as_a_wide_one(
    open_view,
) -> None:
    """The columns are nullable, and absent is not `2+`."""
    page = open_view(
        "questions",
        questions={
            "total": 1,
            "questions": [changed(QUESTION, passage_scope=None, document_scope=None)],
        },
    )

    assert "2+" not in page.tables()


def test_a_picked_question_shows_its_categories(open_view) -> None:
    """What its writer was told it should be, beside its kind."""
    page = open_view("questions").select(0)

    fields = page.table("Field")
    shown = dict(zip(fields["Field"], fields["Value"], strict=True))
    assert shown["Categories"] == "Phrasing=concise-and-natural"


def test_the_quality_checks_count_each_kind_and_category(open_view) -> None:
    """Read off the report's `kind` and `categories`, as the workbook does."""
    page = open_view(
        "questions",
        question_quality=changed(
            QUESTION_QUALITY,
            kind={"single": 1},
            categories={"Phrasing=concise-and-natural": 1},
        ),
    )

    assert "Kind: single" in page.tables()
    assert "Category: Phrasing=concise-and-natural" in page.tables()


def test_accepting_a_question_writes_the_status_and_nothing_else(open_view) -> None:
    """A person overruling a gate changes the verdict, not the question."""
    client = Answers(**answers(questions={"total": 1, "questions": [QUESTION_DRAFT]}))
    page = open_view("questions", client).select(0)

    page.press("Accept")

    assert [one for one in client.calls("decide_question") if one[1][1] == "accepted"]


def test_a_workbook_is_built_only_when_it_is_asked_for(open_view) -> None:
    """The download is two presses, and the first is what costs anything.

    `st.download_button` wants its bytes up front, so a page holding one
    unconditionally would write a workbook of every question on each
    rerun - on every keystroke in the search box. Nothing is asked of the
    backend until somebody presses.
    """
    client = Answers(**answers(question_workbook=b"PK\x03\x04 a workbook"))
    page = open_view("questions", client)

    assert not client.calls("question_workbook")

    page = page.press("Build a workbook")

    assert client.calls("question_workbook")
    assert page.raised == []
    assert page.downloads()


def test_a_workbook_is_dropped_when_the_filter_moves_under_it(open_view) -> None:
    """A file offered after the filter changed is the wrong set under a right name."""
    client = Answers(**answers(question_workbook=b"PK\x03\x04 a workbook"))
    page = open_view("questions", client)
    page = page.press("Build a workbook")

    moved = page.choose("questions-status", "accepted")

    assert moved.button("Build a workbook") is not None
    assert not moved.downloads()


def test_a_workbook_is_dropped_once_a_verdict_moves_the_counts(open_view) -> None:
    """A question rejected a moment ago must not download as accepted."""
    decided: list[tuple] = []
    client = Answers(
        **answers(
            question_workbook=b"PK\x03\x04 a workbook",
            decide_question=lambda *asked: decided.append(asked) or QUESTION,
            question_quality=lambda **_: changed(
                QUESTION_QUALITY, accepted=1 - len(decided)
            ),
        )
    )
    built = open_view("questions", client).press("Build a workbook").select(0)
    assert built.downloads()

    judged = built.press("Reject")

    assert decided == [(QUESTION["id"], "rejected")]
    assert not judged.downloads()
    assert judged.button("Build a workbook") is not None


def test_the_questions_page_says_when_a_cited_fact_no_longer_holds(open_view) -> None:
    """A question resting on a rejected fact is not a question any more."""
    page = open_view(
        "questions",
        question={
            "question": QUESTION,
            "sources": [changed(QUESTION_SOURCE, validated=False)],
            "thread": [],
        },
    ).select(0)

    assert "no longer passes its checks" in page.text()
