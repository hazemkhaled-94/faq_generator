"""Filling a prompt template's placeholders."""

from __future__ import annotations

import re
from collections.abc import Mapping

#: What a placeholder in a prompt template looks like.
_PLACEHOLDER = re.compile(r"\{\{\w+\}\}")


def fill(template: str, values: Mapping[str, str]) -> str:
    """The template with every placeholder `values` names replaced, in one pass.

    Keyed by the placeholder as written, `{{name}}`. One pass, so a value
    carrying a placeholder of its own is left as it is.
    """
    return _PLACEHOLDER.sub(lambda found: values.get(found[0], found[0]), template)
