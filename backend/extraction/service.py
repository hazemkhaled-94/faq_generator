"""The extraction flow: claim, skip what asserts nothing, read, check, store."""

from __future__ import annotations

import logging
import re
from collections import Counter, deque
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import ClassVar, NamedTuple

from sqlalchemy import ARRAY, BigInteger, any_, bindparam
from sqlalchemy.exc import IntegrityError

from confidence import Measurement, confidence, scored
from database.qa_generator import FactKind, Passage, Rejection
from database.qa_generator.passages import headings_of
from extraction.extractors import (
    BridgeExtractor,
    DigestExtractor,
    ExtractionFailed,
    Extractor,
    ExtractorRegistry,
    LlmExtractor,
)
from extraction.links import Link, linked
from extraction.models import (
    CheckedFact,
    PassageToExtract,
    Refused,
    Twin,
    from_repair,
)
from extraction.repository import DIGEST_FAILED, DigestQueue, FactCatalog, PassageQueue
from extraction.validation import WRITTEN, FactChecker, _cited_text
from nlp.analysis import AMOUNT_WORDS, claim, normalised, numbers
from nlp.embedding import Embedder, cosine
from settings.runs import run_id
from stages import StageService
from stages.service import STOP_AFTER, is_outage, stop_at_cap
from telemetry import tracer, working
from telemetry.evaluations import Evaluations, Verdict, current_ids

log = logging.getLogger(__name__)
span = tracer(__name__)

#: What a fact that passed every rule its kind faces is labelled.
_VALIDATED = "validated"

#: How many re-judged facts to write at once.
_REJUDGE_BATCH = 500

#: How many claims a passage must carry before a digest is asked for.
_DIGESTIBLE = 2

#: How much of a reason the note keeps.
_NOTE_CHARS = 500

#: How many readable passages the drain looks back over for a model that
#: answers nothing, and how many of them it takes to stop. A model that
#: works finds claims in almost every passage it is shown, and one that
#: answers empty finds none, so any window from 30 to 70 and any share from a
#: third to two thirds tells them apart.
_WINDOW = 50
_EMPTY_STOP = _WINDOW // 2


class _Read(NamedTuple):
    """What reading one passage produced."""

    facts: list[CheckedFact]
    #: What the passage lacks: the note a digest that could not be had leaves.
    note: str | None
    #: True when a model read it and proposed nothing, False when one read it
    #: and proposed something, None when no model was asked.
    silent: bool | None


def revalidate(
    catalog: FactCatalog,
    checker: FactChecker,
    within=None,
    *,
    threshold: float = 0.0,
    cap: int | None = None,
) -> int:
    """Judges every stored fact again, without calling the model.

    A refusal the checks now validate was never probed for a twin - a fact
    a check refused is not - nor counted against the cap. So once every
    other verdict is written, each one is probed as `dedup` probes a
    refusal, in id order, so that one validated earlier in the pass is a
    twin for the ones after it, and refused as a duplicate where a twin
    reaches `threshold`. Then the passages of the ones that stay validated,
    and no others, are re-capped.

    Args:
        catalog: Where the facts are read from and written back to.
        checker: What judges them, holding the shares this configuration
            sets. Passed rather than built here, as the bridge pass already
            does: built here it would read the process environment, and a
            deployment that changed EXTRACTION_DIGEST_MAX_SHARE through
            /settings stores the new value rather than exporting it - so a
            digest would be re-judged against the file while the fact was
            stamped with the stored configuration's version.
        within: A condition narrowing which facts are re-judged, or None for
            all of them.
        threshold: EXTRACTION_DUPLICATE_COSINE. 0 probes nothing.
        cap: The cap the passages of the refusals it validates are re-capped
            to, as `recap` takes it.

    Returns:
        How many facts were written back.
    """
    verdicts: list[tuple[int, CheckedFact]] = []
    flipped: list[tuple[Refused, CheckedFact]] = []
    written = 0

    def flush() -> None:
        """Writes what has piled up, holding back the refusals it validates."""
        nonlocal written
        refused = {
            one.fact_id: one
            for one in catalog.refused(
                [fact_id for fact_id, checked in verdicts if checked.validated]
            )
        }
        flipped.extend(
            (refused[fact_id], checked)
            for fact_id, checked in verdicts
            if fact_id in refused
        )
        written += catalog.rejudge(
            [
                (fact_id, checked)
                for fact_id, checked in verdicts
                if fact_id not in refused
            ]
        )
        verdicts.clear()

    skipped = 0
    for fact_id, passages, candidate, method in catalog.judged(within):
        if _uncitable(candidate):
            skipped += 1
            continue
        verdicts.append((fact_id, _rejudge(checker, passages, candidate, method)))
        if len(verdicts) >= _REJUDGE_BATCH:
            flush()
    flush()
    moved: set[int] = set()
    twins = 0
    for refused, checked in flipped:
        twin = _twin(catalog, refused) if threshold > 0 else None
        if twin is not None and twin.similarity >= threshold:
            checked = _duplicate(checked, twin, threshold)
            twins += 1
        else:
            moved.add(refused.passage_id)
        # One at a time, so the next probe finds it.
        written += catalog.rejudge([(refused.fact_id, checked)])
    log.info("re-judged %d fact(s)", written)
    if flipped:
        log.info(
            "validated %d stored refusal(s); %d of them repeat a validated fact "
            "and are refused as duplicates",
            len(flipped),
            twins,
        )
    if moved:
        recap(catalog, cap, _among(moved))
    if skipped:
        log.warning(
            "left %d fact(s) alone: their citation resolved to no sentence, so "
            "there is nothing to judge them against and re-judging would "
            "overwrite the only record of what they cited. A bridge among them "
            "was drawn before the prompt recorded its sentences; run --bridge "
            "to replace those.",
            skipped,
        )
    return written


#: How many rows one backfill batch embeds. The forward pass is the cost and
#: it is per batch, not per row.
_EMBED_BATCH = 64


def for_passage(text: str) -> str:
    """A passage's text, as both paths that embed one prepare it."""
    return normalised(text)


def for_statement(text: str) -> str:
    """A fact's statement, as both paths that embed one prepare it.

    As written, and the identity is the point. What matters is not which
    of the two preparations is better but that the two WRITERS of one
    column agree: `_deduplicated` embedded the statement as it stands and
    this backfill folded it, so `facts.embedding` held vectors of two
    different texts - `normalised` case-folds, and a German statement
    casefolded is not the string the model was given at extraction time.
    The dedup gate then compared a raw candidate against a mixture, and so
    did `selection.meets` when it paired two facts for one sample.

    Unfolded rather than folded because the live path is what wrote almost
    every row: a corpus re-levelled the other way would have to be
    re-embedded whole. `make extract-embed` after clearing the column is
    what does that if a deployment wants the other convention.
    """
    return text


