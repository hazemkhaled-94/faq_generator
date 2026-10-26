# Configs

Service configuration and init scripts: every decision, as opposed to a
credential, that lives in git.

The credentials and the model the deployment calls are in `.env`, which is not
in git. The provider's credentials are in `env/provider.env`, which is not in
git either. The ports and addresses are in
[`env/deployment.env`](env/deployment.env), because neither is a secret and a
diff should show both. [docs/configuration.md](../docs/configuration.md) has
the full picture.

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
| `backend.env` | yes | How the pipeline behaves: the parsing, chunking, extraction, topic, question and assessment settings |
| `deployment.env` | yes | Where the deployment puts things: the ports, the container-side addresses, the topology, the role names |
| `elasticsearch.env` | yes | The node's certificate paths, security flags and heap. One node serves both Argilla and the logs |
| `seaweedfs-filer.env` | yes | Which metadata store the filer uses |
| `orchestration.env` | yes | How long Dagster waits on a stage it started |
| `review.env` | yes | How a review sample is drawn |
| `evaluation.env` | yes | What a golden-set run is called in Phoenix |
| `provider.env` | no | The env vars the model provider needs. Optional: `make setup` copies it from `provider.env.example`. The four services that call a model read it |

A name appears in exactly one of these files, and never in both `.env` and a
file here. No file overrides another, so no order applies.
`tests/static/test_env_files.py` refuses a second copy. A value that could be
written twice, such as a port inside an address or a password inside a
connection string, is derived and written nowhere.
[docs/configuration.md](../docs/configuration.md) lists the derived values.

`backend.env` is the long form: each setting carries paragraphs explaining
what it does. [`settings/catalog.py`](../backend/settings/catalog.py) carries
the one-line version. `tests/static/` refuses a catalogued setting that none
of `backend.env`, `deployment.env` and `.env.example` declares.

compose hands each file to the services that need it with `env_file`. The
Makefile sources `backend.env`, `deployment.env`, `provider.env` and `.env`
for host commands. `deployment.env` is also one of the two files compose
interpolates `${...}` from, so every compose command goes through
`$(COMPOSE_CMD)`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env
```

## `postgres/`

[`init.sh`](postgres/init.sh) creates four databases (the image creates the
application's from `POSTGRES_DB`), the application role, the `grafana_reader`
role, and the `vector` and `pg_trgm` extensions.

It runs only on the first boot of an empty volume. On a stack that already has
one, run it by hand:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env \
  exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

`grafana_reader` holds `SELECT` and nothing else. It is granted on two
databases, the application's and Phoenix's, which the Run dashboard reads
together. On Phoenix's it reads only the five tables that dashboard queries,
which `make up` grants once Phoenix has made them.

## `grafana/`

Four dashboards over three datasources, all provisioned. What each dashboard
shows is in [docs/operations.md](../docs/operations.md). A dashboard edited in
the UI keeps the edit until its JSON changes, which overwrites it. Write a
kept edit back to the JSON.

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
| `Phoenix` | Phoenix's own database: the same PostgreSQL server, a different database, the same read-only role |

Logs say what happened once. The tables say what is true now. Dashboard 3
crosses that split, which is why `Phoenix` exists as a datasource. A run is
`questions.run_id` on one side and, for a run named with `RUN_ID`, a project
named `<position>-<stage>-<name>` on the other.

`tests/static/test_dashboards.py` checks each panel against the datasource and
the fields that serve it.

## `filebeat/`

[`filebeat.yml`](filebeat/filebeat.yml) reads the shared logs volume and
writes the `qa-logs` data stream.

Two settings in it matter, and [`telemetry/README.md`](../telemetry/README.md)
explains them. `setup.template.append_fields` keeps `stage` a keyword rather
than analysed text. Without `setup.template.overwrite`, an edit to the file
does nothing.

## `seaweedfs/`

[`bucket-init.sh`](seaweedfs/bucket-init.sh) creates the buckets that
`S3_BUCKETS` names, at first boot.

## `dagster/`

[`dagster.yaml`](dagster/dagster.yaml) is the instance, with its run storage
in the `dagster` database. [`workspace.yaml`](dagster/workspace.yaml) names
the one code location, [`orchestration/`](../orchestration/README.md).

## Certificates

`certs/` is not in git. `make certs` generates it, and `make dev` runs that.
Elasticsearch reads its certificate, its key and `ca.crt`. Argilla, Filebeat
and Grafana read `ca.crt` alone. Each container is given only the files it
reads, so `ca.key` reaches none.

## Limits

- `init.sh` runs once, on an empty volume. Every change to it needs re-running
  by hand on a stack that already exists.
- A Grafana dashboard edited in the UI keeps the edit until its JSON changes,
  which overwrites it. Write a kept edit back to the JSON.
- `provider.env` is optional. `make setup` writes it from
  `provider.env.example`, and its absence is not an error.
- An edit to `filebeat.yml` does nothing without `setup.template.overwrite`.
- Everything here is in git except `provider.env`, and `.env` is not. A value
  in the wrong one either leaks or goes missing. `.env` holds the secrets and
  the model the deployment calls. A test checks that every other value in
  `.env.example` is a placeholder.
- A bare `podman compose` does not read `deployment.env`. Use `make`, or
  export `COMPOSE_ENV_FILES=configs/env/deployment.env,.env`. It cannot be set
  inside `.env`, because compose resolves the file list before reading one.
