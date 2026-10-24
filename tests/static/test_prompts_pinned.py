"""Every prompt a stage writes with, pinned to its version.

Every prompt each stage's `catalogue()` records is pinned over all three
halves `_write` in `stages/prompts.py` calls drift: system prompt, user
template and response schema.

"Two prompts are two datasets" is what PROMPT_VERSION is for, and nothing
checked it: a rule could be added to `types.py`, every question written
after it would differ from every question written before, and both would
carry version 8.

So each prompt is pinned by digest. Changing one fails this file, and the
only way to make it pass is to bump PROMPT_VERSION and write the new digest
down - which is the decision the version exists to record.

The digest and not the text, because the prompts are eight hundred lines
and a copy of them here would be a second place for them to drift. Which
one moved is what the per-prompt entries say; `test_prompts_name_no_domain`
is what reads their content.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from question_generation.types import SPECS
from stages.prompts import Composed
from tests.static.prompt_catalogues import recorded

#: Every prompt a stage records, by service and name: its version, and the
#: digest over its system prompt, user template and response schema.
RECORDED = {
    ("questions", "aggregation"): ("30", "05c64939662d8799"),
    ("questions", "application"): ("30", "d3197697c15c6d16"),
    ("questions", "application (spans)"): ("30", "0729e72e91fa000c"),
    ("questions", "application (compound)"): ("30", "e8d148bb8aa2c759"),
    ("questions", "comparison"): ("30", "b2a0b0e6254e079b"),
    ("questions", "condition"): ("30", "68b86af3c0106a6b"),
    ("questions", "condition (spans)"): ("30", "ce61d3d329a1e153"),
    ("questions", "condition (compound)"): ("30", "721da6cca7e29125"),
    ("questions", "consequence"): ("30", "de97e7243226b3bd"),
    ("questions", "consequence (spans)"): ("30", "0ce4ab28a8a70673"),
    ("questions", "consequence (compound)"): ("30", "b5160fd866a1277e"),
    ("questions", "definition"): ("30", "08e4b8531e74c739"),
    ("questions", "definition (spans)"): ("30", "ccd30795b44713df"),
    ("questions", "definition (compound)"): ("30", "b517380ea3972e85"),
    ("questions", "entity"): ("30", "d0822e011aa597c2"),
    ("questions", "entity (spans)"): ("30", "0b0b8bb62d33f137"),
    ("questions", "entity (compound)"): ("30", "afbecf4f72ba2623"),
    ("questions", "enumeration"): ("30", "269ab35de4bffedc"),
    ("questions", "enumeration (spans)"): ("30", "4a4b7beceeeab655"),
    ("questions", "enumeration (compound)"): ("30", "1d744c6da1566422"),
    ("questions", "factoid"): ("30", "0622ab3cb3bec043"),
    ("questions", "factoid (spans)"): ("30", "03b8760aa6c69469"),
    ("questions", "factoid (compound)"): ("30", "824407c3b45ef9f6"),
    ("questions", "implication"): ("30", "294a907374dee3f2"),
    ("questions", "procedure"): ("30", "67d3e73e4b72cab8"),
    ("questions", "procedure (spans)"): ("30", "099ca65e44ca5afa"),
    ("questions", "procedure (compound)"): ("30", "2031ff4c1a7171f4"),
    ("questions", "reason"): ("30", "26e771e4ae823a83"),
    ("questions", "reason (spans)"): ("30", "e6917d52211aa63e"),
    ("questions", "reason (compound)"): ("30", "0eb46ae4c24875e3"),
    ("questions", "temporal"): ("30", "2e31d84f1085b18e"),
    ("questions", "perturb"): ("30", "359d04b108ea052c"),
    ("questions", "perturb (out-of-corpus)"): ("30", "86dcfea2f1783cd8"),
    ("questions", "perturb (false-presupposition)"): ("30", "55d51b915fbaea99"),
    ("questions", "perturb (underspecified)"): ("30", "3b1f4f246509023b"),
    ("questions", "perturb (nonsensical)"): ("30", "5162136703dde38e"),
    ("questions", "follow"): ("30", "a5bdef00784bc62b"),
    ("questions", "phrasing: source"): ("4", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("4", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("4", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("14", "90355c701e4dc229"),
    ("questions", "verifier: supported"): ("14", "878f2f66c9f02748"),
    ("questions", "verifier: computes"): ("14", "cb490a5be3baf6d9"),
    ("questions", "verifier: follows"): ("14", "81f7804379a4f105"),
    ("questions", "verifier: settles"): ("14", "bfd1104149fdfdf5"),
    ("questions", "verifier: same answer"): ("14", "054fa0307cf7bcd9"),
    ("questions", "verifier: stated"): ("2", "5e388e91b06b7d95"),
    ("extraction", "atomic"): ("13+cap4", "82954abf4910d65f"),
    ("extraction", "repair"): ("repair-2", "01e3f734f1925a77"),
    ("extraction", "digest"): ("6", "ccebbf3220c0bafc"),
    ("extraction", "bridge"): ("7", "d3d17a4c60f34db5"),
    ("topics", "label"): ("4", "32b83e6befac4427"),
    ("assessment", "fact: hallucination"): ("5", "217dc127c24eca3e"),
    ("assessment", "fact: relevance"): ("5", "b3b165b0643bfd61"),
    ("assessment", "fact: toxicity"): ("5", "4f05eef49868eaf3"),
    ("assessment", "topic: summarization"): ("5", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("5", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("5", "831dd4df69f31022"),
    ("assessment", "question: qa_correctness"): ("5", "2a52ed6638d5c514"),
    ("assessment", "question: refusal"): ("5", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("5", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("5", "eb392c185d32eb90"),
    ("assessment", "question: rubric"): ("5", "776bc49a00f540d4"),
}


#: The notes a refused draft is written again with, a kind's included, by
#: the writer's version: the writer reads them on every retry, and no
#: catalogue entry holds them.
NOTES = ("30", "c9c5397c7935ac07")


def halves(one: Composed) -> str:
    """One digest over the three halves `_write` compares."""
    schema = json.dumps(one.response_schema, sort_keys=True)
    return digest(f"{one.text}\0{one.user_text}\0{schema}")


def digest(text: str) -> str:
    """The first sixteen hex characters of one prompt's SHA-256."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize(("service", "name"), sorted(RECORDED))