def embed(catalog: FactCatalog, embedder: Embedder, within=None) -> int:
    """Writes the vectors onto passages and facts already stored.

    The replay for this gate, as `recap` is for the cap: it calls no served
    model, because a vector is read off a statement that is already written.
    What it does not do is apply the gate - a fact stored before the column
    existed was accepted, and refusing it now would rewrite a verdict the
    corpus was measured under. Re-extract to have it judged.

    Args:
        catalog: Where the rows are read and written.
        embedder: The model the vectors come from.
        within: A condition narrowing which rows are read, or None.

    Returns:
        How many rows were embedded, passages and facts together.
    """
    done = 0
    for read, write, prepare in (
        (catalog.unembedded_passages, catalog.embed_passages, for_passage),
        (catalog.unembedded, catalog.embed_facts, for_statement),
    ):
        while batch := read(_EMBED_BATCH, within):
            vectors = embedder.embed_all([prepare(text) for _, text in batch])
            done += write(
                [(row, vector) for (row, _), vector in zip(batch, vectors, strict=True)]
            )
            log.info("embedded %d row(s)", done)
    return done


def _over_cap_reason(cap: int | None) -> str:
    """Why an atomic fact is over the cap, as a recap and a read in flight both write it."""
    return (
        f"the passage yielded more atomic facts than it has room for - its own "
        f"sentences and list items, or the {cap} EXTRACTION_MIN_OTHER_SHARE leaves "
        f"room for where that is more - and the ones asserting a number, a date "
        f"or a name were kept ahead of it"
    )


def recap(catalog: FactCatalog, cap: int | None, within=None) -> int:
    """Applies the atomic cap to facts already stored.

    Args:
        catalog: Where the facts are read from and written back to.
        cap: The most validated atomic facts one passage may keep, or None
            when EXTRACTION_MIN_OTHER_SHARE sets no cap. A passage stating
            more sentences and list items than this keeps that many instead.
        within: A condition narrowing which passages are read, or None.

    Returns:
        How many facts were refused or given back.
    """
    written = catalog.recap(cap, _over_cap_reason(cap), within)
    log.info(
        "moved %d atomic fact(s) across the cap of %s a passage, or its own "
        "sentence and item count where that is more",
        written,
        cap,
    )
    return written


def dedup(
    catalog: FactCatalog,
    threshold: float,
    within=None,
    floor: float = 0.0,
    *,
    checker: FactChecker | None = None,
    cap: int | None = None,
) -> int:
    """Re-decides every stored `duplicate` refusal, without calling the model.

    The replay for this gate, as `recap` is for the cap: what the model wrote
    is kept and only the verdict moves. Two steps, in this order:

    1. Every citation an earlier version's refusal folded into the fact it
       repeated is deleted, and that fact's evidence is rebuilt from the
       citation it keeps. A refusal now writes nothing onto its twin, and a
       fold counted the refused passage towards every question asked of it.
    2. Every refusal is probed again as a candidate is in flight - the
       corpus's facts of its language and kind read from other passages, and
       what its own passage keeps - and is given back, validated as it was
       judged when extracted, when no twin naming its numbers reaches
       `threshold`. One at a time, so a refusal given back is a twin for the
       ones after it and one claim refused twice comes back once.

    A fact given back was judged by the checks of its own extraction and has
    not been counted against the cap, so with a `checker` the passages of
    the facts given back are then re-judged, as `revalidate` judges, and
    re-capped, as `recap` caps - those passages and no others, so a replay
    after a deletion re-stamps what it moved rather than the corpus. Its
    stored reading is replaced by the one this probe took, against this
    bar, as a fact read in flight would carry; with no twin left it carries
    none. The refusal's own margin is never left on a validated fact.

    Args:
        catalog: Where the refusals are read from and written back to.
        threshold: EXTRACTION_DUPLICATE_COSINE. 0 refuses nothing, so every
            refusal is given back.
        within: A condition narrowing which facts are read, or None.
        floor: EXTRACTION_DUPLICATE_FLOOR, which a reading's margin is
            measured down to.
        checker: What re-judges the passages of the facts given back, or
            None to leave them as given back.
        cap: The cap those passages are re-capped to, as `recap` takes it.
            Read only with a `checker`.

    Returns:
        How many refusals were given back.
    """
    unfolded, left = catalog.unfold(_cited_text, within)
    log.info("took the folded citations out of %d fact(s)", unfolded)
    if left:
        log.warning(
            "left the folded citations on %d fact(s) whose own citation is gone: "
            "their passage was read again, and taking the rest out would delete "
            "them and the questions resting on them. `make extract-rerun` over "
            "those passages replaces them.",
            left,
        )
    given = 0
    moved: set[int] = set()
    for refused in catalog.duplicates(within):
        twin = _twin(catalog, refused)
        if threshold <= 0 or twin is None:
            back = catalog.give_back(refused.fact_id)
        elif twin.similarity >= threshold:
            continue
        else:
            reading = _measured(twin, threshold, floor)
            back = catalog.give_back(
                refused.fact_id, scored([reading]), confidence([reading])
            )
        given += back
        if back:
            moved.add(refused.passage_id)
    log.info("gave back %d duplicate refusal(s) today's rule would not make", given)
    if checker is not None and moved:
        narrowed = _among(moved)
        revalidate(catalog, checker, narrowed, threshold=threshold, cap=cap)
        recap(catalog, cap, narrowed)
    return given


def _among(passages: set[int]):
    """The condition selecting these passages, and no others.

    One array rather than a parameter per passage, which a replay over a
    large corpus could move more of than a statement may bind.
    """
    return Passage.id == any_(
        bindparam("moved", sorted(passages), type_=ARRAY(BigInteger))
    )


def _twin(catalog: FactCatalog, refused: Refused) -> Twin | None:
    """The closest fact a stored refusal could be the twin of, or None.

    Probed as a candidate is in flight: the corpus's facts of its language
    and kind read from other passages, and what its own passage keeps. None
    for a refusal stored with no vector, which nothing can probe.
    """
    if refused.embedding is None:
        return None
    probed = catalog.nearest_fact(
        refused.embedding,
        excluding=refused.passage_id,
        language=refused.language,
        kind=refused.kind,
        alike=_naming(refused.statement, refused.language),
    )
    return _closest(
        refused.statement,
        refused.kind,
        refused.language,
        refused.embedding,
        probed,
        catalog.kept(refused.passage_id),
    )


def _uncitable(candidate) -> bool:
    """Whether a stored fact recorded no sentence to judge it against.

    Two kinds of row look like this and neither is worth re-reading.

    A bridge drawn before prompt version 2 named its passages and not the
    sentences in them. Judging one would resolve nothing and refuse it as
    evidence_absent, which would throw away a fact that was correct under the
    prompt that wrote it.

    A fact already refused as evidence_absent is the other. The numbers its
    citation named survive nowhere but its own `validation_error`: the link
    rows carry NULL, which is what says they resolved to nothing. Re-judging
    one rebuilds the candidate from those NULLs, reaches the same verdict,
    and rewrites the message as `names (none)` - so the only record of what
    the model actually cited is lost to a pass that learned nothing.

    Read off the field `_rejudge` will read, which is not the same one for
    both kinds: a bridge is judged against the sentences named per passage
    and everything else against the candidate's own.
    """
    if candidate.kind == FactKind.BRIDGE:
        return not any(one.sentences for one in candidate.passages)
    return not candidate.sentences


