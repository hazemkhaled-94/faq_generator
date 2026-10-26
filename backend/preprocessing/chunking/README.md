# Chunking

Cuts the converted document into passages and reads each one for its
language, the numbered units a fact may cite, and the vocabulary a topic model
is fitted over.

Chunking reads the converted document from the `parsed` bucket, never the
PDF. Every later stage works on passages, and re-chunking deletes every
passage of a document that it cuts differently, with the facts, topic
memberships and questions resting on them.

A citation is an index, not a quote. Every sentence is numbered and its
character offsets recorded. A fact says "sentence 4", and the evidence span is
resolved from the offsets. For a table, the rendered Markdown lines are
numbered the same way.

The neighbouring stages are [ingestion](../../ingestion/README.md) and
[parsing](../parsing/README.md).

## What it does

One worker process, `chunk-worker`, runs
`python -m preprocessing.chunking.run --watch`. It claims the next document
whose `chunk_status` is `pending` with `FOR UPDATE SKIP LOCKED`. A worker
killed mid-document leaves its row `in_progress`, and the next run's sweep
fails any claim older than the lease. Passages arrive with
`extract_status = 'new'`, so chunking does not start extraction.

### Step 1: Cut

Docling's `HybridChunker` splits on the document's structure first and then
merges or divides by token count, using the tokenizer of `EMBEDDING_MODEL`.
`CHUNKING_MERGE_PEERS` decides whether undersized neighbours under one
heading are combined. Every block, tables included, is serialised into the
passage text as Markdown, because evidence must be a span of that text.

A list keeps its lead-in. The chunker can close a chunk between a paragraph
ending in ":" and the list it introduces. [`lead_ins_kept`](passages.py)
finds a chunk ending on such a lead-in, followed under the same headings by a
chunk that opens with a list item, and then:

- Moves the lead-in into the list's chunk when both fit the token budget.
- Otherwise appends the lead-in to that chunk's heading trail, which
  extraction and question generation show the model.
- For a list longer than one chunk, appends it to the trail of every later
  chunk that opens with a list item under the same headings.
- For a lead-in followed by a sub-heading, does the same for each section the
  sub-heading opens, until a heading at or above its depth ends it.

A lead-in ends on ":" or the full-width "：". A list item ending on one stays
where it is and heads the list after it through the trail.

### Step 2: Number and count

[`chunking_of`](passages.py) drops chunks holding only whitespace, numbers
the rest from 1 without a gap and counts how many exceed the token budget.
`oversized` counts passages above the budget, which the split should make
impossible. Nothing is discarded on size. A document yielding no passages
fails as `NoPassages`.

### Step 3: Read each chunk into a row

Each row holds the stripped text (the string every offset indexes), the
heading trail, the block type, the converter's item references, one bounding
box per page spanned (top-left origin) and the cell grid of every table.

**The heading trail starts in its own chapter.** The converter's heading tree
misses a chapter that opens on a decorative title, so the last numbered
heading of the previous chapter would head every passage of the next.
[`furniture.py`](furniture.py) therefore reads the document's `page_header`
and `page_footer` items before the cut:

- Each item is split into fields on bars, or else on tabs, runs of spaces and
  a dash, middle dot or bullet between spaces. A hyphen
  (`IV - Other provisions`) does not split.
- A field that numbers pages ("Page 3 of 12", "iv") is dropped, and so is a
  field printed on every page that prints any (the title, the edition). A
  field printed on one page is not a chapter field.
- What is left, printed on a run of pages and changing from one run to the
  next, is the chapter label. A page printing only the title, or only some of
  the chapter's fields, belongs to the chapter of the last page that printed
  one.
- A page printing only single-page fields belongs to the chapter on both
  sides of it when both print the same one. Otherwise it names a one-page
  chapter only when its running item is laid out like those of multi-page
  chapters, and else it is in no chapter.

Fields are compared with whitespace removed and case folded. Heads that
alternate between title and chapter name no chapters.

