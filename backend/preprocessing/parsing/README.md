# Parsing

Turns the uploaded PDF into a structured document: headings in a hierarchy,
tables as cell grids, text in reading order. It is the expensive stage, so it
runs in a worker, one document at a time, off a queue.

The converted document is stored before anything reads values from it, so
the two refusals in Step 7 fire after the object exists. A re-parse is
stored only after they pass, so a refused one leaves the earlier converted
document in place.

Parsing does not start the next stage. It writes neither `page_count` nor
`chunk_status`, so a re-parse leaves the old passages standing and chunking
must be redone.

The neighbouring stages are [ingestion](../../ingestion/README.md) and
[chunking](../chunking/README.md).

## What it does

One worker process, `parse-worker`, runs
`python -m preprocessing.parsing.run --watch`. It claims the next document
whose `parse_status` is `pending` with `FOR UPDATE SKIP LOCKED`. A worker
killed mid-document leaves its row `in_progress`, and the next run's sweep
fails any claim older than the shared lease; see
[`backend/stages/`](../../stages/README.md).

The worker sits on the internal `parsing` network with the Hugging Face hub
offline and reads Docling's weights from the `models` volume. `make install`
puts them there through `make docling-weights`, which runs
[`weights.py`](weights.py) in a container that can reach the hub.

### Step 1: Dispatch on the media type

[`PipelineRegistry`](pipelines/__init__.py) picks the pipeline for the media
type ingestion detected. An unhandled type fails the document with the list
of handled types.

### Step 2: Decide whether the document is scanned

A document is scanned when `char_count / page_count` is below
`PARSING_OCR_CHAR_THRESHOLD`, or when it has no counts. OCR is not
implemented, so a scanned document is refused here.