def _rejudge(
    checker: FactChecker,
    passages: list[PassageToExtract],
    candidate,
    method: str,
) -> CheckedFact:
    """Judges one stored fact against the passages it was drawn from.

    A non-bridge fact is judged on its first passage, and keeps the evidence
    of any further citation it still carries - one an earlier version's
    duplicate refusal added - so its evidence and its citations agree.
    """
    if candidate.kind == FactKind.BRIDGE:
        return checker.check_bridge(passages, candidate)
    checked = checker.check(passages[0], candidate, method)
    evidence = checked.evidence_text
    for passage, cited in zip(passages[1:], candidate.passages[1:], strict=False):
        sentences = [
            passage.sentences[at]
            for at in cited.sentences
            if 0 <= at < len(passage.sentences)
        ]
        segment = _cited_text(passage, sentences) if sentences else ""
        if segment and segment not in evidence:
            evidence = f"{evidence}\n{segment}"
    return replace(checked, evidence_text=evidence)


class CitedBridges(Exception):
    """Accepted questions cite a bridge the pass would delete."""


def bridge(
    catalog: FactCatalog,
    extractor: BridgeExtractor,
    checker: FactChecker,
    groups_per_topic: int,
    size: int,
    within=None,
    force: bool = False,
    missing: bool = False,
) -> int:
    """Writes the bridge facts a corpus's topics offer.

    One model call per group. Every bridge in scope is deleted once the links
    are dealt and before the first call, so a second run replaces what the
    first wrote instead of adding to it, and one that dies reading the corpus
    deletes nothing.

    With `missing`, nothing is deleted and only the topics holding no bridge
    are read: what a whole-corpus run asks for, so a second one neither
    replaces bridges that accepted questions cite nor stops on them.

    Args:
        catalog: Where the groups are read from and the facts written to.
        extractor: The model-backed reader of a group.
        checker: What judges what it proposed.
        groups_per_topic: How many groups one topic is worth.
        size: How many passages one group holds.
        within: A condition selecting the topics to read, or None.
        force: Delete the bridges in scope even where an accepted question
            cites one.
        missing: Read only the topics holding no bridge, and delete nothing.

    Returns:
        How many bridge facts were stored, refused ones included.

    Raises:
        CitedBridges: If an accepted question cites a bridge in scope and
            `force` is not set. Nothing is deleted.
        SpendCapReached: If SPEND_CAP was reached between two topics. The
            facts written so far are kept, and the number is `kept`.
    """
    # ponytail: counted and deleted in two transactions, so a question
    # accepted between them is not counted. Upgrade: count and delete in one
    # transaction holding a lock on the bridges.
    done: frozenset[int] = frozenset()
    if missing:
        done = catalog.bridged_topics(within)
        log.info("leaving the %d topic(s) that already hold a bridge", len(done))
    elif not force and (cited := catalog.accepted_on_bridges(within)):
        raise CitedBridges(
            f"{cited} accepted question(s) cite a bridge this pass would delete, "
            "and would be rejected or deleted with it"
        )
    written = 0
    # Groups the model could not be asked about. Counted because skipping
    # one and carrying on is right - a batch over many groups must
    # not end because one call failed - but a pass that quietly wrote fewer
    # facts than it could have is a pass whose result cannot be read. The
    # same ExtractionFailed fails a PASSAGE outright, and the difference
    # between the two was invisible.
    dropped = 0
    scoped = list(catalog.by_topic(within))
    whole = scoped if within is None else list(catalog.by_topic(None))
    topic_of = {one.id: topic for topic, ones in whole for one in ones}
    # The same gate the per-passage stage applies, so the two cannot drift.
    # Without it a link is spent on a table of contents or a heading:
    # `by_topic` asks only that a passage was segmented.
    readable = [one for _, ones in whole for one in ones if skipped(one) is None]
    # A passage with no validated fact has nothing to compose from, so it is
    # taken out before the links are dealt: dropped afterwards, its head
    # would lose its link and its topic's slot would stay empty.
    facts = catalog.atomic_of({one.id for one in readable})
    partners = [one for one in readable if one.id in facts]
    heads = [
        one
        for _, ones in scoped
        for one in ones
        if skipped(one) is None and one.id in facts
    ]
    # What is left after the clear is what this pass must not repeat,
    # whichever side of a cross-topic pair heads it: the bridges that stay.
    held = catalog.bridged_pairs(within, replaced=not missing)
    offers: list[tuple[str, list[Link]]] = []
    topic: object = object()  # none yet, so the first link reads the cap too
    for language in sorted({one.language or "" for one in partners}):
        links = linked(
            [one for one in heads if (one.language or "") == language],
            [one for one in partners if (one.language or "") == language],
            topic_of,
            groups_per_topic,
            size,
            done,
            held,
        )
        kinds = Counter(link.kind for link in links)
        log.info(
            "offered %d link(s) in %r (%d reference, %d sibling, %d term)",
            len(links),
            language,
            kinds["reference"],
            kinds["sibling"],
            kinds["term"],
        )
        offers.append((language, links))
    # After the links are dealt, which is the long read of the whole corpus
    # and the part that can run out of memory: a pass that dies there has
    # deleted nothing.
    if not missing:
        log.info("replacing %d bridge fact(s)", catalog.clear_bridges(within))
    for _, links in offers:
        for link in links:
            # Between topics, so what is written is kept, nothing is held, and
            # no topic is left half bridged: `missing` skips any that has one.
            if (at := topic_of.get(link.head or 0)) != topic:
                stop_at_cap(written)
                topic = at
            offered = list(link.passages)
            try:
                proposed = extractor.extract(offered, link, facts)
            except ExtractionFailed as exc:
                log.warning(
                    "link %s: a group failed: %s", [one.id for one in offered], exc
                )
                dropped += 1
                continue
            try:
                written += catalog.add_bridges(
                    [
                        _headed(
                            checker.check_bridge(
                                offered, candidate, extractor.provenance
                            ),
                            link.head,
                        )
                        for candidate in proposed
                    ]
                )
            except IntegrityError as exc:
                # A passage of the link was deleted since the links were read
                # (a document removed, a re-chunk): its write rolled back.
                log.warning(
                    "link %s: dropped, a passage is gone: %s",
                    [one.id for one in offered],
                    str(exc.orig).splitlines()[0],
                )
                dropped += 1
    if dropped:
        log.warning(
            "wrote %d bridge fact(s), and %d group(s) were dropped because the "
            "model would not answer or a passage was deleted. This pass is short by whatever they held; "
            "`make extract-bridge` again is what asks for them.",
            written,
            dropped,
        )
    else:
        log.info("wrote %d bridge fact(s)", written)
    return written


