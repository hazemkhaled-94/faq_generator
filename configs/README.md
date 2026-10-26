# Configs

Service configuration and init scripts: every decision, as opposed to a
credential, that lives in git.

`.env` holds the secrets and the model the deployment calls, and
`env/provider.env` the provider's credentials. Neither is in git. A test
checks that every other value in `.env.example` is a placeholder.
[docs/configuration.md](../docs/configuration.md) has the full picture.

| Path | Holds |
|---|---|
| [`env/`](env/) | The tuning files, one per concern |
| [`dagster/`](dagster/) | The Dagster instance and its one code location |
| [`filebeat/`](filebeat/) | What the log shipper reads, and where it puts it |
| [`grafana/`](grafana/) | Three datasources and four dashboards, provisioned |
| [`postgres/`](postgres/) | The init script: the databases, the roles and the two extensions |
| [`seaweedfs/`](seaweedfs/) | The S3 gateway's bucket init and entrypoint |

## `env/`

| File | In git | Holds |
|---|---|---|
| `backend.env` | yes | Pipeline behaviour: parsing, chunking, extraction, topic, question and assessment settings |
| `deployment.env` | yes | Ports, container-side addresses, topology, role names |
| `elasticsearch.env` | yes | The node's certificate paths, security flags and heap. One node serves Argilla and the logs |
| `seaweedfs-filer.env` | yes | Which metadata store the filer uses |
| `orchestration.env` | yes | How long Dagster waits on a stage it started |
| `review.env` | yes | How a review sample is drawn |
| `evaluation.env` | yes | What a golden-set run is called in Phoenix |
| `provider.env` | no | The env vars the model provider needs. Optional: `make setup` copies it from `provider.env.example`. |

A name appears in exactly one of these files, and never in both `.env` and a
file here. `tests/static/test_env_files.py` refuses a second copy. Values that
could be written twice, such as a port inside an address, are derived and
written nowhere (see [docs/configuration.md](../docs/configuration.md)).

[`settings/catalog.py`](../backend/settings/catalog.py) has the one-line help
of each setting. `tests/static/` refuses a catalogued setting that none of
`backend.env`, `deployment.env` and `.env.example` declares.

compose hands each file to its services with `env_file`. The Makefile sources
`backend.env`, `deployment.env`, `provider.env` and `.env` for host commands.
compose also interpolates `${...}` from `deployment.env` and `.env`, so every
compose command goes through `$(COMPOSE_CMD)`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env
```

A bare `podman compose` does not read `deployment.env`. Use `make`, or export
`COMPOSE_ENV_FILES=configs/env/deployment.env,.env`. It cannot be set inside
`.env`.

## `postgres/`

[`init.sh`](postgres/init.sh) creates four databases (the image creates the
application's from `POSTGRES_DB`), the application role, the `grafana_reader`
role, and the `vector` and `pg_trgm` extensions.

It runs only on the first boot of an empty volume. On an existing stack, run
it by hand:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env \
  exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

`grafana_reader` holds `SELECT` only, on the application database and
Phoenix's. On Phoenix's it reads the five tables the Run dashboard queries,
which `make up` grants once Phoenix has made them.

## `grafana/`

Four provisioned dashboards. [docs/operations.md](../docs/operations.md) says
what each shows. A dashboard edited in the UI keeps the edit until its JSON
changes, which overwrites it: write a kept edit back to the JSON.

| File | Dashboard | Reads |
|---|---|---|
| `pipeline-state.json` | 1 · Where the corpus is now | `Pipeline` |
| `pipeline-throughput.json` | 2 · What each stage is doing | `Logs` |
| `pipeline-runs.json` | 3 · One run, end to end | all three |
| `pipeline-logs.json` | 4 · Every line every process wrote | `Logs` |

| Datasource | Points at |
|---|---|
| `Pipeline` | The application database |
| `Logs` | Elasticsearch, the `qa-logs` data stream |
| `Phoenix` | Phoenix's database: the same PostgreSQL server, the same read-only role |

`tests/static/test_dashboards.py` checks each panel against its datasource and
fields.

## `filebeat/`

[`filebeat.yml`](filebeat/filebeat.yml) reads the shared logs volume and
writes the `qa-logs` data stream. `setup.template.append_fields` keeps `stage`
a keyword. An edit to the file does nothing without
`setup.template.overwrite`. See
[`telemetry/README.md`](../telemetry/README.md).

## `seaweedfs/`

[`bucket-init.sh`](seaweedfs/bucket-init.sh) creates the buckets that
`S3_BUCKETS` names, at first boot.

## `dagster/`

[`dagster.yaml`](dagster/dagster.yaml) is the instance, with run storage in
the `dagster` database. [`workspace.yaml`](dagster/workspace.yaml) names the
one code location, [`orchestration/`](../orchestration/README.md).

## Certificates

`certs/` is not in git. `make certs` generates it, and `make dev` runs that.
Elasticsearch reads its certificate, key and `ca.crt`. Argilla, Filebeat and
Grafana read `ca.crt` alone.
