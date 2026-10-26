# Ingestion

Takes an uploaded file, decides whether the corpus accepts it, and if so
stores the bytes and writes one row. It runs synchronously in the API
process, with no queue or worker, and does only what takes about a second.

A document's identity is the SHA-256 of its bytes: the primary key of
`documents`, the object key in both buckets and the basis of duplicate
detection. `ingest_events` records every attempt, refused ones included.

The next stages are [parsing](../preprocessing/parsing/README.md) and
[chunking](../preprocessing/chunking/README.md).

## What it does

The route calls `IngestService.ingest`. The document arrives with every
stage at `new`.

### Step 1: Refuse before reading the file

The route checks the declared `Content-Length` before it parses the
multipart form. A length above `MAX_FILE_SIZE_MB` plus the multipart framing
(`_FRAMING` in the upload route) is refused without reading the body, and
[`refuse_oversized`](service.py) writes the event with the filename
`unnamed`. A request declaring no length is refused `length_required` and
writes no event. Any other request is read to at most one byte past the
limit and measured by the checks below.

### Step 2: Run the checks

The checks run cheapest first, and nothing is written until all pass.

| Order | Check | Refusal |
|---|---|---|
| 1 | `size_bytes > MAX_FILE_SIZE_MB` | `too_large`, with both figures |
| 2 | The leading bytes are not in `ALLOWED_MIME_TYPES` | `unsupported_type`, naming what was detected |
| 3 | The digest is already in `documents` | `duplicate_bytes` |
| 4 | The PDF does not open, is password protected, has more than `PARSING_MAX_PAGES` pages or is not read within `PARSING_TIMEOUT_SECONDS` | `unsupported_type`, with the reader's reason, or the count and the setting |

### Step 3: Write the object, then the row

The object is written first, so a failed row write leaves a harmless object.
The object carries S3 user metadata: the digest, the original filename, the
time and the pipeline version.

### Step 4: Delete

[`removal.py`](removal.py) offers three operations.

- `delete` removes the object in `documents`, the object in `parsed` and the
  row. The cascade removes the passages, facts, memberships and questions.
  Only the `ingest_events` rows survive. The objects are moved while the
  row deletion is open, and it commits only after every move succeeded. A
  failed move rolls the rows back and returns the objects already moved.
- `delete_derived` drops the passages and what cascades from them, returns
  `chunk_status` to `new` and keeps both objects.
- `delete_every`, behind `make wipe`, runs `delete` on every document, then
  drops the `ingest_events` rows.

No deletion destroys data. An AFTER DELETE trigger copies the rows into
`archived_rows`, and the objects are **moved** to the `archive` bucket. See
[`archive/`](../archive/README.md).

## Inputs and outputs

The input is one born-digital PDF, up to `MAX_FILE_SIZE_MB`, posted to
`POST /documents` or picked on the Upload page. SeaweedFS keeps the bytes
unchanged, without expiry, at `documents/{sha[0:2]}/{sha[2:4]}/{sha}.pdf`.

| Table | Holds |
|---|---|
| `ingest_events` | Filename, size, outcome, reason and the document it became |
| `documents` | Digest, media type, page and character counts, and every stage's status |

| Route | Answers |
|---|---|
| `POST /documents` | Uploads one file and reports what became of it |
| `GET /documents` | Lists the corpus with stage statuses and passage counts |
| `GET /documents/names` | Lists digests and filenames |
| `GET /documents/{sha256}/file` | Returns the stored bytes |
| `DELETE /documents/{sha256}` | Removes the document and everything derived from it. `twinless` in the answer counts facts that were refused as duplicates of this document's and now lack a source. The extraction worker re-decides them when its queue is empty, or `make extract-dedup` does where no worker runs |
| `DELETE /documents/{sha256}/derived` | Removes the passages and what cascades, and keeps both objects. It gives the same count; `make delete-derived` runs the replay |

```sh
make documents
make ingest DIR=<directory>
make delete SHA=<sha256> CONFIRM=<database>
make delete-derived SHA=<sha256> CONFIRM=<database>
make wipe CONFIRM=<database>
```

`make ingest` sends every PDF in a host directory through this service.

## Configuration

Settings are read from the environment on every upload and overlaid with any
stored override. Tuning lives in
[`configs/env/backend.env`](../../configs/env/backend.env).

| Setting | What it does |
|---|---|
| `MAX_FILE_SIZE_MB` | Largest accepted upload, at most 150. Keep it equal to `server.maxUploadSize` in `frontend/.streamlit/config.toml` |
| `PARSING_MAX_PAGES`, `PARSING_TIMEOUT_SECONDS` | The parse stage's settings, read here too (0 pages: no cap; timeout 1800 s as shipped). The Upload page gives up after 60 s and reports a timeout, while the api keeps reading and stores the PDF if it finishes |
| `ALLOWED_MIME_TYPES` | Comma-separated. May name only types this build detects from leading bytes. Any other value stops the service at start-up |

The `pipeline-version` in object metadata is the `version` in
`pyproject.toml`.

## Tests

```sh
poetry run pytest tests/unit/intake/test_intake_ingestion.py
poetry run pytest tests/unit/ingestion tests/integration/test_ingest.py
```

Unit tests stand in only for the database, the three buckets and the PDF
reader. Integration tests run against a real PostgreSQL and SeaweedFS.
[`test_intake_pinned.py`](../../tests/static/test_intake_pinned.py) checks that
parsing handles exactly the types this stage accepts.

## Limits

- Different bytes with the same text pass ingestion. Parsing refuses them on
  `content_sha256`.
- An upload refused on `Content-Length` is recorded as `unnamed`. One
  declaring none writes no `ingest_events` row.
- An upload that fails on the object store returns a 500 and writes no
  `ingest_events` row.
