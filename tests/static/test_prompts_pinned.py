"""Every prompt a stage writes with, pinned to its version.

Question generation and the judge. The two are held the same way and for
the same reason, and they are here together because a reader looking for
"what stops a prompt moving under a fixed version" should find one file.

Every prompt each stage's `catalogue()` records - extraction's and the
topic labeller's too - is also pinned over all three halves `_write` in
`stages/prompts.py` calls drift: system prompt, user template and response
schema.


"Two prompts are two datasets" is what PROMPT_VERSION is for, and nothing
checked it: a rule could be added to `types.py`, every question written
after it would differ from every question written before, and both would
carry version 8.

So each prompt is pinned by digest. Changing one fails this file, and the
only way to make it pass is to bump PROMPT_VERSION and write the new digest
down - which is the decision the version exists to record.

The digest and not the text, because the prompts are eight hundred lines
and a copy of them here would be a second place for them to drift. Which
one moved is what the per-type entries say; `test_prompts_name_no_domain`
is what reads their content.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from assessment import prompts as assessment
from assessment.templates import PROMPT_VERSION as JUDGE_VERSION
from assessment.templates import TEMPLATES
from extraction import prompts as extraction
from question_generation import phrasing, verifier
from question_generation import prompts as questions
from question_generation.generation import _FOLLOW, _PERTURB
from question_generation.types import PROMPT_VERSION, SPECS
from stages.prompts import Composed
from topic_modelling import prompts as topics

#: The version every digest below was taken under.
VERSION = "11"

#: The prompts of the two gates that are not the writer's, each pinned to
#: its own module's PROMPT_VERSION. They were unpinned and the verifier was
#: unversioned until a gate verdict had to say which prompt reached it - and
#: an unpinned prompt is exactly the drift the writer's pinning exists to
#: stop, so all three are held the same way now.
GATES = {
    "phrasing": (
        phrasing,
        "3",
        {
            "source": phrasing._SOURCE,
            "names": phrasing._NAMES,
            "contained": phrasing._CONTAINED,
        },
    ),
    "verifier": (
        verifier,
        "2",
        {
            "verify": verifier._VERIFY,
            "support": verifier._SUPPORT,
            "computes": verifier._COMPUTES,
            "follows": verifier._FOLLOWS,
        },
    ),
}

#: Each gate prompt's digest, under its module's version above.
GATE_PROMPTS = {
    "source": "867ffe8a2658a4cd",
    # Unpinned until now, and unrecorded with it: `_NAMES` is the third
    # phrasing judgement and both this file and the catalogue knew of two.
    "names": "1e20e3cb47a06b42",
    "contained": "e1ecbfc515b009c2",
    "verify": "5ff0d4c7dca5f205",
    "support": "9e809a5e0c9f0395",
    "computes": "48ee508c865b8c53",
    "follows": "f1f9cef0e0db1194",
}

#: Each type's whole system prompt: the shared role, steps, context and
#: format rules, the answer form, and its own guidance and worked example.
TYPES = {
    "aggregation": "fdd5e04bd6498b60",
    "application": "b117f77a12d7c48b",
    "comparison": "b830d07a45e28b0e",
    "condition": "5aa6a7bfa2b47d63",
    "consequence": "cb040e89c09dd27a",
    "definition": "3611bc6e84479fe3",
    "entity": "3ed7e7ffa7b302f1",
    "enumeration": "815f03137711aa29",
    "factoid": "197f849c62c1a2b6",
    "implication": "8f28c60b01012c1e",
    "procedure": "7a9ee6f977f5b75c",
    "reason": "4f95746de48aa871",
    "temporal": "0cd864fbf29687b0",
}

#: The two prompts that are not a type's: the perturbation that writes the
#: unanswerable questions, and the one that writes the next turn.
OTHERS = {
    "perturb": "5e529d86b898c767",
    "follow": "7a0b084fee6bea7e",
}

#: The version the judging templates below were taken under.
JUDGE = "2"

#: What the judge asks, by kind and metric - the names `assessment/prompts.py`
#: records and Phoenix shows, so a failure here names the same prompt the
#: table and the Evaluations view do.
#:
#: One version over all eleven, unlike the question types above. The
#: judge's PROMPT_VERSION covers the SET a kind is asked as well as the
#: wording of each template, because a row's verdicts are read against
#: both - which is why the pinning below checks the names too, and not
#: only the texts.
JUDGEMENTS = {
    "fact: hallucination": "434e71c9f4e1da52",
    "fact: relevance": "1f07d89037187981",
    "fact: toxicity": "8aa7cbe4c3ec5524",
    "topic: summarization": "34433bc756e189cd",
    "topic: relevance": "6041b3bd157b74c5",
    "question: hallucination": "627af3102475c8a9",
    "question: qa_correctness": "09445b11658c776d",
    "question: relevance": "2b28fc01a2f3a234",
    "question: refusal": "b90c67879cbadc36",
    "question: conciseness": "dbd2e6340ac0f180",
    "question: toxicity": "7416cf020159f9ec",
}

#: Every prompt a stage records, by service and name: its version, and the
#: digest over its system prompt, user template and response schema.
RECORDED = {
    ("questions", "aggregation"): ("11", "05970b20ebc3eb32"),
    ("questions", "application"): ("11", "de838bf56ffe48c3"),
    ("questions", "application (spans)"): ("11", "ff2011a6799ef52b"),
    ("questions", "comparison"): ("11", "118a27b27e54e3bb"),
    ("questions", "condition"): ("11", "d9c1eff02c508bbb"),
    ("questions", "condition (spans)"): ("11", "614e78fa87ce3ed7"),
    ("questions", "consequence"): ("11", "f52d3250507bbf7b"),
    ("questions", "consequence (spans)"): ("11", "a87744c064b750f2"),
    ("questions", "definition"): ("11", "1cd1dc1ef6024051"),
    ("questions", "definition (spans)"): ("11", "1deca374169f41ea"),
    ("questions", "entity"): ("11", "51f242a8d6080e9c"),
    ("questions", "entity (spans)"): ("11", "27f449c2ea4152ae"),
    ("questions", "enumeration"): ("11", "acd1abeb5d2a6a2a"),
    ("questions", "enumeration (spans)"): ("11", "2ecb00f7256dda47"),
    ("questions", "factoid"): ("11", "6009903fc261a5f4"),
    ("questions", "factoid (spans)"): ("11", "75cc36d1ddb6b854"),
    ("questions", "implication"): ("11", "d7a8cd6ec96b040c"),
    ("questions", "procedure"): ("11", "1bc9d1555c1185f2"),
    ("questions", "procedure (spans)"): ("11", "64d3f6e02fe71e8f"),
    ("questions", "reason"): ("11", "e80b0159ce9b2e70"),
    ("questions", "reason (spans)"): ("11", "39909223579093fe"),
    ("questions", "temporal"): ("11", "2bee1f3623741873"),
    ("questions", "perturb"): ("11", "b2f73048094e4f8c"),
    ("questions", "follow"): ("11", "71e82cb87e9cbabc"),
    ("questions", "phrasing: source"): ("3", "8feff436a4b70d4d"),
    ("questions", "phrasing: names something"): ("3", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("3", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("2", "3b55c01d7aa9e2b4"),
    ("questions", "verifier: supported"): ("2", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("2", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("2", "9941c681a2936bc1"),
    ("extraction", "atomic"): ("9+cap4", "c25cb9725eac75db"),
    ("extraction", "digest"): ("3", "f7003be75e42b82e"),
    ("extraction", "bridge"): ("4", "d93f5daae44104bb"),
    ("topics", "label"): ("1", "744885b5f08d5066"),
    ("assessment", "fact: hallucination"): ("2", "ab72d40652bc51c4"),
    ("assessment", "fact: relevance"): ("2", "3a8b74aeaeb83dc5"),
    ("assessment", "fact: toxicity"): ("2", "dba712835cd5db91"),
    ("assessment", "topic: summarization"): ("2", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("2", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("2", "3e9a0ea18c9eb0b1"),
    ("assessment", "question: qa_correctness"): ("2", "145aae25f81d7438"),
    ("assessment", "question: relevance"): ("2", "7c844240bd726f6d"),
    ("assessment", "question: refusal"): ("2", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("2", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("2", "eb392c185d32eb90"),
}


def recorded() -> dict[tuple[str, str], Composed]:
    """Every prompt each stage's catalogue records, by service and name.

    Extraction's under a cap, so the paragraph a cap appends is pinned too.
    """
    return {
        (service, one.name): one
        for service, held in (
            (questions.SERVICE, questions.catalogue()),
            (extraction.SERVICE, extraction.catalogue(4)),
            (topics.SERVICE, topics.catalogue()),
            (assessment.SERVICE, assessment.catalogue()),
        )
        for one in held
    }


def halves(one: Composed) -> str:
    """One digest over the three halves `_write` compares."""
    schema = json.dumps(one.response_schema, sort_keys=True)
    return digest(f"{one.text}\0{one.user_text}\0{schema}")


def judgements() -> dict[str, str]:
    """Every judging template's system prompt, by the name it is pinned under."""
    return {
        f"{kind}: {one.metric}": one.system
        for kind, group in TEMPLATES.items()
        for one in group
    }