A title naming the chapter is put before the chapter's first block, so the
chunker never merges across it. If the first page holds its own heading, the
title goes before that heading. The heading counts as one of the label's
fields when it matches word for word, or when one is the other with words cut
from its start beside a number: `B Geschäftskunden` under `Geschäftskunden`,
`Kapitel 3: Gebühren` under `Gebühren`. Any other heading (`Fees` under
`Fees and charges`) is a section of the chapter and opens nothing. The
chapter's fields then lead the trail, replacing leading segments that repeat
them. The title is appended to the document's texts, so no stored item
reference moves.

**Debris is not passage text.** These move to the furniture layer before the
cut:

- A paragraph that is a running head or foot, with page numbers allowed after
  it. A line that opens with the foot's name and goes on (an imprint, a
  contact line) stays.
- A one-letter paragraph or heading followed by text starting with that
  letter, which is a glossary's index divider. The longest run of the
  document's lone letters in code-point order is the index, and any other
  lone letter stays as text.
- A paragraph that only repeats a heading or running field of the document.
  It gets a heading put before it, a level below the heading it follows.
- A paragraph that is a page number: a bare integer of up to four digits,
  framed at most by dashes or brackets (`47`, `– 12 –`), in the top or bottom
  tenth of its page and equal to the page number plus the document's offset.
  A value beside or under its label, a price, a phone number and a date stay.
- A body paragraph in the top or bottom tenth of its page whose left edge and
  top are within a point of the running items of three or more other pages.
- A lone list item that repeats a heading of the document.

A trail segment with no letter or digit (an ellipsis) is dropped. So is a
lone conjunction, one of the language's `_CONJUNCTIONS` in
[`furniture.py`](furniture.py) (`oder`, `or`), unless it is in capitals. A
conjunction heading between two list items or two paragraphs is read as a
paragraph. A heading that is a member of a list group is read as the list
item it is.

A table is rendered into the passage text as Markdown rows, and the grid is
kept separately, because the rendering loses header flags, positions and
spans. Each data row is paired with the rendered line that shows it, matched
**by position**: every value must sit at its own column index. Two identical
rows take two lines. A data row the passage does not render belongs to
another piece of a split table and is dropped. Header rows are kept and carry
no line. A `row_header` cell does **not** make its row a header row. It marks
the stub in the first column of a data row. A table is boxed over the rows
the passage renders, on the page each is printed on.

### Step 4: Read the linguistic surface

`_read` detects each passage's language on its own text and falls back to the
document's language when the passage is too short. A chunk ends where its
paragraphs or list items change language. A table passage takes the
document's language without detection.

One spaCy batch per language then produces the numbered units a fact may cite
and the content lemmas the topic model is fitted over. The units are
sentences for prose, each with its finite-verb count, and the rendered lines
for a table, where a prose line carries the finite-verb count of the
sentences on it. Every passage is read for vocabulary, a table included.

Three rules apply to lemmas. Web addresses are excluded, because Markdown
renders a link as `[text](url)` and the tokenizer offers every path segment
as a word. A lemma must hold a letter and be longer than one character. In a
language named in `NLP_CAPITALISED_NOUNS`, a lower-case word tagged as a noun
is treated as foreign and dropped, unless the text writes no word after its
first with a capital.

### Step 5: Store

One transaction deletes the document's old passages, inserts the new ones,
writes `oversized` and sets the status, so a document never reads as chunked
while holding another run's passages.

An old passage that the new set repeats (same text, heading trail, sentences
and cell grid) is kept. It keeps its id, and with it its facts, topic
memberships and embedding, and takes its new ordinal, pages and box. A
re-chunk therefore rebuilds only the passages that changed. The delete of
every other old passage cascades to its facts and topic memberships.

### Step 6: Re-read stored passages

`revocabulary` in [`service.py`](service.py) applies a change to how language
or vocabulary is read without re-chunking. It replaces `passages.language` and
`passages.lemmas` in place and moves `facts.language` with the passage each
fact opens on, so the dedup probe still finds the facts. A table passage takes
the document's language without detection. Sentence offsets are left alone,
because moving them would point every citation at different text.

