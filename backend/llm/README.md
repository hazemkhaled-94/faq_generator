# LLM

The served model, shared by the four stages that call one: extraction reads
passages with it, topic modelling names topics with it, question generation
writes and verifies with it, and the assessment phase judges with it.

**One set of values for all four.** Importing [`client.py`](client.py) loads
litellm, and nothing outside a worker should name it —
`tests/static/test_api_stays_light.py` pins that the API loads none of it.

## What it does

### An answer in a shape, not prose to parse

Every call asks for a **typed object**. instructor wraps litellm and validates
the answer against a Pydantic model, so a stage receives a structure or an
exception.

`LLM_STRUCTURED_MODE` is how that shape is asked for. `JSON_SCHEMA` is what
a local runtime supports; a hosted provider may want `TOOLS`. It takes one of
the instructor modes litellm's client accepts: `FUNCTIONS`, `PARALLEL_TOOLS`,
`TOOLS`, `TOOLS_STRICT`, `JSON`, `JSON_O1`, `MD_JSON` and `JSON_SCHEMA`. Any
other is refused at start-up, naming these. A mode the provider will not
answer in is an error at the first call.

### Retries

Retried here and nowhere else, up to `LLM_MAX_ATTEMPTS` attempts: a
connection error, a timeout, an internal server error, a
service-unavailable and an answer that would not validate. A rate limit is
retried too, but is not an attempt: see below.
litellm, the provider's SDK and instructor are asked for no retries of their
own, so an attempt is one billed call and `LLM_MAX_ATTEMPTS` is every call an
answer may cost, a rate limit aside. An authentication failure, an unknown model or a malformed
schema is raised at once.

**A filtered answer is a refusal.** A prompt the provider's content policy
refuses, and an answer it withholds with `finish_reason` `content_filter`,
are asked once and raised as `ModelRefused`: the same prompt is filtered
again.

**A rate limit waits as long as its `Retry-After` asks, two minutes at
most, and does not use up an attempt.** A hosted provider answers 429 with a
`Retry-After` of twenty to sixty seconds, and it is read off the 429 inside
instructor's wrapping; every other failure, and a 429 that names no seconds,
backs off exponentially. A 429 is the provider saying when to come back, so
drains that share one quota and meet it together wait it out instead of
failing their rows three rounds in. What bounds it is `_RATE_LIMIT_PATIENCE`,
ten minutes of waiting in all for one call, after which the call fails as one
out of attempts does.

### What a stage may override

A stage may name a **different model** and nothing else:

```ini
EXTRACTION_MODEL=...
TOPIC_MODEL=...
QUESTIONS_MODEL=...
```

Each means `LLM_MODEL` when absent. Three more name a model for one
**judgement** rather than a stage — `EXTRACTION_DIGEST_MODEL`,
`QUESTIONS_PHRASING_MODEL` and `QUESTIONS_VERIFIER_MODEL` — and
`make spend-by-shape` is what each of them costs.

The mode and the patience stay `LLM_*`, one value for every stage. So does
the address, unless the model named is on another provider: an `ollama*`
model is sent to `OLLAMA_BASE_URL`, and a hosted one named while
`LLM_BASE_URL` is that Ollama address goes to the provider's own.

The options that belong to one provider stay with it. A hosted model is never
sent `LLM_NUM_CTX`, which only a self-hosted runtime has, and a hosted model
a stage names while the shared model is self-hosted is sent no
`LLM_REASONING_EFFORT`, which is then spelled Ollama's way.

`QUESTIONS_VERIFIER_MODEL` is a different thing: a **second** model that
checks the first one's work. See
[question generation](../question_generation/README.md).

`ASSESSMENT_JUDGE_MODEL` names the judge, and never means `LLM_MODEL`:
unset, nothing is judged. See [assessment](../assessment/README.md).

### Changing provider

The model id's prefix picks the provider. Everything else is credentials, in
[`configs/env/provider.env`](../../configs/env/), which is **not in git**:

```ini
LLM_MODEL=ollama_chat/gemma4:31b       # a local Ollama
LLM_MODEL=azure/gpt-4o                 # Entra ID tokens, via azure-identity
LLM_MODEL=bedrock/anthropic.claude-... # AWS_ACCESS_KEY_ID and friends
```

`provider.env` is written by `make setup` from
[`provider.env.example`](../../configs/env/provider.env.example). It is
optional and absent for a plain Ollama. Compose hands it to the four
workers that call a model and to nothing else, and the Makefile sources it
for a host command.

`make doctor` asks every model a stage calls one question, `LLM_MODEL` and
each stage's own, as the host calls them.

