"""A value outside a closed set a route accepts is refused, over HTTP.

Each set is a Literal, so the OpenAPI document lists what is accepted and a
typo answers 422 before any query: not an empty page, and not the column's
CHECK with a worse message. The snapshot records parameter names and not
the values they allow, so the refusals are held here.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

#: One value each closed set does not list, as (method, path, query, body).
REFUSED = [
    ("GET", "/assessment", {"kind": "passage"}, None),
    ("GET", "/facts", {"kind": "paragraph"}, None),
    ("GET", "/lineage/sentence/1", None, None),
    ("GET", "/questions", {"status": "acepted"}, None),
    ("PATCH", "/questions/999999", None, {"status": "approved"}),
    ("GET", "/settings/nonsense", None, None),
    ("POST", "/parsing/obliterate", None, None),
    ("POST", "/chunking/obliterate", None, None),
    ("POST", "/extraction/obliterate", None, None),
]


@pytest.mark.parametrize(
    ("method", "path", "params", "body"),
    REFUSED,
    ids=[f"{method} {path}" for method, path, *_ in REFUSED],
)
def test_a_value_no_closed_set_lists_is_refused(
    client, method, path, params, body
) -> None:
    """Whatever the database holds."""
    answered = client.request(method, path, params=params, json=body)

    assert answered.status_code == 422, answered.text
