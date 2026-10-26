# Blob store

Object storage over any S3 implementation, one module per bucket. It is the
only package that builds an S3 client.

## The five buckets

| Bucket | Key | Holds | Expires |
|---|---|---|---|
| `documents` | `{sha[0:2]}/{sha[2:4]}/{sha}.pdf` | The uploaded bytes, exactly as they arrived | never |
| `parsed` | `{sha[0:2]}/{sha[2:4]}/{sha}.json` | The converter's complete output | never |
| `models` | `topics/{database}/{language}.npz` | The factorisation each language's topics came from | replaced by the next fit |
| `export` | `topics/{database}/{language}.html` | Each language's pyLDAvis figure | replaced by the next fit |
| `archive` | `{origin}/{the key it had}@{UTC time}` | What a deletion took from the other four, and the model and figure a fit replaced | `make archive-purge` |

`{database}` is the path of `DATABASE_URL`, so two databases on one store do
not overwrite each other's figure and model. The older key
`topics/{language}.*` is not read: run `make topics-discover` again.

`models` is durable and `export` is disposable: a figure is drawn from a
model, and a model comes only from a fit. `parsed` keeps everything the
converter produced, reached through `passages.doc_item_refs`.

`archive` is the only bucket a deletion writes. `ArchiveBucket.take` copies an
object across and then deletes the original, so a failure between the two
leaves it in both places. See [`archive/`](../archive/README.md).

A key is derived in code from the digest and media type and never stored.
The two-level hex prefix spreads a corpus over 65,536 directories, which
avoids a write hotspot in the SeaweedFS filer. The bucket classes are in
[`s3/bucket.py`](s3/bucket.py).

## Ordering

Nothing is atomic across the object store and the database, so each flow
fixes an order.

- Writing: object first, row last. An object with no row is harmless. A row
  with no object fails every later stage.
- Deleting: the row inside a transaction, the objects moved while it is open,
  the commit last. A failed move rolls the row back.
- Topics go the other way: a fit and `make topics-delete` change the rows
  first and the model and figure after.

## Configuration

Addresses and credentials only, none changeable at runtime. The two keys are
in `.env`, the rest in `configs/env/deployment.env`. `S3_ENDPOINT` is
derived: a host command's from `S3_PORT` (the S3 gateway, published on
127.0.0.1 only), a container's from `S3_CONTAINER_ENDPOINT`. No other
SeaweedFS server publishes a port.

| Setting | What it is |
|---|---|
| `S3_ENDPOINT` | Where the store answers. Empty for AWS |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | The credential. Empty lets boto3 find one (an instance role, a profile) |
| `S3_REGION` | `local` for a self-hosted gateway, the real region for AWS, `auto` for R2 |
| `S3_ADDRESSING_STYLE` | `path` for a self-hosted gateway, `auto` for AWS |
| `S3_BUCKETS` | The buckets [`configs/seaweedfs/bucket-init.sh`](../../configs/seaweedfs/bucket-init.sh) creates at first boot |

An empty value means the SDK's default. A setting not set at all raises, so
a missing env file fails instead of addressing another account. This package
creates no bucket: `bucket-init.sh` does on SeaweedFS, the provider's tooling
elsewhere. `GET /status` reports which required buckets are missing.

## Tests

```sh
poetry run pytest tests/unit/blob_store tests/integration/blob
```

[`test_keys.py`](../../tests/unit/blob_store/test_keys.py) covers keys,
[`test_bucket.py`](../../tests/integration/blob/test_bucket.py) a real S3
gateway and [`test_removal.py`](../../tests/integration/test_removal.py)
deleting a document across the three stores.

## Limits

- A media type with no known file extension raises.
- Every key is stored under the database's name (`<database>/<key>`), so one
  set of buckets serves every database on the stack. A delete, a re-parse and
  `archive-purge` touch only that prefix. `get` and `find` fall back to the
  bare key stored before the prefix existed (read only; `take` copies it).
- `make s3-prefix` copies the objects this database's rows name under its
  prefix, once per database, never over an existing object.
- A fit moves each language's old model and figure to `archive` and writes
  new ones. A language with no figure returns 404 until the next fit or
  `make topics-render`.
- No bucket expires on its own. The `s3.bucket.quota` lines in
  [`bucket-init.sh`](../../configs/seaweedfs/bucket-init.sh) are not run
  automatically.
- `make topics-render` redraws a language's figure from its `models` object.
  It is the only reader of `models`. Losing both buckets costs a re-fit.
  `topics-visualise` reads `export` and does not render.
- One model is kept per language. `--language` picks a language, not a fit.
- An upload that fails on the object store returns a 500 and writes no
  `ingest_events` row.
