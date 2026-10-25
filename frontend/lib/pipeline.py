"""The corpus as one control, on the page a document lands on.

Every other control in this frontend belongs to one stage, and `lib/stage.py`
says so: a page carries the stage that produced what it lists, and no page
can reach another page's stage. This does not break that rule, because it
reaches no stage at all. It asks the orchestrator to decide that the pipeline
should run, which is the same decision `make corpus` and the nightly schedule
make, and the orchestrator is what then starts each stage in turn.

That distinction is the whole reason a Run button can exist here and a
"start chunking" button cannot. Running the corpus means waiting for one
stage to drain before starting the next, and nothing in a browser can hold
that wait: closing the tab would abandon it half way. So the wait lives in a
Dagster run, this asks for one, and what the panel then shows is that run
getting on with it.

**Without an orchestrator the panel still works.** Run is disabled and says
why; Start, Stop and Retry are queue verbs and go on doing exactly what the
per-stage buttons do, over every stage at once.
"""

from __future__ import annotations

import streamlit as st

from lib import page

#: How often the panel redraws. The same interval the stage controls use.
POLL_SECONDS = 3

#: Whether anything is queued or running, as the last draw found it. While
#: nothing is, the panel has no timer; a button redraws it.
_BUSY = "pipeline-busy"

#: What each Dagster run status means for somebody reading a page. Anything
#: not here is shown as Dagster spells it, lower-cased.
_RUN_READS = {
    "QUEUED": "queued",
    "NOT_STARTED": "starting",
    "STARTING": "starting",
    "STARTED": "running",
    "CANCELING": "stopping",
    "SUCCESS": "finished",
    "FAILURE": "failed",
    "CANCELED": "stopped",
}


def panel(client) -> None:
    """Draws the whole-pipeline controls, and goes on drawing them.

    Through `page.render`, because a fragment reruns on its own and so
    outside the guard the view was called under: an unreachable backend
    would otherwise replace the panel with a stack trace.
    """
    polling = st.session_state.get(_BUSY, True)

    @st.fragment(run_every=POLL_SECONDS if polling else None)
    def drawn() -> None:
        """Draws the controls, and keeps drawing them while anything moves."""
        answers: list[bool] = []
        page.render(lambda: answers.append(_controls(client)))
        now = answers[0] if answers else True
        if now != st.session_state.get(_BUSY, True):
            st.session_state[_BUSY] = now
            st.rerun()

    drawn()


def _controls(client) -> bool:
    """Draws one pass of the panel.

    Returns:
        Whether anything is queued, running or unanswered, which is what
        keeps the panel polling.
    """
    state = client.state()
    if not state:
        st.caption("The backend is not answering.")
        return True

    stages = state.get("stages") or []
    orchestration = state.get("orchestration") or {}
    available = bool(orchestration.get("available"))
    running = orchestration.get("running")
    working = bool(state.get("working"))
    failed = int(state.get("failed") or 0)
    ready = sum(
        (one.get("rows") or {}).get("new", 0)
        for one in stages
        if one.get("stage") != "assessment"
    )

    row = st.container(horizontal=True, vertical_alignment="center", key="pipeline-row")

    if row.button(
        "Run the pipeline",
        key="pipeline-run",
        type="primary",
        width="content",
        disabled=not available or running is not None,
        help=_run_help(available, running, bool(state.get("host_runner"))),
    ):
        _report(client.run())

    # Every label here names the corpus, because the panel below this one
    # carries the same three verbs for the one stage this page owns. Two
    # controls reading `Start` on one page is a control nobody can use.
    if row.button(
        "Start every stage",
        key="pipeline-start",
        width="content",
        disabled=not ready,
        help=f"Queues the {ready:,} row(s) ready to be worked, in every "
        "stage. One stretch of the pipeline, not all of it."
        if ready
        else "Nothing is ready to be queued.",
    ):
        _report(client.act("start"))

    if row.button(
        "Stop everything",
        key="pipeline-stop",
        width="content",
        disabled=not working and running is None,
        help="Takes back everything queued and stops the run behind it. "
        "Whatever a worker holds right now finishes."
        if working or running
        else "Nothing is queued or running.",
    ):
        _report(client.act("stop"))

    if row.button(
        "Retry failures",
        key="pipeline-retry",
        width="content",
        disabled=not failed,
        help=f"Returns the {failed:,} failed row(s) of every stage to the queue."
        if failed
        else "Nothing has failed.",
    ):
        _report(client.act("retry"))

    row.caption(_reads(stages, running, working, failed))
    with row:
        _automation(client, orchestration.get("automation") or {})
    return working or running is not None


