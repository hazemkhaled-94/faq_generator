# Chunking

Cuts the converted document into passages, and reads each one for the
language, the numbered units a fact may cite, and the vocabulary a topic
model is fitted over.

A passage is the unit everything downstream works in, which makes this the
stage whose decisions are hardest to undo: re-chunking deletes every passage
of a document it cuts differently, and the facts, topic memberships and
questions resting on them go with it.

It reads the converted document out of the `parsed` bucket and never the
original PDF, so re-chunking never re-parses.

**A citation is an index, not a quote.** Every sentence is numbered and its
character offsets recorded; a fact says "sentence 4" and the evidence span is
resolved from the offsets. There is no similarity threshold anywhere in this
stage. For a table, the rendered Markdown lines are numbered the same way.

The other two stages that turn a PDF into passages are
[ingestion](../../ingestion/README.md) and [parsing](../parsing/README.md).

## What it does

One worker process, `chunk-worker`, running
`python -m preprocessing.chunking.run --watch`. It claims the next document
whose `chunk_status` is `pending` with `FOR UPDATE SKIP LOCKED`. A worker
killed mid-document leaves its row `in_progress`; the next run's sweep fails
any claim older than the lease.

Passages arrive with `extract_status = 'new'`, so nothing this stage does
starts extraction.

### Step 1 — Cut

Docling's `HybridChunker`, sized by the tokenizer of `EMBEDDING_MODEL` rather
than its own English default, with `CHUNKING_MERGE_PEERS` deciding whether
undersized neighbours sharing a heading are combined. It splits on the
document's structure first and only then merges or divides by token count, so
a passage keeps its heading trail.

Every kind of block is serialised into the passage text as Markdown, tables
included, because evidence has to be a span of the passage text.

**A list keeps its lead-in.** The chunker closes a chunk wherever the budget
runs out, which can fall between a paragraph ending in ":" and the list it
introduces, and every item of that list then reads as a rule of its own.
[`lead_ins_kept`](passages.py) finds a chunk ending on such a lead-in
followed, under the same headings, by a chunk opening with a list item. The
lead-in moves into the list's chunk when the two fit the budget together,
measured as the chunker measures; otherwise it is appended to that chunk's
heading trail, which extraction and question generation both show the
model. A list longer than one chunk carries its lead-in on: every chunk
after, under the same headings, that opens with a list item and follows a
chunk ending on one has the lead-in appended to its trail, wherever the
lead-in itself was kept. A lead-in followed by a sub-heading introduces
what the sub-heading opens, as `The bank charges a fee when:` does a section
per case: it moves into that chunk the same way, and heads every later chunk
opening with a list item under a heading below its own, until a heading at
or above its depth ends what it introduces. A lead-in ends on ":" or on the
full-width "：".

### Step 2 — Number and count

[`chunking_of`](passages.py) drops chunks holding only whitespace, numbers the
rest from 1 contiguously, and counts how many exceed the token budget.

Nothing is discarded on size. `oversized` is a tripwire: the chunker splits on
the same budget it is counted against, so anything above it means the split
did not happen. A document yielding no passages fails as `NoPassages`.

### Step 3 — Read each chunk into a row

Out: the stripped text (the string every offset indexes), the heading trail,
the block type, the converter's item references, one bounding box per page
spanned normalised to a top-left origin, and the cell grid of every table.

**The heading trail starts in its own chapter.** The converter's heading
tree misses a chapter that opens on a decorative title, so the last numbered
heading of the chapter before heads every passage of the next. The page's
running heads and feet name the chapter, and
[`furniture.py`](furniture.py) reads them before the cut, from the
document's own `page_header` and `page_footer` items:

- each is split into fields — on its bars when it has any, otherwise on tabs
  and runs of spaces
