# Frontend

A Streamlit application with one page per stage. A page runs its own stage
and no other.

The frontend calls one address, `BACKEND_URL`, and has no access to the
database or the object store. `PHOENIX_BASE_URL` is never called: it is
written into links that a browser follows, so compose leaves it as the host
sees it.

## The pages

| Page | Lists | Runs | Over | Configures |
|---|---|---|---|---|
| Upload | nothing | ingestion | the files chosen | ingestion |
| Documents | documents | parsing | a document | parsing |
| Passages | passages | chunking | a document | chunking |
| Facts | facts | extraction | a passage | extraction |
| Topics | topics | topic modelling | the whole corpus | topics |
| Questions | questions | question generation | a topic | questions |
| Assessment | the judge's verdicts | the evaluation phase | the kinds ticked | assessment |
| System health | components and containers | nothing | nothing | the platform |

Documents also has the **Pipeline** panel. It asks the orchestrator to run
every stage except the topic fit, in order. See
[`lib/pipeline.py`](lib/pipeline.py). Assessment can be switched off: see
[`backend/assessment/`](../backend/assessment/README.md). System health reads
`GET /services`.

Chunking replaces all of a document's passages, and extraction writes all of
a passage's facts, so on those pages a picked row runs through the unit the
stage queues.

### Links from a question

On the Questions page, Type is what a question asks for (`question_type`)
and Kind is how it was written (single, needs_both, compound). A picked
question links to two things:

- Phoenix, from `questions.span_id` (the gate decision) and
  `questions.trace_id` (the whole topic). Without `PHOENIX_BASE_URL` on the
  `streamlit` service, the ids show as text.
- The prompt as sent, inline, from `questions.prompt_version` and
  `question_type` through `GET /prompts`.

### How an artefact was produced

Documents, Passages, Facts, Topics and Questions each have a **How this was
produced** fold, from [`lib/lineage.py`](lib/lineage.py) over
`GET /lineage/{kind}/{id}`. It shows the chain from document to passages,
facts, topics and questions, with each step's stage number, verdict, judge
opinion and span link.

On a question, the fold also lists every gate that read it. Gates after the
one that refused the question are absent, because the checker stops at the
first failure. The fold ends with **Where to look next**: the Grafana Run
dashboard for the run, the Dagster asset the stage materialises, the Argilla
datasets, and the Phoenix span and trace. The addresses come from
`GET /services` (`SERVICE_URLS`), cached for ten minutes. A tool the
deployment does not publish gets no line.

## The shape of every page

The six stage pages that list something draw these panels, top to bottom:

```
the few figures worth seeing on arrival
the stage's controls, then one row of folds: `Analysis`, how the stage
  works, and `Configuration`
the search box, the filters and the pager, in one panel
the table
— only once a row is picked —
everything held about that row, as one table of every field it has
```

Upload draws its figures, the upload form and, after an upload, a table of
what became of each file. A selection above 20 files or 200 MB in all is
refused (`UPLOAD_MAX_FILES` and `UPLOAD_MAX_BYTES` in
[`lib/config.py`](lib/config.py)), and the page names `make ingest
DIR=<directory>` for larger loads. The cap is checked after the selection is
in memory. A timeout shows as unknown: check the Documents list.

A setting added to [`settings/catalog.py`](../backend/settings/catalog.py)
appears on its page without a frontend change.

Only Documents (with or without what was derived) and Topics (all at once)
have a delete box.

Redo asks for confirmation in two clicks and says what it costs. A re-chunk
or re-extraction deletes the questions resting on that work, a re-judge
blanks the stored verdicts, a re-parse replaces the stored parse, and a
re-ask of the questions calls the model for every topic. A whole-stage Redo
is sent with `confirm=true`, which the API requires. A picked bridge fact
offers no Redo and names `make extract-bridge`.

Counts and controls redraw every few seconds. A verb only moves rows between
statuses; a worker does the work.

## Layout

