"""A store error that is not "no such object" is raised, never read as absence.

Absence decides what happens next: a missing file is re-uploaded, a missing
bucket is made, a missing archive copy means nothing to give back. Reading a
refused permission or a server fault as absence would act on a guess.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from blob_store.s3.client import S3Store


class Refusing:
    """A client whose every call fails with one S3 error code."""

    def __init__(self, code: str) -> None:
        self.code = code

    def _fail(self, **_):
        raise ClientError({"Error": {"Code": self.code}}, "Op")

    get_object = head_object = copy_object = head_bucket = _fail


def calls(store: S3Store):
    """Each read that answers absence, by name."""
    return {
        "get": lambda: store.get("documents", "qa_x/ab12.pdf"),
        "exists": lambda: store.exists("documents", "qa_x/ab12.pdf"),
        "copy": lambda: store.copy("documents", "qa_x/ab12.pdf", "archive", "k"),
        "has_bucket": lambda: store.has_bucket("documents"),
    }


@pytest.mark.parametrize("call", ["get", "exists", "copy", "has_bucket"])
@pytest.mark.parametrize("code", ["AccessDenied", "InternalError", "SlowDown"])
def test_a_refusal_or_fault_is_raised_not_read_as_absent(call: str, code: str) -> None:
    """Each read that answers "absent" on 404 raises on anything else."""
    with pytest.raises(ClientError) as raised:
        calls(S3Store(Refusing(code)))[call]()
    assert raised.value.response["Error"]["Code"] == code


@pytest.mark.parametrize(
    ("call", "absent"),
    [("get", None), ("exists", False), ("copy", False), ("has_bucket", False)],
)
def test_no_such_object_is_read_as_absent(call: str, absent) -> None:
    """The counterpart: a 404 is the answer "not there", not an error."""
    assert calls(S3Store(Refusing("404")))[call]() is absent
