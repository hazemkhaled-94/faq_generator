# Blob store

Object storage, one module per bucket, over any S3 implementation.

The one package that builds an S3 client. A service asks for a bucket; it
never builds a client or learns a credential.

## The five buckets

| Bucket | Key | Holds | Expires |
|---|---|---|---|
| `documents` | `{sha[0:2]}/{sha[2:4]}/{sha}.pdf` | The uploaded bytes, exactly as they arrived | never |
| `parsed` | `{sha[0:2]}/{sha[2:4]}/{sha}.json` | The converter's complete output | never |
| `models` | `topics/{database}/{language}.npz` | The fitted factorisation each language's topics were read off | replaced by the next fit |
| `export` | `topics/{database}/{language}.html` | Each language's pyLDAvis figure, and nothing else | replaced by the next fit |
| `archive` | `{origin}/{the key it had}@{UTC time}` | What a deletion took out of the other four, and the model and figure a fit replaced | `make archive-purge` |

`{database}` is the path of `DATABASE_URL`, so a second database on the same
store (a test copy, a staging fit) neither overwrites nor archives another's
figure and model. The key `topics/{language}.*` of earlier releases is not
read: a database upgraded from one runs `make topics-discover` again.

`models` and `export` are one fit's two halves, and which is which matters.
`models` holds the factorisation; `export` holds a picture drawn from it. The
picture is derivable from the model and the model is derivable from nothing
short of another fit, so they have opposite durability contracts despite
being written in the same pass. Until `models` existed only the picture was
kept, which made a disposable view the one durable trace of an hour's work.

The same split as `parsed`, one level up: the database holds what a stage
reads or a person queries — each topic's top terms, its label, its coverage
flag — and the matrix those were read off stays in the object store.

`archive` is the only one written by a **deletion**. `ArchiveBucket.take`
copies an object across and then deletes the original — in that order, so a
failure between the two leaves it in both places rather than neither. The key
keeps the bucket it came out of as a prefix and the time it was taken as a
suffix, so a second deletion of the same key keeps a second copy. See
[`archive/`](../archive/README.md).

A key is **derived in code and never stored**: it is a pure function of the
digest and the media type, so a row holding a stale path is not a state this
can reach.

The two-by-two hex prefix is not cosmetic. The SeaweedFS filer keys its
metadata on (directory hash, name), so one flat directory becomes a write
hotspot; two levels of 256 spread a corpus over 65,536 directories.

`parsed` keeps the converter's **complete** output, so nothing it produced is
ever lost. The database holds only what a later stage reads or a person
queries; figures, formulas as LaTeX, code blocks, per-line geometry and the
heading tree stay here, reachable through `passages.doc_item_refs`. That is
what makes re-chunking cheap.

## Ordering

Nothing is atomic across an object store and a database, so every flow fixes
an order and accepts the one failure that order leaves.

**Writing:** object first, row last. An object with no row holds exactly the
bytes its key means and is harmless; a row pointing at a missing object fails
every later stage. If the row cannot be written, the object is left.

**Deleting:** the row inside a transaction, the objects moved while it is
open, the commit last. A failed move rolls the row back and gives back what
was moved, so a row is never left without its file.

The topics go the other way both times: a fit and `make topics-delete` write
or delete the rows first and the model and figure after.

The bucket classes are shared behaviour in [`s3/bucket.py`](s3/bucket.py)
and one subclass per bucket, so a caller names the bucket it means rather
than a string.

## Configuration

Addresses and credentials only, none configurable at runtime. The two keys
are in `.env`, the rest in `configs/env/deployment.env`. `S3_ENDPOINT` is
derived: a host command's from `S3_PORT`, the S3 gateway's port, published
on 127.0.0.1 only; a container's from `S3_CONTAINER_ENDPOINT`. SeaweedFS's
master, filer and volume servers publish no port.

| Setting | What it is |
|---|---|
| `S3_ENDPOINT` | Where the store answers. Empty for AWS, which resolves its own |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | The credential. Empty to let boto3 find one — an instance role, a profile |
| `S3_REGION` | `local` for a self-hosted gateway, the real region for AWS, `auto` for R2 |
| `S3_ADDRESSING_STYLE` | `path` for a self-hosted gateway, `auto` for AWS |
| `S3_BUCKETS` | The buckets [`configs/seaweedfs/bucket-init.sh`](../../configs/seaweedfs/bucket-init.sh) creates at first boot |

**Empty is a value and absent is a mistake.** Empty means the SDK's own
default, which is what makes AWS reachable; a name that is not set at all
raises rather than falling back, so a deployment missing its env file fails
here instead of addressing somebody's real account.

Buckets are created by [`bucket-init.sh`](../../configs/seaweedfs/bucket-init.sh)
on SeaweedFS and by the provider's own tooling anywhere else. Nothing here
creates one; `GET /status` reports which are missing.

`GET /status` reports whether each required bucket exists, as classes rather
than names.

## Tests

```sh
poetry run pytest tests/unit/blob_store tests/integration/blob
```

| File | Covers |
|---|---|
| [`test_keys.py`](../../tests/unit/blob_store/test_keys.py) | The object key a stored document is found under |
| [`test_bucket.py`](../../tests/integration/blob/test_bucket.py) | Storing and reading objects against a real S3 gateway |
| [`test_removal.py`](../../tests/integration/test_removal.py) | Deleting a document across the three stores that hold one |

## Limits

- **A media type with no known file extension raises rather than storing.**
  A key nothing could find again is worse than a refusal.
- **Every key is stored under the database's name** (`<database>/<key>`),
  because the buckets are one set for every database on the stack and a
  digest is the same in each. A delete, a re-parse and `archive-purge` in
  one database touch only its prefix. `get` and `find` fall back to the bare
  key a store holds from before the prefix (read, never written or
  deleted; `take` copies it), and `make s3-prefix` copies the ones this
  database's rows name (its documents, archived documents and topic keys)
  under its prefix, once per database, and never over an object the prefix
  already holds.
- **Rewriting an object in `documents` or `parsed` is harmless to the
  database that wrote it.** The key is content-addressed.
- **A fit replaces both `models` and `export`.** It moves each language's old
  model and figure to `archive` before writing its own. A language with no
  figure 404s until the next fit, or until `make topics-render` draws one
  from its `models` object.
- **No bucket expires on its own.** The `s3.bucket.quota` lines in
  [`bucket-init.sh`](../../configs/seaweedfs/bucket-init.sh) are operator
  notes that file says are not run automatically, and no TTL is set anywhere.
  Each bucket is bounded by what overwrites or purges it, which is the
  `Expires` column above and nothing else.
- **A topic figure cannot be redrawn from the database.** pyLDAvis is
  prepared from the whole term-topic matrix and the database keeps only each
  topic's top terms. It can be redrawn from the `models` object for its
  language, which is what that bucket is for; losing both costs a re-fit.
  `topics-visualise` reads the `export` bucket — it does not render.
- **`make topics-render` is the only thing that reads `models` back.** It
  redraws a language's figure from its stored model, which is what makes
  `export` disposable. No route serves a model; a reader wanting the matrix
  itself fetches the key by hand.
- **There is one model per language, and no way to ask for an older one.**
  The next fit moves it to `archive` and writes its own, because the database
  holds one fit's topics per language — `replace` drops a fitted language's
  rows and writes the new fit's. A figure drawn from a previous model would
  number its topics off rows that are gone, so `--language` picks which
  language to redraw, not which fit.
- **An upload that fails on the object store writes no `ingest_events`
  row.** A stored upload's event is written with its document row, after the
  object; an unreachable bucket is a 500.
