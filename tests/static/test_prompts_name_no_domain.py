"""Every prompt is about nothing in particular, and stays that way.

The pipeline's one substantive claim about itself is that it is not bound to
a subject: the parser, the chunker and the topic model work over whatever the
documents say, and the thirteen question types are FORMS - a `comparison` is
askable of a contract, a manual or a report equally. Nothing in the code
decides what a corpus is about.

A prompt is where that claim is lost, and it is lost the same way every time.
Somebody debugs against the corpus at hand, finds a real question that the
gate got wrong, and pastes it in as a worked example - which is exactly what
extraction's own prompt warns about: an example drawn from the corpus at hand
teaches the model to expect it. It happened here. Four of `phrasing.py`'s
examples named the syllabi this deployment was pointed at, down to the
standard numbers, and `prompt_version` 2 recast them.

So every prompt each stage's catalogue records is checked, as it is sent,
against the vocabulary of the corpora this project has been aimed at. That
list is a REGRESSION GUARD and not a definition of what a domain is - there
is no such list. Point the pipeline at contracts and add the words a
contract is full of; the test earns its keep by failing when the next person
debugging a gate reaches for the nearest real example.

A failure names the prompt and the word.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.static.prompt_catalogues import recorded

ROOT = Path(__file__).resolve().parents[2]

#: Every code file whose strings reach a model, read as source by the
#: placeholder check below.
PROMPT_MODULES = (
    "backend/question_generation/types.py",
    "backend/question_generation/generation.py",
    "backend/question_generation/verifier.py",
    "backend/question_generation/phrasing.py",
    "backend/extraction/extractors/llm.py",
    "backend/extraction/extractors/bridge.py",
    "backend/extraction/extractors/digest.py",
    "backend/topic_modelling/labels.py",
    "backend/assessment/templates.py",
)

#: Modules whose templates are filled in one loop rather than one
#: `.replace` per placeholder. The placeholder check below counts a name
#: twice and cannot apply to them; each declares the fields its templates
#: take and raises when one is missing, which is the same guarantee made
#: where the substitution actually happens.
RENDERED_GENERICALLY = frozenset({"backend/assessment/templates.py"})

#: What the corpora this deployment has been aimed at are about. Lower-case,
#: matched as a substring, and deliberately short: these are the words a
#: person reaching for a real example would bring with them.
#:
#: Two corpora so far - software-testing syllabi and a regulatory set - and
#: the German compounds are why a substring match is right here. `Lehrplan`
#: is the leak whether it arrives as `Lehrplaninhalt` or `Lehrplänen`.
SUBJECTS = (
    # The software-testing syllabi
    "lehrplan",
    "lehrplän",
    "iso/iec",
    "ieee",
    "ctfl",
    "ctal",
    "testteam",
    "teststufe",
    "testfall",
    "fehlerzustand",
    "überdeckung",
    "skripterstellung",
    "softwaretest",
    "black-box",
    "white-box",
    "wcag",
    # The regulatory set
    "bafin",
    "kryptowert",
    "anlassprüfung",
    "arbeitslosenquote",
    "liquiditätsmanagement",
    "bankensektor",
)


#: What a placeholder in a prompt template looks like.
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


@pytest.mark.parametrize("module", PROMPT_MODULES)
def test_every_placeholder_in_a_prompt_is_filled_in_the_same_module(
    module: str,
) -> None:
    """A template variable nobody substitutes reaches the model as itself.

    Skipped for the modules that substitute GENERICALLY rather than one
    `.replace` per name. The check below counts a name twice - once in the
    template and once where the call fills it - and a module that renders
    every placeholder in one loop writes each name once by construction.
    Those declare the fields each template takes and refuse to render
    without them, which is the same property checked at run time and
    against the query that supplies the values; see
    `tests/unit/assessment/test_templates.py`.

    The user half of every prompt is held as a TEMPLATE, so the row records
    what a version asked for rather than the passages one call happened to
    carry. The cost of that is a new way to be wrong: add `{{pointers}}` to
    a template, forget the `.replace`, and the model is sent the braces
    themselves with no error anywhere and an answer that looks fine.

    Each placeholder is written twice - once in the template, once where the
    call fills it - and both are in the module that sends the prompt. So a
    name that appears once is the one nobody substitutes.
    """
    if module in RENDERED_GENERICALLY:
        pytest.skip(f"{module} declares its fields and checks them when rendering")
    source = (ROOT / module).read_text(encoding="utf-8")
    once = [
        name
        for name in sorted(set(PLACEHOLDER.findall(source)))
        if source.count("{{" + name + "}}") < 2
    ]

    assert not once, (
        f"{module} names {once} in a prompt template and substitutes nothing "
        f"for it, so the model is sent the braces themselves"
    )


#: Every prompt each stage's catalogue records, by service and name.
CATALOGUED = recorded()


@pytest.mark.parametrize(("service", "name"), sorted(CATALOGUED))
def test_no_catalogued_prompt_names_what_a_corpus_is_about(
    service: str, name: str
) -> None:
    """Its system prompt, user template and response schema, as sent."""
    one = CATALOGUED[(service, name)]
    sent = "\n".join(
        (one.text, one.user_text, json.dumps(one.response_schema, ensure_ascii=False))
    ).casefold()
    guilty = [subject for subject in SUBJECTS if subject in sent]

    assert not guilty, (
        f"{service}/{name} names {guilty}. Recast it into the neutral domain "
        f"the other examples use and bump its module's PROMPT_VERSION."
    )


#: The lemma lists a new language has to be added to, and the README section
#: that is supposed to name all of them.
LEMMA_LISTS = {
    "backend/question_generation/gates.py": (
        "_DIVISIONS",
        "_NORMATIVE",
        "_DOCUMENTS",
        "_ATTRIBUTIONS",
        "_AGENTS",
    ),
    "backend/nlp/analysis.py": ("_ANAPHORIC",),
}

ONBOARDING = ROOT / "backend/nlp/README.md"


def test_every_lemma_list_is_named_in_the_onboarding_guide() -> None:
    """A list nobody is told about is a gate that silently never fires.

    Most readings here are Universal Dependencies features and need no edit
    for a new language. The handful that are WORDS do, and a language
    missing from one of them gets no error and no log - just a judgement
    nothing makes. So the guide has to name all of them, and this is what
    says it still does.
    """
    guide = ONBOARDING.read_text(encoding="utf-8")
    missing = [
        f"{name} in {module}"
        for module, names in LEMMA_LISTS.items()
        for name in names
        if name not in guide
    ]

    assert not missing, (
        "these lemma lists are not named in "
        "backend/nlp/README.md#adding-a-language:\n  " + "\n  ".join(missing)
    )


def test_the_guide_names_no_list_that_has_been_deleted() -> None:
    """The other direction: a guide naming a list nothing holds is stale.

    Read off the guide's own table, where `same` is the module above.
    """
    named: dict[str, Path] = {}
    where = None
    for name, place in re.findall(
        r"^\| `(_[A-Z_]+)` \| (.+?) \|", ONBOARDING.read_text(), re.MULTILINE
    ):
        linked = re.search(r"\]\(([^)]+)\)", place)
        where = (ONBOARDING.parent / linked[1]).resolve() if linked else where
        assert where is not None, f"{name} names no module"
        named[name] = where

    stale = [
        f"{name} in {path.name}"
        for name, path in named.items()
        if not re.search(rf"^{name}\b", path.read_text(), re.MULTILINE)
    ]

    assert named, "the guide's table of lists was not found"
    assert not stale, f"named but no longer defined: {stale}"