## spaCy

spaCy is used in three places, and the medium models are required, because
`de_core_news_sm` does not tag a German modal as a finite verb:

- Sentence segmentation, once per passage batch. Its offsets are what every
  fact cites. The rule-based splitter is not used, because it breaks German
  legal text on `Abs.`, `Nr.` and `z. B.`
- The finite-verb count per sentence, stored as `predicates` on each numbered
  unit. It tells a sentence that asserts something from a heading or caption.
- Content lemmas, written here so one segmentation serves both stages.

Both models must be in the image, and nothing downloads one at run time.

## Inputs and outputs

The input is one claimed row of `documents` with `chunk_status = 'pending'`
and the JSON object it names in the `parsed` bucket. Nothing is written to
SeaweedFS. Extraction, topic modelling and question generation read the
output.

| Table | Holds |
|---|---|
| `passages` | The text, language, numbered units, lemmas, pages, heading trail, block type, item references, bounding boxes and table grids |
| `documents` | Only `oversized`, `chunk_status`, `chunk_error`, `chunk_claimed_at` and `chunk_trigger` |

| Route | Answers |
|---|---|
| `GET /chunking/status` | The queue depth, and whether a worker is on it |
| `POST /chunking/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim` |
| `GET\|POST /chunking/{scope}/{value}/…` | The same, narrowed to one document |
| `GET /passages` | One page of passages, narrowed by document, block type and a text search |
| `GET /passages/types` | The block types the corpus holds |
| `GET /passages/{passage_id}` | One passage in full, with its table cells and numbered sentences |

Commands: `make chunk-status`, `chunk-start`, `chunk-stop`, `chunk-retry`,
`chunk-rerun`, `chunk` and `chunk-revocabulary`. `SHA=<sha>`
(`--only document=<sha>`) narrows every target except `chunk`, which drains
the whole queue on the host, for developing the stage. The container workers
build the dataset.

## Configuration

Settings are read from the environment and can be overridden as
[`backend/settings/`](../../settings/README.md) describes.

| Setting | What it does |
|---|---|
| `EMBEDDING_MODEL` | The model whose tokenizer sizes a passage and that embeds it |
| `EMBEDDING_MAX_TOKENS` | The model's context window. The chunker cuts a passage to it less the tokens the embedder adds, so an embedded passage fits. At least 64: a lower value is refused |
| `CHUNKING_MERGE_PEERS` | Whether undersized neighbours under one heading are combined |

There is no character floor or ceiling, because a character count is a
different unit from the token budget.

### Language

The language settings are shared with parsing.

| Setting | What it does |
|---|---|
| `NLP_MODELS` | `language:model` pairs: the spaCy pipeline per language and the languages the detector may answer with. Both models must be in the image |
| `NLP_DEFAULT_LANGUAGE` | The pipeline for a passage whose language neither it nor its document gives. Must be a language `NLP_MODELS` names |
| `NLP_CAPITALISED_NOUNS` | Languages that write every noun with a capital. May be empty |

## Tests

```sh
poetry run pytest tests/unit/intake/test_intake_chunking.py
poetry run pytest tests/unit/intake/test_intake_surface.py
poetry run pytest tests/unit/chunking
```

Unit tests stand in only for the database and the passage builder
(`ChunkDriver` and `RevocabularyDriver` in
[`tests/unit/intake/intake_drivers.py`](../../../tests/unit/intake/intake_drivers.py)).