| Path | Holds |
|---|---|
| [`app.py`](app.py) | The entry point: `st.navigation` over the views |
| [`views/`](views/) | One module per page, run top to bottom on every interaction |
| [`lib/`](lib/) | Shared panels (`page.py`, `stage.py`, `catalog.py`, `configure.py`, `lineage.py`) and the API clients in `lib/backend/` |
| [`styles.css`](styles.css) | The custom styling, on top of the theme |

## Themes and colour

The palette is `#A100FF` (core purple), `#460073` and `#7500C0` (deep),
`#C2A3FF` and `#E6DCFF` (light), `#FF50A0`, `#224BFF` and `#05F2DB`
(secondary) and neutral greys. The app shows no logo. Type is
Graphik where installed, otherwise Arial: Graphik is licensed and not
shipped.

[`.streamlit/config.toml`](.streamlit/config.toml) holds the theme under
`[theme.light]` and `[theme.dark]`. The app follows the browser's
`prefers-color-scheme`, and the toolbar menu switches it. A colour set in
`[theme]` itself, or `theme.base`, applies to both themes.
[`styles.css`](styles.css) holds the rest.

Purple fills the one control in a group that commits something (Start, Fit,
Save, Accept). Red is used only for deletion. Every other button is outlined,
and a control that would do nothing is greyed out, not hidden.

Rules for editing the styles:

- Keep every colour pair at 4.5:1 contrast or better in both themes.
- Do not set a translucent colour on an element and its descendants. It
  compounds through Streamlit's nested button label and leaves an empty
  button, so `--qa-disabled` is an opaque pair.
- Set `textColor` and `primaryColor` in both sidebar palettes. A section that
  inherits them from the page puts dark type on a dark panel.
- Tables use the light-header variant, because the grid draws header text on
  a canvas that no stylesheet can change.

## Configuration

| Setting | Where | What it does |
|---|---|---|
| `BACKEND_URL` | compose, from `BACKEND_CONTAINER_URL` in `configs/env/deployment.env`; the Makefile derives the host's | The one address the frontend calls |
| `PAGE_SIZE` | `configs/env/deployment.env` | Rows per page in the listings |
| `PHOENIX_BASE_URL` | compose and the Makefile, from `PHOENIX_PORT` | Where a browser reaches Phoenix. Optional: unset shows the ids as text |
| `LOG_LEVEL` | `configs/env/deployment.env` | The log level |

`BACKEND_URL` and `PAGE_SIZE` are required. A variable in an env file must
also be listed in the `streamlit` service's `environment` in `compose.yaml`,
or it does not reach the frontend. A missing or out-of-range `PAGE_SIZE`
(1 to 500) raises an error that names it. A missing `BACKEND_URL` raises a
bare `KeyError`.

In [`.streamlit/config.toml`](.streamlit/config.toml),
`server.maxUploadSize` must match `MAX_FILE_SIZE_MB`, and
`server.allowedHosts` (`localhost` and `127.0.0.1`) needs a proxy's name
added.

## Tests

```sh
poetry run pytest tests/frontend
```

An `AppTest` runs each view with the backend stubbed, covering what a page
does with an answer, including a refusal. The tests need no container and no
spaCy, and `make test-fast` runs them.

| File | Covers |
|---|---|
| [`test_views.py`](../tests/frontend/test_views.py) | The rules every page keeps |
| `test_*_page.py` | Assessment, facts, questions and topics in depth, against a scripted backend |
| `test_pipeline_panel.py`, `test_configuration_panel.py`, `test_lineage_panel.py`, `test_backend_clients.py` | The Pipeline panel, the configuration panel, the lineage links and the shared HTTP behaviour |
| [`pages.py`](../tests/frontend/pages.py) | One page object over every view, and the answers each needs |
| [`test_frontend_vocabularies.py`](../tests/static/test_frontend_vocabularies.py) | That lists copied from a backend enum, such as the gate list, equal the enum |

## Limits

- A spinner does not mean the page is working. Closing the tab stops neither
  the worker nor a pipeline run.
- Run is disabled without an orchestrator. The other pipeline controls keep
  working.
- A rejected question stays visible: the discarded share is the evidence
  behind the coverage report.