def digest(text: str) -> str:
    """The first sixteen hex characters of one prompt's SHA-256."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def test_the_version_pinned_here_is_the_one_the_code_declares() -> None:
    """Bumping one and not the other leaves the pinning meaningless."""
    assert PROMPT_VERSION == VERSION, (
        f"PROMPT_VERSION is {PROMPT_VERSION} and this file pins {VERSION}. "
        f"Update VERSION and the digests below in the same commit."
    )


@pytest.mark.parametrize("name", sorted(TYPES))
def test_a_type_writes_the_prompt_it_was_pinned_with(name: str) -> None:
    """A rule added to one type changes what that type's questions are."""
    assert digest(SPECS[name].system()) == TYPES[name], (
        f"the {name} prompt changed. Bump PROMPT_VERSION and write the new "
        f"digest here: questions written before and after are two datasets."
    )


@pytest.mark.parametrize(("name", "text"), [("perturb", _PERTURB), ("follow", _FOLLOW)])
def test_the_prompts_that_are_not_a_type_are_pinned_too(name: str, text: str) -> None:
    """The unanswerable share and the follow-ups are written by these."""
    assert digest(text) == OTHERS[name], (
        f"the {name} prompt changed. Bump PROMPT_VERSION and write the new digest here."
    )


@pytest.mark.parametrize("gate", sorted(GATES))
def test_a_gate_declares_the_version_pinned_here(gate: str) -> None:
    """Bumping one and not the other leaves the pinning meaningless."""
    module, version, _ = GATES[gate]
    assert module.PROMPT_VERSION == version, (
        f"{gate}'s PROMPT_VERSION is {module.PROMPT_VERSION} and this file "
        f"pins {version}. Update both in the same commit."
    )


