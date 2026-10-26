# LLM

The served model, shared by the four stages that call one: extraction,
topic modelling, question generation and the assessment judge.

[`client.py`](client.py) loads litellm. Only workers may import it; the API
loads none of it (`tests/static/test_api_stays_light.py`).

## Structured answers

Every call asks for a typed object, which instructor validates against a
Pydantic model. `LLM_STRUCTURED_MODE` sets how the shape is requested. Values
are `FUNCTIONS`, `PARALLEL_TOOLS`, `TOOLS`, `TOOLS_STRICT`, `JSON`, `JSON_O1`,
`MD_JSON` and `JSON_SCHEMA`. `JSON_SCHEMA` suits a local runtime; a hosted
provider may need `TOOLS`. Any other value is refused at start-up.

## Retries

A call is attempted up to `LLM_MAX_ATTEMPTS` times. Retried failures are a
connection error, a timeout, an internal server error, a service-unavailable
and an answer that fails validation. Each attempt is one billed call. An
authentication failure, an unknown model or a malformed schema is raised at
once.

A prompt the content policy refuses, or an answer withheld with
`finish_reason` `content_filter`, is asked once and raised as `ModelRefused`.

A rate limit uses no attempt. The call waits as long as `Retry-After` asks,
two minutes at most; a 429 without seconds backs off exponentially.
`_RATE_LIMIT_PATIENCE` caps the waiting at ten minutes per call, after which
the call fails. Five such failed rows in a row stop the drain.

## Stage models

A stage may name a different model and nothing else:

```ini
EXTRACTION_MODEL=...
TOPIC_MODEL=...
QUESTIONS_MODEL=...
```

Each defaults to `LLM_MODEL`. `EXTRACTION_DIGEST_MODEL`,
`QUESTIONS_PHRASING_MODEL` and `QUESTIONS_VERIFIER_MODEL` name a model for one
judgement. `make spend-by-shape` shows what each costs.

The structured mode and the patience are shared. So is the address, unless the
stage's model is on another provider: an `ollama*` model goes to
`OLLAMA_BASE_URL`, and a hosted model goes to the provider's own address. A
hosted model is never sent `LLM_NUM_CTX`.

`QUESTIONS_VERIFIER_MODEL` is a second model that checks the writer's work;
see [question generation](../question_generation/README.md).
`ASSESSMENT_JUDGE_MODEL` names the judge and never defaults to `LLM_MODEL`:
unset, nothing is judged. See [assessment](../assessment/README.md).

## Providers

### Changing provider

The model id's prefix picks the provider. Credentials go in
[`configs/env/provider.env`](../../configs/env/), which is not in git:

```ini
LLM_MODEL=ollama_chat/gemma4:31b       # a local Ollama
LLM_MODEL=azure/gpt-4o                 # Entra ID tokens, via azure-identity
LLM_MODEL=bedrock/anthropic.claude-... # AWS_ACCESS_KEY_ID and friends
```

`make setup` writes `provider.env` from
[`provider.env.example`](../../configs/env/provider.env.example). The file is
optional for a plain Ollama. Compose passes it only to the four workers that
call a model. `make doctor` asks every model a stage calls one question, as the
host calls them. The local encoders do not depend on the provider.

### The containers call Ollama

Credentials such as an interactive cloud login or a login keychain exist only
on the host.

```ini
LLM_MODEL=<what the host calls>                     # .env
LLM_CONTAINER_MODEL=<what the containers call>
QUESTIONS_VERIFIER_CONTAINER_MODEL=<what the containers verify with>
OLLAMA_CONTAINER_URL=<where the containers reach Ollama>
```

`LLM_CONTAINER_MODEL` and `OLLAMA_CONTAINER_URL` are required: `compose.yaml`
fails to start without them. Compose resolves a variable when it creates a
container, so a `.env` edit reaches a running stack only through
`up --force-recreate`.

`make doctor` refuses a container model that is not an `ollama*` one, except
`ASSESSMENT_JUDGE_CONTAINER_MODEL`, which may name a hosted model that
`provider.env` authenticates.

A stage's own model has no container counterpart. `EXTRACTION_MODEL`,
`EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL` and
`QUESTIONS_PHRASING_MODEL` come from
[`configs/env/backend.env`](../../configs/env/backend.env), which containers
take unchanged. A line there that names a hosted model sends that stage's
container calls to it, authenticated only by `provider.env`.

`EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are local encoders from the same
file. They run in the worker, never through Ollama, and the settings API
refuses to change them.

A host drain refuses while that stage's worker is running. Container workers
build the dataset; a host drain is for developing a stage. Nothing keeps a host run out of the dataset:
a host drain writes the same tables in the same database, and only `RUN_ID`,
when set, tells its rows apart. To compare two models, use `RUN_ID` over the
same rows; see [settings](../settings/README.md).

## Preflight

A watching worker whose model does not answer stays up and asks again, backing
off 5s, 10s, 20s up to a minute, and claims nothing meanwhile. A one-off drain
exits instead.

`before_work` in [`check.py`](check.py) runs before the watch loop and asks for
one trivial structured answer. `make doctor` does the same through
[`api/doctor.py`](../api/doctor.py).

```text
questions will not start: ollama_chat/no-such-model:1b at
http://host.docker.internal:11434 did not answer: ... model not found
```

## Span relations

`spans.py` holds the relations a bridge may name: defines, limits,
consequence, applies, parallel and contrast. The bridge prompt and answer
schema read them from this table. A new relation also needs a revision that
adds it to the `facts.bridge` CHECK.

## Cost and latency

Every call is logged with its duration, token counts and, where litellm has a
price, its cost. Failed attempts are counted too.

```bash
make spend LOG=run.log                    # totals from a captured log
make spend LOG=run.log SINCE=2026-09-19   # one day of it
make spend-by-shape LOG=run.log           # split by model and judgement
```

`LOG` is required: the text log a drain wrote to a terminal, not the shipped
JSON. For a run in progress, use Grafana's "2 · What each stage is doing"
dashboard and Phoenix. [measurements.md](../../docs/measurements.md) has the
last run's latency and spend.

## Configuration

| Setting | Declared in | What it does |
|---|---|---|
| `LLM_MODEL` | `.env` | LiteLLM model id. The prefix picks the provider |
| `LLM_BASE_URL` | `.env` | Where that model is served. Leave out for a hosted model |
| `LLM_STRUCTURED_MODE` | `backend.env` | How a typed answer is requested |
| `LLM_TEMPERATURE` | `backend.env` | Sampling temperature |
| `LLM_TIMEOUT_SECONDS` | `backend.env` | How long one call may take |
| `LLM_MAX_ATTEMPTS` | `backend.env` | Attempts per call |
| `SPEND_CAP` | `backend.env` | The most, in USD, one drain spends. See [stages](../stages/README.md#what-a-drain-exits-with). A call litellm cannot price is logged `llm.unpriced` and refused at the start of a capped drain |
| `LLM_NUM_CTX` | `backend.env` | The context window for a self-hosted runtime. Never sent to a hosted model |
| `LLM_REASONING_EFFORT` | `backend.env` | For a model that has the setting. Unset sends nothing. Never sent to a hosted model that does not reason (gpt-4.1, gpt-4o) |
| `OLLAMA_BASE_URL` | `.env` | Where a self-hosted model is served |
| `LLM_CONTAINER_MODEL` | `.env` | `LLM_MODEL` as the containers see it |
| `QUESTIONS_VERIFIER_CONTAINER_MODEL` | `.env` | The verifier as the containers see it |
| `EXTRACTION_MODEL`, `QUESTIONS_MODEL`, `TOPIC_MODEL` | `backend.env` | One stage calling a different model |
| `EXTRACTION_DIGEST_MODEL`, `QUESTIONS_PHRASING_MODEL` | `backend.env` | One judgement on a smaller model |

## Tests

```sh
poetry run pytest tests/unit/llm
```

The tests cover retries (`test_client.py`), the preflight (`test_check.py`),
stage model overrides (`test_overridden.py`) and prompt filling
(`test_prompt_fill.py`). None reaches a network. The
[evaluation](../../evaluation/README.md) layer asks a real served model.

## Limits

- The lowest `LLM_TEMPERATURE` does not guarantee determinism.
- With `QUESTIONS_VERIFIER_MODEL` and `QUESTIONS_MODEL` both unset, the writer
  checks its own questions, and the worker warns on every start.
