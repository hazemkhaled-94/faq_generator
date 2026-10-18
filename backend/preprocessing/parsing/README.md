# Parsing

Turns the uploaded PDF into a structured document: headings in a hierarchy,
tables as cell grids, text in reading order.

This is the expensive stage — layout and table-structure models over every
page — so it runs in a worker, one document at a time, off a queue.

The converted document is written to its bucket **before** anything reads
values out of it, so a bug in the reading does not mean paying for the
conversion twice. Two refusals therefore fire after the object exists. A
re-parse is written only after them, so a refused one leaves the earlier
converted document, which the standing passages were cut from, in place.

Nothing this stage does starts the next one. `complete` writes neither
`page_count`, which is ingestion's, nor `chunk_status`, which is chunking's,
so a re-parse leaves the old passages standing.

The other two stages that turn a PDF into passages are
[ingestion](../../ingestion/README.md) and [chunking](../chunking/README.md).

## What it does

One worker process, `parse-worker`, running
`python -m preprocessing.parsing.run --watch`. It claims the next document
whose `parse_status` is `pending` with `FOR UPDATE SKIP LOCKED`. A worker
killed mid-document leaves its row `in_progress`; the next run's sweep fails
any claim older than the lease every stage shares; see
[`backend/stages/`](../../stages/README.md).

The worker sits on the internal `parsing` network, which holds only
Postgres, the S3 gateway and Phoenix, with the Hugging Face hub offline:
Docling's weights are read from the `models` volume, never fetched.
`make install` puts them there through `make docling-weights`, which runs
[`weights.py`](weights.py) in a container that can reach the hub.

### Step 1 — Dispatch on the media type

[`PipelineRegistry`](pipelines/__init__.py) picks the pipeline that owns the
format ingestion detected from the leading bytes. A type no pipeline handles
fails the document with the list of types that are handled.

### Step 2 — Decide whether the document is scanned

`char_count / page_count < PARSING_OCR_CHAR_THRESHOLD`, read from counts that
already exist. A document with no counts counts as scanned.

OCR is not implemented, so a scanned document is refused here, where the
reason is still known.

### Step 3 — Convert

Docling, built to accept PDF and no other input format, with heading
hierarchy and table structure on and OCR off. Any failure becomes a
`ConversionFailed` carrying the exception's type and message.
`PARSING_TIMEOUT_SECONDS` is passed to Docling as its own document timeout.
When it runs out, or a page cannot be parsed, Docling returns only the
finished pages without raising; a conversion that did not end in success is
failed with Docling's errors rather than stored as the whole document.

### Step 4 — Remove struck-through words, then repair the text

A PDF marks a deletion with nothing but a line drawn through the word: no
annotation, no font flag, no colour. The converter keeps the word, so
"a maximum of six eight" reaches a passage where the page shows only
"eight". [`_unstruck`](pipelines/pdf.py) reads the source again with
pymupdf and finds every word a stroke deletes. A stroke qualifies when it:

- is horizontal — a line of a stroked path made of nothing but level lines
  (each rising or falling less than 0.3 pt), or a filled bar — and longer
  than 2 pt, or than 0.15 × the font size where that is less, so a full stop
  struck in small type goes
- covers at least 60% of the word's width
- sits, its own line width included, between 0.15 and 0.55 × the font size
  above the word's baseline: through the x-height, in any colour

One path may draw many strokes, so each of its lines, and each rectangle of
a filled path made of rectangles alone, is read on its own. A path striking
two words of a line keeps the word between them, and one striking a word on
each of two lines strikes both.

So an underline below the baseline, a table rule above the capitals or below
the descenders, and the frame of a highlight are not strikes. The struck
words are removed from every text item and its `orig` — section headers
included — and from every table cell, whose provenance box holds them. An
item left with no text moves to the `invisible` content layer, so a struck
bullet is not rendered as an empty one and a struck heading heads nothing;
it stays in place, so no other item's reference moves. The
converter's boxes may count up from the page foot and pymupdf's count down,
so each box is turned to a top-left origin before it is matched. The string
is aligned with the page word by word in reading order, so the same word
printed unstruck elsewhere in it stays.

Text a clip path hides — a diagram's label layer — reaches the converter
too, and goes the same way. Each page is read twice, with its clip and
without, and a character of the second read is hidden when the first holds
no same character within 1 pt of it: compared character to character, not by
position alone, so a label hidden over a visible line or inside a large
letter's box is still found, while a word a writer drew twice for a bold
face is in both reads twice and stays. What the second read sets past the
page's edge is dropped first, as the converter drops it, so a label cut at
the edge is matched as the converter spells it. An item every page word in
whose box is hidden goes whole, however the converter spelled it. Text drawn
invisible is in both reads, so a scan's OCR layer is never hidden.

A page that strikes and hides nothing is never touched. A source pymupdf
cannot open, or a page the two readers give different sizes, is left as
converted, with a warning.

[`_mend`](pipelines/pdf.py) then rewrites every string before anything reads
it:

