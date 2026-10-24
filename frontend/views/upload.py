"""Upload view. The ingestion service, and nothing else."""

from __future__ import annotations

import requests
import streamlit as st

from lib import backend, config, configure, page
from lib.backend.base import refusal
from lib.backend.upload import UploadApi

#: Where the last upload's outcomes are kept, so a redraw does not lose them.
_LAST = "upload-last"


def _over_the_cap(files: list) -> str | None:
    """Says why a selection is too large to send from this page, if it is."""
    size = sum(one.size for one in files)
    if len(files) <= config.UPLOAD_MAX_FILES and size <= config.UPLOAD_MAX_BYTES:
        return None
    return (
        f"{len(files)} files, {size / 1048576:,.0f} MB: this page sends at most "
        f"{config.UPLOAD_MAX_FILES} files and {config.UPLOAD_MAX_BYTES / 1048576:,.0f} "
        f"MB at once, and nothing was uploaded. Load a larger set from the "
        f"host with `make ingest DIR=<directory>`."
    )


def view() -> None:
    """Renders the upload page, submitting every chosen file at once."""
    page.header("Upload")

    client = backend.upload_api()
    # Filled after the uploads below.
    overview = st.container()

    with page.panel("Ingestion"):
        with st.form("upload", border=False):
            files = st.file_uploader(
                "PDFs",
                type=["pdf"],
                accept_multiple_files=True,
                help="Stored under the digest of its own bytes. A file the "
                "corpus already holds is recorded and stores nothing.",
            )
            submitted = st.form_submit_button("Upload all", type="primary")
        # Outside the upload form, inside the panel: a form holds no form.
        configure.panel("ingestion")

    if submitted and files and (too_much := _over_the_cap(files)):
        st.error(too_much)
    elif submitted and files:
        with st.spinner(f"Uploading {len(files)} file(s)…"):
            st.session_state[_LAST] = [
                _report(uploaded.name, client, uploaded.getvalue())
                for uploaded in files
            ]
    elif submitted:
        st.warning("Select at least one PDF.")

    if last := st.session_state.get(_LAST):
        with page.panel("Last upload"):
            st.dataframe(last, hide_index=True, width="stretch")

    held = client.counts()
    with overview, page.panel("Overview"):
        page.stats(
            {
                "Documents": (
                    f"{held.get('documents', 0):,}",
                    "PDFs held in the object store.",
                ),
                "Uploads": (
                    f"{held.get('upload_attempts', 0):,}",
                    "Uploads recorded, accepted and refused alike.",
                ),
            }
        )


def _report(filename: str, client: UploadApi, data: bytes) -> dict[str, str]:
    """Uploads one file, shows what became of it, and returns the table row."""
    named = page.plain(filename)
    try:
        outcome = client.add_document(filename, data)["outcome"]
    except requests.exceptions.Timeout:
        # The api may have stored it: the answer is what never came.
        st.error(
            f"{named}: unknown, no answer in time. Check the Documents list "
            f"before uploading it again."
        )
        return {"File": filename, "Outcome": "unknown, no answer in time"}
    except requests.exceptions.RequestException as exc:
        # The reason for a 413 or 415 is in the response body.
        reason = refusal(exc)
        st.error(f"{named}: {reason}")
        return {"File": filename, "Outcome": f"refused: {reason}"}

    if outcome == "stored":
        st.success(f"{named}: stored.")
    else:
        st.info(f"{named}: {outcome.replace('_', ' ')} — already held.")
    return {"File": filename, "Outcome": outcome.replace("_", " ")}


page.render(view)