def test_a_recorded_prompt_is_the_one_pinned_under_its_version(
    service: str, name: str
) -> None:
    """Any of the three halves moving under one version is drift."""
    key = (service, name)
    every = recorded()
    assert key in every, f"{key} is pinned here and no stage records it"

    version, pinned = RECORDED[key]
    assert every[key].version == version, (
        f"{key} is at version {every[key].version} and this file pins "
        f"{version}. Write the new version and digest here."
    )
    assert halves(every[key]) == pinned, (
        f"{key} changed under version {version}: its system prompt, user "
        f"template or response schema. Bump its module's PROMPT_VERSION and "
        f"write the new digest here."
    )


def test_every_prompt_a_stage_records_is_pinned() -> None:
    """A prompt added to a catalogue with no digest is one nothing watches."""
    found = set(recorded())

    assert found == set(RECORDED), (
        f"added: {sorted(found - set(RECORDED))}, gone: {sorted(set(RECORDED) - found)}"
    )


def test_the_shared_rules_reach_every_type() -> None:
    """One rule block, so two prompts cannot come to disagree.

    The pinning above would pass if `READS` were dropped from one type and
    that type's digest updated, which is the drift this is about.
    """
    for name, spec in SPECS.items():
        written = spec.system()
        assert "NEVER SAY WHERE THE ANSWER IS" in written, name
        assert "ONE question, ending in a question mark" in written, name
        assert "You write TWO answers" in written, name


def test_a_type_that_spans_is_told_to_span() -> None:
    """The row otherwise carries a spread the question never used."""
    for name, spec in SPECS.items():
        if spec.spans:
            assert "MORE THAN ONE PASSAGE" in spec.system(), name


def test_a_single_passage_type_is_told_to_span_only_when_the_sample_does() -> None:
    """A factoid drawn from two documents is a cross-document factoid."""
    factoid = SPECS["factoid"]

    assert "MORE THAN ONE PASSAGE" not in factoid.system()
    assert "MORE THAN ONE PASSAGE" in factoid.system(spans=True)


def test_the_retry_notes_are_the_ones_pinned_under_the_writers_version() -> None:
    """A note moving under one writer version is drift, as a prompt moving is."""
    from question_generation.service import _KIND_NOTES, _NOTES, _QUERY_NOTES
    from question_generation.types import PROMPT_VERSION

    version, pinned = NOTES
    notes = json.dumps([_NOTES, _QUERY_NOTES, _KIND_NOTES], sort_keys=True)

    assert PROMPT_VERSION == version, (
        f"the writer is at version {PROMPT_VERSION} and this file pins its notes "
        f"under {version}"
    )
    assert digest(notes) == pinned, (
        f"the retry notes moved under version {version}: bump PROMPT_VERSION and "
        f"pin {digest(notes)}"
    )