- a field that numbers pages is dropped: one with no letter, and every field
  of a shape, its numerals masked, that no two pages print alike ("Page 3 of
  12", "iv")
- a field printed on every page that prints any is dropped: the title, the
  edition
- a field printed on a single page is not read as a chapter field
- what is left, printed on a run of pages and changing from one run to the
  next, is the chapter label; a page printing only the title is in the
  chapter of the last page that printed one, and so is a page printing only
  some of that chapter's fields, its number without its title
- a page printing only single-page fields is in the chapter printed either
  side of it when both sides print the same one, as a facing page's topic
  is
- otherwise its single-page fields name a chapter of one page when its
  running item is laid out as one naming a chapter of several (the same
  fields constant and varying, in the same places) and no page beside it
  prints a single-page field of its own: a short chapter prints its foot on
  one page, while guide words print a different one on every page in a row;
  failing that it is in no chapter, and its passages keep today's trail,
  with no chapter prefix and no reset
- a label's spacing is read off the body: a running head set in a tracked
  font comes out letter-spaced (`Sav ings ac counts`), so the spaces of the
  shortest run of up to eight body words with the same letters are used,
  and the field keeps its own letters and case

Fields are compared with whitespace removed and case folded, so a word the
converter split is the same field. If a field comes back after another took
over, as on pages whose heads alternate between title and chapter, the heads
do not name chapters and none is read.

A title naming the chapter is put before the chapter's first block, so the
chunker starts it with an empty trail and never merges across it. The
chapter's fields then lead the trail, replacing any leading segments that
already repeat them. The title is appended to the document's texts, so no
stored item reference moves.

**Debris is not passage text.** A paragraph that starts with one of the
document's running heads or feet, field for field with whitespace removed,
is the converter reading furniture as body text; a paragraph or heading that
is one letter, when the next text starts with that letter in either case, is
a glossary's index divider — the converter takes some index letters as
headings and some as text. Both move to the furniture layer before the cut.
A lone letter followed by anything else is content — an energy class, a part
marker — and stays. An index has two letters or more, each after the one
before in code-point order once case is folded: the longest such run of the
document's letters is its index, and a letter outside the run stays as
text, whether a stray one the page hides or a class "A" over a line that
happens to start with an A. A document whose letters never run, holding
only one or only letters running backwards, keeps them all. An index whose
language files a letter outside code-point order, as Swedish files Å before
Ä, keeps that one letter as text. A trail segment that holds no letter or digit, such as an
ellipsis, is dropped, and so is one that is a lone conjunction — one of the
language's `_CONJUNCTIONS` in [`furniture.py`](furniture.py), such as `oder`
or `or` — unless it is written in capitals, as a manual heads its section on
the OR gate. A heading that is a lone conjunction between two list items or
two paragraphs, a picture between them aside, is the layout reading the
word between two alternatives as a heading, and is read as the paragraph it
is before the cut, so both alternatives stay in one passage with the word
between them. One between two headed sections stays a heading, out of the
trail, and is glued to neither.

A document with no running head or foot is cut with today's trail.

A table is rendered into the passage text as Markdown rows, and the grid is
kept separately because the rendering loses the header flags, positions and
spans. Each data row is paired with the rendered line that shows it, matched
**by position** — every value must sit at its own column index — and lines
are consumed in order, so two identical rows take two different lines. A
line one table took is no other table's in the same passage.

A data row this passage does not render is dropped: it belongs to another
piece of a table the chunker split. Header rows are kept whether matched or
not and carry no line. A `row_header` cell does **not** make its row a header
row — it marks the stub in the first column of an ordinary data row.

A table is boxed over the rows the passage renders, on the page each row is
printed on. A table parsing joined across a page holds one place per piece,
in order: walked in row order, a row whose top lies above the row before it
opens the next piece, so a passage of the rows on the second page cites that
page, and one of rows from both cites both.

### Step 4 — Read the linguistic surface

`_read` detects each passage's language on its own text, falling back to the
document's when the passage is too short to judge. Per passage rather than per
document, because a document carrying an English summary of a German report
would send half its passages to the wrong pipeline. A table passage takes the
document's language without detection.

Then one spaCy batch per language, producing the **numbered units** a fact may
cite — sentences for prose, each with its finite-verb count; the rendered
lines for a table, a line of prose among them carrying the finite-verb count
of the sentences on it — and the **content lemmas** the topic model is fitted
over.

Every passage is read for vocabulary, a table included, since its headings and
cell values are what it is about.

Three choices sit inside the lemma reading: web addresses are excluded,
because Markdown renders a link as `[text](url)` and the tokenizer offers
every path segment as a word; a lemma must hold a letter and be longer than
one character, because a lemmatiser handed a word from another language
returns the placeholder `--`; and in a language named in
`NLP_CAPITALISED_NOUNS`, a lower-case word tagged as a noun is treated as
foreign and dropped.

### Step 5 — Store

One transaction deletes the document's old passages, inserts the new ones,
writes `oversized` and sets the status, so a document can never read as
chunked while holding another run's passages.

An old passage the new set repeats - the same text, heading trail, sentences
and cell grid - is kept instead: it keeps its id and with it its facts,
topic memberships and embedding, and takes its new ordinal, pages and box in
place. So a re-chunk after a parsing or chunking fix rebuilds only the
passages the fix changed. The delete of every other old passage cascades to
the facts drawn from it and the topic memberships it held.

### Step 6 — Re-read stored passages

[`service.py`](service.py) · `revocabulary`. Applies a change to how language
or vocabulary is read without re-chunking, replacing `passages.language` and
`passages.lemmas` in place. As in a chunking run, a table passage takes its
document's language without detection.

Sentence offsets are deliberately left alone: a fact cites one by index, so
moving them would point every citation in the corpus at different text.

## spaCy here

Used in exactly three places, and the medium models are required:
`de_core_news_sm` does not tag a German modal as a finite verb.

- **Sentence segmentation**, once per passage batch. The offsets it produces
  are what every fact in the corpus cites. A trained pipeline rather than the
  rule-based splitter, which breaks German legal text on `Abs.`, `Nr.` and
  `z. B.`
- **The finite-verb count per sentence**, stored as `predicates` on each
  numbered unit. It is what tells a sentence that asserts something from a
  heading or caption.
- **Content lemmas**, written here so one segmentation serves both stages and
  a fit reads a column instead of re-tokenising the corpus.

Everything else in `nlp/analysis.py` belongs to extraction and question
generation, bar `normalised`, which parsing hashes the body with. Both models
must be present in the image; nothing downloads one at run time. Every fact
records the version of the spaCy pipeline that checked it.

## Inputs and outputs

**In:** one claimed row of `documents` where `chunk_status = 'pending'`, and
the JSON object it names in the `parsed` bucket.

**Written, in PostgreSQL:**

| Table | Holds |
|---|---|
| `passages` | the text, the language, the numbered units, the lemmas, the pages, the heading trail, the block type, the converter's item references, the bounding boxes and the table grids |
| `documents` | `oversized`, the `chunk_status` / `chunk_error` / `chunk_claimed_at` triple, and the `chunk_trigger` its verbs set. Nothing else |

**Written, in SeaweedFS:** nothing.

| Route | Answers |
|---|---|
| `GET /chunking/status` | The queue depth, and whether a worker is on it |
| `POST /chunking/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim` |
| `GET\|POST /chunking/{scope}/{value}/…` | The same, narrowed to one document |
| `GET /passages` | One page of passages, narrowed by document, block type and a text search |
| `GET /passages/types` | The block types the corpus holds |
| `GET /passages/{passage_id}` | One passage in full, with its table cells and numbered sentences |

**Command line:** `make chunk-status`, `chunk-start`, `chunk-stop`,
`chunk-retry`, `chunk-rerun`, `chunk`, `chunk-revocabulary`;
`SHA=<sha>` (`--only document=<sha>`) narrows every one but `chunk`, which
drains the whole queue on the host, for developing the stage. The container
workers build the dataset.

**Read by:** extraction, topic modelling and question generation.

## Configuration

Read from the environment with no defaults in code, and overridable as
[`backend/settings/`](../../settings/README.md) describes.

| Setting | What it does |
|---|---|
| `EMBEDDING_MODEL` | The model whose tokenizer sizes a passage, and the model that will embed it. One name for both |
| `EMBEDDING_MAX_TOKENS` | The model's context window. The chunker cuts a passage to it less the tokens the embedder adds, its prefix and special tokens, so an embedded passage still fits. Keep it equal to the model's context window |
| `CHUNKING_MERGE_PEERS` | Whether undersized neighbours sharing a heading are combined |

There is deliberately no character floor and no character ceiling: a
character count is a different unit from the token budget.

### Language

Shared with parsing.

| Setting | What it does |
|---|---|
| `NLP_MODELS` | `language:model` pairs. The spaCy pipeline per language, and the list the detector may answer with. Both models must be in the image |
| `NLP_DEFAULT_LANGUAGE` | The pipeline that reads a passage whose language neither it nor its document gives. Must be one of the languages `NLP_MODELS` names |
| `NLP_CAPITALISED_NOUNS` | Languages that write every noun with a capital. Empty is valid |

## Tests

```sh
poetry run pytest tests/unit/intake/test_intake_chunking.py
poetry run pytest tests/unit/intake/test_intake_surface.py
poetry run pytest tests/unit/chunking
```

`ChunkDriver` and `RevocabularyDriver` live in
[`tests/unit/intake/intake_drivers.py`](../../../tests/unit/intake/intake_drivers.py),
over `MemoryParsed`, `ChunkRows` and `PassageRows`. `ChunkDriver` also stands
in `ScriptedBuilder` for the passage builder, so the chunk reader, the table
pairing and the real spaCy pipelines are reached by calling `PassageBuilder`
and `chunking_of` directly.

| File | Covers |
|---|---|
| [`test_intake_chunking.py`](../../../tests/unit/intake/test_intake_chunking.py) | Numbering, the token budget, block-type labelling, the row-to-line pairing, the cell grids, the bounding boxes, the failure paths and the re-read |
| [`test_intake_surface.py`](../../../tests/unit/intake/test_intake_surface.py) | The spaCy-backed reading with real pipelines: per-passage language, sentence offsets, predicate counts, table rows, and what becomes vocabulary |
| [`tests/unit/chunking/`](../../../tests/unit/chunking) | The chunk reader's decisions, the numbering of a rendered table, a list nested by its indents, within a column and across a column or page break, past a banner or a table set into the margin, but never side by side nor by another list's type size, and where a list's lead-in goes: into the list's chunk when it fits, into its heading trail when it does not, onto every later chunk of a list longer than one, and across a sub-heading into each section it introduces and no further; and, as a property, that no passage holds part of a list cut from its lead-in or exceeds the budget. [`test_furniture.py`](../../../tests/unit/chunking/test_furniture.py): a chapter named only in its running foot not inheriting the chapter before, a trail not naming its chapter twice, a running foot read as body text and a one-letter index divider dropped while a lone letter that heads nothing stays, and so does one letter, or letters out of order, whatever line follows, ellipses and lone lower-case conjunctions out of the trail while one in capitals stays and a lone conjunction read as a heading between two list items or two paragraphs, or repeated as a paragraph, stays text between its alternatives while one between two headed sections is glued to neither, and a document with no running head, with only title and page numbers, with alternating heads, with a stray one-page header or with heads that differ on every page cut as before; a chapter headed on one page filed under its own foot, guide words inside a chaptered guide and a stray foot inside a chapter naming none, a letter-spaced label spelled as the body spells it, a facing page's own topic kept in its chapter, and a page printing part of its chapter's label opening no chapter |
| [`test_intake_cli.py`](../../../tests/unit/intake/test_intake_cli.py) | Which flag combinations the command line refuses |
| [`tests/property/test_invariants.py`](../../../tests/property/test_invariants.py) | Every non-blank chunk is stored, ordinals run from 1 without a gap, `oversized` never exceeds the passages stored |
| [`tests/integration/test_intake_queues.py`](../../../tests/integration/test_intake_queues.py) | Which columns this stage writes, the transactional replacement and its cascade, and every listing filter |
| [`tests/integration/database/test_queue.py`](../../../tests/integration/database/test_queue.py) | The claim mechanics under concurrent workers |
| [`tests/e2e/test_pipeline.py`](../../../tests/e2e/test_pipeline.py) | One document through every stage, and that dropping the derived data lets chunking repeat without re-parsing |
| [`tests/static/test_intake_pinned.py`](../../../tests/static/test_intake_pinned.py) | That this README carries its three sections |

Not covered, by choice: the behaviour of the real embedding tokenizer on a
corpus, which is a property of the model rather than of this code.

## Limits

- **A re-chunk is destructive where it cuts differently.** It deletes every
  passage of the document it does not repeat exactly, which cascades to the
  facts, memberships and questions resting on them.
- **`oversized` should always read 0.** Above 0 means the chunker's split did
  not happen and those passages will be truncated when embedded.
- **A passage too short to detect a language for, in a document with none,
  gets `NULL`**, which puts it outside every topic model and outside question
  generation.
- **A lead-in that cannot travel with its list is repeated as a heading.**
  When the two do not fit one budget, the lead-in stays at the end of the
  passage before and becomes the last segment of the list passage's
  `section_path`, and of every later passage of the same list. A lead-in
  that does not end in a colon, or one split across two chunks, is not
  carried.
- **A sentence cut at a page or column break is joined back.** A paragraph
  or list item ending on no sentence mark (`.`, `!`, `?`, `:`, `;`),
  followed on the next page or in the next column by a paragraph opening in
  lower case, takes that paragraph's text and its place on the page, so
  the passage's pages and box reach the page the sentence ends on; the
  paragraph moves to the furniture layer. A word the page broke at a hyphen
  is whole again once joined (`Kontofüh-` and `rungsgebühr`), while a
  hyphen a joining word completes (`Zoll- und Steuerrecht`) stays, and so
  does one inside a word the document prints whole elsewhere
  (`non-refundable`). A script
  without case is never joined, and two blocks in one column of one page
  are the document's own break.
- **A flattened list is nested again by its indents.** The converter builds
  every list flat. Within one list, an item whose left edge lies more than
  half a line right of the item before it, in the same column of the same
  page and inside that item's width, nests under it, and a later item back
  at an outer edge returns to that level. Across a column break no level
  opens: the item there returns to the open level its indent from its own
  column's left edge matches — the leftmost edge of the page's paragraphs
  and list items reaching across it, never a picture's, a table's or a
  heading's, which may be set into the margin or run across the page — so
  depth open at a column's foot is not carried into the next column.
  Across a page break no level opens either, and the indent is read off the
  edge before it, so sub-items going on onto a page that holds nothing
  else stay nested; a page with another margin is read on the margin of the
  page before. An item genuinely nested right at the top of a column stays
  at the level before it. A line is the height of the list's shortest
  item, one line in nearly every list, where the median is a two-line
  item's wherever items wrap. A paragraph spanning both columns puts the
  second column's edge at the page's, and an item at the top of that column
  keeps the depth the column before ended on. A nested item is rendered
  indented four spaces per level, as the converter renders a list it nested
  itself; the chunker renders each item on its own, so the indent is put
  back after the cut.
- **A paragraph that only repeats a heading is a heading.** One whose whole
  text, spaces, punctuation and case aside, is a running field or a heading
  of its document (a chapter title the converter read as body text) gets a
  heading put before it, a level below the heading it follows, and moves to
  the furniture layer, so it heads the passage after it instead of standing
  as one. Where it repeats the heading right before it, it only moves. A
  lone conjunction is never one, even where the layout took the same word
  for a heading elsewhere in the document. A
  paragraph that is a page number — a bare integer of up to four digits,
  framed at most by dashes or brackets: `47`, `– 12 –`, `(3)` — moves there
  too. A price, a rate, a phone number, a date or a time with no letter
  beside it (`4,90 €`, `0800 123 4567`, `01.01.2026`) stays, and so does an
  elision mark such as `(…)`. A bare integer alone in its paragraph is still
  read as a page number, even where it is a value printed under its label.
- **A chapter is only as good as its running heads.** One whose opening
  pages print none is in the chapter before until its first page that does.
  Heads that come back out of order name no chapter at all. A field printed
  on one page only is no chapter field, so heads that differ on every page
  name no chapter — read as page numbers when they share a shape once their
  numerals are masked, dropped as single-page fields when they do not — and
  neither does a one-page chapter whose foot is laid out unlike the feet of
  longer chapters, or that sits beside guide words: its passages keep
  today's trail, unprefixed and not reset. So does the last
  right-hand page of a chapter whose facing pages head a topic of their own,
  since the next chapter's label follows it. A
  page whose head carries an extra field printed on several pages — another
  document's foot printed over its own — starts a chapter of its own. Only
  a page printing part of the label after the pages printing all of it
  stays in their chapter: one opening a chapter on less than the pages
  after it print starts a chapter that they then start again, and one
  between two pages printing the whole label breaks the run of the field
  it leaves out, so the heads name no chapter at all. The rule reads only
  the fields, not which chapter a page opens: an opening page whose fields
  all sit inside the previous chapter's label, such as ("Part 1",) after
  ("Part 1", "Chapter A"), is filed into that previous chapter, and the
  chapter it opens starts on the page after it.
- **A running foot is recognised by the document's own.** A foot the
  converter read as body text is dropped only when it repeats one the
  document prints as furniture; another document's foot printed over the
  page is kept as text.
- **Text set inside a picture is not written into passages.** Diagram
  labels, logos and banner text the converter nests in a detected picture
  reach no passage: the chunker does not walk into pictures. On a measured
  corpus what a picture held was mostly diagram labels and page numbers,
  and keeping the real banner text needs a filter that tells it from
  labels, which does not exist yet.
- **A lone conjunction is told by a word table.** In a language missing
  from `_CONJUNCTIONS`, only a segment with no letter or digit leaves the
  trail, and no heading is read as a paragraph. A real one-word heading
  that is such a word in lower case is read as text too.
- **`revocabulary` does not renumber sentences.** A change to how sentences
  are split reaches the corpus only through a re-chunk.
- **`start` and `rerun` skip a document parsing has not finished.** This is
  the only stage that queues over rows it did not create — a document exists
  from the moment it is uploaded — so it is the only one that has to check.
  A start over a half-parsed corpus used to queue the rest and fail every
  row of it on the missing parsed object. The guard is `ChunkQueue.ready`;
  see [`backend/stages/`](../../stages/README.md).
