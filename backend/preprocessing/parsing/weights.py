"""Downloads Docling's weights into the Hugging Face cache.

parse-worker reads them from the `models` volume with the hub offline, so
nothing it runs can fetch them. `make install` runs this in a container that
mounts the same volume and can reach the hub.
"""

from __future__ import annotations

from preprocessing.parsing.config import Settings
from preprocessing.parsing.factory import pdf_pipeline


def main() -> int:
    """Builds the converter parsing uses, which fetches what it loads.

    The settings come from the environment alone: the stack need not be up,
    and neither table mode nor the heading hierarchy changes which weights
    are loaded.

    Returns:
        The process exit code.
    """
    pdf_pipeline(Settings.load()).fetch_weights()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