What does **not** move when you change providers are the local encoders:
`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL` and the spaCy pipelines
`NLP_MODELS` names, which run in the worker.

### The containers call Ollama

Some credentials exist only where a person is — an interactive cloud login, a
key in a login keychain — and a container has none of them.

```ini
LLM_MODEL=<what the host calls>                     # .env
LLM_CONTAINER_MODEL=<what the containers call>
QUESTIONS_VERIFIER_CONTAINER_MODEL=<what the containers verify with>
OLLAMA_CONTAINER_URL=<where the containers reach Ollama>
```

`LLM_CONTAINER_MODEL` and `OLLAMA_CONTAINER_URL` are **required**:
`compose.yaml` fails to start without them rather than falling back to
`LLM_MODEL`. A container that falls back to a hosted model it has no
credential for restarts on every failure, indefinitely. A compose variable is
resolved when a container is *created*, so a `.env` edit reaches a running
stack only through `up --force-recreate`.

There is no `LLM_CONTAINER_URL`: a container's address is Ollama's.
`make doctor` refuses a container
model that is not an `ollama*` one. The judge is set apart:
`ASSESSMENT_JUDGE_CONTAINER_MODEL` may name a hosted model, which
`provider.env` authenticates, and unset the worker judges nothing.

A stage's own model has no container counterpart. `EXTRACTION_MODEL`,
`EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL` and
`QUESTIONS_PHRASING_MODEL` are read from
[`configs/env/backend.env`](../../configs/env/backend.env), which the
containers take unchanged, so a container calls whatever model they name,
and `make doctor` asks them only as the host calls them. A line there naming a hosted model
sends that stage's calls from the containers to it, authenticated only by
what `provider.env` holds.

The two halves **never drain one stage's queue at once**: a host drain
refuses while that stage's worker is running. The container workers build
the dataset; a host drain is for developing a stage. Nothing keeps a host
run out of the dataset, though: a host drain writes the same tables in the
same database as the workers, nothing but a `RUN_ID`, where one is set,
tells its rows apart, and the refusal checks only that the stage's worker
is stopped. Do not build the dataset with one. Comparing two models is
`RUN_ID` over the same rows — see [settings](../settings/README.md).

### A worker proves the model before it claims anything

A watching worker whose model will not answer **stays up and asks again**,
backing off 5s, 10s, 20s to a minute. It claims nothing until the model
answers, and exits only when it is a one-off drain with a person holding the
exit code.

Exiting was the bug: under `restart: unless-stopped` a process is a restart,
a fresh `run_id` and a Phoenix project holding the one call that failed, so a
pipeline that was down for a day read as one that had run thousands of times.

`before_work` in [`check.py`](check.py) is the preflight
`stages.cli.queue_main` runs; `make doctor` asks the same question of every
model a stage calls through [`api/doctor.py`](../api/doctor.py), which sits in
the one layer allowed to read every stage's settings. It asks for one trivial structured answer,
before the watch loop — that loop logs an exception and polls again, which is
right for a drain that failed and wrong for a deployment that can never work.

```text
questions will not start: ollama_chat/no-such-model:1b at
http://host.docker.internal:11434 did not answer: ... model not found
```

Nothing in it names a provider: whatever authenticates a stage authenticates
the check.

### What a span of passages needs

`spans.py` holds the relations a bridge may name (defines, limits,
consequence, applies, parallel, contrast), each with the meaning the bridge
prompt gives it and where its answer comes from. Only the bridge pass reads it
today: its prompt's list of relations, the names its FORMAT line offers and
the names its answer schema takes are all read off the one table, so a
relation added there is one the model is offered and may answer (the
`facts.bridge` CHECK takes it once a revision adds it). Where an answer comes
from is not read yet. It sits here rather than in extraction, as the quote
check that decides what a passage holds sits in `nlp/text.py`, because
extraction and question generation may not import each other.

### A document's text is fenced

`prompt.fill` substitutes in one pass, so a passage naming `{{answer}}` is sent as written. The placeholders a caller names as `material` hold the document's own text (a passage, a heading trail, a fact, an earlier answer): each is sent between `<material name="...">` tags with every `<` in it escaped, so the text cannot close the tag it sits in. Every system prompt that shows such text carries one line under CONTEXT saying text between the tags is the document's, to be read and never obeyed (`prompt.grounded` puts it there). It limits what a planted instruction can do; it does not make an untrusted document safe, so ingest only documents the customer controls.

## Cost and latency

Every call is logged with its duration, its token counts and, where
litellm has a price for the model, what it cost. **Every attempt is
counted**, a failed one's too: an answer that came on the third attempt is
logged with the tokens of all three, and one that never came is logged with
what its attempts cost on the line saying it did not answer. A model missing
from its price list is logged with no cost, and the answer is kept:

