"""Every prompt this pipeline sends is RASCEF, and says so in its headings.

Role, Action, Steps, Context, Examples, Format. Twenty-five prompts across
five services were written to that shape and nothing held them to it: a
prompt is a string, and a rule added to one in a hurry goes wherever the
cursor was. A missing FORMAT is the one that bites - a model given no
answer shape invents one, and the client retries it into a
`ModelUnavailable` that reads as the model being down.

The headings are checked, not the content. What a prompt SAYS is
`test_prompts_name_no_domain` and `test_prompts_pinned`; this is only that
the six sections are there to say it in.

Composed rather than as written. `_FOLLOW` carries no EXAMPLES of its own:
its worked example arrives with the type, through `{{type}}`, and checking
the template would report a gap that no call ever has.
"""

from __future__ import annotations

import pytest

from question_generation.generation import _typed
from question_generation.types import SPECS
from tests.static.prompt_catalogues import recorded

#: The six sections, each its own line, in the order RASCEF names them.
SECTIONS = ("ROLE", "ACTION", "STEPS", "CONTEXT", "EXAMPLES", "FORMAT")

#: Every system prompt each stage's catalogue records. `follow`'s example
#: comes with the type, through `{{type}}`, so one type stands for all
#: thirteen.
CATALOGUED = {
    f"catalogue/{service}/{name}": one.text.replace(
        "{{type}}", _typed(SPECS["condition"])
    )
    for (service, name), one in recorded().items()
}


@pytest.mark.parametrize("name", sorted(CATALOGUED))
def test_a_prompt_carries_every_rascef_section(name: str) -> None:
    """A section missing is a section the model was never given."""
    text = f"\n{CATALOGUED[name]}"
    missing = [one for one in SECTIONS if f"\n{one}\n" not in text]

    assert not missing, (
        f"{name} is missing {', '.join(missing)}. Every prompt here is "
        f"RASCEF: {', '.join(SECTIONS)}, each on a line of its own."
    )


@pytest.mark.parametrize("name", sorted(CATALOGUED))
def test_the_sections_come_in_the_order_rascef_names_them(name: str) -> None:
    """A FORMAT above its STEPS reads as two prompts spliced together."""
    text = f"\n{CATALOGUED[name]}"
    at = [text.index(f"\n{one}\n") for one in SECTIONS]

    assert at == sorted(at), (
        f"{name} puts its sections in the order "
        f"{', '.join(one for _, one in sorted(zip(at, SECTIONS, strict=True)))}, and "
        f"RASCEF is {', '.join(SECTIONS)}."
    )
