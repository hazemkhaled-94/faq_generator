"""The settings the frontend reads out of its environment."""

from __future__ import annotations

import os

#: The one address the frontend holds. The database, the object store and the
#: pipeline stages all live behind it.
BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")


def _integer(name: str) -> int:
    """Reads a required whole number, naming it when it is missing.

    Raises:
        RuntimeError: If it is unset, empty, or not a whole number.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise RuntimeError(
            f"{name} must be set for the frontend. It comes from "
            f"configs/env/deployment.env and has to be listed in the streamlit "
            f"service's environment in compose.yaml - being in that file alone "
            f"is not enough."
        )
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name}={raw!r} is not a whole number") from None


#: The most rows a listing route returns: the API's own PAGE_MAX, copied
#: because this image carries no backend, and held to it by a static test.
PAGE_MAX = 500

#: The longest search a listing route takes, the API's SEARCH_MAX, copied
#: and held the same way.
SEARCH_MAX = 200

#: The longest topic label PATCH /topics takes, past which it refuses the
#: whole save; copied and held the same way.
LABEL_MAX = 120

#: The most files, and the most bytes in all, one selection on the Upload
#: page may hold. The browser session keeps every file whole and the page
#: sends them one request at a time; past this, `make ingest DIR=` loads a
#: directory from the host. Plain numbers, not settings: the API's own limit
#: is per file, and this is a limit of the page.
UPLOAD_MAX_FILES = 20
UPLOAD_MAX_BYTES = 200 * 1024 * 1024

#: Rows per page in the listings.
PAGE_SIZE = _integer("PAGE_SIZE")
if not 1 <= PAGE_SIZE <= PAGE_MAX:
    raise RuntimeError(
        f"PAGE_SIZE={PAGE_SIZE} must be between 1 and {PAGE_MAX}, the most a "
        f"listing route returns"
    )

#: Where a BROWSER reaches Phoenix, for the link from a question to the
#: trace that produced it. The host's address and not the container's,
#: because nothing here calls it - the address is written into a link and
#: followed by whoever is reading the page.
#:
#: Optional, unlike everything above. A deployment that publishes no
#: Phoenix shows the trace id as text, which is still enough to find it by
#: hand, and an unfollowable link is worse than none.
PHOENIX_BASE_URL = os.environ.get("PHOENIX_BASE_URL", "").strip().rstrip("/")