def _headed(fact: CheckedFact, head: int | None) -> CheckedFact:
    """A bridge fact whose reading names the passage that headed its link.

    What a narrowed pass reads to tell the bridges it writes back from the
    ones it leaves: the passage shown first heads only a reference link. A
    fact with no reading keeps none, and is read by the passage it opens on.
    """
    if fact.bridge is None or head is None:
        return fact
    return replace(fact, bridge={**fact.bridge, "head": head})


def _is_heading(passage: PassageToExtract) -> bool:
    """Reports whether a passage is its own heading and nothing more."""
    if not passage.section_path:
        return False
    text = normalised(passage.text)
    return any(
        text == normalised(segment) for segment in headings_of(passage.section_path)
    )


#: Block types that say where something is rather than what it says. A table
#: of contents yields "Das Team managen beginnt auf Seite 69"; an index
#: rendered as a code block yields facts of the form "Der Lehrplan umfasst
#: das Thema X". Both are navigation, and a question asked of either
#: measures a reader's page-turning.
_NAVIGATION = frozenset({"document_index", "code"})

# ponytail: the skip heuristics below - _CHARS_PER_CLAIM, _NUMERIC_WORDS,
# _CODE_CELLS, the code-cell pattern and "any © is a notice" - are
# tuned to this corpus. Upgrade: settings, measured again on a new corpus.

#: How many characters a passage may carry per claim before it stops
#: reading as prose. The parser labels what it recognises, and an index it
#: does not recognise arrives as `text`.
#:
#: Why not `claims` alone: that check already exists and refuses only a
#: passage with none, and an index with one stray verb in it passes.
_CHARS_PER_CLAIM = 500

#: The share of a passage's words that may carry a digit before it reads as
#: a list of references. Sparseness alone is not enough to judge on: a
#: German bullet list is sparse because its points are infinitives rather
#: than sentences, and those are content.
#:
#: So both must hold. Digits rather than any word, so this says nothing
#: about a language or a subject; a passage genuinely about numbers is a
#: `table` and exempt above.
_NUMERIC_WORDS = 0.05

#: The glyph a copyright notice opens with, in any language. Front matter
#: asserts things a model will turn into facts - who holds a right, which
#: edition a thing belongs to - and they are about the document rather than
#: about what it says.
_COPYRIGHT = "\u00a9"

_HAS_DIGIT = re.compile(r"\d")

#: A cell holding an identifier rather than a statement: a learning-objective
#: code, a level, a tick. Anchored, so a cell containing one of these among
#: words is not one. A number carries letters before it to be one: a bare
#: figure, `5` or `12.50`, is a value a fee or price table states, and so is
#: one after a currency code, `EUR 5`, which `_code_grid` reads off `letters`.
_CODE_CELL = re.compile(
    r"""^(?:
        (?P<letters>[^\W\d_]{1,6})[-. ]?\d+(?:\.\d+)*   # TM-2.2.1, Abschnitt 4
      | [A-Z]{1,5}-?[A-Z]*\d+              # TA-BO1, FL4
      | [XxKk]\d?                          # K2, X
      | [✓✗X-]                   # tick, cross, dash
    )$""",
    re.VERBOSE,
)

#: The share of a table's filled cells that may be identifiers before the grid
#: stops being a statement of anything. A traceability matrix, a release-note
#: table and an abbreviation list are all mostly codes.
#:
#: Set where nothing good is refused rather than where everything bad is
#: caught: a table wrongly read yields a fact per cell, and a table wrongly
#: skipped yields nothing, but the first is the one that reaches a question.
_CODE_CELLS = 0.5


def _code_grid(passage: PassageToExtract) -> bool:
    """Whether a table's cells are identifiers rather than statements."""
    cells = [
        text
        for grid in passage.table_cells
        for cell in grid.get("cells", ())
        if (text := (cell.get("text") or "").strip())
    ]
    if not cells:
        return False
    amounts = AMOUNT_WORDS.get(passage.language or "", frozenset())
    codes = sum(
        1
        for one in cells
        if (code := _CODE_CELL.match(one))
        and (code["letters"] or "").casefold() not in amounts
    )
    return codes / len(cells) > _CODE_CELLS


def _reference_list(passage: PassageToExtract) -> bool:
    """Whether the passage is a list of references rather than prose.

    Both halves, because either alone is wrong. Sparse-in-claims catches a
    content bullet list; numeric-in-words catches a passage that is simply
    about measurements. An index, a bibliography and a contents page are
    the only things that are both. A list item counts as a claim, as the
    cap counts it, so a price list stating a figure on every line is not
    sparse.
    """
    text = normalised(passage.text)
    words = text.split()
    if not words or len(text) <= _CHARS_PER_CLAIM * (passage.claims + passage.items):
        return False
    numeric = sum(1 for one in words if _HAS_DIGIT.search(one)) / len(words)
    return numeric > _NUMERIC_WORDS


def _nothing_found(passage: PassageToExtract, current) -> None:
    """Says so when a readable passage produced no candidate at all.

    `skipped` has already refused the passages nothing could be read from -
    headings, navigation, a grid of identifiers, anything with no sentences
    - so reaching here means this pipeline decided the passage carries
    claims and the model returned none. That is not the same answer as "it
    carries none", and it used to be recorded as though it were: the row
    went to `extracted` with nothing under it and the run looked clean.

    **The whole corpus can be lost this way without one error.** A model
    answering every call with an empty list marks every passage read and
    writes no fact; the first thing to notice is a topic fit with nothing
    to fit.

    A warning rather than a raise, because one such passage is ordinary -
    a page of prose that asserts nothing does exist - and failing the row
    would strand a corpus on its dullest page. It is the RATE that is the
    signal, which is why the count is on the span as well as in the log.
    """
    log.warning(
        "passage %d: readable, and the model proposed nothing. One is "
        "ordinary; many means the model is answering empty - check "
        "LLM_REASONING_EFFORT and the context window",
        passage.id,
        extra={"passage.id": passage.id, "extract.nothing_found": True},
    )
    current.set_attribute("extract.nothing_found", True)


def skipped(passage: PassageToExtract) -> str | None:
    """Says why a passage is not worth a model call.

    Args:
        passage: The passage about to be read.

    Returns:
        The reason it was skipped, or None when it is worth reading.
    """
    # Ahead of the table exemption: nothing can be cited from a passage with
    # nothing numbered, whatever kind it is. A table read without them
    # produced a fact per cell, every one citing a row that did not exist.
    if not passage.sentences:
        return "no sentences"
    if passage.block_type in _NAVIGATION:
        return f"{passage.block_type}: navigation rather than content"
    if passage.block_type in ("table",):
        # The one furniture check a table is not exempt from. The exemptions
        # below exist because a grid carries no sentences and so no claims,
        # which the signals they read are counted in; this one reads the
        # cells themselves and so says something about a table.
        if _code_grid(passage):
            return "a grid of identifiers rather than of statements"
        return None
    if _is_heading(passage):
        return "heading"
    if not passage.claims:
        return "no finite verb"
    # What the checks above are for, applied to what the parser did not
    # label. Between them these produced questions asking which pages a
    # term appears on and how the document is licensed - answerable,
    # checkable, and about the document rather than about its subject.
    if _COPYRIGHT in passage.text:
        return "a copyright notice, which is about the document"
    if _reference_list(passage):
        return "an index, a bibliography or a contents page rather than prose"
    return None