@pytest.mark.parametrize(
    ("name", "text"),
    [
        (name, text)
        for _, _, prompts in GATES.values()
        for name, text in prompts.items()
    ],
)
def test_a_gate_asks_what_it_was_pinned_asking(name: str, text: str) -> None:
    """A gate's prompt moving is a gate that judges something else.

    The verdict on a question names the gate and the prompt version that
    reached it. Editing the prompt under a fixed version makes those two
    records disagree about what was judged.
    """
    assert digest(text) == GATE_PROMPTS[name], (
        f"the {name} prompt changed. Bump its module's PROMPT_VERSION and "
        f"write the new digest here."
    )


def test_every_type_the_mix_can_name_is_pinned() -> None:
    """A type added with no digest would be a prompt nothing watches."""
    assert set(SPECS) == set(TYPES), (
        "a question type was added or removed without pinning its prompt"
    )


def test_the_judge_declares_the_version_pinned_here() -> None:
    """Bumping one and not the other leaves the pinning meaningless."""
    assert JUDGE_VERSION == JUDGE, (
        f"assessment's PROMPT_VERSION is {JUDGE_VERSION} and this file pins "
        f"{JUDGE}. Update JUDGE and the digests below in the same commit."
    )


@pytest.mark.parametrize("name", sorted(JUDGEMENTS))
def test_a_judgement_asks_what_it_was_pinned_asking(name: str) -> None:
    """A verdict names a template version, and the row outlives the source.

    An edited template under a fixed version makes a corpus judged before
    it and one judged after it the same seven columns, with nothing saying
    they were asked different questions.
    """
    every = judgements()
    assert name in every, f"{name} is pinned here and is no longer a template"

    assert digest(every[name]) == JUDGEMENTS[name], (
        f"the {name} template changed. Bump assessment's PROMPT_VERSION and "
        f"write the new digest here."
    )


def test_every_judgement_the_judge_can_ask_is_pinned() -> None:
    """The SET, because the version covers which metrics a kind is asked.

    Version 2 is version 1 plus toxicity, conciseness and refusal. Adding a
    fourth without bumping it would leave two corpora carrying different
    metrics under one version, which no pinning of the texts alone catches.
    """
    assert set(judgements()) == set(JUDGEMENTS), (
        "a judging template was added or removed without pinning it"
    )


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
