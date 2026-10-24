"""`make doctor` warns when the checkout or the secrets file sits in a synced folder.

A sync client copies what it finds to a vendor's servers and to every device
signed in, and a secret in a checkout it watches goes with it. The check is by
path, so it needs no client installed and names no vendor's API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.doctor import synced


@pytest.mark.parametrize(
    "path",
    [
        "/Users/ana/Library/CloudStorage/OneDrive-Acme/Documents/Projects/qa",
        "/Users/ana/OneDrive/work/qa",
        "/home/bo/Dropbox/qa/.env",
        "/Users/ana/Library/Mobile Documents/com~apple~CloudDocs/qa",
        "/Users/ana/iCloud Drive/qa",
        "C:/Users/bo/OneDrive - Acme/qa",
    ],
)
def test_a_path_under_a_known_sync_root_is_flagged(path: str) -> None:
    """Whatever the vendor's own spelling of the folder."""
    assert synced(Path(path)) is not None


@pytest.mark.parametrize(
    "path",
    [
        "/srv/qa_generator",
        "/home/bo/work/qa",
        "/Users/ana/srv/qa/.env",
        "/etc/qa/secrets.env",
        "/opt/Dropboxer/qa",
    ],
)
def test_a_path_outside_every_sync_root_passes(path: str) -> None:
    """Including one that merely resembles a name."""
    assert synced(Path(path)) is None


def test_the_flag_names_the_folder_that_matched() -> None:
    """So the warning says which part of the path to move out of."""
    assert "OneDrive" in synced(Path("/Users/ana/OneDrive - Acme/qa"))