def _unread_prose(passage: PassageToExtract) -> bool:
    """Whether a table passage also carries lines no reader would reach.

    The chunker labels a merged passage `table` if ANY item in it is one,
    and numbers the whole of it by rendered line rather than by sentence -
    a table passage chunked before its prose lines were counted carries
    `predicates: 0` on every line, so `claims` is zero for it and the prose
    merged into it is invisible to each of the signals above. The cell reader then walks the grid and nothing
    reads the rest.

    Lines outside a table's grids are rendered rows and `|---|`
    separators, or ordinary prose - "In diesem Abschnitt werden die
    geschäftlichen Nutzen aufgeführt...". A finite verb is what tells the
    two apart, so it is asked here rather than read off a column that was
    written as zero.
    """
    return bool(passage.table_cells and _prose(passage))


def _prose(passage: PassageToExtract) -> list:
    """The lines of a table passage outside its grids that assert something."""
    gridded = {
        cell.get("line")
        for grid in passage.table_cells
        for cell in grid.get("cells", ())
    }
    return [
        one
        for one in passage.sentences
        if one.index not in gridded and claim(one.text, passage.language).predicates
    ]


def over_cap(facts: Sequence[CheckedFact], cap: int | None) -> set[int]:
    """Which of one passage's facts the atomic cap refuses, by position.

    Only the validated atomic ones compete for the budget and only they are
    refused. A fact a check already threw out is not taking a place from
    anything, and overwriting its code would lose why it really went.

    The ones asserting a value are kept, which is the rule question
    generation already offers facts by: a fact carrying a number, a date or
    a name is what a checkable question is written from. Ties go to the
    order the model wrote them in, so one passage read twice keeps the same
    facts.

    A statement a deterministic reader composed does not compete. The cap is
    EXTRACTION_MIN_OTHER_SHARE read the other way round - the share of a
    passage's facts that may be something other than atomic - and what makes
    a floor on the others a cap on these is that a passage yields a FIXED
    number of digests beside them. A table yields none: its rendered rows
    carry no finite verb, so `_DIGESTIBLE` is never met and there is no
    other kind for the share to be. Applying the cap there is arithmetic
    about a quantity that is zero, and it threw away table facts - the
    cheapest and most checkable facts in the corpus - by grid position.

    A fact the repair call wrote does not compete either. The passage's room
    counted the refused statement's sentence once, the checker found it
    states several claims, and its pieces stand in for it; counted one each
    they overflow the one slot the refusal freed and are refused by
    position, not by quality.
    """
    if cap is None:
        return set()
    competing = [
        (position, fact)
        for position, fact in enumerate(facts)
        if fact.kind == FactKind.ATOMIC
        and fact.validated
        and fact.extraction_method == WRITTEN
        and not from_repair(fact.prompt_version)
    ]
    if len(competing) <= cap:
        return set()
    ranked = sorted(competing, key=lambda one: (not one[1].units_statement, one[0]))
    return {position for position, _ in ranked[cap:]}


def _refuse(fact: CheckedFact, cap: int | None) -> CheckedFact:
    """Marks one atomic fact as over the cap, leaving the rest of it alone.

    `cap` is EXTRACTION_MIN_OTHER_SHARE's, not the passage's room, so the
    reason reads as the one `recap` writes.
    """
    return replace(
        fact,
        validated=False,
        rejection_code=Rejection.OVER_CAP,
        validation_error=_over_cap_reason(cap),
    )


def _measured(twin: Twin, threshold: float, floor: float) -> Measurement:
    """The dedup gate's reading of one twin, as the stored confidence takes it.

    The only reading in this service that is a measurement: every other check
    is structural, and a citation resolves or it does not. High is what
    refuses, so a statement far from anything already stored has the whole
    margin.
    """
    return Measurement(
        "duplicate", twin.similarity, threshold, high_is_safe=False, safe_end=floor
    )


def _counted_alike(statement: str, twin: str, language: str | None) -> bool:
    """Whether two statements name the same numbers, as often as each other."""
    return numbers(statement, language) == numbers(twin, language)


def _naming(statement: str, language: str | None) -> Callable[[Twin], bool]:
    """What a probe for this statement takes as a twin: one naming its numbers.

    Handed to the index probe, which reads past a nearer fact naming others.
    """
    return lambda twin: _counted_alike(statement, twin.statement, language)


#: A passage's two digests: readings of the whole, not claims one repeats.
_DIGESTS = {FactKind.SUMMARY, FactKind.OUTLINE}


def _closest(
    statement: str,
    kind: str,
    language: str | None,
    vector: Sequence[float],
    probed: Twin | None,
    kept: Sequence[tuple[str, str, Sequence[float]]],
) -> Twin | None:
    """The closest fact that could be this statement's twin, or None.

    `probed` is what the index answered for the rest of the corpus, and
    `kept` is what the statement's own passage keeps, as (statement, kind,
    vector). One rule for the gate in flight and for `dedup`, which replays
    it over the refusals already stored.

    Only a fact stating the statement's own numbers is a twin, on either
    probe: two statements naming different numbers are two claims however
    near their vectors sit, and a bare statement scores high on a shared
    subject alone.

    And inside one passage only a fact of another kind - a summary or an
    outline repeating one of the passage's claims - or one of its kind
    saying the statement word for word. A passage's summary and its outline
    are two readings of it, which embed alike and repeat nothing of each
    other. Two atomic facts of one passage are
    otherwise two of its claims - two items of a list, two conditions, a
    least and a most - which differ by a word and score as near as a
    restatement. The question dedup refuses a second question on a near
    repeat.
    """
    twin = probed
    if twin is not None and not _counted_alike(statement, twin.statement, language):
        twin = None
    for other_statement, other_kind, other in kept:
        if (
            (
                other_kind == kind
                and normalised(other_statement) != normalised(statement)
            )
            or ({kind, other_kind} == _DIGESTS)
            or not _counted_alike(statement, other_statement, language)
        ):
            continue
        score = cosine(list(vector), list(other))
        if twin is None or score > twin.similarity:
            twin = Twin(fact_id=0, statement=other_statement, similarity=score)
    return twin