def _run_help(available: bool, running: dict | None, hosted: bool = False) -> str:
    """Why Run is offered, or why it is not."""
    if hosted:
        return (
            "The go-live profile runs the model stages on the host, through "
            "`make corpus-hosted`, and Dagster is not part of it. A stage's "
            "own Start queues its rows for that run."
        )
    if not available:
        return (
            "This deployment has no orchestrator, so nothing can wait for "
            "one stage to drain before starting the next. Use Start, or "
            "`make corpus` from a terminal."
        )
    if running is not None:
        return (
            f"Run {running.get('id', '')[:8]} is already taking this corpus "
            "through. Stop it first, or wait for it."
        )
    return (
        "Takes every document through every stage but the topic fit, in "
        "order, waiting for each to finish. Only what has not been done "
        "already."
    )


def _reads(stages: list[dict], running: dict | None, working: bool, failed: int) -> str:
    """One line saying where the corpus has got to."""
    parts = []
    if running is not None:
        status = _RUN_READS.get(running.get("status", ""), "").strip()
        parts.append(f"run {running.get('id', '')[:8]} {status or 'running'}")
    elif working:
        parts.append("working")
    stalled = [one["stage"] for one in stages if (one.get("rows") or {}).get("failed")]
    if failed:
        parts.append(f"{failed:,} failed in {', '.join(stalled)}")
    if not parts:
        done = sum(
            count
            for one in stages
            for status, count in (one.get("rows") or {}).items()
            if status not in ("new", "pending", "in_progress", "failed")
        )
        parts.append(f"{done:,} row(s) done" if done else "nothing has run yet")
    return " · ".join(parts)


def _automation(client, automation: dict) -> None:
    """The two switches that start a run without being asked.

    Folded away, because turning one on is a decision made once and the
    four buttons beside it are the ones pressed daily. Off is what ships: a
    stack that starts working the moment it comes up is one nobody chose.
    """
    available = bool(automation.get("available"))
    on_arrival = bool(automation.get("on_arrival"))
    nightly = bool(automation.get("nightly"))
    running = [
        name for name, on in (("on upload", on_arrival), ("nightly", nightly)) if on
    ]

    # Outside the fold, because a fold is opened by somebody who expects
    # something in it. Nothing to switch is worth reading without the click.
    if not available:
        st.caption(
            "No orchestrator, so nothing can watch for uploads or run to a "
            "clock. `make corpus` from a terminal is the other way to take "
            "a corpus through in order."
        )
        return

    # The switches follow the backend whenever it moved since this page last
    # read it: a keyed toggle takes `value` only the first time it is drawn.
    if st.session_state.get("pipeline-automation-seen") != (on_arrival, nightly):
        st.session_state["pipeline-automation-seen"] = (on_arrival, nightly)
        st.session_state["pipeline-on-arrival"] = on_arrival
        st.session_state["pipeline-nightly"] = nightly

    with st.expander(
        "Run it without being asked" + (f" · {', '.join(running)}" if running else "")
    ):
        chosen = st.toggle(
            "When a document is uploaded",
            key="pipeline-on-arrival",
            help="Starts a run whenever documents are sitting unasked-for. "
            "This is what makes the pipeline unattended.",
        )
        clocked = st.toggle(
            "Every night at 02:00 UTC",
            key="pipeline-nightly",
            help="Runs every stage but the topic fit over whatever is "
            "waiting. A refit is Fit all on the Topics page.",
        )
        if chosen != on_arrival or clocked != nightly:
            done, said = client.automate(on_arrival=chosen, nightly=clocked)
            if not done:
                # Redrawn from the backend next run, or the toggle keeps the
                # refused value and every poll sends it again.
                st.session_state.pop("pipeline-automation-seen", None)
            _report((done, said))


def _report(outcome: tuple[bool, str]) -> None:
    """Shows what a verb did, and redraws the page under it."""
    done, said = outcome
    if done:
        page.acted()
        st.toast(said)
        st.rerun()
    else:
        st.warning(said)