```bash
make spend LOG=run.log                    # totals from a captured log
make spend LOG=run.log SINCE=2026-09-19   # one day of it
make spend-by-shape LOG=run.log           # split by model and judgement
```

`LOG` is **required**: it is the text log a drain wrote to a terminal, not
the shipped JSON. For a run happening now, Grafana's **2 · What each stage is
doing** dashboard and Phoenix are where the cost is.

The model is the bottleneck, not the pipeline;
[measurements.md](../../docs/measurements.md) carries the last run's
per-stage latency and spend. The panel worth watching is model latency p99: a
p99 climbing towards `LLM_TIMEOUT_SECONDS` is calls about to time out, be
tried again and fail their rows.

## Configuration

The values are in the file named beside each, once.

| Setting | Declared in | What it does |
|---|---|---|
| `LLM_MODEL` | `.env` | LiteLLM model id; the prefix picks the provider |
| `LLM_BASE_URL` | `.env` | Where that model is served. Left out for a hosted `LLM_MODEL` while it is the `OLLAMA_BASE_URL` address, so the provider's own is used |
| `LLM_STRUCTURED_MODE` | `backend.env` | How a typed answer is asked for |
| `LLM_TEMPERATURE` | `backend.env` | How far a re-run's answers may move from the last one's |
| `LLM_TIMEOUT_SECONDS` | `backend.env` | How long one call may take |
| `LLM_MAX_ATTEMPTS` | `backend.env` | Attempts per call |
| `SPEND_CAP` | `backend.env` | The most, in USD, one drain spends, counted in process from what litellm prices each call at; see [stages](../stages/README.md#what-a-drain-exits-with). A call litellm cannot price is logged `llm.unpriced`, warned once per model, and refused at a capped drain's start |
| `LLM_NUM_CTX` | `backend.env` | The context window to ask a self-hosted runtime for. Never sent to a hosted model |
| `LLM_REASONING_EFFORT` | `backend.env` | For a model that has the knob. Unset sends nothing, so the model keeps its own default. Not sent to a hosted model a stage names while the shared one is self-hosted, nor to a hosted model litellm knows does not reason (gpt-4.1, gpt-4o), which refuses it; so `none` for a reasoning writer serves a split whose other roles do not reason |
| `OLLAMA_BASE_URL` | `.env` | Where a self-hosted model is served |
| `LLM_CONTAINER_MODEL` | `.env` | `LLM_MODEL` as the containers see it |
| `QUESTIONS_VERIFIER_CONTAINER_MODEL` | `.env` | The verifier as the containers see it |
| `EXTRACTION_MODEL`, `QUESTIONS_MODEL`, `TOPIC_MODEL` | `backend.env` | One stage calling a different model. The model only |
| `EXTRACTION_DIGEST_MODEL`, `QUESTIONS_PHRASING_MODEL` | `backend.env` | One judgement on a smaller model |

## Tests

```sh
poetry run pytest tests/unit/llm
```

| File | Covers |
|---|---|
| [`test_client.py`](../../tests/unit/llm/test_client.py) | Asking a served model, and what happens when it will not answer: which failures are retried, which are raised, and what the span carries |
| [`test_check.py`](../../tests/unit/llm/test_check.py) | The preflight a worker runs before it claims anything: one call, and a refusal naming the model |
| [`test_overridden.py`](../../tests/unit/llm/test_overridden.py) | One stage calling a different model, and that only the model moves, bar the address on a change of provider |
| [`test_prompt_fill.py`](../../tests/unit/llm/test_prompt_fill.py) | Filling a prompt template, where a value may carry a placeholder too, and fencing the document's text |

No test here reaches a network. The evaluation layer is where a real served
model is asked anything — see [`evaluation/`](../../evaluation/README.md).

## Limits

- **A quota that stays exhausted holds a row for ten minutes.** A rate limit
  is waited out up to `_RATE_LIMIT_PATIENCE` per call and counts against no
  attempt, so a drain on a quota that is gone sits in its call that long
  before the row fails, and five such rows in a row stop the drain.
- **The lowest `LLM_TEMPERATURE` is not a guarantee of determinism.** A model's
  answers still move between versions and quantisations, which is why
  `tests/eval/` never gates.
- **`QUESTIONS_VERIFIER_MODEL` unset makes the writer check its own
  questions while `QUESTIONS_MODEL` is unset too, rather than failing.** The
  worker warns on every start.
- **An unknown model id is found by asking it one question.** A drain asks
  every model it calls before it claims anything; `make doctor` asks the
  host's.