- compose to NFC
- rejoin words the page broke across two lines — both the soft-hyphen
  spelling and a real hyphen before a lower-case continuation, unless a word
  that completes a hanging hyphen follows (`und`, `als`, `bis`, `vs.` and
  their kin, `JOINING` in [`nlp/text.py`](../../nlp/text.py), every
  configured language's at once), because `Zoll- und Steuerrecht` is not a
  broken word; and a compound broken at its own hyphen keeps it where the
  document prints the word whole elsewhere, so `third- party` is
  `third-party` and not `thirdparty`
- drop control and zero-width characters
- fold every other kind of space to U+0020

It runs on the text items *and* on the table grid. A character a model cannot
reproduce is one no quote of it can match.

[`_tabled`](pipelines/pdf.py) then joins the tables the converter broke,
reading the grid and the case and never a word:

- a table with no header row that comes right after a table of its width, on
  the same page or the next, with at most a picture between them, is that
  table's rest: its rows go under the first table's, and it moves to the
  furniture layer, so no reference a passage stores moves
- a rest whose first row the converter flagged a header is a rest all the
  same when each cell of that row is set in the font most of the first
  table's data in its column is set in, and not in the font of its header
  there, read off the PDF with pymupdf; the row then joins as data. A second
  table whose header is set as the first's stays apart, and so does the rest
  of a table whose header and data share one font
- a row with no label in its first column, one cell of which goes on in
  lower case, and over which no cell ends a sentence (`.`, `!`, `?` — a
  colon opens what follows), is a wrapped cell's rest and joins the row
  above, whatever its other cells open with (`9,90 EUR` going on
  `(inkl. MwSt.)`); a second tier of one service under an empty label,
  `online` with its own fee, joins it too, a known fault its tests mark
  as expected to fail
- a row holding a label and nothing else, over a row whose label opens in
  lower case, is that label's head and joins it

Each join is mended again as `_mend` mends a line, since a word the cell
wrapped at a hyphen (`Kontofüh-` over `rungsentgelt`) is whole only once its
halves meet.

A script without case joins no row, which is the safe side.

### Step 5 — Store the converted document

The converter's own exported dictionary, one JSON object in the `parsed`
bucket keyed by the source digest, carrying the digest and the Docling
version that converted it as its metadata. Re-parsing overwrites, but only
once Step 7 has passed. This is what chunking reads, so re-chunking never
re-parses.

### Step 6 — Read the values the row holds

[`DocumentAnalyser`](analysis.py) renders the body as text — table values
included, running headers and footers excluded — finds the title, detects the
language, and hashes the body with whitespace collapsed and case folded. A
conversion with no body text fails as `EmptyDocument`.

### Step 7 — Two refusals after the fact

A conversion whose **lower-bound** confidence is under
`PARSING_MIN_CONFIDENCE` fails; the lower bound rather than the mean, because
it says how bad the worst of the document is.

A document whose `content_sha256` another document already holds fails too.
Ingestion catches a file uploaded twice by its bytes; the same report
released as a second PDF has different bytes and the same text.
`content_sha256` is not written on the copy that fails, so every later copy
fails against the one that parsed.

Both run after Step 5, so a new document failing either leaves a converted
form in the `parsed` bucket with no row pointing at it. It is collected when
the document is deleted. A re-parse failing either leaves the earlier
converted form untouched.

## Inputs and outputs

**In:** one claimed row of `documents` where `parse_status = 'pending'`, and
the object it names in the `documents` bucket.

**Written, in PostgreSQL:** on `documents` — `title`, `language`,
`content_sha256`, `parse_confidence`, `parse_confidence_low`, the run, trace
and span that parsed it (`parse_run_id`, `parse_trace_id`, `parse_span_id`),
the `parse_status` / `parse_error` / `parse_claimed_at` triple, and the
`parse_trigger` its verbs set. Nothing else.

**Written, in SeaweedFS:** `parsed`, at
`{sha[0:2]}/{sha[2:4]}/{sha}.json` — the converted document, regenerable from
the uploaded bytes.

| Route | Answers |
|---|---|
| `GET /parsing/status` | The queue depth, and whether a worker is on it |
| `POST /parsing/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim` |
| `GET\|POST /parsing/{scope}/{value}/…` | The same, narrowed to one document |

The routes only move rows between statuses; the worker picks up whatever
became claimable on its next poll.

**Command line:** `make parse-status`, `parse-start`, `parse-stop`,
`parse-retry`, `parse-rerun`, `parse`; `SHA=<sha>` (`--only document=<sha>`)
narrows every one but `parse`, which drains the whole queue on the host, for
developing the stage. The container workers build the dataset.

**Read by:** [chunking](../chunking/README.md).

## Configuration

Read from the environment with no defaults in code, and overridable as
[`backend/settings/`](../../settings/README.md) describes. Tuning is in
[`configs/env/backend.env`](../../../configs/env/backend.env).

| Setting | What it does |
|---|---|
| `PARSING_OCR_CHAR_THRESHOLD` | Characters per page below which a document is treated as scanned and refused |
| `PARSING_MIN_CONFIDENCE` | Lowest lower-bound confidence a conversion may carry and be kept, in [0, 1] |
| `PARSING_TABLE_MODE` | TableFormer mode: `fast` or `accurate`. Anything else is refused when the pipeline is constructed |
| `PARSING_HEADING_HIERARCHY` | Whether the converter rebuilds the heading tree. Turning it on also turns on `generate_parsed_pages` |
| `PARSING_TIMEOUT_SECONDS` | Longest one conversion may run |
| `DOCLING_ARTIFACTS_PATH` | Where Docling's weights are. Must be a real path or absent — an empty value resolves to the working directory |

The language settings are shared with chunking and described there.
Connection settings belong to `database` and `blob_store`.

Docling is configured with its own `docling-parse` backend rather than
pypdfium2, because that is the backend reporting the font style heading
levels are ranked by. `enforce_same_font` is turned **off**; left on, a text
cell is cut wherever the font changes, and an f-ligature is set in a font of
its own.

## Tests

```sh
poetry run pytest tests/unit/intake/test_intake_parsing.py
poetry run pytest tests/unit/parsing
```

Non-UI tests act through a driver. `ParseDriver` lives in
[`tests/unit/intake/intake_drivers.py`](../../../tests/unit/intake/intake_drivers.py),
over `MemoryDocuments`, `MemoryParsed` and `ParseRows`. Only the database,
the two buckets and Docling itself are stood in for.

| File | Covers |
|---|---|
| [`test_intake_parsing.py`](../../../tests/unit/intake/test_intake_parsing.py) | Dispatch, the converter taking PDF alone, the scanned decision at its boundaries, the store-before-read ordering, a refused re-parse leaving the earlier converted form, all five failure paths, the confidence floor, the content-digest refusal, and the analyser |
| [`test_text_repair.py`](../../../tests/unit/parsing/test_text_repair.py) | The text repair, case by case, on real corpus strings |
| [`test_tables.py`](../../../tests/unit/parsing/test_tables.py) | A table's rest on the next page joined to it, past a picture, and when its first row was flagged a header but is set in the data's font, and not one with a header in the header's font, after a table whose header is set as its data, of another width or with text between; a wrapped cell's rest, one going on in a bracket or a German noun, and a wrapped label's head joined to their row, a second tier under an empty label joined as well (expected to fail), a cell wrapped at a hyphen made one word and one wrapped inside a compound the document prints keeping its hyphen, and a row whose label did not span kept |
| [`test_strikethrough.py`](../../../tests/unit/parsing/test_strikethrough.py) | Struck words removed from paragraphs, `orig`, headings and table cells, from boxes of either origin; each line of one path read as its own stroke; underlines, table rules, a frame's edge, partial strokes and a short tick beside a price removing nothing; a struck full stop removed; clipped labels removed over visible text, inside a large letter, at the page's edge and spelled apart, and a fake-bold line and an OCR layer kept; an unreadable source changing nothing; and, as a property, a page with no strike coming out unchanged |
| [`test_intake_regression.py`](../../../tests/unit/intake/test_intake_regression.py) | Fixes nothing at run time would report if they were undone |
| [`test_intake_cli.py`](../../../tests/unit/intake/test_intake_cli.py) | Which flag combinations the command line refuses |
| [`tests/property/test_invariants.py`](../../../tests/property/test_invariants.py) | The repair is idempotent and leaves no control character |
| [`tests/integration/test_intake_queues.py`](../../../tests/integration/test_intake_queues.py) | Which columns this stage writes and which it must leave alone |
| [`tests/integration/database/test_queue.py`](../../../tests/integration/database/test_queue.py) | The claim mechanics, including `SKIP LOCKED` and the abandoned-claim sweep |
| [`tests/e2e/test_pipeline.py`](../../../tests/e2e/test_pipeline.py) | One document through every stage, with the converter stood in for |
| [`tests/static/test_intake_pinned.py`](../../../tests/static/test_intake_pinned.py) | That the PDF pipeline handles exactly the types ingestion may accept, and that this README carries its three sections |

The regression suite holds one test each for: every space codepoint folding
to U+0020 and every zero-width mark removed, named one at a time; every
control character except newline and tab dropped; the repair reaching `orig`
and the table grid; `enforce_same_font` off and the backend Docling's own;
`generate_parsed_pages` following `PARSING_HEADING_HIERARCHY`; `do_ocr` off;
table structure on with mode, timeout and weights path passed through; a bad
table mode refused at construction; the converter built once; and a
conversion Docling finished only in part refused.

Not covered: the five lines of `PdfPipeline.convert` that call Docling, whose
models are a multi-gigabyte download. OCR and any format other than PDF are
not covered because neither exists.

## Limits

- **A re-parse does not re-chunk.** After re-parsing, redo chunking.
- **A failed parse can leave an object in the `parsed` bucket.** It is
  collected when the document is deleted.
- **A duplicate by content costs a stored file and a failed row.**
- **Only a drawn strike is read.** A deletion marked by a strikeout
  annotation, by a font, or on a line of text that is not horizontal is kept
  as text. So is a struck word the converter and pymupdf split or spell
  differently, because the two are aligned word by word.
- **A struck word is removed, not reported.** Nothing in the converted
  document records that the page deleted it.
