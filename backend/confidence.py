"""How close an artefact came to the verdict that would have refused it.

Every gate in this pipeline that is a MEASUREMENT reads a number and
compares it to a threshold, and until now only the comparison survived. A
question 0.92 from an accepted twin and one 0.01 from it are both stored as
`accepted` against a 0.93 ceiling, and nothing anywhere says which of the
two a reviewer should look at first.

**This is not a probability and must not be read as one.** The readings are
on different scales - a cosine, an NLI head's entailment output, a share of
lemmas - and averaging them would invent a number none of them supports.
What is derived instead is the MARGIN: how far one reading sat from its own
threshold, as a share of the room it had on the safe side. That is a
comparable quantity because it is dimensionless, and the aggregate is the
SMALLEST of them, which answers the only question a single number honestly
can - what is the weakest thing about this row.

The room is measured to where the scale actually ends, which is what
`safe_end` carries. A cosine is the case that forces it: nothing an
embedder compares sits at 0, so a margin measured to 0 is a share of room
that was never there.

A gate that is a judgement rather than a measurement contributes nothing
here, and that is the point. `leaks_source` answered by a model is a yes or
a no with no number behind it; recording 1.0 for it would put a confidence
on an opinion. One that is worth keeping on the row anyway - `settles`,
whose verdict is what a reviewer of an unanswerable question needs - is
stored as an `opinion`: beside the readings, with no margin, and feeding no
confidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Measurement:
    """One gate's measurement, against the threshold it was read for.

    Attributes:
        gate: The gate that took it, named as `gates_ran` names it.
        value: What was measured, on that gate's own scale.
        threshold: The value at which the verdict changes.
        high_is_safe: Whether a HIGH reading is what keeps the artefact.
            The entailment rescue needs one; `near_duplicate` refuses one.
        safe_end: The reading a scale takes when it is as safe as it ever
            gets, or None for the end of the unit interval. A cosine from a
            trained embedder does not reach 0, so the room a
            `near_duplicate` reading has is the distance from its threshold
            to where unrelated questions sit and not to zero.
        opinion: Whether this is a model's verdict rather than a number a
            gate measured. Recorded with no margin, and left out of
            `confidence`.
        version: The prompt version an opinion was given under, or None.
            A rewritten prompt is a new judgement, and this is how a re-run
            tells the verdicts it still has to ask for from the ones it has.
        shadow: Whether this is a gate measured before it gates anything,
            stored so its bar can be set on real readings. Like an opinion,
            recorded with no margin and left out of `confidence`.
    """

    gate: str
    value: float
    threshold: float
    high_is_safe: bool = True
    safe_end: float | None = None
    opinion: bool = False
    version: str | None = None
    shadow: bool = False

    @property
    def _safest(self) -> float:
        """The reading this scale takes at its safe end."""
        if self.safe_end is not None:
            return self.safe_end
        return 1.0 if self.high_is_safe else 0.0

    @property
    def margin(self) -> float:
        """How much room this reading had, as a share of the room available.

        1.0 is as far from refusal as the scale allows, 0.0 is on the line
        or past it. Clamped at both ends: a rejected artefact has no
        negative confidence, it has none at all, and a threshold sitting on
        the safe end leaves no room to be a share of and yields 0.0 rather
        than a division by zero.
        """
        room = abs(self._safest - self.threshold)
        if room <= 0:
            return 0.0
        distance = (
            self.value - self.threshold
            if self.high_is_safe
            else self.threshold - self.value
        )
        return max(0.0, min(1.0, distance / room))

    def recorded(self) -> dict[str, Any]:
        """This reading as the JSON column stores it.

        `margin` is written out rather than left to be re-derived. Every
        reader of the column would otherwise need this module's arithmetic,
        including the ones that are SQL and the ones that are a dashboard.

        `high_is_safe` and `safe_end` are written for the same reason. A
        value of 0.88 is comfortable under one gate and refusing under
        another, and a reader that had to know which way each gate runs
        would be a second list of gates to keep in step with this one.

        An opinion carries no margin, and says it is one; a measurement's
        row is what it always was, so a recalibration rewrites none of them.
        """
        recorded: dict[str, Any] = {
            "gate": self.gate,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "margin": None if self.opinion or self.shadow else round(self.margin, 4),
            "high_is_safe": self.high_is_safe,
            "safe_end": round(self._safest, 4),
        }
        if self.opinion:
            recorded["opinion"] = True
        if self.shadow:
            recorded["shadow"] = True
        if self.version is not None:
            recorded["version"] = self.version
        return recorded


def scored(readings: Sequence[Measurement]) -> list[dict[str, Any]]:
    """Every reading as the column stores them, in the order they were taken."""
    return [one.recorded() for one in readings]


def confidence(readings: Sequence[Measurement]) -> float | None:
    """The weakest margin of the lot, or None when nothing was measured.

    None rather than 0.0, and the distinction is load-bearing: a question
    no measuring gate read is not a question that barely survived one. It
    is a question whose gates were all judgements or all free rules, and a
    column of zeroes would sort those to the top of every review queue.
    An opinion is left out for the same reason.
    """
    measured = [one.margin for one in readings if not one.opinion and not one.shadow]
    if not measured:
        return None
    return round(min(measured), 4)