| File | Covers |
|---|---|
| [`test_intake_chunking.py`](../../../tests/unit/intake/test_intake_chunking.py) | Numbering, the token budget, row-to-line pairing, cell grids, bounding boxes, the failure paths and the re-read |
| [`test_intake_surface.py`](../../../tests/unit/intake/test_intake_surface.py) | The spaCy reading with real pipelines: language, sentence offsets, predicate counts and vocabulary |
| [`tests/unit/chunking/`](../../../tests/unit/chunking) | The chunk reader: lists, lead-ins, running heads and feet, chapters, debris and page joins |
| `tests/property/test_invariants.py` | Every non-blank chunk is stored, ordinals run from 1 without a gap, `oversized` never exceeds the passages stored |
| `tests/integration/test_intake_queues.py`, `tests/integration/database/test_queue.py` | The columns this stage writes, the transactional replacement and the claim mechanics |
| `tests/e2e/test_pipeline.py` | One document through every stage |
| [`test_intake_pinned.py`](../../../tests/static/test_intake_pinned.py) | That this README has its three sections |

## Limits

- A re-chunk is destructive where it cuts differently. It deletes every
  passage of the document that it does not repeat exactly, with the facts,
  memberships and questions resting on them.
- `oversized` should read 0. Above 0 means the split did not happen and those
  passages will be truncated when embedded.
- A passage too short to detect a language for, in a document with none, gets
  `NULL`. That puts it outside every topic model and question generation.
- `start` and `rerun` skip a document parsing has not finished. Chunking is
  the only stage that queues over rows it did not create, since a document
  exists from upload, so it alone checks. The guard is `ChunkQueue.ready`;
  see [`backend/stages/`](../../stages/README.md).
- `revocabulary` does not renumber sentences. A change to sentence splitting
  reaches the corpus only through a re-chunk.
- A lead-in set as a heading reaches no passage when sub-headings of its own
  level follow it. The chunker replaces it with the next heading.
- A lead-in that cannot travel with its list is repeated as a heading. When
  the two do not fit one budget, it stays at the end of the previous passage
  and becomes the last segment of the `section_path` of the list passage and
  every later passage of the list. A lead-in that does not end in a colon, or
  that is split across two chunks, is not carried.
- A German list item heavy with English words can cut its list. An item of
  product names (`Premium Card mit Cashback, Travel Insurance und Priority
  Pass Lounge Access`) detects as English and ends the chunk around it.
- A contact line of the foot's name and a bare phone number is dropped.
  `Musterbank AG | 0800 123 456` has no letter after the name, so it reads as
  the foot with a page number. A labelled field (`Kundenservice: 0800 123
  456`) stays.
- A heading that holds ` > ` is spelled ` › ` in `section_path`, because
  readers split the path on ` > `. `headings_of` in
  `database.qa_generator.passages` writes the heading back as printed. A
  passage stored before this keeps its old path until its document is
  chunked again, and is then replaced with the facts resting on it.
- Text set inside a picture reaches no passage, because the chunker does not
  walk into pictures. A footnote the converter attaches to a picture is
  written beneath its caption, as a table's is.
- A chapter is only as good as its running heads. Opening pages that print
  none belong to the chapter before. Heads that return out of order, differ on
  every page, or sit beside guide words name no chapter, and their passages
  keep the unprefixed trail. A head whose fields are parted only by single
  spaces (`Preisverzeichnis Kreditkarten Seite 4`) is one field and names no
  chapter.
- In a language missing from `_CONJUNCTIONS`, only a trail segment with no
  letter or digit is dropped.
- A sentence cut at a page or column break is joined back. A paragraph or
  list item that ends on no sentence mark (`.`, `!`, `?`, `:`, `;`), followed
  on the next page or column by a paragraph opening in lower case, takes that
  paragraph's text and place on the page, and the paragraph moves to the
  furniture layer. A word broken at a hyphen is made whole (`Kontofüh-` and
  `rungsgebühr`), except before a joining word (`Zoll- und Steuerrecht`). A
  rest that opens in capitals or with a figure also joins when the tagger
  reads the first block as ending on an article, preposition, conjunction or
  auxiliary and the second as opening with a noun or a figure: `Die Gebühr für
  die` and `Ersatzkarte beträgt 15 EUR.` are one sentence.
- A flattened list is nested again by its indents. An item whose left edge
  lies more than half a line right of the item before it, in the same column
  and page, nests under it. Across a column or page break no level opens. A
  nested item is rendered indented four spaces per level.