A digital PDF page with at most `PARSING_OCR_CHAR_THRESHOLD` characters
(a merge tool's `Seite 2 von 3` stamp included) and a picture over at least
half of it is image-only. The document is parsed for its text pages, and the
page is named in a warning, in the `image-only-pages` metadata and in
`documents.parse_error`, which the documents page, the API and
`make parse-status` show. A re-parse clears it.

### Step 3: Convert

A document longer than `PARSING_MAX_PAGES` is refused before conversion. The
pipeline counts the pages with pymupdf and fails the row, naming the count
and the setting. `make parse-retry` returns refused documents to the queue.

Docling holds every page it converts, and a document too long for the
worker's 4 GB ends the container with the claim held. Measured offline, a
conversion needs 1.5 GB at 35 pages, 2.0 GB at 70, 2.4 GB at 139 and 4.9 GB
at 278, so the shipped limit of 180 needs about 3.1 GB. The curve did not
reproduce on a second host. Raise the limit together with the worker's
memory limit in `compose.yaml`.

Docling accepts PDF only, with heading hierarchy and table structure on and
OCR off. Any failure becomes a `ConversionFailed` carrying the exception's
type and message. `PARSING_TIMEOUT_SECONDS` is Docling's document timeout.
When it runs out, Docling returns the finished pages without raising, and a
conversion that did not end in success is failed and not stored.

### Step 4: Remove struck and hidden words, then repair the text

A PDF marks a deletion with a line drawn through the word, which the
converter ignores. [`_unstruck`](pipelines/pdf.py) rereads the source with
pymupdf and removes every word a stroke deletes. A stroke qualifies when it:

- is horizontal (a stroked path of level lines, each rising or falling less
  than 0.3 pt, or a filled bar) and longer than 2 pt
- covers at least 60% of the width of a run of letters or digits, or 50% of
  a punctuation mark, so a stroke through "six" in "six/eight" leaves "eight"
- sits between 0.15 and 0.55 times the font size above the word's baseline,
  which is through the x-height in any colour

An underline, a table rule and the frame of a highlight are not strikes.
Struck words are removed from every text item, its `orig` and every table
cell. An item left with no text moves to the `invisible` content layer, so no
other item's reference moves.

Text a clip path hides, such as a diagram's label layer, is removed the same
way. So is text no reader sees (`page.get_texttrace()`): render mode 3, fully
transparent, set under 2 points, or white with no fill and no picture under
it. It is dropped only on a page whose other text paints ink, so a scan's OCR
layer stays. The count of dropped characters is noted in
`documents.parse_error` and the metadata `hidden-characters`.

A source pymupdf cannot open, or a page the two readers size differently, is
left as converted, with a warning.

[`_mend`](pipelines/pdf.py) then rewrites every string, in the text items and
the table grid:

- Compose to NFC and spell a Latin or Armenian ligature as its letters (`ﬀ`
  as `ff`). Superscripts, fractions and full-width forms stay.
- Rejoin words the page broke across two lines, at a soft hyphen or at a
  real hyphen between letters. The join is skipped before a word that
  completes a hanging hyphen (`und`, `als`, `bis`, `vs.` and kin, `JOINING`
  in [`nlp/text.py`](../../nlp/text.py)), as in `Zoll- und Steuerrecht`. A
  compound keeps its hyphen where the document prints it whole elsewhere:
  `third- party` becomes `third-party`.
- Drop control characters and format characters (zero-width marks, bidi
  marks and isolates). A zero-width joiner stays between letters of a script
  that spells words with one (`_JOINING_SCRIPTS`) and inside an emoji
  sequence. A C1 control is read as the cp1252 character it stands for.
- Fold every other kind of space to U+0020.

[`_tabled`](pipelines/pdf.py) then joins tables the converter broke, reading
the grid and the case, never a word. The rules are:

- A table with no header row that follows a table of its width, on the same
  page or the next, is that table's rest. Its rows go under the first
  table's. It moves to the furniture layer, so no stored reference moves.
  A rest the converter flagged as having a header joins as data when each
  cell of its first row uses its column's data font and holds a figure where
  that data does.
- A row with no label whose cell continues in lower case and none of whose
  cells ends a sentence joins the row above. A second tier of one service
  under an empty label is a known fault, and its test is marked as expected
  to fail.
- A label alone on a row that opens in lower case, or closes the bracket the
  label above left open, joins that label. A row holding only a label, over
  a row whose label opens in lower case, is that label's head and joins it.

Each join is mended again.

### Step 5: Store the converted document

The converter's exported dictionary is stored as one JSON object in the
`parsed` bucket, keyed by the source digest, with the digest and the Docling
version as metadata. A re-parse overwrites it, but only after Step 7 passes.
Chunking reads this object.

### Step 6: Read the values the row holds

[`DocumentAnalyser`](analysis.py) renders the body as text (tables included,
running headers and footers excluded), finds the title, detects the language
and hashes the body with whitespace collapsed and case folded. A conversion
with no body text fails as `EmptyDocument`. A language that `NLP_MODELS` does
not name fails as `UnconfiguredLanguage`.

The PDF pipeline offers title candidates, best first (`Conversion.titles`):

1. The first heading, when it heads the document, is set in the largest type
   of its page and does not end in a comma, colon or semicolon.
2. The cover: the block of lines in the largest type of the first page with
   text.
3. The running head every page prints, unless it is a heading.

The analyser takes the first, or the document's first section heading if
there is none. A title another document holds takes the next candidate, as
`Title - Next`.

[`_interleaved_pages`](pipelines/pdf.py) names the two-column pages where the
converter joined a line of each column into one block, in the parse note and
in the object's `interleaved-pages` metadata. Nothing is reordered. On the 30
football and 50 shop PDFs it names no page.

### Step 7: Two refusals after the fact

A conversion whose low score is under `PARSING_MIN_CONFIDENCE` fails. The low
score is Docling's: each page's 5% quantile of its component scores, averaged
over the pages, so one garbled page among many is averaged away. A conversion
with no score is not checked. Every page whose own low score is under the
floor is named in `documents.parse_error` and in the object's
`low-confidence-pages` metadata, and the document still parses. A page with
no text, picture or drawing is not named.

A document whose `content_sha256` another document holds fails too, which
catches the same report released as a second PDF. The failed copy's digest is
not written, so every later copy fails against the one that parsed.

The digest is taken over the mended text. After a change to `_mend` that
rewrites a body beyond case and spacing, run `make parse-rerun` to write
every digest anew. A document whose re-parse fails keeps its old digest.

A new document that fails either refusal leaves a converted object in the
`parsed` bucket with no row, collected when the document is deleted.

## Inputs and outputs

The input is one claimed row of `documents` with `parse_status = 'pending'`
and the object it names in the `documents` bucket.

The stage writes only these columns on `documents`: `title`, `language`,
`content_sha256`, `parse_confidence`, `parse_confidence_low`, `parse_run_id`,
`parse_trace_id`, `parse_span_id`, `parse_status`, `parse_error`,
`parse_claimed_at` and `parse_trigger`. The converted document goes to
`parsed` at `{sha[0:2]}/{sha[2:4]}/{sha}.json`.

| Route | Answers |
|---|---|
| `GET /parsing/status` | The queue depth, and whether a worker is on it |
| `POST /parsing/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim`. A whole-stage `rerun` or `reclaim` needs `?confirm=true` |
| `GET\|POST /parsing/{scope}/{value}/…` | The same, narrowed to one document |

Commands: `make parse-status`, `parse-start`, `parse-stop`, `parse-retry`,
`parse-rerun` and `parse`. `SHA=<sha>` (`--only document=<sha>`) narrows every
target except `parse`, which drains the whole queue on the host, for
developing the stage. The container workers build the dataset.
[Chunking](../chunking/README.md) reads the output.

## Configuration

Settings are read from the environment and can be overridden as
[`backend/settings/`](../../settings/README.md) describes. Tuning is in
[`configs/env/backend.env`](../../../configs/env/backend.env).

| Setting | What it does |
|---|---|
| `PARSING_OCR_CHAR_THRESHOLD` | Characters per page below which a document is scanned and refused. Also the most text an image-only page may hold |
| `PARSING_MIN_CONFIDENCE` | Lowest low score a conversion may carry, in [0, 1]: Docling's, averaged over the pages (Step 7) |
| `PARSING_TABLE_MODE` | TableFormer mode, `fast` or `accurate`. Any other value is refused when the pipeline is built |
| `PARSING_HEADING_HIERARCHY` | Whether the converter rebuilds the heading tree. On also turns on `generate_parsed_pages` |
| `PARSING_TIMEOUT_SECONDS` | Longest one conversion may run. Also the longest an upload may spend reading a PDF's text |
| `PARSING_MAX_PAGES` | Longest document converted, in pages; 0 for any. A longer one is refused before conversion and at upload, naming this setting |
| `DOCLING_ARTIFACTS_PATH` | Where Docling's weights are. A real path or absent: an empty value resolves to the working directory |

The language settings are described under chunking.

Docling uses its own `docling-parse` backend, which reports the font style
that ranks heading levels. `enforce_same_font` is **off**: on, a text cell is
cut wherever the font changes.

## Tests

```sh
poetry run pytest tests/unit/intake/test_intake_parsing.py
poetry run pytest tests/unit/parsing
```

Unit tests stand in only for the database, the two buckets and Docling
(`ParseDriver` in
[`tests/unit/intake/intake_drivers.py`](../../../tests/unit/intake/intake_drivers.py)).

| File | Covers |
|---|---|
| [`test_intake_parsing.py`](../../../tests/unit/intake/test_intake_parsing.py) | Dispatch, the scanned decision, store-before-read order, a refused re-parse, the failure paths, the confidence floor, the content-digest refusal and the analyser |
| `tests/unit/parsing/` | The text repair, the table joins, and struck and clipped words, with the cases that must stay unchanged |
| [`test_intake_regression.py`](../../../tests/unit/intake/test_intake_regression.py) | Fixes that nothing at run time would report if undone |
| `tests/integration/test_intake_queues.py`, `tests/integration/database/test_queue.py` | The columns this stage writes, and the claim mechanics |
| `tests/e2e/test_pipeline.py` | One document through every stage, with the converter stood in for |
| [`test_intake_pinned.py`](../../../tests/static/test_intake_pinned.py) | That the PDF pipeline handles exactly the types ingestion accepts |

Not covered: the lines of `PdfPipeline.convert` that call Docling, whose
models are a multi-gigabyte download.

## Limits

- A re-parse does not re-chunk. Redo chunking after it.
- A duplicate by content costs a stored file and a failed row.
- Only a drawn strike is read. A strikeout annotation, a font strike or a
  line that is not horizontal is kept as text, as is a struck word that the
  converter and pymupdf split or spell differently.
- A struck word is removed without a record in the converted document.