def _duplicate(fact: CheckedFact, twin: Twin, threshold: float) -> CheckedFact:
    """Marks one fact as a near twin of a fact already stored."""
    named = f"fact {twin.fact_id}" if twin.fact_id else "a fact this passage kept"
    return replace(
        fact,
        validated=False,
        rejection_code=Rejection.DUPLICATE,
        twin_id=twin.fact_id or None,
        validation_error=(
            f"says what {named} already says at cosine "
            f"{twin.similarity:.3f}, over the {threshold:g} "
            f"EXTRACTION_DUPLICATE_COSINE allows: {twin.statement!r}"
        ),
    )


class ExtractionService(StageService):
    """Draws facts out of passages, one passage at a time.

    A passage that yields no facts is not a failure, and neither is a fact
    that fails a check: that one is stored with the reason.
    """

    name: ClassVar[str] = "extraction"
    unit: ClassVar[str] = "passage"
    #: Measured on the 2026-10 build: 13.11 USD and 2 h 01 min over 1,973 passages.
    estimate: ClassVar[tuple[float, float] | None] = (0.0066, 3.7)

    def __init__(
        self,
        *,
        repository: PassageQueue,
        extractors: ExtractorRegistry,
        checker: FactChecker,
        digest: DigestExtractor | None = None,
        atomic_cap: int | None = None,
        digest_min_chars: int = 0,
        embedder: Embedder | None = None,
        duplicate_cosine: float = 0.0,
        duplicate_floor: float = 0.0,
        catalog: FactCatalog | None = None,
    ) -> None:
        """Initialises the service with its collaborators.

        Args:
            repository: The queue it claims passages from.
            extractors: One reader per block type, with a default.
            checker: What judges everything they propose.
            digest: The reader of a passage's summary and outline, or None
                when this deployment writes neither.
            atomic_cap: The most atomic facts one passage keeps, or None for
                no cap. EXTRACTION_MIN_OTHER_SHARE is where it comes from. A
                passage stating more sentences and list items keeps that many.
            digest_min_chars: The shortest passage worth digesting. 0
                digests every passage carrying enough claims.
            embedder: The embedding model, or None to write no vectors and
                run no dedup gate.
            duplicate_cosine: How alike two statements may be before the
                second is refused. 0 turns the gate off and leaves the
                vectors being written.
            duplicate_floor: The cosine two unrelated statements score,
                which the stored confidence is measured from. Calibration
                only; it refuses nothing.
            catalog: Where the dedup replay runs when the queue empties
                after this service replaced facts, or None to run none.
        """
        super().__init__(repository)
        self._repository: PassageQueue = repository
        self._extractors = extractors
        self._checker = checker
        self._digest = digest
        self._atomic_cap = atomic_cap
        self._digest_min_chars = digest_min_chars
        self._embedder = embedder
        self._duplicate_cosine = duplicate_cosine
        self._duplicate_floor = duplicate_floor
        self._catalog = catalog
        # Whether a passage stored since the last replay replaced facts.
        self._replaced = False
        # Held for the life of the service, as question generation holds
        # its own: the client is one connection and the batch spans
        # passages, so a passage yielding four facts costs no call.
        self._evaluations = Evaluations()
        # Whether each of the last readable passages came back with nothing:
        # (passage id, nothing found).
        self._answers: deque[tuple[int, bool]] = deque(maxlen=_WINDOW)
        # How many passages in a row the digest model could not be reached
        # for, and whether it is asked no more for the rest of this drain.
        self._digest_outages = 0
        self._digest_off = False

    def drain(self, stopping: Callable[[], bool] | None = None) -> int:
        """Works the queue, asking the digest model afresh."""
        self._digest_outages = 0
        self._digest_off = False
        return super().drain(stopping) if stopping else super().drain()

    def process_next(self) -> int | None:
        """Reads one queued passage and stores what it yielded.

        Returns:
            The passage's id, or None when the queue is empty.
        """
        passage = self._repository.claim()
        if passage is None:
            if self._replaced:
                self._replay()
            return None

        with working(
            span,
            "extract",
            {
                "stage": self.name,
                "passage.id": passage.id,
                "passage.block_type": passage.block_type or "",
            },
        ) as current:
            try:
                read = self._passage(passage, current)
                if read.silent is not None and self._silenced(passage.id, read.silent):
                    return passage.id
                facts, note = read.facts, read.note
                facts = self._capped(
                    passage,
                    self._deduplicated(facts, current, passage.id, passage.language),
                    current,
                )
                if self._replays() and not self._replaced:
                    self._replaced = self._repository.cited(passage.id)
                settled: list[CheckedFact] = []

                def settle(
                    kept: list[CheckedFact], passage=passage, settled=settled
                ) -> list[CheckedFact]:
                    """The facts again against what is stored now, under the lock."""
                    settled[:] = self._untwinned(
                        kept, None, passage.id, passage.language
                    )
                    return settled

                stored = self._repository.store(
                    passage.id, facts, self._embedded(passage), note=note, settle=settle
                )
                facts = settled or facts
                validated = sum(1 for fact in facts if fact.validated)
                self._done(current)
                # After store, so what is recorded is the verdict that
                # survived the cap and the dedup rather than the one the
                # checker reached before either ran.
                self._record(passage, facts)
                current.set_attribute("extract.facts", stored)
                current.set_attribute("extract.validated", validated)
                log.info(
                    "passage %d: %d fact(s), %d validated (%d rejected)",
                    passage.id,
                    stored,
                    validated,
                    stored - validated,
                    extra={
                        "facts.stored": stored,
                        "facts.validated": validated,
                        "facts.rejected": stored - validated,
                    },
                )
            except ExtractionFailed as exc:
                self._fail(passage.id, str(exc), current, is_outage(exc))
            except Exception as exc:
                self._fail(passage.id, f"{type(exc).__name__}: {exc}", current)
                log.exception("failed passage %d", passage.id)
        return passage.id

    def _replays(self) -> bool:
        """Whether this service replays the dedup gate where its drain ends.

        Only where it runs the gate: with the gate off the replay gives
        every refusal back, which is `make extract-dedup`'s to decide.
        """
        return (
            self._catalog is not None
            and self._embedder is not None
            and self._duplicate_cosine > 0
        )

    def _replay(self) -> None:
        """Re-decides every stored duplicate refusal, as `make extract-dedup` does.

        A passage read again has its facts replaced, and a refusal elsewhere
        naming one of them as its twin is left refused against a fact that
        is gone. A retry or a rerun only queues the rows, so the drain that
        deletes is this one and the replay runs where it finds its queue
        empty. Under a lock, so two workers' replays never interleave: the
        second waits for the first and then replays what that one left.
        """
        assert self._catalog is not None
        with self._catalog.replaying():
            dedup(
                self._catalog,
                self._duplicate_cosine,
                floor=self._duplicate_floor,
                checker=self._checker,
                cap=self._atomic_cap,
            )
        self._replaced = False

    def _record(self, passage: PassageToExtract, facts: list[CheckedFact]) -> None:
        """Puts every fact's verdict in Phoenix's Evaluations view.

        A span of its own per fact, because an annotation is filed against
        a span and the passage has one span for however many facts it
        yielded. The same arrangement question generation uses for a
        question, and for the same reason: `validation` scored 1 or 0
        means a project's mean over it IS the validation rate, and the
        rejection codes compare run to run without a query.

        Two annotations per fact, not one. `validation` is what became of
        it; `validation: <rule>` is the rule that refused it, so the
        Evaluations view is a column per rule the way it is a column per
        gate - which is the only way to see that `not_atomic` moved while
        the total held still.
        """
        if not self._evaluations.enabled:
            return
        about = {"run_id": run_id(), "passage_id": str(passage.id)}
        for fact in facts:
            with span.start_as_current_span("check_fact") as current:
                # No run.id: telemetry.traces stamps every span with the run
                # that queued the row, and RUN_ID set here split one trace.
                current.set_attribute("passage.id", passage.id)
                current.set_attribute("fact.kind", str(fact.kind))
                current.set_attribute("fact.validated", fact.validated)
                current.set_attribute("fact.method", fact.extraction_method or "")
                rule = str(fact.rejection_code) if fact.rejection_code else ""
                if rule:
                    current.set_attribute("fact.rejection", rule)
                _, span_id = current_ids()
                if not span_id:
                    continue
                verdicts = [
                    Verdict(
                        span_id=span_id,
                        name="validation",
                        label=rule or _VALIDATED,
                        score=float(fact.validated),
                        explanation=fact.validation_error or "",
                        metadata=about | {"kind": str(fact.kind)},
                    )
                ]
                if rule:
                    verdicts.append(
                        Verdict(
                            span_id=span_id,
                            name=f"validation: {rule}",
                            label="refused",
                            score=0.0,
                            explanation=fact.validation_error or "",
                            metadata=about,
                        )
                    )
                self._evaluations.record(*verdicts)
        self._evaluations.flush()

    def _silenced(self, passage_id: int, nothing: bool) -> bool:
        """Counts one readable passage, and stops the drain on a silent model.

        One passage with nothing found is ordinary; `_EMPTY_STOP` of the last
        `_WINDOW` is a model answering empty, which every row would call a
        success. The drain stops, and the passages it counted as empty go
        back to the queue with the one in hand, so none stays marked read
        with nothing under it.
        """
        self._answers.append((passage_id, nothing))
        silent = [one for one, empty in self._answers if empty]
        if len(silent) < _EMPTY_STOP:
            return False
        self._answers.clear()
        self._stop(
            f"the model proposed nothing for {len(silent)} of the last {_WINDOW} "
            "readable passages, so it is answering empty; they are back in the "
            "queue. Check LLM_REASONING_EFFORT and the context window",
            *silent,
            passage_id,
            standing=True,
        )
        return True

    def _passage(self, passage: PassageToExtract, current) -> _Read:
        """Reads one passage and checks everything it produced."""
        reason = skipped(passage)
        if reason is not None:
            # Marked read with nothing found, not failed: there was nothing
            # here to read, which is an answer and not an error.
            current.set_attribute("extract.skipped", reason)
            return _Read([], None, None)

        readers = self._readers(passage, current)
        facts: list[CheckedFact] = []
        for reader, shown in readers:
            read = [
                self._checker.check(
                    passage, candidate, reader.method, reader.provenance
                )
                for candidate in reader.extract(shown)
            ]
            facts += read + self._repaired(passage, reader, shown, read, current)
        # Only a model can answer empty: a cell reader finding no row to
        # compose is the grid's answer, not a silent model.
        asked = any(reader.method == WRITTEN for reader, _ in readers)
        if not facts and asked:
            _nothing_found(passage, current)
        silent = (not facts) if asked else None
        try:
            digests = self._digested(passage)
        except ExtractionFailed as failure:
            self._counted(failure)
            return _Read(facts, self._missing(passage, failure), silent)
        if digests:
            self._digest_outages = 0
        return _Read(facts + digests, None, silent)

    def _counted(self, failure: ExtractionFailed) -> None:
        """Counts a digest the model could not give, and stops asking at a run.

        `STOP_AFTER` passages in a row it could not be reached for: its retry
        budget is paid in full for each, and the atomic facts, which a
        drain is for, wait on it. The passages are noted as any digest
        failure is, and `make extract-digests` gives them once it is back.
        """
        if not is_outage(failure):
            self._digest_outages = 0
            return
        self._digest_outages += 1
        if self._digest_outages == STOP_AFTER and not self._digest_off:
            self._digest_off = True
            log.error(
                "the digest model could not be reached for %d passage(s) in a "
                "row, so it is asked no more in this drain; they and the "
                "passages after are noted, and make extract-digests gives "
                "them a digest once it answers",
                STOP_AFTER,
            )

    def _repaired(
        self,
        passage: PassageToExtract,
        reader: Extractor,
        shown: PassageToExtract,
        read: list[CheckedFact],
        current,
    ) -> list[CheckedFact]:
        """The claims the model joined into statements refused as `not_atomic`.

        Asked for once, in one more call for the passage, from the model
        that wrote them and shown what it was shown. What comes back faces
        the same checks, so a repair still joining two claims is refused
        again and not sent back a second time. The refusals themselves are
        stored as they were. A repair call that fails costs the passage
        nothing it had: the refusals stand, and the reason is logged.
        """
        refused = [fact for fact in read if fact.rejection_code == Rejection.NOT_ATOMIC]
        if not refused or not isinstance(reader, LlmExtractor):
            return []
        current.set_attribute("extract.repair", len(refused))
        try:
            candidates = reader.repair(shown, refused)
        except ExtractionFailed as exc:
            current.set_attribute("extract.repair_failed", str(exc))
            log.warning(
                "passage %d: the repair call failed, so %d not_atomic "
                "refusal(s) stand: %s",
                passage.id,
                len(refused),
                exc,
            )
            return []
        return [
            self._checker.check(
                passage, candidate, reader.method, reader.repair_provenance
            )
            for candidate in candidates
        ]

    def _capped(
        self, passage: PassageToExtract, facts: list[CheckedFact], current
    ) -> list[CheckedFact]:
        """Refuses the atomic facts past the cap, after dedup has refused its own.

        The cap this passage has room for, which is never below what it
        states: see `PassageToExtract.room`.
        """
        cap = passage.room(self._atomic_cap)
        refused = over_cap(facts, cap)
        if cap is None or not refused:
            return facts
        current.set_attribute("extract.over_cap", len(refused))
        return [
            _refuse(fact, self._atomic_cap) if position in refused else fact
            for position, fact in enumerate(facts)
        ]

    def _embedded(self, passage: PassageToExtract) -> list[float] | None:
        """The passage's own vector, or None when this deployment writes none."""
        if self._embedder is None:
            return None
        return self._embedder.embed(for_passage(passage.text))

    def _deduplicated(
        self,
        facts: list[CheckedFact],
        current,
        passage_id: int,
        language: str | None,
    ) -> list[CheckedFact]:
        """Embeds every fact and refuses the ones already in the corpus.

        Two probes per candidate, because neither alone is enough. The index
        holds what earlier passages stored; `written` holds what this passage
        has already kept, without which one passage would happily store the
        same statement twice - a summary and an atomic fact often say the
        same thing about a short passage. Across kinds, or word for word:
        two atomic facts of one passage are otherwise two of its claims.

        Only validated facts compete and only they are refused: a fact a
        check already threw out is not a duplicate of anything, and comparing
        it would make the corpus's first copy depend on which passage was
        read first.
        """
        if self._embedder is None:
            return facts
        vectors = self._embedder.embed_all(
            [for_statement(fact.statement) for fact in facts]
        )
        return self._untwinned(
            [
                replace(fact, embedding=vector)
                for fact, vector in zip(facts, vectors, strict=True)
            ],
            current,
            passage_id,
            language,
        )

    def _untwinned(
        self,
        facts: list[CheckedFact],
        current,
        passage_id: int,
        language: str | None,
    ) -> list[CheckedFact]:
        """Refuses the embedded facts that have a twin among the facts stored.

        Run twice for a passage when drains run side by side: once before the
        store, and once inside it, under the lock `store` holds, against what
        another drain committed in between.
        """
        threshold = self._duplicate_cosine
        written: list[tuple[str, str, list[float]]] = []
        checked: list[CheckedFact] = []
        refused = 0
        for fact in facts:
            if threshold <= 0 or not fact.validated or fact.embedding is None:
                checked.append(fact)
                continue
            vector = fact.embedding
            twin = self._nearest(fact, vector, written, passage_id, language)
            if twin is not None:
                reading = _measured(twin, threshold, self._duplicate_floor)
                fact = replace(
                    fact,
                    gate_scores=scored([reading]),
                    confidence=confidence([reading]),
                )
            if twin is not None and twin.similarity >= threshold:
                refused += 1
                checked.append(_duplicate(fact, twin, threshold))
                continue
            written.append((fact.statement, fact.kind, vector))
            checked.append(fact)
        if refused and current is not None:
            current.set_attribute("extract.duplicates", refused)
        return checked

    def _nearest(
        self,
        fact: CheckedFact,
        vector: list[float],
        written: Sequence[tuple[str, str, list[float]]],
        passage_id: int,
        language: str | None,
    ) -> Twin | None:
        """The closest stored fact that could be this one's twin, or None.

        This passage's own kept facts included. Not one of the facts this
        passage's last reading left, which `store` is about to replace, and
        from the rest of the corpus only one in this fact's language and of
        its kind.
        """
        # ponytail: one index query per candidate. Upgrade: one batched
        # unnest + LATERAL probe per passage.
        probed = self._repository.nearest_fact(
            vector,
            excluding=passage_id,
            language=language,
            kind=fact.kind,
            alike=_naming(fact.statement, language),
        )
        return _closest(fact.statement, fact.kind, language, vector, probed, written)

    def _readers(self, passage: PassageToExtract, current) -> list:
        """Which extractors read one passage, in the order they are applied.

        Usually the one its block type routes to. A passage that merged a
        table with the prose around it gets both: the cell reader for the
        grid and the model for the prose lines alone. Each beside the
        passage it is shown.
        """
        routed = self._extractors.for_block_type(passage.block_type)
        default = self._extractors.default
        if routed is default or not _unread_prose(passage):
            return [(routed, passage)]
        current.set_attribute("extract.prose_beside_a_table", True)
        return [
            (routed, passage),
            (default, replace(passage, sentences=_prose(passage))),
        ]

    def _digested(self, passage: PassageToExtract) -> list[CheckedFact]:
        """Reads what the passage is about, when there is enough to condense.

        Two floors, and the second is the one that costs money. A digest is
        a FIXED size - the prompt asks for two or three sentences, or two to
        six points - so how much it condenses is decided by the passage
        rather than by the model.

        Raises:
            ExtractionFailed: If the model could not give the digest.
        """
        if self._digest is None or passage.claims < _DIGESTIBLE:
            return []
        if len(normalised(passage.text)) < self._digest_min_chars:
            return []
        if self._digest_off:
            raise ExtractionFailed("not asked: the digest model is out of reach")
        return [
            self._checker.check(
                passage, candidate, self._digest.method, self._digest.provenance
            )
            for candidate in self._digest.extract(passage)
        ]

    @staticmethod
    def _missing(passage: PassageToExtract, failure: ExtractionFailed) -> str:
        """Logs a digest that could not be had, and words the note it leaves.

        A digest is optional. One the model cannot give - it is down, or the
        provider's filter refuses the passage every time - costs the passage
        the digest and nothing else: the atomic facts were paid for and are
        what questions rest on. The note, which `DigestQueue` finds by its
        opening, is what `DigestPass` gives the digest from later.
        """
        log.warning(
            "passage %d: no digest, so its facts stand without one: %s",
            passage.id,
            failure,
            extra={"passage.id": passage.id},
        )
        return f"{DIGEST_FAILED}{failure}"[:_NOTE_CHARS]


