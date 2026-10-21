"""Upload view. The ingestion service, and nothing else."""

from __future__ import annotations

import requests
import streamlit as st

from lib import backend, configure, page
from lib.backend.base import refusal
from lib.backend.upload import UploadApi


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

    if submitted and files:
        with st.spinner(f"Uploading {len(files)} file(s)…"):
            for uploaded in files:
                _report(uploaded.name, client, uploaded.getvalue())
    elif submitted:
        st.warning("Select at least one PDF.")

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


def _report(filename: str, client: UploadApi, data: bytes) -> None:
    """Uploads one file and shows what became of it."""
    named = page.plain(filename)
    try:
        outcome = client.add_document(filename, data)["outcome"]
    except requests.exceptions.RequestException as exc:
        # The reason for a 413 or 415 is in the response body.
        st.error(f"{named}: {refusal(exc)}")
        return

    if outcome == "stored":
        st.success(f"{named}: stored.")
    else:
        st.info(f"{named}: {outcome.replace('_', ' ')} — already held.")


page.render(view)