class DigestPass(ExtractionService):
    """Gives the digest to passages that finished without one.

    The passages are the ones `ExtractionService` left a note on, and only the
    summary and the outline are written: the atomic facts, their ids and what
    questions rest on them are not touched. A digest that fails again leaves
    the note where it was, so this can be run whenever the model is back.
    """

    _repository: DigestQueue  # pyright: ignore[reportIncompatibleVariableOverride]

    def process_next(self) -> int | None:
        """Digests one passage, returning its id, or None when none is left."""
        passage = self._repository.claim()
        if passage is None:
            return None
        with working(
            span, "extract_digest", {"stage": self.name, "passage.id": passage.id}
        ) as current:
            try:
                digests: list[CheckedFact] = []
                note: str | None = None
                if (reason := skipped(passage)) is not None:
                    # What the first pass never sends to a model, finished
                    # with no call: a contents page, a notice, a reference list.
                    current.set_attribute("extract.skipped", reason)
                else:
                    try:
                        digests = self._digested(passage)
                    except ExtractionFailed as failure:
                        note = self._missing(passage, failure)
                        # Counted, not failed: the row stays as it was.
                        if self._missed(passage.id, is_outage(failure), failed=False):
                            return passage.id
                facts = self._deduplicated(
                    digests, current, passage.id, passage.language
                )
                stored = self._repository.store_digests(passage.id, facts, note)
                if note is None:
                    self._done(current)
                current.set_attribute("extract.facts", stored)
                log.info(
                    "passage %d: %d digest fact(s)",
                    passage.id,
                    stored,
                    extra={"facts.stored": stored},
                )
            except Exception as exc:
                # `DigestQueue.fail` keeps the passage extracted, with the
                # reason as its digest note: its facts stand.
                self._fail(passage.id, f"{type(exc).__name__}: {exc}", current)
                log.exception("failed digest of passage %d", passage.id)
            except BaseException:
                # Interrupted: the row goes back as it was, for the next pass.
                self._repository.release(passage.id)
                raise
        return passage.id
