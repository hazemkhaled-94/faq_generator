# `certs` uses process substitution, which /bin/sh does not have.
SHELL := /bin/bash

# Override for Docker: make CONTAINER=docker COMPOSE="docker compose" up
COMPOSE ?= podman compose

# The file the secrets and the model are read from: `.env` beside this Makefile
# unless ENV_FILE names another, so a go-live host can keep them outside the
# checkout (docs/operations.md, "Keeping the secrets out of the checkout").
# A path without a space, because compose is handed it too. A relative one is
# read from the checkout, and ENV_PATH says so: `. name` would search PATH.
ENV_FILE ?= .env
ENV_PATH = $(if $(filter /%,$(ENV_FILE)),$(ENV_FILE),./$(ENV_FILE))

# The two files compose interpolates `${...}` out of, in precedence order:
# the deployment's ports and addresses, then the secrets over them. Compose
# reads only one such file on its own - `.env` - so both are named here, and
# the last one wins.
#
# Every compose command in this file goes through $(COMPOSE_CMD) for that
# reason, and $(COMPOSE_CMD) stays the engine alone so that the documented
# `make COMPOSE="docker compose" up` still carries the files rather than
# replacing them.
#
# A bare `podman compose` outside make sees deployment.env not at all and
# fails on the first missing port; export COMPOSE_ENV_FILES to it, which
# `make doctor` says how to do. It cannot be set inside .env - compose has
# to resolve the file list before it reads one.
COMPOSE_CMD = $(COMPOSE) --env-file configs/env/deployment.env --env-file $(ENV_FILE)

# The engine itself, for the build and run that `lock` needs; compose has no
# equivalent of --target.
CONTAINER ?= podman

# The advisories `make audit` accepts, each with its lock, reason and review-by date.
AUDIT_ACCEPTED ?= configs/audit-accepted.txt

# poetry.lock's pins as name==version lines, torch and torchvision at their +cpu
# builds, which resolve only from PyTorch's index. The audit reads them, and the
# image locks are resolved under them, so a package both lock is held to one version.
# A package poetry.lock holds twice (the CUDA wheels for another platform)
# comes out at its first version.
HOST_PINS = poetry run python -c 'import tomllib; seen = {}; [seen.setdefault(p["name"], p["version"]) for p in tomllib.load(open("poetry.lock", "rb"))["package"] if p["name"] not in ("torch", "torchvision") or p["version"].endswith("+cpu")]; print(*(f"{n}=={v}" for n, v in seen.items()), sep="\n")'

# Every directory ruff reads, so `lint` and `format` cannot cover different
# ones. orchestration, review and evaluation are here and not in pyright's
# `include`: they are checked by both, but pyright is configured in
# pyproject.toml rather than on this command line.
SOURCES := backend frontend telemetry orchestration review evaluation tests

# What every host command reads, and in the same order the containers do: how
# the pipeline behaves, then where this deployment put things, then .env for
# the credentials and the model.
#
# OVERRIDE re-applies whatever was given on the command line, because sourcing
# the files above would otherwise overwrite it - which is why
# `make topics TOPIC_PASSES=20` used to run with the file's value and say
# nothing. QA_COMMAND_LINE names them, so a stored row for one gives way too.
#
# Applied twice: before DERIVED, so an address is built from a port given on
# the command line, and after it, so an address given there is not rebuilt.
#
# The names are the variables whose origin is the command line, not the
# words of MAKEOVERRIDES, where make escapes a value's spaces and nothing
# else: split, `OUT="a - b.xlsx"` named `-` and `b.xlsx` settings too.
# APP_DB_NAME is the one name also taken from the environment: deployment.env
# sets qa_generator, so sourcing it replaced the database a shell had exported,
# and a destructive target meant for a scratch copy ran on the real one.
# Each value is exported single-quoted, its own quotes escaped, for the same
# reason: re-read by the shell, a `(`, `&` or `'` in a path was a syntax error.
GIVEN = $(strip $(foreach given,$(.VARIABLES),$(if $(filter command line,$(origin $(given))),$(given)))$(if $(filter environment,$(origin APP_DB_NAME)), APP_DB_NAME))
OVERRIDE = $(if $(GIVEN),&& export $(foreach given,$(GIVEN),$(given)='$(subst ','\'',$($(given)))') QA_COMMAND_LINE="$(GIVEN)",)

# The values that are never written down, because they are built out of ones
# that are. A copy of a port inside an address is a copy free to disagree
# with it, and a copy of a password inside a connection string is a secret
# in two places.
#
# compose builds the container's half of each of these out of the same
# names; this is the host's. One assignment-only command, so `set -a` above
# exports every one of them.
#
# The addresses are localhost and a PUBLISHED port: a host command reaches a
# service the way a browser would, not by the compose service name.
DERIVED = DATABASE_URL=postgresql+psycopg://$$APP_DB_USER:$$APP_DB_PASSWORD@localhost:$$POSTGRES_PORT/$$APP_DB_NAME \
          BACKEND_URL=http://localhost:$$BACKEND_PORT \
          S3_ENDPOINT=http://localhost:$$S3_PORT \
          PHOENIX_BASE_URL=http://localhost:$$PHOENIX_PORT \
          OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:$$PHOENIX_GRPC_PORT \
          ARGILLA_API_URL=http://localhost:$$ARGILLA_PORT

# The provider's credentials, for whichever host command calls a model.
# Optional and absent for a plain Ollama, which needs none - hence the test
# rather than a plain `.`, which would stop every target on a clone that has
# no such file.
#
# Here rather than beside each model-calling target because compose hands
# this file to the four services that call a model and the host was given
# it nowhere: `make extract` against a hosted provider read backend.env and
# .env, found no key in either, and failed to authenticate.
PROVIDER = { [ ! -f ./configs/env/provider.env ] || . ./configs/env/provider.env; }

LOADENV = set -a && . ./configs/env/backend.env && . ./configs/env/deployment.env \
          && $(PROVIDER) && . "$(ENV_PATH)" $(OVERRIDE) && $(DERIVED) $(OVERRIDE) && set +a

# What `wipe` leaves standing. Comma-separated, and empty by default: the
# command is called wipe, and a default that quietly kept things would be
# the wrong way round.
#
#   make wipe-all KEEP=golden        the Phoenix datasets and their experiments
#   make wipe-all KEEP=runs          the Dagster run history
#   make wipe-all KEEP=golden,runs   both
#
# Each is something a deployment may want back and nothing upstream
# rebuilds: the golden cases come from evaluation/ and the run history is
# the record of what ran. The rest of what a wipe takes outside the
# database and the buckets is gone for good: every Phoenix project, the
# three review datasets in Argilla with any answer not yet pulled, and the
# logs. `wipe` refuses any other name.
KEEP ?=

# KEEP's names, split on commas, so a space after one does not hide a name.
comma := ,
KEPT = $(subst $(comma), ,$(KEEP))

# True, and says so, when KEEP names $(1). $(2) is what to call it.
SPARED = case " $(KEPT) " in *" $(1) "*) echo "KEEP=$(1): leaving $(2)";; \
         *) false;; esac

# The same, for a tool with a tuning file of its own:
#
#     $(call WITH,review.env) && python -m review.run --status
#
# Sourced inside the `set -a` region, which is the whole point of having
# this rather than appending `&& . ./configs/env/x.env` to LOADENV: after
# `set +a` a sourced file's values are set in the shell and not exported,
# so the process below saw none of them and stopped naming the first.
WITH = set -a && . ./configs/env/backend.env && . ./configs/env/deployment.env && \
       . ./configs/env/$(1) && $(PROVIDER) && . "$(ENV_PATH)" $(OVERRIDE) && \
       $(DERIVED) $(OVERRIDE) && set +a

# Narrows a stage target to one item instead of the whole queue, mirroring
# the route's /{scope}/{value} segment:
#
#   make parse-start     SHA=<sha256>     one document
#   make chunk-rerun     SHA=<sha256>     one document
#   make extract-start   SHA=<sha256>     every passage of one document
#   make extract-retry   PASSAGE=<id>     one passage
#   make questions-start TOPIC=<id>       one topic
#
# Which scopes a stage accepts is the stage's own; parsing and chunking take
# a document, extraction takes either, question generation takes a topic, and
# topic modelling takes none. The first one given wins.
ONLY = $(if $(SHA),--only document=$(SHA),\
       $(if $(PASSAGE),--only passage=$(PASSAGE),\
       $(if $(TOPIC),--only topic=$(TOPIC))))

# Refuses a host drain while $(1), the container worker draining the same
# queue, is running, and prints the command that stops it. Passes when no
# container engine answers or the stack is down.
#
#     @$(call IDLE,extract-worker)
IDLE = ! $(COMPOSE_CMD) ps -q $(1) 2>/dev/null | grep -q . || \
       { echo "$(1) is running and drains this queue. Stop it first:" >&2; \
         echo "  $(COMPOSE_CMD) stop $(1)" >&2; exit 1; }

# True while compose has a running container for the service $(1).
RUNNING = $(COMPOSE_CMD) ps -q $(1) 2>/dev/null | grep -q .

# What `wipe` and `wipe-preflight` both say of a store that is not running: it
# is not checked, and the wipe skips its step $(2), so the preflight never
# passes a store whose step the wipe then fails on half way.
STORE_DOWN = echo "$(1) is not running: not checked, and $(2) is skipped by the wipe."

# Runs the wipe step $(2) when the service $(1) runs, and says it skips it otherwise.
WIPE_STEP = if $(call RUNNING,$(1)); then $(MAKE) $(2); else $(call STORE_DOWN,$(1),$(2)); fi

# Names where a command acts, once the settings are loaded.
BANNER = $(LOADENV) && echo "on database $$APP_DB_NAME on localhost:$$POSTGRES_PORT" >&2

# Refuses unless CONFIRM, typed on the command line (one exported in the shell
# does not count), equals the database the settings resolve to, and
# names the database and the port it would act on. $(1) says what is asked.
#
#     @$(call CONFIRMED,wipe)
CONFIRMED = $(LOADENV) && { [ "$(if $(filter command line,$(origin CONFIRM)),$(CONFIRM))" = "$$APP_DB_NAME" ] || \
            { echo "REFUSED: $(1) acts on database $$APP_DB_NAME on localhost:$$POSTGRES_PORT." >&2; \
              echo "  Run it again with CONFIRM=$$APP_DB_NAME to go on." >&2; exit 2; }; }

# What a drain is given under WAIT=1, which `corpus` sets, while $(1), the
# container worker draining the same queue, is running: --wait, so the stage
# is waited for until that worker has emptied its queue rather than drained
# beside it. The go-live `make up` starts the parse and chunk workers, and a
# chain that refused there never reached a model stage. Empty otherwise, and
# without WAIT the drain's IDLE refuses instead.
#
#     python -m preprocessing.parsing.run $(call AWAIT,parse-worker)
AWAIT = $(if $(WAIT),$$($(COMPOSE_CMD) ps -q $(1) 2>/dev/null | grep -q . && echo --wait))

# True when this is the go-live profile: HOST_RUNNER is a spelling of yes.
# The host runs the model stages through `make corpus-hosted`, the model
# workers and Dagster stay stopped, and Ollama is not called.
GO_LIVE = case "$$(printf %s "$${HOST_RUNNER:-}" | tr '[:upper:]' '[:lower:]')" in 1|true|yes|on) true;; *) false;; esac

# Refuses, naming the host runner, on the go-live profile. The same sentence
# the pipeline routes answer 409 with, which tests/static pins.
NOT_GO_LIVE = $(LOADENV) && { ! $(GO_LIVE) || \
              { echo "the go-live profile runs the model stages through make corpus-hosted" >&2; exit 1; }; }

# Where a corpus run keeps what its drains spent, and where the hosted run
# keeps its process group and database, and its log: scripts/corpus-hosted.sh
# writes both.
CORPUS_LEDGER = logs/corpus-spend.usd
HOSTED_PID = logs/corpus-hosted.pid
HOSTED_LOG = logs/corpus-hosted.log

# What the hosted run is given: the database it acts on, recorded beside its
# process group, and RESET when asked for. The rest of a command line, such
# as SPEND_CAP, reaches its `make corpus` through MAKEFLAGS.
HOSTED_ARGS = APP_DB_NAME=$(CORPUS_DB) $(if $(RESET),RESET=1)

# What a resumed run puts back in the queue before it starts: a drain killed
# mid-row leaves its row failed, and rows left failed are not claimed again.
CORPUS_RETRIES = parse-retry chunk-retry extract-retry topics-retry questions-retry assess-retry

# The database a run acts on, as every host command reads it: the one a
# command line gives or the shell exports, which OVERRIDE puts over the files,
# else the files' in their order. Lazy, so only a target that names it pays for the shell.
CORPUS_DB = $(if $(filter command line environment,$(origin APP_DB_NAME)),$(APP_DB_NAME),$(shell \
              set -a; . ./configs/env/deployment.env 2>/dev/null; \
              [ ! -f "$(ENV_PATH)" ] || . "$(ENV_PATH)" 2>/dev/null; printf %s "$$APP_DB_NAME"))

# What every target of the corpus is given on its command line, which beats the
# files a host command sources: the database the run announced, the Hub off,
# the spend ledger, and WAIT, so a stage whose container worker runs is waited
# for (see AWAIT). A line is `$(MAKE) target $(CORPUS_PINS)` and not a
# macro around it, because make runs a line holding `$(MAKE)` even under
# `make -n`, which is how the targets it names are read without running.
CORPUS_PINS = $(if $(CORPUS_DB),APP_DB_NAME=$(CORPUS_DB)) HF_HUB_OFFLINE=1 SPEND_LEDGER=$(CORPUS_LEDGER) WAIT=1

# Every profile of compose.yaml unless a command says otherwise, so `down`,
# `ps`, `logs` and `stop` reach a container whichever profile started it.
# Only `up` narrows it: see UP.
export COMPOSE_PROFILES ?= *

# Starts the stack. In development every profile, so the model workers and
# Dagster come up as they always did. On the go-live profile the services no
# profile names, and the profiles `.env`'s COMPOSE_PROFILES asks for (review,
# logs, tools) - never local-models or orchestrated, which that profile does
# not run.
UP = $(LOADENV) && if $(GO_LIVE); then \
       profiles=$$(printf %s "$$COMPOSE_PROFILES" | tr , '\n' | grep -vxE '\*|local-models|orchestrated' | paste -sd, -); \
     else profiles='*'; fi; \
     COMPOSE_PROFILES="$$profiles" $(COMPOSE_CMD) up -d

# ── Help ───────────────────────────────────────────────────────────────────

# Listed before anything runs, because `make` on its own used to install
# dependencies and start nine containers.
.DEFAULT_GOAL := help

# Every target there is, grouped, with what each one does.
#
# Read out of this file rather than written out again here: the section
# banner a target sits below is its group, and the first sentence of the
# comment above it is its description. A target cannot be added without
# appearing, and a description cannot drift from the target it names.
#
# Colour only when a terminal is reading, so `make help | grep` is clean.
help:
	@if [ -t 1 ]; then b=$$(printf '\033[1m'); c=$$(printf '\033[36m'); r=$$(printf '\033[0m'); fi; \
	printf '%sFAQ Generator%s\n\n' "$$b" "$$r"; \
	printf '  usage:      make <target> [VAR=value]\n'; \
	printf '  first run:  %smake setup%s, then %smake doctor%s, then %smake dev%s\n' \
	  "$$c" "$$r" "$$c" "$$r" "$$c" "$$r"; \
	printf '  detail:     docs/make.md, docs/configuration.md\n'; \
	awk -v b="$$b" -v c="$$c" -v r="$$r" ' \
	  function reset() { p = ""; done = 0 } \
	  /^# / && index($$0, "──") { s = $$0; gsub(/[─#]/, "", s); \
	    sub(/^ +/, "", s); sub(/ +$$/, "", s); reset(); next } \
	  /^#/ { \
	    line = $$0; sub(/^# ?/, "", line); \
	    if (line ~ /^[ \t]*$$/) { done = (p != ""); next } \
	    if (!done) p = (p == "" ? line : p " " line); \
	    next \
	  } \
	  /^[a-z][a-zA-Z0-9_-]*:/ { \
	    t = $$1; sub(/:.*/, "", t); \
	    if (p != "") { \
	      if (match(p, /\. /)) p = substr(p, 1, RSTART); \
	      if (length(p) > 66) p = substr(p, 1, 63) "..."; \
	      if (s != shown) { printf "\n%s%s%s\n", b, s, r; shown = s } \
	      printf "  %s%-20s%s %s\n", c, t, r, p \
	    } \
	    reset(); next \
	  } \
	  { reset() } \
	' $(MAKEFILE_LIST)

.PHONY: help setup doctor upgrade \
        dev install install-python docling-weights up grafana-grants down down-volumes logs logs-frontend logs-api \
        logs-shipper logs-retention logs-prune logs-dir logs-orchestration \
        logs-wipe \
        prune spend spend-by-shape estimate \
        schema schema-reset schema-status schema-down schema-stamp migration \
        parse parse-status parse-start parse-stop parse-retry parse-rerun \
        chunk chunk-status chunk-start chunk-stop chunk-retry chunk-rerun \
        chunk-revocabulary \
        extract extract-status extract-start extract-stop extract-retry \
        extract-rerun extract-revalidate extract-bridge extract-recap \
        extract-dedup extract-embed extract-digests \
        topics topics-status topics-discover topics-stop topics-delete \
        topics-retry topics-visualise topics-render topics-name \
        settings settings-set settings-unset \
        questions questions-status questions-start questions-stop wipe \
        questions-retry questions-reclaim questions-rerun questions-reverify \
        questions-rescore \
        confidence-recalibrate \
        assess assess-status assess-start assess-enrol assess-stop \
        assess-retry assess-reclaim assess-rerun diversity \
        questions-balance questions-export questions-rejudge \
        questions-runs questions-diff \
        documents ingest delete delete-derived wipe-all wipe-preflight dagster-wipe \
        archive archive-purge restore-documents s3-prefix backup restore-backup restore-backup-stack \
        test test-fast test-unit test-integration test-e2e test-golden golden-refresh test-smoke \
        test-eval test-coverage test-perf mutation \
        check typecheck audit lint lint-imports deps \
        eval-phrasing \
        format lock \
        certs dagster-dev \
        review-status review-push-facts review-pull-facts \
        review-push-topics review-pull-topics \
        review-push-questions review-pull-questions review-delete review-all \
        phoenix-projects phoenix-prune phoenix-purge phoenix-retention \
        eval-upload eval-score prompts-publish \
        all corpus corpus-hosted corpus-hosted-stop open services review pull auto manual pipeline runs \
        pipeline-status pipeline-stop pipeline-retry

# ── Upgrade ────────────────────────────────────────────────────────────────

# What a build needs free in the engine's disk, in GB, which is the room the
# backend image takes and then some: a build that runs out half way leaves a
# stack that will not start.
UPGRADE_FREE_GB ?= 20

# Take a deployment to the code in this checkout: check the engine has the
# room, build, reclaim what the build orphaned, stop the workers, migrate, and
# start. Stops at the first step that fails, so a build that did not finish
# never reaches the migration. The room is read in the engine's VM where it has
# one (`podman machine`) and on the host otherwise.
upgrade:
	@[ "$(UPGRADE_FREE_GB)" = 0 ] || { \
	  free=$$($(CONTAINER) machine ssh -- df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc 0-9); \
	  [ -n "$$free" ] || free=$$(df -BG --output=avail /var/lib 2>/dev/null | tail -1 | tr -dc 0-9); \
	  [ -n "$$free" ] || { echo "the engine's free disk could not be read: UPGRADE_FREE_GB=0 skips the check" >&2; exit 1; }; \
	  [ "$$free" -ge $(UPGRADE_FREE_GB) ] || { echo "the engine has $$free GB free, under the $(UPGRADE_FREE_GB) GB an upgrade is budgeted at: make prune, free space, or set UPGRADE_FREE_GB" >&2; exit 1; }; }
	$(COMPOSE_CMD) build
	$(MAKE) prune
	$(COMPOSE_CMD) stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
	$(MAKE) schema
	$(MAKE) up

# ── Bootstrap ──────────────────────────────────────────────────────────────

# The assignments in .env, which is where a placeholder counts. The file's
# own first line says to replace every change_me_* value and is not one.
ASSIGNED = grep -E '^[A-Z][A-Z0-9_]*=' "$(ENV_PATH)"

# Write the two configuration files a clone does not come with, and fill in
# every password. Safe to run twice: it replaces the placeholders and
# nothing else, so a file already edited by hand keeps what it says.
#
# One secret per distinct placeholder, replaced everywhere it appears. It
# used to be what kept APP_DB_PASSWORD and the password inside DATABASE_URL
# the same string; the connection string is derived now, so there is no
# second copy left for this to have to keep in step.
#
# Longest placeholder first, because `change_me_phoenix` is a prefix of
# `change_me_phoenix_ui_password` and replacing the short one first would
# leave the long one half rewritten.
#
# Hex is lower-case and a digit is appended, which is what
# PHOENIX_ADMIN_SECRET requires of the deployment: 32 characters or more,
# with a digit and a lower-case letter.
setup:
	@test -f "$(ENV_PATH)" || { cp .env.example "$(ENV_PATH)"; echo "wrote $(ENV_FILE)"; }
	@test -f configs/env/provider.env || { \
	  cp configs/env/provider.env.example configs/env/provider.env; \
	  echo "wrote configs/env/provider.env"; }
	@for token in $$($(ASSIGNED) | grep -oE 'change_me_[a-z0-9_]*' | sort -u \
	                 | awk '{ print length, $$0 }' | sort -rn | cut -d' ' -f2-); do \
	  secret="$$(openssl rand -hex 24)1"; \
	  sed -i.bak "s|$$token|$$secret|g" "$(ENV_PATH)" && rm -f "$(ENV_PATH).bak"; \
	  echo "generated $$token"; \
	done
	@echo
	@echo "Now name the model in .env (LLM_MODEL, LLM_BASE_URL) and put"
	@echo "whatever credentials it needs in configs/env/provider.env."
	@echo "Then: make doctor"

# What a first run gets wrong, before a corpus pays for it.
#
# Every check runs and the failures are counted, rather than stopping at the
# first: somebody setting this up wants the whole list, not one item of it
# six times.
#
# The settings the api serves are compared with this checkout's, because the
# api and the workers run the image they were built from and a checkout
# moves on without them. An api that is down is a warning and not a
# failure: on a first run the stack is not up yet.
#
# The last check is a real call to every model a stage calls, which is the
# one thing no amount of reading the files can tell you. An unknown model id, a
# wrong address and a rejected credential all fail at the first call, and
# without this that call is the first passage of a real run.
doctor:
	@fail=0; \
	say() { printf '  %-8s %s\n' "$$1" "$$2"; }; \
	command -v $(CONTAINER) >/dev/null && say ok "$(CONTAINER)" \
	  || { say MISSING "$(CONTAINER) - install it, or set CONTAINER= and COMPOSE="; fail=1; }; \
	command -v poetry >/dev/null && say ok "poetry" \
	  || { say MISSING "poetry - https://python-poetry.org/docs/#installation"; fail=1; }; \
	if test -f configs/env/provider.env; then say ok "configs/env/provider.env"; \
	  else say "-" "no configs/env/provider.env, which a plain Ollama does not need"; fi; \
	if ! test -f "$(ENV_PATH)"; then say MISSING "$(ENV_FILE) - run: make setup"; \
	  echo; echo "Fix the above, then run make doctor again."; exit 1; fi; \
	say ok "$(ENV_FILE)"; \
	if test -f configs/env/deployment.env; then \
	  say ok "configs/env/deployment.env"; \
	  else say MISSING "configs/env/deployment.env - it is in git; git checkout it"; fail=1; fi; \
	say "-" "compose reads both: make passes them, a bare podman compose needs"; \
	say "" "  export COMPOSE_ENV_FILES=configs/env/deployment.env,$(ENV_FILE)"; \
	if $(ASSIGNED) | grep -q change_me; then \
	  say FAIL "$$($(ASSIGNED) | grep -c change_me) placeholder password(s) left - run: make setup"; fail=1; \
	  else say ok "no placeholder passwords"; fi; \
	$(LOADENV); \
	if printf '%s' "$$PHOENIX_ADMIN_SECRET" | grep -qE '^.{32,}$$' \
	   && printf '%s' "$$PHOENIX_ADMIN_SECRET" | grep -q '[0-9]' \
	   && printf '%s' "$$PHOENIX_ADMIN_SECRET" | grep -q '[a-z]'; then \
	  say ok "PHOENIX_ADMIN_SECRET"; \
	  else say FAIL "PHOENIX_ADMIN_SECRET needs 32+ characters, a digit and a lower-case letter"; fail=1; fi; \
	if $(GO_LIVE); then \
	  say "-" "the model workers are stopped (HOST_RUNNER): the containers' model is not checked"; \
	elif test -z "$$OLLAMA_CONTAINER_URL"; then \
	  say FAIL "OLLAMA_CONTAINER_URL is unset, and it is the only address a container may call"; fail=1; \
	elif test -z "$$LLM_CONTAINER_MODEL"; then \
	  say FAIL "LLM_CONTAINER_MODEL is unset: containers run Ollama and never inherit the host's model"; fail=1; \
	elif case "$$LLM_CONTAINER_MODEL" in ollama*) false;; *) true;; esac; then \
	  say FAIL "LLM_CONTAINER_MODEL is $$LLM_CONTAINER_MODEL; containers reach Ollama only"; fail=1; \
	elif test -n "$$QUESTIONS_VERIFIER_CONTAINER_MODEL" && \
	     case "$$QUESTIONS_VERIFIER_CONTAINER_MODEL" in ollama*) false;; *) true;; esac; then \
	  say FAIL "QUESTIONS_VERIFIER_CONTAINER_MODEL is $$QUESTIONS_VERIFIER_CONTAINER_MODEL; containers reach Ollama only"; fail=1; \
	else \
	  say ok "containers call $$LLM_CONTAINER_MODEL at $$OLLAMA_CONTAINER_URL"; \
	fi; \
	echo; echo "Comparing the settings the api serves with this checkout's..."; \
	PYTHONPATH=backend poetry run python -m settings.drift $(COMPOSE_CMD) || fail=1; \
	echo; echo "Asking every model a stage calls one question, as the host calls it..."; \
	PYTHONPATH=backend poetry run python -m api.doctor || fail=1; \
	echo; \
	PYTHONPATH=backend poetry run python -m archive.run --size || say "-" "the archive could not be read"; \
	echo; \
	if test $$fail -eq 0; then echo "Ready. Next: make dev"; \
	  else echo "Fix the above, then run make doctor again."; exit 1; fi

# Install dependencies, start every service, and create the schema. Then
# grant Grafana its Phoenix tables, as `up` does.
dev: install certs logs-dir
	@$(UP)
	@echo "Waiting for PostgreSQL..."
	@$(LOADENV) && \
	  ready=; for i in $$(seq 1 30); do \
	    $(COMPOSE_CMD) exec -T postgres pg_isready -h 127.0.0.1 -U "$$POSTGRES_SUPERUSER" -q \
	      && ready=1 && break; \
	    sleep 2; \
	  done; \
	  [ -n "$$ready" ] || { echo "PostgreSQL was not ready after 60 seconds" >&2; exit 1; }
	$(MAKE) schema
	@$(MAKE) --no-print-directory grafana-grants
	-@$(MAKE) --no-print-directory phoenix-retention

# The spaCy pipelines are downloaded, not resolved: they are not on PyPI
# under a version range.
#
# READ OFF NLP_MODELS rather than written out again, and exported so that
# `compose build` bakes exactly what the workers will try to LOAD. The two
# used to be separate lists in four files, and a language added to
# NLP_MODELS gave a worker that starts and then cannot read it.
#
# Retried, because they come from GitHub's release downloads rather than
# from an index: a 504 there fails the whole install, and did.
SPACY_MODELS := $(strip $(shell sed -n 's/^NLP_MODELS=//p' configs/env/backend.env \
                                | tr ',' '\n' | cut -d: -f2))
export SPACY_MODELS
SPACY_MODEL_VERSION := $(shell sed -n 's/^ARG SPACY_MODEL_VERSION=//p' backend/api/Dockerfile)

# Install the Python dependencies, the spaCy pipelines and Docling's weights.
install: install-python docling-weights

# Install the Python dependencies and the spaCy pipelines, on the host alone.
#
# What CI's setup action runs: its jobs need the virtualenv and never the
# `models` volume, and a runner has no .env for compose to read.
install-python:
	poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
	@for model in $(SPACY_MODELS); do \
	  attempt=1; \
	  until poetry run python -m spacy download $$model-$(SPACY_MODEL_VERSION) --direct; do \
	    attempt=$$((attempt + 1)); \
	    if [ $$attempt -gt 3 ]; then \
	      echo "could not download $$model after 3 attempts" >&2; exit 1; \
	    fi; \
	    echo "spacy download $$model failed; retrying in 15s"; sleep 15; \
	  done; \
	done

# Download Docling's weights into the `models` volume parse-worker reads.
#
# parse-worker has the hub offline and sits on a network with no route out,
# so a fresh volume failed every document. chunk-worker is the same image
# with the same volume on a network that reaches the hub. Builds the image
# if there is none yet; fetches nothing already cached.
docling-weights:
	$(COMPOSE_CMD) run --rm --no-deps chunk-worker python -m preprocessing.parsing.weights

# ── Services ───────────────────────────────────────────────────────────────

# The directory a host command writes its JSON log lines to, which compose
# bind-mounts into the shipper read-only. Made here rather than left to the
# container engine: a missing bind-mount source is created by the engine
# itself, which can leave it owned by root, and then the host process the
# directory exists for cannot write to it.
logs-dir:
	@mkdir -p logs

# Start every service, generating the certificates first if they are missing.
up: certs logs-dir
	@$(UP)
	@$(MAKE) --no-print-directory grafana-grants
	-@$(MAKE) --no-print-directory phoenix-retention

# Grafana's reader gets SELECT on the Phoenix tables the run dashboard queries,
# once Phoenix has made them. Run by `up` and `dev`; safe to run again.
grafana-grants:
	@for i in $$(seq 1 30); do \
	  $(COMPOSE_CMD) exec -T postgres sh -c 'psql -q -U "$$POSTGRES_USER" -d "$$PHOENIX_DB_NAME" -c "TABLE span_annotations LIMIT 0"' >/dev/null 2>&1 && break; \
	  sleep 5; \
	done
	$(COMPOSE_CMD) exec -T postgres sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$PHOENIX_DB_NAME" -c "GRANT SELECT ON projects, traces, spans, span_costs, span_annotations TO $$GRAFANA_DB_USER"'

# Phoenix keeps every prompt, which is a passage of a customer's document, until
# told otherwise. Sets the default trace retention policy to
# PHOENIX_TRACE_RETENTION_DAYS (configs/env/deployment.env; 30 where unset).
# Run by `up` and `dev`, which ignore a failure so the stack still starts;
# safe to run again.
phoenix-retention:
	$(LOADENV) && poetry run python -m telemetry.projects --retention

# Stop every service. The volumes are kept.
down:
	$(COMPOSE_CMD) down
	@$(MAKE) --no-print-directory prune

# Reclaim the images a rebuild orphaned. Neither podman nor docker collects
# them: an untagged layer may still be the cache the next build reuses, so
# the engine keeps it until asked. A tag rebuilt six times leaves five
# untagged copies of itself.
#
# Dangling only. `-a` would take images no container is running right now,
# which on a stopped stack is all of them.
prune:
	-$(CONTAINER) image prune -f

# Deletes every volume. Irreversible.
down-volumes:
	@echo "WARNING: this deletes all persistent data. Ctrl-C within 5s to abort."
	@sleep 5
	$(COMPOSE_CMD) down -v

# The container logs, as the engine holds them. Every service, this project's
# and the infrastructure alike. What the api, the six workers and the
# frontend log also goes to Elasticsearch as JSON; Grafana is where you read
# it back across services, filtered and over time.
logs:
	$(COMPOSE_CMD) logs -f

# The Streamlit application's log.
logs-frontend:
	$(COMPOSE_CMD) logs -f streamlit

# Upload failures surface here; the frontend only sees the status code.
logs-api:
	$(COMPOSE_CMD) logs -f api

# The shipper's own log. Where to look when Grafana shows nothing: a
# connection refused, a certificate it will not trust, or a rejected mapping
# is reported here and nowhere else.
logs-shipper:
	$(COMPOSE_CMD) logs -f filebeat

# The webserver and the daemon together. A code location that will not load
# is reported by the webserver, and a schedule or sensor that fired and
# failed by the daemon.
logs-orchestration:
	$(COMPOSE_CMD) logs -f dagster-webserver dagster-daemon

# How long the logs are kept. Run once against a running stack, after the
# shipper has written something: the retention belongs to the data stream,
# Elasticsearch remembers it, and every backing index the stream rolls over
# to afterwards inherits it. Nothing deletes anything until this has run,
# which is the state the stack ships in.
#
# The data stream's own lifecycle, not an ILM policy. A shipper cannot
# create an ILM policy, and naming one in filebeat.yml does not work either:
# Filebeat strips `index.lifecycle` out of the template it installs when
# `setup.ilm.enabled` is false, so the setting arrived nowhere and the
# indices were aged by nothing.
#
# The wildcard covers the dated streams an earlier version of filebeat.yml
# created alongside today's single one.
#
# Idempotent - PUT replaces. LOGS_RETENTION_DAYS overrides the default:
#
#     make logs-retention LOGS_RETENTION_DAYS=90
LOGS_RETENTION_DAYS ?= 30
# Age the shipped logs out after LOGS_RETENTION_DAYS. Until this has run,
# nothing is deleted.
#
# Run through `sh -c`, with the credential read from the container's own
# environment rather than passed in, so it stays out of the process list
# and out of make's echo of the command.
#
# No `--fail-with-body`, which is how this would normally report a refusal:
# the curl in the Elasticsearch image predates it and exits with a usage
# error instead. So the answer is read directly, which is also the only way
# to see which streams it matched.
logs-retention:
	@$(COMPOSE_CMD) exec -T elasticsearch sh -c 'answer=$$(curl -sS \
	  --cacert /usr/share/elasticsearch/config/certs/ca.crt \
	  -u "elastic:$$ELASTIC_PASSWORD" \
	  -X PUT "https://localhost:9200/_data_stream/qa-logs*/_lifecycle" \
	  -H "Content-Type: application/json" \
	  -d "{\"data_retention\":\"$(LOGS_RETENTION_DAYS)d\"}"); \
	  echo "$$answer"; \
	  case "$$answer" in *\"acknowledged\":true*) ;; *) exit 1;; esac'
	@echo "qa-logs is kept for $(LOGS_RETENTION_DAYS) days."

# The other half of the retention, and the one `logs-retention` cannot do.
# That target ages what Elasticsearch holds; this ages the FILES the shipper
# read them out of, and nothing else does.
#
# Each process writes {service}-{host}-{pid}.log, because the WRITER is what
# the name has to be unique per: two processes rotating one file take each
# other's lines with them. The cost is a file per container and a file per
# host run, and nothing else deletes one. `RotatingFileHandler` only rotates
# the file its own live process owns, filebeat mounts both directories
# read-only on purpose, and filebeat's `ignore_older` and `clean_inactive`
# age its REGISTRY and not the disk.
#
# Both places a line is written: the volume, through the api, which mounts
# it writable, and ./logs on the host, which make can delete from itself.
# Deletes by mtime, so a file a live process is still appending to is never
# old enough to take.
#
# Counted one place at a time under pipefail: piped into the count together,
# a stopped api was "0 file(s) deleted" and passed.
#
#     make logs-prune LOGS_KEEP_DAYS=7
LOGS_KEEP_DAYS ?= 30
# Delete the log files no process has written to for LOGS_KEEP_DAYS.
logs-prune: logs-dir
	@set -o pipefail; find logs -type f -mtime +$(LOGS_KEEP_DAYS) -print -delete \
	  | wc -l | xargs printf '%s file(s) deleted in ./logs.\n'
	@set -o pipefail; $(COMPOSE_CMD) exec -T api sh -c \
	  'find /var/log/qa -type f -mtime +$(LOGS_KEEP_DAYS) -print -delete' \
	  | wc -l | xargs printf '%s file(s) deleted on the volume.\n'

# Empties the log files, on the volume the services write to and in ./logs. The
# half of `logs-wipe` that needs no Elasticsearch, which `wipe` runs alone where
# the stack has none.
LOG_FILES = { $(COMPOSE_CMD) exec -T api sh -c 'find /var/log/qa -type f -exec truncate -s 0 {} +' || true; \
              find logs -type f -exec truncate -s 0 {} + 2>/dev/null || true; }

# This database's log lines: the `db` field every line carries is what
# Elasticsearch deletes by, so another database's lines stay. The JSON files
# Filebeat ships from are shared by every database and are left.
# `ALL_DATABASES=1` takes the whole `qa-logs*` data streams that Grafana
# reads and empties the files. What `make wipe` runs - a log trail of a
# corpus that is gone describes nothing.
#
# Through the container: elasticsearch publishes no port, and Argilla
# reaches it over TLS with a certificate the host does not have. Filebeat
# recreates the stream on its next line, so nothing needs restarting. The
# credential is read from the container's own environment, as in
# logs-retention.
#
# The answer is read: `index_not_found_exception` is a deployment that has
# logged nothing yet and passes; anything but that or an acknowledgement,
# a stopped container included, stops here.
#
# The files are emptied, not deleted: every running service holds its own
# open, and an unlinked one goes on being written where Filebeat cannot see
# it until a restart or a rotation.
logs-wipe:
	@$(call CONFIRMED,logs-wipe: it deletes this database's log lines)
	@$(LOADENV) && answer=$$($(COMPOSE_CMD) exec -T -e WIPE_DB="$(if $(filter 1,$(ALL_DATABASES)),,$$APP_DB_NAME)" elasticsearch sh -c 'if [ -z "$$WIPE_DB" ]; then \
	  curl -sS --cacert /usr/share/elasticsearch/config/certs/ca.crt -u "elastic:$$ELASTIC_PASSWORD" \
	  -X DELETE "https://localhost:9200/_data_stream/qa-logs*"; else \
	  curl -sS --cacert /usr/share/elasticsearch/config/certs/ca.crt -u "elastic:$$ELASTIC_PASSWORD" \
	  -X POST "https://localhost:9200/qa-logs*/_delete_by_query?conflicts=proceed&refresh=true" \
	  -H "Content-Type: application/json" -d "{\"query\":{\"bool\":{\"should\":[{\"term\":{\"db\":\"$$WIPE_DB\"}},{\"term\":{\"db.keyword\":\"$$WIPE_DB\"}}],\"minimum_should_match\":1}}}"; fi' 2>&1); \
	  echo "$$answer"; \
	  case "$$answer" in *'"acknowledged":true'*|*'"deleted":'*|*index_not_found_exception*) ;; *) exit 1;; esac
	@if [ "$(ALL_DATABASES)" = 1 ]; then \
	  $(LOG_FILES); \
	  echo "log stream deleted and files emptied."; \
	else echo "this database's log lines deleted; the shared files are left (ALL_DATABASES=1 empties them)."; fi

# ── Database ───────────────────────────────────────────────────────────────
#
# Alembic owns the schema. The models say what the tables should be; a
# revision says how to get an existing database there, which `create_all`
# could never do. Runs on the host against the mapped port, as the
# application role, so tables are not owned by the superuser.
#
# After changing a model:  make migration m="what changed"  then  make schema
# Review the generated revision before applying it: autogenerate sees tables,
# columns, indexes and constraints, and never a trigger or a data backfill.

# Bring the database up to the newest revision.
schema:
	$(LOADENV) && poetry run alembic upgrade head

# Write a revision from the difference between the models and the database.
#   make migration m="add the dropped counts"
migration:
	@[ -n "$(m)" ] || { echo 'usage: make migration m="what changed"'; exit 2; }
	$(LOADENV) && poetry run alembic revision --autogenerate -m "$(m)"

# What the database is at, and everything it could be at.
schema-status:
	$(LOADENV) && poetry run alembic current
	$(LOADENV) && poetry run alembic history --indicate-current

# Take the newest revision back off. From the first revision that drops
# every table, archived_rows included, so it refuses without CONFIRM as schema-reset does
# does.
schema-down:
	@echo "At the first revision this drops every table, archived_rows included;"
	@echo "make schema-status says which one it is at."
	@$(call CONFIRMED,schema-down)
	$(LOADENV) && poetry run alembic downgrade -1

# Adopt a database that already holds the tables, without running anything:
# records it as being at the newest revision. For a deployment that predates
# migrations.
schema-stamp:
	$(LOADENV) && poetry run alembic stamp $(or $(rev),head)

# Drops every table and rebuilds from the revisions. Irreversible.
schema-reset:
	@$(call CONFIRMED,schema-reset: it drops every table)
	$(LOADENV) && poetry run alembic downgrade base
	$(LOADENV) && poetry run alembic upgrade head

# ── Pipeline stages ────────────────────────────────────────────────────────
#
# Nothing starts by itself. A row arrives `new` and no worker looks at it;
# `-start` is what makes it claimable and `-stop` is what takes it back. A
# stage never sets another stage going.
#
# The bare target runs one drain on the host, in the foreground, against the
# same database the workers use - which is what you want while developing a
# stage. It, every `-rerun` and `topics-discover` refuse while that stage's
# container worker is running, and print the command that stops it. Every
# other target is the same operation as the route beside it:
#
#   make parse-status      GET /parsing/status
#   make parse-start      POST /parsing/start
#   make parse-stop       POST /parsing/stop
#   make parse-retry      POST /parsing/retry
#   make parse-rerun      POST /parsing/rerun
#   make chunk-status      GET /chunking/status
#   make chunk-start      POST /chunking/start
#   make chunk-stop       POST /chunking/stop
#   make chunk-retry      POST /chunking/retry
#   make chunk-rerun      POST /chunking/rerun
#   make extract-status    GET /extraction/status
#   make extract-start    POST /extraction/start
#   make extract-stop     POST /extraction/stop
#   make extract-retry    POST /extraction/retry
#   make extract-rerun    POST /extraction/rerun
#
# Add SHA or PASSAGE to narrow any of them to one item, which mirrors the
# route's own /{scope}/{value} segment:
#
#   make parse-start SHA=abc…       POST /parsing/document/abc…/start
#   make extract-rerun SHA=abc…     POST /extraction/document/abc…/rerun
#   make extract-retry PASSAGE=41   POST /extraction/passage/41/retry
#   make extract-status SHA=abc…     GET /extraction/document/abc…/status
#
# None of them but `-rerun` runs anything: they move rows between statuses,
# and whichever worker is watching picks up what is claimable. `-rerun`
# checks the model, queues every row again and drains here.
#
# No stage route runs anything either. The work happens in the workers, and
# the api container is sized to serve JSON. `POST /pipeline/run` is not an
# exception: it asks the ORCHESTRATOR for a run and answers at once with the
# run's id, which is why it is the one control that needs a component other
# than the backend. See the pipeline targets further down.

# Drain the parsing queue here. The first run downloads Docling's weights.
parse:
	@$(if $(WAIT),,$(call IDLE,parse-worker))
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run $(call AWAIT,parse-worker)

# Report how many documents are in each parse state.
parse-status:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run --status $(ONLY)

# Queue every document this stage has not been asked to do yet. Nothing
# reaches a worker until this runs.
parse-start:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run --start $(ONLY)

# Take back whatever has not begun. The one in hand finishes.
parse-stop:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run --stop $(ONLY)

# Return every failed document to the pending queue. A document a worker died
# holding is failed by the next run, so this covers that too.
parse-retry:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run --retry $(ONLY)

# Run this stage again over every document, finished ones included. For when
# the code behind it changed and its output needs rebuilding.
parse-rerun:
	@$(if $(strip $(ONLY)),:,$(call CONFIRMED,parse-rerun: it parses every document again))
	@$(call IDLE,parse-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.parsing.run --rerun $(ONLY)

# Split every parsed document into passages. Replaces the passages a document
# already had and the new cut does not repeat, which cascades to the facts and
# questions drawn from them; a passage repeated exactly keeps its facts.
chunk:
	@$(if $(WAIT),,$(call IDLE,chunk-worker))
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run $(call AWAIT,chunk-worker)

# Report how many documents are in each chunking state.
chunk-status:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --status $(ONLY)

# Queue every document this stage has not been asked to do yet. Nothing
# reaches a worker until this runs.
chunk-start:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --start $(ONLY)

# Take back whatever has not begun. The one in hand finishes.
chunk-stop:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --stop $(ONLY)

# Return every failed document to the pending queue.
chunk-retry:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --retry $(ONLY)

# Run this stage again over every document, finished ones included. For when
# the code behind it changed and its output needs rebuilding. A passage the new
# cut repeats exactly - text, heading trail, sentences and cells - is kept with
# its facts and takes its new ordinal and pages in place. Every other passage
# is replaced, and with it go its topic memberships, any fact left citing no
# passage and any bridge that cited it; a question resting on one is rejected
# as source_changed and kept, and its follow-ups leave the release. Without
# SHA that is
# the whole corpus, so it refuses unless CONFIRM names the database. It refuses, naming the
# counts, while released, accepted or reviewed questions rest on what it
# would replace; FORCE=1 goes on, and those questions are rejected as
# source_changed, never deleted.
chunk-rerun:
	@$(call IDLE,chunk-worker)
	@$(BANNER)
	@$(if $(strip $(ONLY)),:,$(call CONFIRMED,chunk-rerun: it replaces every passage the new cut changes))
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --rerun $(if $(filter 1,$(FORCE)),--force) $(ONLY)

# Read every stored passage's language and vocabulary again, in place. Only
# those two change, and facts.language moves with the passage a fact opens
# on; passages, sentence offsets and facts all stay, which is
# what chunk-rerun cannot promise - it deletes every passage whose sentences
# moved, and the facts go with them. Fit the topics afterwards to see the
# difference.
chunk-revocabulary:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m preprocessing.chunking.run --revocabulary $(ONLY)

# Drain the extraction queue here. Needs the model in LLM_MODEL to be
# served at LLM_BASE_URL.
extract:
	@$(if $(WAIT),,$(call IDLE,extract-worker))
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run $(call AWAIT,extract-worker)

# Report the extraction queue, and how many facts passed every check.
extract-status:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --status $(ONLY)

# Queue every passage this stage has not been asked to do yet. Nothing
# reaches a worker until this runs.
extract-start:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --start $(ONLY)

# Take back whatever has not begun. The one in hand finishes.
extract-stop:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --stop $(ONLY)

# Return every failed passage to the pending queue.
extract-retry:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --retry $(ONLY)

# Run this stage again over every passage, finished ones included. For when
# the code behind it changed and its output needs rebuilding. Each passage's
# citations, bridges' aside, are replaced, and with them go any fact left
# citing no passage; a question resting on one is rejected as source_changed
# and kept, and its follow-ups leave the release. Without SHA or PASSAGE that is the
# whole corpus, so it refuses unless CONFIRM names the database. A fact read again word for word
# is kept. It refuses, naming the counts, while released, accepted or
# reviewed questions rest on what it would replace; FORCE=1 goes on.
extract-rerun:
	@$(call IDLE,extract-worker)
	@$(BANNER)
	@$(if $(strip $(ONLY)),:,$(call CONFIRMED,extract-rerun: it replaces every passage's facts))
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --rerun $(if $(filter 1,$(FORCE)),--force) $(ONLY)

# Judge every stored fact again with today's checks. The model is not called
# and no statement changes: only what the checks read off one. This is what
# applies a change to the checks without re-extracting the corpus.
extract-revalidate:
	@$(call IDLE,extract-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --revalidate $(ONLY)

# Read every topic's passage groups for the claims that need more than one of
# them. A pass of its own rather than part of the queue: the unit is a group
# of passages the topic model put together, so topics must be fitted first.
# Re-running replaces the bridges it wrote last time instead of adding to
# them. It refuses, deleting nothing, while an accepted question cites one
# of those bridges, and says how many; FORCE=1 replaces them anyway, and
# those questions are rejected as source_changed with them, and kept. MISSING=1 deletes nothing
# and reads only the topics holding no bridge yet, which is what `corpus`
# runs, so a second build neither replaces nor stops on cited bridges.
#
#   make extract-bridge FORCE=1
#   make extract-bridge MISSING=1
extract-bridge:
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --bridge $(if $(filter 1,$(FORCE)),--force) $(if $(filter 1,$(MISSING)),--missing) $(ONLY)

# Refuse the atomic facts a passage yielded above the cap
# EXTRACTION_MIN_OTHER_SHARE works out to, or above the passage's own
# sentences plus list items where those are more, keeping the ones that
# assert a number, a date or a name. No model is called, so a corpus
# extracted before the cap existed is re-balanced in seconds rather than
# re-read over hours.
# Only the verdict moves: nothing is deleted, and the facts refused carry
# `over_cap` like any other refusal. It moves both ways: a fact an earlier,
# lower cap refused is given back as it was judged when extracted, and
# `make extract-revalidate` run afterwards judges it with today's checks.
extract-recap:
	@$(call IDLE,extract-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --recap $(ONLY)

# Re-decide every stored `duplicate` refusal under today's dedup rule, and take
# out the citations an earlier version's refusal added to the fact it
# repeated. No model is called. A citation folded in counted the refused
# passage towards every question asked of that fact; it goes, and the fact's
# evidence is rebuilt from the citation it keeps. A refusal the rule would no
# longer make - another number, another language or kind, a cosine under
# EXTRACTION_DUPLICATE_COSINE - is given back as it was judged when
# extracted, and the passages of the ones given back, and no others, are
# then judged again and re-capped as extract-revalidate and extract-recap
# would. Run questions-rescore before questions-reverify.
#
# This, extract-revalidate and extract-recap write verdicts across the
# corpus, so each refuses to run while extract-worker writes them too.
extract-dedup:
	@$(call IDLE,extract-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --dedup $(ONLY)

# Write the vectors onto passages and facts already stored. No model is
# called - a vector is read off a statement that is already written - so a
# corpus extracted before the embedding columns existed is filled in at the
# speed of the embedding model rather than re-read over hours.
#
# It does not apply the dedup gate. A fact stored before the gate existed was
# accepted, and refusing it now would rewrite a verdict the corpus was
# measured under; re-extract to have it judged.
extract-embed:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --embed $(ONLY)

# Give a digest to the passages that finished extraction without one: the
# model could not give it, or the provider's filter refused the passage. Their
# atomic facts were kept and are not read again; only the summary and the
# outline are written, and a passage whose digest fails again keeps its note
# and is tried on the next run. Also those above EXTRACTION_DIGEST_MIN_CHARS
# that hold no digest, which is how a lowered floor reaches stored passages.
# Calls the digest model once per such passage.
extract-digests:
	@$(call IDLE,extract-worker)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m extraction.run --digests

# ── Topic modelling ────────────────────────────────────────────────────────
#
# The one stage nothing triggers on its own. Every topic is fitted jointly
# over one vocabulary, so a topic cannot be rediscovered by itself and a fit
# is asked for: POST /topics/discover queues one for the worker, and
# topics-discover queues one and runs it here.
#
#   make topics-status       GET /topics/status
#   make topics-discover    POST /topics/discover
#   make topics-visualise    GET /topics/visualisation/{language}
#   make topics-render       (no route; redraws it from the stored model)
#   make topics-name         (no route; names the topics a fit left unnamed)
#   make topics-stop        POST /topics/stop
#   make topics-retry       POST /topics/retry
#   make topics-delete    DELETE /topics

# Run any queued fit now, in the foreground.
topics:
	@$(call IDLE,topic-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run

# Report the run queue, how many topics and memberships are stored, and how
# many passages are in no topic.
topics-status:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --status

# Queue a fit and run it. Replaces the topics and memberships of each
# language it fits; a name or coverage choice a person gave goes to the new
# topic holding most of its passages.
topics-discover:
	@$(call IDLE,topic-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --discover $(if $(ENSURE),--ensure)

# Write each language's pyLDAvis page to ./topics/<language>.html. Reads the
# stored page; topics-render is what draws one.
topics-visualise:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --visualise

# Redraw each language's page from its stored model, without re-fitting the
# corpus. This is what the `models` bucket is for: `export` holds a view and
# `models` holds what the view is of, so a lost or corrupted page costs a
# render rather than a fit.
#
# The page it writes REPLACES the one already there. One model is kept per
# language - the next fit replaces it, as the database holds one fit's
# topics per language - so this picks which language to redraw and not which
# fit to redraw from. A figure drawn from an older model would number its
# topics off rows that no longer exist.
#
# CODE and not LANG: make imports the environment, LANG is the POSIX locale
# and is always set, so `make topics-render` quietly ran with
# `--language C.UTF-8` and refused every language the corpus has.
#
#   make topics-render
#   make topics-render CODE=de
topics-render:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --render $(if $(CODE),--language $(CODE))

# Name the topics a fit left unnamed, off the stored fit and with no refit:
# what to run when the naming model was down or refused a batch. A topic
# that has a name, a person's included, is left as it is.
topics-name:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --name

# Delete every topic and membership, any fit queued or running, the judge's
# verdicts on the topics and each topic's question-generation queue state.
# Each language's figure and stored model go to the `archive` bucket.
# Passages, facts and questions stay. A label a person assigned is stored
# nowhere else, and the archived row is now the only copy of one.
topics-delete:
	@$(call CONFIRMED,topics-delete: it deletes every topic and any label on one)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --delete

# Withdraw a fit that has been asked for but not started.
topics-stop:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --stop

# Return every failed fit to the queue.
topics-retry:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --retry

# ── Question generation ────────────────────────────────────────────────────
#
# The same five verbs as every other stage, over topics. A question's subject
# is a topic, so that is what the queue is over, and TOPIC=<id> narrows any
# of them to one:
#
#   make questions-status                 GET /questions/status
#   make questions-start                 POST /questions/start
#   make questions-start TOPIC=7         POST /questions/topic/7/start
#
# Needs the model in LLM_MODEL served at LLM_BASE_URL, the second model in
# QUESTIONS_VERIFIER_MODEL served beside it, and EMBEDDING_MODEL downloaded -
# the first run fetches it into the Hugging Face cache and later runs read it
# from there.
#
# What is written is QUESTIONS_TYPE_MIX and QUESTIONS_DIFFICULTY_MIX, both in
# configs/env/backend.env, and both proportions rather than counts. A kind
# with a weight of 0 is never planned; a follow-up takes its kind from
# QUESTIONS_FOLLOWUP_TYPES. The Questions page puts the mix that
# was asked for beside the mix that came out.
#
# LLM_NUM_CTX and LLM_REASONING_EFFORT apply to every model it calls: a
# thinking model asked for a structured answer spends its window reasoning
# and returns an empty string.

# Drain the question queue here, in the foreground.
questions:
	@$(if $(WAIT),,$(call IDLE,question-worker))
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run $(call AWAIT,question-worker)

# Report the queue by topic state, and how many questions are held.
questions-status:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --status $(ONLY)

# Queue every topic this stage has not been asked to do yet. Nothing reaches
# a worker until this runs.
questions-start:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --start $(ONLY)

# Take back whatever has not begun. The one in hand finishes.
questions-stop:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --stop $(ONLY)

# Return every failed topic to the pending queue.
questions-retry:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --retry $(ONLY)

# Return a topic a dead worker still holds, without waiting out its lease.
#
# The gap between `retry`, which takes the failed, and `rerun`, which skips
# what a worker holds. An interrupted topic is `in_progress` and neither of
# those touches it, so until this existed the only thing that moved one was
# the lease.
#
#   make questions-reclaim TOPIC=473    one topic
#   make questions-reclaim              every one the stage holds
#
# NARROW IT while a worker may be up. Nothing here can tell a dead claim
# from a live one, and handing a live worker's row to a second worker is
# what the lease exists to prevent. Over the whole stage only when it is
# stopped, which is what it asks first; narrowed, it does not.
questions-reclaim:
	@$(if $(strip $(ONLY)),,$(call IDLE,question-worker))
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --reclaim $(ONLY)

# Run this stage again over every topic, finished ones included. Cheaper than
# it looks: facts an accepted question already rests on are skipped, so this
# writes about what the last run did not reach rather than starting over.
questions-rerun:
	@$(if $(strip $(ONLY)),:,$(call CONFIRMED,questions-rerun: it writes questions over every topic again))
	@$(call IDLE,question-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --rerun $(ONLY)

# Put every stored question through the gates that need no model: its facts
# still pass their own checks and no person rejected one in review, its
# evidence is still spread the way its difficulty says, it is still well
# formed, and no earlier question already asks it. Rejects what no longer
# holds and never un-rejects, because accepting is a person's. A question a
# person accepted is rejected only when its facts no longer hold; no other
# gate overrules the person. This is what carries extract-revalidate, or a
# re-extraction of one document, through to the questions resting on it.
questions-reverify:
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --reverify $(ONLY)

# Rewrite every stored question's passage, document and topic scope and its
# difficulty from the facts it cites now, as generation bands a new one. No
# model is called and no verdict moves. For after the make extract-dedup that
# takes out an earlier version's fold citations - the v0.2.2 upgrade - and
# before questions-reverify: those citations leave a stored scope describing
# evidence the question never rested on, which questions-reverify would
# reject as source_changed. After any other change to a citation - a
# re-extraction, a deleted document, the extract-dedup a deletion runs - leave
# it out: the question lost a fact it rested on, and source_changed is right.
questions-rescore:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --rescore $(ONLY)

# Take every stored margin again, after a change to where a similarity scale
# is measured from. Reads QUESTIONS_DUPLICATE_FLOOR and
# EXTRACTION_DUPLICATE_FLOOR and rewrites gate_scores and confidence on the
# questions and the facts.
#
# No model, no embedder, no service: every number it needs is already in the
# row, so this is arithmetic over one column. It moves NO verdict - a
# question's status and rejected_reason are untouched, which is what
# separates it from questions-reverify. Running it twice writes nothing the
# second time.
confidence-recalibrate:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m stages.recalibrate_run

# Ask the verifier again, of every accepted question written to have no
# answer, whether its passages settle it - state the answer, refute its
# premise, or cover its case with a list or a general rule - over what it
# cites and then over the corpus probe the checker reads. Rejects what they
# settle as answerable_after_all or answerable_elsewhere, released questions
# included, and leaves one a person accepted alone. CALLS THE VERIFIER MODEL,
# two calls a question at most, which is why it is not part of
# questions-reverify. Each verdict is written to the row's gate_scores, and a
# row already carrying one is skipped, so running it again costs only what is
# new. Run make questions-balance after it to draw the release again.
#
#   make questions-rejudge TOPIC=473    one topic
#   make questions-rejudge              every accepted unanswerable question
questions-rejudge:
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --rejudge $(ONLY)

# Draw the balanced release out of every accepted question, and report what
# it came out as. Accepting a question says it is sound; this says what the
# SET looks like, and the two are different problems - every gate can do its
# job and still leave a set lopsided towards the unanswerable and the easy,
# because what survives a filter is whatever the material happened to offer.
#
# Holds four shares at once: how much of the release has no answer, how it
# spreads over the difficulty bands, over the kinds and over the languages -
# QUESTIONS_RELEASE_UNANSWERABLE, _DIFFICULTY, _TYPES and _LANGUAGES in
# backend.env - and one question of each twin group. Calls the verifier:
# each released question is put to it with its nearest released neighbour of
# its language, about one call per released question, and a pair it reads as
# wanting one answer is a twin group the next draw holds to. A column on the
# rows already there, so nothing is deleted, the questions left out stay
# queryable, and running it again replaces the draw. Reports the
# yield - how much of the accepted pool made it in - and names any quota the
# pool could not fill. Always over every topic: TOPIC= does not narrow it.
questions-balance:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.run --balance

OUT ?= questions.xlsx

# The questions as a spreadsheet: four sheets - Questions, Citations (the
# facts each cites), Assessment (what the judge said of each) and Summary
# (counts). A question's own row carries what it rests on
# too - the facts, the evidence under them, its subjects, its documents by
# title, the answer at length and the judge's reasoning - so a row reads
# without joining the citations by id. This is the way the dataset leaves
# the database - everything else that reads these rows is a service, and
# Argilla is NOT
# this: it holds a disposable copy of a stratified SAMPLE pushed for review,
# so exporting from there gives back the rows somebody was asked to look at
# rather than the set.
#
# OUT names the file. FILTER is passed through to the exporter, and takes
# the same narrowing the Questions page and the API do - so what lands in
# the workbook is what the filter says, with no default scope quietly
# applied. Ask for nothing and you get everything, rejected rows included,
# which is what the same request to /questions returns.
#
#   make questions-export
#   make questions-export OUT=release.xlsx FILTER="--released"   # what questions-balance drew
#   make questions-export OUT=exam.xlsx FILTER="--status accepted --cognitive-level analyse"
#   make questions-export FILTER="--status accepted --unanswerable"
#   make questions-export FILTER="--no-citations"      # much faster, questions only
#
#   python -m question_generation.export --help        # every filter there is
questions-export:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.export --out "$(OUT)" $(FILTER)

# ── The evaluation phase ───────────────────────────────────────────────────
#
# An LLM judge over every fact, topic and question, run AFTER the whole
# pipeline and never during it. A separate phase because it is a separate
# question: every stage before it decides what to keep, and this one decides
# nothing at all.
#
# What it produces is an opinion recorded BESIDE the checker's verdict, in a
# column of its own, and the pair where they differ is the output that
# matters - an artefact the pipeline kept and the judge refused is either a
# check that let something through or a judge that is wrong, and only a
# person settles which. See backend/assessment/README.md, and
# evaluation/README.md on why a model's answer cannot be a gate here.
#
#   make assess-start && make assess      # judge everything, then watch
#   make assess-status                    # how far it has got
#   make assess-enrol                     # enrol and count, before paying; not a dry run
#
# Off unless ASSESSMENT_ENABLED is true in .env, and every target below says
# so and stops rather than quietly doing nothing.
#
# ASSESSMENT_JUDGE_MODEL is who judges, and it should not be LLM_MODEL: a
# model asked whether its own facts follow from its own evidence says yes.
# Unset, `assess` judges nothing.
#
# ASSESSMENT_KINDS and ASSESSMENT_SAMPLE in configs/env/backend.env are the
# cost dials. A sample bounds how many model calls a kind costs; every
# fact of a large corpus is tens of thousands.
ASSESS = $(LOADENV) && PYTHONPATH=backend poetry run python -m assessment.run

# Drain the judging queue here, in the foreground.
assess:
	@$(if $(WAIT),,$(call IDLE,assess-worker))
	@$(BANNER)
	$(ASSESS) $(call AWAIT,assess-worker)

# Report the queue by artefact state, and warn when no judge is named.
assess-status:
	$(ASSESS) --status $(ONLY)

# Enrol every artefact that has no assessment and queue it. Nothing is
# judged until this runs, and nothing upstream enrols anything: a fact
# arrives from extraction with nowhere to record a judgement, so this is
# what creates the row as well as what queues it.
#
# Narrow it with ONLY to pay for one kind:
#   make assess-start ONLY=--only\ kind=question
assess-start:
	$(ASSESS) --start $(ONLY)

# Enrol without queuing. Not a dry run: it writes a `new` assessment for
# every artefact it draws, which no worker claims until `assess-start`
# queues it, and reports how many there are before anybody pays for them.
# A fact costs three model calls, a topic two and a question six, one of
# them returning six scores (a follow-up five, without that one).
# `assess-start` enrols again first, and under the same settings draws the
# same rows.
assess-enrol:
	$(ASSESS) --enrol

# Take back whatever has not begun. The artefact in hand finishes.
assess-stop:
	$(ASSESS) --stop $(ONLY)

# Return every artefact the judge could not be reached for. A failure here
# is the MODEL being down, not an artefact being bad: a judgement that came
# back as a refusal is recorded as one and is not a failed row.
assess-retry:
	$(ASSESS) --retry $(ONLY)

# Return an artefact a dead worker still holds, without waiting out its
# lease. Narrow it unless the worker is stopped, which over the whole stage
# it asks first; see stages/README.md.
assess-reclaim:
	@$(if $(strip $(ONLY)),,$(call IDLE,assess-worker))
	$(ASSESS) --reclaim $(ONLY)

# Judge everything again, finished rows included. This is what a changed
# template or a changed judge model calls for, so a corpus never holds two
# opinions from two template versions with nothing saying which is current.
# The judge is asked first: one that does not answer or is not named leaves
# every stored verdict as it was. Once it answers, every verdict and metric
# in scope is cleared, the sample is enrolled again, and each row is judged
# again; a row whose judging fails holds no verdict rather than an old one.
assess-rerun:
	@$(if $(strip $(ONLY)),:,$(call CONFIRMED,assess-rerun: it judges every sampled question again))
	@$(call IDLE,assess-worker)
	@$(BANNER)
	$(ASSESS) --rerun $(ONLY)

# How varied an exported workbook's questions are, the way the DataMorgana
# paper measures a benchmark: n-gram diversity (higher is more varied),
# self-repetition, the word and part-of-speech compression ratios and the
# homogenization score (lower is more varied), one row per language. No LLM
# is asked; the spaCy pipeline and the embedding model are loaded. FILE is
# what questions-export wrote; its FILTER chooses the set, and the paper's
# is the answerable questions.
# SIZE draws that many from each language, because these metrics move with
# a set's size and two sets compare only at one. AGAINST compares FILE with
# a second workbook as the paper compares two methods: both drawn fifty
# times to 80% of the smaller set, every metric put to Welch's t-test.
# BY=category measures each category of each language on its own, and
# BY=kind each kind (single, needs_both, compound). Where the workbook holds
# the paper's judge, its mean scores follow. BY=document draws the paper's
# Figure 1: the part-of-speech compression ratio of SIZE questions (200
# unless given) drawn from 5, 10, 15 ... documents, for a corpus of many
# documents. LABELS=<file> takes reviewers' yes/no labels of some questions
# (JSONL, an id and one field per label) and corrects each labelled share by
# the paper's judge's verdict on all of them, per language and pooled, with
# its 95% interval. CODE and not LANG, as for topics-render.
#
#   make questions-export OUT=set.xlsx FILTER="--status accepted --answerable --roots-only"
#   make diversity FILE=set.xlsx SIZE=200
#   make diversity FILE=new.xlsx AGAINST=old.xlsx
#   make diversity FILE=set.xlsx BY=category
#   make diversity FILE=set.xlsx BY=kind
#   make diversity FILE=pool.xlsx BY=document SIZE=200
#   make diversity FILE=set.xlsx LABELS=labels.jsonl
#   make diversity FILE=set.xlsx LABELS=labels.jsonl FIELDS=usable,key_correct
# Every field of LABELS but id and question is a label, except a workbook
# column (released, status, answerable), which is refused; FIELDS names the
# labels when the file holds other things.
diversity:
	@[ -n "$(FILE)" ] || { echo 'usage: make diversity FILE=<workbook> [AGAINST=<workbook>] [BY=category|kind|document] [CODE=de] [SIZE=200] [LABELS=<file> [FIELDS=a,b]]'; exit 2; }
	$(ASSESS) --diversity --file "$(FILE)" $(if $(AGAINST),--against "$(AGAINST)") $(if $(BY),--by $(BY)) $(if $(CODE),--language $(CODE)) $(if $(SIZE),--size $(SIZE)) $(if $(LABELS),--labels "$(LABELS)") $(if $(FIELDS),--fields "$(FIELDS)")

# ── Question runs ──────────────────────────────────────────────────────────

# The 20 newest runs, newest first, and how many questions each wrote.
# A run is named by RUN_ID where one was given and by a uuid otherwise; see
# backend/settings/runs.py. A run marked (deleted) has had its questions
# removed and is being read out of archived_rows.
questions-runs:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.runs --list

# Two runs side by side, on the gate that stopped each question. Ordered by
# how much the two disagree, because that is the question being asked.
#
#   make questions-diff RUNS="a-gpt-4.1 b-gemma4-12b"
#
# Reads the live questions AND the archived ones. A rerun appends, so two
# runs' questions stand side by side; the archive is what keeps the rows a
# deletion or a re-chunk took since. Nothing here gates - a model's answers
# move between two runs at the same temperature.
questions-diff:
	@test -n "$(RUNS)" || { echo 'usage: make questions-diff RUNS="<older> <newer>"'; exit 2; }
	$(LOADENV) && PYTHONPATH=backend poetry run python -m question_generation.runs $(RUNS)

# ── Cost ───────────────────────────────────────────────────────────────────

# What the models have cost, read off a CAPTURED log - the text one a drain
# wrote to a terminal, as `make questions ... | tee run.log` leaves behind.
# Every call logs its tokens and its price; litellm prices the response
# rather than this counting it, because the provider is the only thing that
# knows what it billed for. A self-hosted model has no published price and
# logs no cost at all, which is the truth about it rather than a zero.
#
# LOG is required, and that is the fix for what these used to do. They
# defaulted to /var/log/qa/*.log, which is a path inside the containers and
# not on the host they run on - and holds JSON, which the pattern below
# cannot match anyway. Both printed "no priced calls in the log", which
# reads as "the pipeline cost nothing" rather than "I read nothing". A LOG
# naming no readable file stops them for the same reason: cat said so on
# stderr, and the total still said nothing was spent, with exit status 0.
#
# For the LIVE numbers, neither of these: Grafana's Pipeline throughput
# dashboard sums llm.cost_usd off Elasticsearch, and Phoenix has the same
# figures per span, per run. What these two have that neither does is a log
# from a run that is over, on a machine with no stack up.
#
# Both read the log through SPENT, so one log has one total. A call that
# failed after it was billed is spend too, and is counted: its line says
# "did not answer" and carries its price as an answered one does.
#
#   make spend LOG=run.log
#   make spend LOG=run.log SINCE=2026-09-18
SPENT = test -r "$(LOG)" && test ! -d "$(LOG)" || { echo "cannot read LOG=$(LOG)" >&2; exit 2; }; \
 cat "$(LOG)" \
 | $(if $(SINCE),grep "$(SINCE)",cat) \
 | grep -oE '[^ ]+ (answered|did not answer) _[A-Za-z]+ in [0-9.]+s \([0-9,]+ in, [0-9,]+ out, \$$[0-9.]+\)' \
 | sed -E 's/^([^ ]+) (answered|did not answer) (_[A-Za-z]+) in [0-9.]+s \(([0-9,]+) in, ([0-9,]+) out, \$$([0-9.]+)\)/\1 \3 \4 \5 \6/' \
 | tr -d ','

# What the models have cost, split by which model answered and what it was
# asked for.
#
# The shape is the Pydantic class the call had to return, and every stage
# has its own: _Facts and _Digest read a passage, _Answered writes a
# question, _Recovered gets its answer back out, _NamesItsSource and
# _SelfContained judge the wording. So this is what each JUDGEMENT costs,
# which `make spend` cannot say and which is the number to look at after
# moving one of them to another model.
#
#   make spend-by-shape LOG=run.log
#   make spend-by-shape LOG=run.log SINCE=2026-09-21
#
# Ordered by call count, because the shape at the top is the one worth
# moving somewhere cheaper.
spend-by-shape:
	@test -n "$(LOG)" || { echo 'usage: make spend-by-shape LOG=<a captured log> [SINCE=<date>]'; exit 2; }
	@printf '%-24s %-18s %8s %12s %12s %10s\n' \
	   MODEL SHAPE CALLS 'TOKENS IN' 'TOKENS OUT' COST
	@$(SPENT) \
	 | awk '{k=$$1" "$$2; n[k]++; i[k]+=$$3; o[k]+=$$4; c[k]+=$$5} \
	     END {for (k in n) {split(k,p," "); \
	       printf "%-24s %-18s %8d %12d %12d %9.4f\n", p[1],p[2],n[k],i[k],o[k],c[k]}}' \
	 | sort -k3 -rn
	@$(SPENT) \
	 | awk '{i+=$$3; o+=$$4; c+=$$5; n++} END {if (n==0) {print "\nno priced calls in the log"; exit} \
	     printf "%-24s %-18s %8d %12d %12d %9.4f\n", "", "TOTAL", n, i, o, c}'

# What the rows still to do will take and cost, before anything is queued: the
# documents not chunked, the passages not extracted, the topics not written
# for and the accepted questions, each times what a row of its stage took in
# the reviewed build. A stage not yet reached is projected from the one
# before it at that build's ratios, the topics from the whole corpus and not
# from the passages still to extract. DRAINS says how many drains work a stage
# at once and divides its time, never its spend.
#
#   make estimate
#   make estimate DRAINS=questions=2,extract=2
estimate:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m stages.estimate $(if $(DRAINS),--drains $(DRAINS))

# What the models have cost in total, over the same log.
spend:
	@test -n "$(LOG)" || { echo 'usage: make spend LOG=<a captured log> [SINCE=<date>]'; exit 2; }
	@$(SPENT) \
	 | awk '{i+=$$3; o+=$$4; c+=$$5; n++} END {if (n==0) {print "no priced calls in the log"; exit} \
	     printf "calls   %d\ntokens  %d in, %d out\ncost    $$%.4f  (mean $$%.5f a call)\n", n, i, o, c, c/n}'

# ── Settings ───────────────────────────────────────────────────────────────
#
# What each service is configured to do, and changing it. The same operation
# as the route beside it, and as the Configuration panel on that service's
# page:
#
#   make settings SERVICE=topics                GET  /settings/topics
#   make settings-set SERVICE=topics SET=...   PATCH /settings/topics
#   make settings-unset SERVICE=topics UNSET=…  PATCH, with a null
#
# A value written here reaches a worker once its queue next runs dry: a
# worker reads its settings again between drains, not per row. Nothing is
# requeued: the command names what it staled, and that stage's -rerun is what
# rebuilds it.
#
# The environment still supplies every setting; these write an override over
# it, and -unset deletes that override.

# Report one service's settings, beside what the files say.
#   make settings SERVICE=extraction
settings:
	@[ -n "$(SERVICE)" ] || { echo "usage: make settings SERVICE=<name>"; exit 2; }
	$(LOADENV) && PYTHONPATH=backend poetry run python -m settings.run --service $(SERVICE)

# Change one or more of them. Repeat SET for each, space separated.
#   make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
settings-set:
	@[ -n "$(SERVICE)" ] && [ -n "$(SET)" ] || { echo 'usage: make settings-set SERVICE=<name> SET="NAME=VALUE"'; exit 2; }
	$(LOADENV) && PYTHONPATH=backend poetry run python -m settings.run --service $(SERVICE) $(foreach one,$(SET),--set $(one))

# Return one or more to what the files say.
#   make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
settings-unset:
	@[ -n "$(SERVICE)" ] && [ -n "$(UNSET)" ] || { echo 'usage: make settings-unset SERVICE=<name> UNSET="NAME"'; exit 2; }
	$(LOADENV) && PYTHONPATH=backend poetry run python -m settings.run --service $(SERVICE) $(foreach one,$(UNSET),--unset $(one))

# ── Documents ──────────────────────────────────────────────────────────────

# List up to 1000 stored documents, each with its digest and parse state.
documents:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m ingestion.run --list

# Load every PDF in a directory of the host through the service the Upload
# page uses, under its limits, a value stored on the page included, so a set
# too large for the page goes in at once. One line per file, then a summary: a
# file the corpus holds already is reported as a duplicate and stores nothing,
# and a file the service refuses fails the run.
#   make ingest DIR=$HOME/documents/prices
ingest:
	@[ -n "$(DIR)" ] || { echo 'usage: make ingest DIR=<directory of PDFs>'; exit 2; }
	$(LOADENV) && PYTHONPATH=backend poetry run python -m ingestion.run --add "$(DIR)"

# Delete a document, its file, its converted form and everything derived from
# it. The rows are archived and the objects are moved to the `archive` bucket,
# so `make archive-purge` is what makes it final. The upload record in
# ingest_events is kept. A fact another document's passage also cites
# stays, with its question; a question on a fact this removes goes, one written
# from two documents with either, since it cannot stand on half its sources.
#
# Then extract-dedup, which calls no model. A duplicate refusal cites only
# its own passage, so a fact another document repeats rests on this one
# alone, and deleting it leaves the repeat refused against a fact that is
# gone. The dedup gives it back, and re-judges and re-caps its passage.
# Over the whole corpus, SHA cleared, because the repeat is in another
# document. The deletion ends with one line naming how many refusals lost
# their twin. After a deletion through the API or the UI, extract-worker
# re-decides them when its queue is empty, finding a refusal that points at
# no twin; where none runs, `make extract-dedup`. Nor can this resume a replay
# that failed, since the document is gone by then: `make extract-dedup` is the
# recovery.
# The replay's guard is asked first for that reason: asked by the replay
# alone, it refused once the document was already gone.
#   make delete SHA=<sha256>
delete:
	@[ -n "$(SHA)" ] || { echo "usage: make delete SHA=<sha256>"; exit 2; }
	@$(call CONFIRMED,delete $(SHA))
	@$(call IDLE,extract-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m ingestion.run --delete $(SHA)
	$(MAKE) extract-dedup SHA=

# Empty the corpus: every document, every file, every converted form, and
# with them by cascade every passage, membership, fact and question. Then the
# topics, which are none of those. All of it is archived on the way out; see
# `make archive`.
#
# Two commands and not one because `topics` has no foreign key to a document:
# a fit is over the corpus rather than over a file, so deleting every document
# leaves the topics behind, holding their labels, their coverage flags and
# their question-generation queue state, all describing passages that are
# gone. Deleting the topics takes their figures out of the export bucket too.
#
# The upload history goes with the documents here, though a single deletion
# keeps it: an empty corpus reporting upload attempts is a status panel
# describing documents nothing has.
# Everything the corpus left behind goes with it, and that is the point:
# once the documents are gone, a trace of the run that read them, a review
# dataset of facts that no longer exist and a log line about a passage
# nothing holds are all describing a corpus nobody can look at. Leaving
# them is how a fresh run starts against four services still full of the
# last one.
#
# Those four deletions are final; nothing archives them. Phoenix loses every
# project and, unless KEEP spares them, its datasets and their experiments;
# Argilla loses the three review datasets and any answer not yet pulled;
# the logs go; and the Dagster run history goes unless KEEP spares it.
#
# **The archive is the exception, and deliberately.** The rows and objects
# deleted here are the first of two deletions: the triggers copy each row
# into `archived_rows` and the removal paths move each object into the
# `archive` bucket. That is what makes the corpus recoverable at all, so a
# wipe that purged it would leave nothing. `make archive-purge ALL=1` is
# the second decision, and stays one.
wipe:
	@[ -z "$(filter-out golden runs,$(KEPT))" ] || \
	  { echo "KEEP names $(filter-out golden runs,$(KEPT)); it takes golden and runs."; exit 2; }
	@echo "This deletes every document, topic, fact and question; the"
	@echo "archive keeps those, see make archive-purge. It deletes for good this"
	@echo "database's Phoenix projects, its three Argilla review datasets with any"
	@echo "answer not yet pulled, and its log lines; its Phoenix datasets and"
	@echo "experiments unless KEEP=golden; its Dagster runs unless KEEP=runs."
	@echo "ALL_DATABASES=1 takes every database's Phoenix projects, datasets, log lines and"
	@echo "Dagster runs; the Argilla datasets are this database's either way."
	@$(call CONFIRMED,wipe)
	$(MAKE) wipe-preflight
	$(LOADENV) && PYTHONPATH=backend poetry run python -m ingestion.run --delete-all
	$(LOADENV) && PYTHONPATH=backend poetry run python -m topic_modelling.run --delete
	@$(call WIPE_STEP,phoenix,phoenix-purge)
	@$(call WIPE_STEP,argilla,review-delete)
	@$(call WIPE_STEP,elasticsearch,logs-wipe)
	@$(call RUNNING,elasticsearch) || [ "$(ALL_DATABASES)" != 1 ] || $(LOG_FILES)
	@$(call WIPE_STEP,dagster-webserver,dagster-wipe)

# What `wipe` asks first: that each store it is about to empty answers to
# the key this shell holds. Six irreversible steps run in turn, and a key
# Argilla refuses was found after Phoenix and the database were already
# gone, leaving a corpus half deleted. Reads only. A store whose service is
# not running is skipped with a note, and the wipe skips its step with the
# same note: a wipe step on a stopped store fails on connect, half way.
# Every store that fails is named, with where its setting lives.
wipe-preflight:
	@failed=0; \
	if $(call RUNNING,phoenix); then out=$$($(LOADENV) && poetry run python -m telemetry.projects --list 2>&1) || \
	  { echo "REFUSED: Phoenix did not answer: $$(echo "$$out" | tail -n 1)" >&2; \
	    echo "  Check PHOENIX_BASE_URL and PHOENIX_API_KEY in .env." >&2; failed=1; }; \
	else $(call STORE_DOWN,phoenix,phoenix-purge); fi; \
	if $(call RUNNING,argilla); then out=$$($(REVIEW) --check 2>&1) || \
	  { echo "REFUSED: Argilla did not answer: $$(echo "$$out" | tail -n 1)" >&2; \
	    echo "  Check ARGILLA_API_URL and ARGILLA_API_KEY in .env." >&2; failed=1; }; \
	else $(call STORE_DOWN,argilla,review-delete); fi; \
	if $(call RUNNING,elasticsearch); then out=$$($(COMPOSE_CMD) exec -T elasticsearch sh -c 'curl -fsS --cacert /usr/share/elasticsearch/config/certs/ca.crt -u "elastic:$$ELASTIC_PASSWORD" https://localhost:9200/_cluster/health' 2>&1) || \
	  { echo "REFUSED: elasticsearch did not answer: $$(echo "$$out" | tail -n 1)" >&2; \
	    echo "  Check ELASTIC_PASSWORD in .env and that the container is healthy." >&2; failed=1; }; \
	else $(call STORE_DOWN,elasticsearch,logs-wipe); fi; \
	if $(call RUNNING,dagster-webserver); then out=$$($(COMPOSE_CMD) exec -T dagster-webserver dagster run list --limit 1 2>&1) || \
	  { echo "REFUSED: dagster-webserver did not answer: $$(echo "$$out" | tail -n 1)" >&2; failed=1; }; \
	else $(call STORE_DOWN,dagster-webserver,dagster-wipe); fi; \
	[ $$failed = 0 ]

# Both deletions, in the only order they work in: `wipe` fills the archive
# and `archive-purge` empties it, so the purge has to come second or it
# takes nothing.
#
# This is the one command for "leave nothing", and it is separate from
# `wipe` rather than a flag on it because the two answer different
# questions. `wipe` is "start again from the documents", and the archive is
# what makes that survivable - there is a restore script in this tree
# written for the morning after. This one is "leave nothing", and after it
# that script has nothing to read.
wipe-all: wipe
	$(MAKE) archive-purge ALL=1

# The runs this database launched, and the event log under each: the corpus
# job tags every run with the database, and a run with no tag is left.
# `ALL_DATABASES=1` takes every run the instance remembers. What `make
# wipe` runs: a run record for a corpus that is gone names assets nothing
# can open. `KEEP=runs` spares it.
#
# Through the webserver container, which is where DAGSTER_HOME and the
# instance's database configuration are; `--force` because the prompt has
# no terminal to answer it.
dagster-wipe:
	@$(call CONFIRMED,dagster-wipe: it deletes this database's Dagster runs)
	@$(call SPARED,runs,the Dagster run history) || \
	  $(if $(filter 1,$(ALL_DATABASES)),$(COMPOSE_CMD) exec -T dagster-webserver dagster run wipe --force,$(LOADENV) && $(COMPOSE_CMD) exec -T -e APP_DB_NAME="$$APP_DB_NAME" dagster-webserver python -m orchestration.wipe)

# Delete what the pipeline built from one document: its passages, and with
# them their topic memberships, any fact left citing no passage, any bridge
# that cited one, and every question resting on a fact this removes, with its
# follow-ups and the assessments of each; one written from two documents goes
# too. A fact another document also cites stays, with its question. The document
# and its file stay, and chunking goes back to `new`, so the next run
# rebuilds them once somebody starts it. Then extract-dedup, as `make delete`
# runs it and for the same reason, with the same recovery and the same guard
# first.
#   make delete-derived SHA=<sha256>
delete-derived:
	@[ -n "$(SHA)" ] || { echo "usage: make delete-derived SHA=<sha256>"; exit 2; }
	@$(call CONFIRMED,delete-derived $(SHA))
	@$(call IDLE,extract-worker)
	@$(BANNER)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m ingestion.run --delete-derived $(SHA)
	$(MAKE) extract-dedup SHA=

# ── Archive ────────────────────────────────────────────────────────────────
#
# Every deletion of a row or an object above is the first of two; what
# wipe takes from Phoenix, Argilla, the logs and Dagster is final. An AFTER
# DELETE trigger on every table copies the row into `archived_rows` as it
# goes - which catches the cascades and the orphan triggers, where most of
# the deleting actually happens - and the removal paths move the objects
# into the `archive` bucket instead of dropping them. Nothing reads any of
# it; it is there so the second deletion is a separate decision.

# What is held, by table, with its age and what it costs.
archive:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.run --status

# The second deletion. This one is final.
#
#   make archive-purge TABLE=questions    one table's rows
#   make archive-purge DAYS=30            everything archived before then
#   make archive-purge ALL=1              the whole thing, objects included
#
# TABLE is about rows, so it leaves the bucket alone: an archived upload
# belongs to no table. DAYS and ALL take the objects too. Each of the three
# is final and refuses unless CONFIRM names the database. Only ALL=1 means
# everything.
archive-purge:
	@[ -n "$(TABLE)$(DAYS)$(filter 1,$(ALL))" ] || { echo "usage: make archive-purge [TABLE=<table>] [DAYS=<n>] [ALL=1]"; exit 2; }
	@$(call CONFIRMED,archive-purge: it deletes what the archive holds)
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.run --purge \
	   $(if $(TABLE),--table $(TABLE)) $(if $(DAYS),--older-than $(DAYS)) $(if $(filter 1,$(ALL)),--all)

# Copy the objects a store holds from before keys were prefixed with the
# database's name under this database's prefix. Run it once per database
# that used the store. It copies and never moves: `get` still falls back to
# the bare key, and another database may be reading it.
s3-prefix:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m blob_store.s3.rekey

# Every database and every bucket, to a directory: a pg_dump -Fc of the
# application, SeaweedFS, Phoenix and Dagster databases through the postgres
# container, a copy of every object of the five buckets through the stack's S3
# endpoint, and a manifest of the row counts of the application database and the
# key and sha256 of every object and dump. Never .env, provider.env or a
# certificate key. Argilla's database is left out unless ARGILLA=1: its users
# table holds the owner's API key in clear, so that dump is a secret to store as
# one, and without it the review datasets come back from `make review-push-*`.
#
#   make backup DIR=/backups/2026-10-24 [ARGILLA=1]
#
# DIR must hold no backup yet. The drill that proves one restores is in
# docs/operations.md.
backup:
	@[ -n "$(DIR)" ] || { echo "usage: make backup DIR=<directory>"; exit 2; }
	@[ ! -e "$(DIR)/manifest.json" ] || { echo "REFUSED: $(DIR) already holds a backup." >&2; exit 2; }
	@echo "A worker still running writes while this copies: the dumps, the objects and the row counts are of different moments. Stop the workers first (docs/operations.md, Backups)." >&2
	@mkdir -p "$(DIR)/db"
	$(LOADENV) && umask 077 && for name in $$APP_DB_NAME $$SEAWEEDFS_DB_NAME $$PHOENIX_DB_NAME $$DAGSTER_DB_NAME $(if $(filter 1,$(ARGILLA)),$$ARGILLA_DB_NAME); do \
	  $(COMPOSE_CMD) exec -T postgres sh -c "pg_dump -Fc -U \"\$$POSTGRES_USER\" -d $$name" > "$(DIR)/db/$$name.dump" || exit 1; \
	done
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.backup --backup "$(DIR)"

# Put one database back from a backup: pg_restore of the application database
# alone and the objects under its own prefix, each checked against the manifest.
# Phoenix, Dagster, Argilla, the SeaweedFS filer and every other database's
# objects are shared by the whole stack and stay as they are; restore-backup-stack
# is the target that puts those back. Refuses while any worker runs, and unless
# CONFIRM names the database. Stop everything but postgres and seaweedfs first,
# as the drill in docs/operations.md says: pg_restore cannot replace a database
# in use.
restore-backup:
	@[ -n "$(DIR)" ] && [ -f "$(DIR)/manifest.json" ] || { echo "usage: make restore-backup DIR=<a directory make backup wrote> CONFIRM=<database>"; exit 2; }
	@$(foreach worker,parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker,$(call IDLE,$(worker)); )
	@$(call CONFIRMED,restore-backup: it replaces the application database and its objects from $(DIR))
	$(LOADENV) && $(COMPOSE_CMD) exec -T postgres sh -c "pg_restore --clean --if-exists --single-transaction -U \"\$$POSTGRES_USER\" -d $$APP_DB_NAME" < "$(DIR)/db/$$APP_DB_NAME.dump"
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.backup --restore "$(DIR)"

# Put the whole stack back from a backup: the five databases and every
# database's objects. The SeaweedFS filer, Phoenix, Dagster and Argilla are
# shared, so this rolls back every other database's objects, traces and runs to
# the backup's, and the objects the filer wrote since are lost to it. It refuses
# while more than one application database exists on the server, unless
# ALL_DATABASES=1, and unless CONFIRM=stack.
restore-backup-stack:
	@[ -n "$(DIR)" ] && [ -f "$(DIR)/manifest.json" ] || { echo "usage: make restore-backup-stack DIR=<a directory make backup wrote> CONFIRM=stack"; exit 2; }
	@$(foreach worker,parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker,$(call IDLE,$(worker)); )
	@$(LOADENV) && n=$$($(COMPOSE_CMD) exec -T postgres sh -c "psql -At -U \"\$$POSTGRES_USER\" -d $$APP_DB_NAME -c \"SELECT count(*) FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('postgres','\$$POSTGRES_USER','$$SEAWEEDFS_DB_NAME','$$PHOENIX_DB_NAME','$$DAGSTER_DB_NAME','$$ARGILLA_DB_NAME')\"") && \
	  { [ "$$n" -le 1 ] || [ "$(ALL_DATABASES)" = 1 ] || \
	    { echo "REFUSED: $$n application databases share this stack. restore-backup-stack puts every database's objects back to the backup's, and what they wrote since is lost to the restored filer; the other databases keep their rows." >&2; \
	      echo "  restore-backup puts one database back. Run this with ALL_DATABASES=1 to go on regardless." >&2; exit 2; }; }
	@[ "$(CONFIRM)" = stack ] || { echo "REFUSED: restore-backup-stack rolls back the shared SeaweedFS filer, Phoenix, Dagster, Argilla and every database's objects to $(DIR)." >&2; echo "  Run it again with CONFIRM=stack to go on." >&2; exit 2; }
	$(LOADENV) && for name in $$APP_DB_NAME $$SEAWEEDFS_DB_NAME $$PHOENIX_DB_NAME $$DAGSTER_DB_NAME $$ARGILLA_DB_NAME; do \
	  [ "$$name" != "$$ARGILLA_DB_NAME" ] || [ -f "$(DIR)/db/$$name.dump" ] || continue; \
	  $(COMPOSE_CMD) exec -T postgres sh -c "pg_restore --clean --if-exists --single-transaction -U \"\$$POSTGRES_USER\" -d $$name" < "$(DIR)/db/$$name.dump" || exit 1; \
	done
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.backup --restore "$(DIR)" --stack

# Put back what a deletion archived, after an accidental wipe.
#
#   make restore-documents                         the newest deleting transactions
#   make restore-documents SINCE=2026-10-07T09:14  every one from then on (lists)
#   make restore-documents AT=<time>[,<time>]      put those deletions back
#
# Run it before `archive-purge`, which is what makes the archive unreadable.
# Only the transactions AT names come back: the archive also holds every row a
# rerun replaced, and a setting somebody cleared. service_settings and prompts
# stay out unless TABLES names them, and a refit's topics are not offered.
restore-documents:
	$(LOADENV) && PYTHONPATH=backend poetry run python -m archive.restore

# ── Tests ──────────────────────────────────────────────────────────────────

# Everything that gates: the unit layers, the static gates, and the
# integration layers, which start a Postgres and a SeaweedFS of their own
# and are skipped where no container engine answers. Configuration lives in
# [tool.pytest.ini_options] in pyproject.toml.
#
# The order is shuffled every run, and the seed is printed at the top. A
# failure that only happens in one order is a test depending on another,
# and `-p randomly --randomly-seed=<n>` reproduces it.
test:
	poetry run pytest -m "not slow and not smoke and not eval and not perf"

# Without the slow ones: no spaCy pipelines, no pyright, no containers.
# Over every core, which the unit layer can be: it shares no container.
test-fast:
	poetry run pytest -n auto -m "not nlp and not types and not integration and not slow and not smoke and not eval and not perf"

# The layers on their own, for working on one of them.
test-unit:
	poetry run pytest -n auto -m "not integration and not slow and not smoke and not eval and not perf"

# Everything needing a Postgres and a SeaweedFS, short of end to end.
test-integration:
	poetry run pytest -m "integration and not e2e and not perf"

# One corpus, every stage, against a stack of its own.
test-e2e:
	poetry run pytest -m e2e

# Real PDFs through the real converter and chunker, against the snapshots in
# tests/golden/snapshots: what a Docling release does to text, headings, pages
# and tables. Weights from the cache, offline, so a missing one fails the run.
test-golden:
	HF_HUB_OFFLINE=1 poetry run pytest -m slow tests/golden

# After a change to the parse or the chunker that is meant: rewrite the
# snapshots that test-golden compares against, then read the diff before
# committing it.
golden-refresh:
	HF_HUB_OFFLINE=1 GOLDEN_REFRESH=1 poetry run pytest -m slow tests/golden

# Builds both images and reads the compose file. Minutes, not seconds, and
# it starts no stack: compose.yaml binds its ports from deployment.env, so a
# second copy would collide with a running one rather than run beside it.
test-smoke:
	poetry run pytest -m smoke

# Scores the served model LLM_MODEL names against the golden passages.
# Never a gate: a model's answers move between versions and between runs.
test-eval:
	$(LOADENV) && poetry run pytest -m eval -s

# Branch coverage over every package a deployment runs, both layers
# combined. Combined because neither covers the other's half: the
# repositories are the integration layer's and the gates are the unit
# layer's, so a threshold against either alone is against the wrong number.
#
# What it is measured over, what is left out and the floor it has to clear
# are [tool.coverage.*] in pyproject.toml.
# --cov-fail-under=0 on each half: the floor is against the combination,
# and enforced per run it fails the first one for not being the second.
test-coverage:
	poetry run coverage erase
	poetry run pytest -m "not integration and not slow and not smoke and not eval and not perf" \
	  --cov --cov-append --cov-report= --cov-fail-under=0
	poetry run pytest -m "integration and not perf" --cov --cov-append --cov-report= --cov-fail-under=0
	poetry run coverage report

# Times the ceilings the code names in a comment: the combination search in
# `adds_up`, the release draw, the composition report. Never a gate - a
# budget on a shared runner measures the runner.
test-perf:
	poetry run pytest -m perf

# Whether the tests would notice a gate changing. Line coverage says the
# line ran; this changes it and asks whether anything fails.
#
# Which modules and which layers are [tool.mutmut] in pyproject.toml.
# Hours, so nightly rather than per change; `mutmut browse` reads the
# survivors afterwards.
mutation:
	poetry run mutmut run
	poetry run mutmut results

# Everything that gates. Another name for `test`.
check: test

# ── Static checks ──────────────────────────────────────────────────────────

# Every type error pyright finds, which the suite holds at zero.
# Configuration lives in [tool.pyright] in pyproject.toml.
typecheck:
	poetry run pyright

# Known advisories against what the images install and what the host and CI
# install: both image locks and poetry.lock. Fails on one in any of them,
# after reading all three: the nightly job that runs it blocks no merge, so
# a red run is how an advisory is reported, and a run that always passed
# reported none.
#
# --no-deps because both locks already pin every transitive dependency.
#
# Against OSV rather than pip-audit's default, PyPI's own feed, which listed
# 18 of the 21 advisories OSV holds on Pillow 12.3.0 and left out a critical
# one. pip-audit reads one service a run, and OSV listed every one PyPI did.
#
# torch and torchvision are held out: they are pinned to +cpu builds, which
# is a local version PyPI does not carry and PyTorch's own index publishes
# only for linux. Resolving them anywhere else fails, so their advisories
# are not covered here - `pip-audit -r` inside the built image is what
# would cover them.
#
# It runs whole on Linux only, where the nightly job runs it: poetry.lock
# also pins CUDA wheels with no macOS build, cuda-bindings among them, so
# on a Mac its leg fails on a package pip cannot find rather than on an
# advisory, and only the two image locks are audited.
#
# The scratch files live in a temporary directory, removed on any exit, so an
# interrupted run leaves nothing among the sources. poetry.lock is read with
# its own parser into the same name==version form.
#
# shortcut: a package poetry.lock holds twice (the CUDA wheels for another
# platform) is audited at its first version, when one of those matters read
# the second off the lock by hand.
#
# The advisories accepted, each with its lock, reason and review-by date, are
# in configs/audit-accepted.txt; a date that has come fails the audit before
# any lock is read. pip-audit reports every advisory of each lock as JSON, and
# configs/audit_ignores.py fails on one not accepted for its lock, and on an
# accepted id that no lock it covers reports any more, which the list would
# otherwise keep hiding.
audit:
	@d=$$(mktemp -d) && trap 'rm -rf $$d' EXIT && \
	  grep -viE "^(torch|torchvision)==" backend/api/requirements.lock > $$d/api.lock; \
	  $(HOST_PINS) | grep -vE "^(torch|torchvision)==" > $$d/poetry.lock && \
	  for l in api frontend poetry; do \
	    poetry run python configs/audit_ignores.py $$l $(AUDIT_ACCEPTED) > /dev/null || exit 1; \
	  done && \
	  for f in api:$$d/api.lock frontend:frontend/requirements.lock poetry:$$d/poetry.lock; do \
	    poetry run pip-audit --vulnerability-service osv --no-deps --progress-spinner off --format json --aliases on --output $$d/found.$${f%%:*}.json -r $${f#*:}; \
	  done; \
	  poetry run python configs/audit_ignores.py --verdict $(AUDIT_ACCEPTED) $$d

# ruff check and format check over every source directory. Configuration
# lives in [tool.ruff] in pyproject.toml.
lint:
	poetry run ruff check $(SOURCES)
	poetry run ruff format --check $(SOURCES)

# The two architecture rules the root README states. Configuration, and the
# reasoning, live in .importlinter.
#
# PYTHONPATH=backend because the image puts each backend package at the top
# level: `extraction` is the name a container resolves, not
# `backend.extraction`, and contracts written against the other name would
# pass by matching nothing. tests/static/test_import_contracts.py runs this
# same check under `make test`.
lint-imports:
	PYTHONPATH=backend:. poetry run lint-imports --verbose

# A declared dependency nothing imports, an import nothing declares, and a
# package reached only through somebody else's. Configuration is
# [tool.deptry] in pyproject.toml, which is also where each deliberate
# exception is argued for.
deps:
	poetry run deptry .

# Fix what ruff can fix, then format every source directory.
format:
	poetry run ruff check --fix $(SOURCES)
	poetry run ruff format $(SOURCES)

# ── Dependency locks ───────────────────────────────────────────────────────

# Rewrites backend/api/requirements.lock and frontend/requirements.lock from
# the ranges in their requirements.txt, under the pins of poetry.lock. Run it
# after changing a requirements.txt; the image build refuses a lock that does
# not pin everything requirements.txt declares.
#
# The resolving happens in the Dockerfile's `resolve` stage, in the same
# base image the runtime uses, because a lock resolved on macOS pins wheels
# that do not exist for linux/aarch64. The file's comment header is carried
# over; everything below it is replaced.
lock:
	@d=$$(mktemp -d) && trap 'rm -rf $$d' EXIT && \
	  $(HOST_PINS) | grep -v '^nvidia-' > $$d/pins && \
	  $(CONTAINER) build --target resolve --build-arg "HOST_PINS=$$(cat $$d/pins)" \
	    -t qa_generator-resolve -f backend/api/Dockerfile . && \
	  awk '/^#/ {print; next} {exit}' backend/api/requirements.lock > $$d/api && \
	  { set -o pipefail; $(CONTAINER) run --rm qa_generator-resolve | sort >> $$d/api; } && \
	  cp $$d/api backend/api/requirements.lock && \
	  awk '/^#/ {print; next} {exit}' frontend/requirements.lock > $$d/frontend && \
	  { set -o pipefail; $(CONTAINER) run --rm \
	      -v ./frontend/requirements.txt:/r.txt:ro -v $$d/pins:/c.txt:ro python:3.13-slim \
	      sh -c 'pip install -q -c /c.txt -r /r.txt && pip freeze' | sort >> $$d/frontend; } && \
	  cp $$d/frontend frontend/requirements.lock
	@echo "backend/api/requirements.lock and frontend/requirements.lock rewritten; rebuild with: $(COMPOSE_CMD) build api frontend"

# ── TLS certificates ───────────────────────────────────────────────────────

# Generates a self-signed CA and an Elasticsearch node certificate into certs/,
# for the Elasticsearch instance Argilla connects to. Idempotent; delete certs/
# to rotate.
#
# Three details are load-bearing:
#
#   elasticsearch.key is mode 644. Elasticsearch runs as uid 1000, but under
#   rootless Podman the host user maps to container uid 0 and the host group
#   does not map at all, so the key arrives as 0:65534. At 600 the node cannot
#   read it and exits with AccessDeniedException. ca.key stays 600; no
#   container reads it.
#
#   The -addext flags on the CA are required. `openssl req -x509` emits no
#   keyUsage extension, and OpenSSL 3 clients reject such a CA even when it is
#   passed explicitly as the trust anchor.
#
#   The key identifiers are named, not left to the tool. OpenSSL 3 adds them
#   unasked; macOS's /usr/bin/openssl is LibreSSL and does not. Python 3.13
#   verifies strictly and refuses a chain without them, so Argilla failed with
#   "Missing Authority Key Identifier" and reported Elasticsearch as down.
#
# A failed step stops the rest, and the skip asks for the last file written,
# so a run that stopped half-way is made again rather than skipped.
#
# For a real deployment these come from a secret store.
certs:
	@mkdir -p certs
	@set -e; \
	[ -f certs/elasticsearch.crt ] && echo "certs/ already exists, skipping generation" && exit 0; \
	openssl genrsa -out certs/ca.key 4096; \
	openssl req -new -x509 -days 3650 -key certs/ca.key -out certs/ca.crt \
	  -subj "/CN=qa-generator-ca" \
	  -addext "basicConstraints=critical,CA:TRUE" \
	  -addext "keyUsage=critical,keyCertSign,cRLSign" \
	  -addext "subjectKeyIdentifier=hash"; \
	openssl genrsa -out certs/elasticsearch.key 4096; \
	openssl req -new -key certs/elasticsearch.key -out certs/elasticsearch.csr \
	  -subj "/CN=elasticsearch"; \
	openssl x509 -req -days 3650 \
	  -in certs/elasticsearch.csr \
	  -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
	  -extfile <(printf "%s\n" \
	    "subjectAltName=DNS:elasticsearch,DNS:localhost,IP:127.0.0.1" \
	    "basicConstraints=critical,CA:FALSE" \
	    "keyUsage=critical,digitalSignature,keyEncipherment" \
	    "extendedKeyUsage=serverAuth" \
	    "subjectKeyIdentifier=hash" \
	    "authorityKeyIdentifier=keyid,issuer") \
	  -out certs/elasticsearch.crt; \
	rm -f certs/elasticsearch.csr certs/ca.srl; \
	echo "Certificates written to certs/"
	@chmod 600 certs/ca.key
	@chmod 644 certs/elasticsearch.key

# ── Golden-set experiments ─────────────────────────────────────────────────
#
# `make test-eval` scores a served model against the cases in
# evaluation/cases.py and prints the numbers. These record the same scores
# in Phoenix instead, so two runs are comparable by more than scrollback:
#
#   make eval-upload    put the cases in Phoenix, as a new dataset version
#   make eval-score     run the model against them and record the scores
#
# Never a gate, for the reason test-eval is not: a model's answers move
# between versions, between quantisations and between two runs at the same
# temperature.
#
# Name a run when the model is not what changed:
#
#     make eval-score EVAL_RUN_NAME=extraction-prompt-v7
EVAL = $(call WITH,evaluation.env) && \
       PYTHONPATH=backend poetry run python -m evaluation.run
EVAL_DATASET ?= extraction-golden

# Put the golden cases in Phoenix, as a new dataset version.
eval-upload:
	$(EVAL) --upload $(EVAL_DATASET)

# Run the served model against them and record the scores in Phoenix.
eval-score:
	$(EVAL) --score $(EVAL_DATASET)

# Republish every recorded prompt to Phoenix.
#
# NOT the way prompts get there. A stage publishes what it records when it
# starts, so this is a repair rather than a step: the case it covers is a
# Phoenix wiped while the `prompts` rows stayed, which nothing can detect -
# the table then matches what the stages send, so they write nothing and
# publish nothing.
#
# Read from the `prompts` table rather than from the code, so a version the
# source has moved past goes too - which is the reason that table exists.
# The stages write it when they start, so run one of them first.
#
# Each prompt goes back against the model it goes to - the judge's against
# ASSESSMENT_JUDGE_MODEL, the verifier's against QUESTIONS_VERIFIER_MODEL -
# because the row records which one. A published prompt is replayed in the
# playground against the model named on it, so that is not cosmetic.
#
# The source is still the code. An edit in Phoenix's UI reaches nothing and
# the next publish writes over it.
prompts-publish:
	$(EVAL) --publish-prompts

# The two phrasing judgements, each against the floor a judge that ignores
# its input reaches. That floor is the point: a judgement scoring barely
# above a constant answer is one that hardly ever fires.
#
#     make eval-phrasing                       # upload, then score
#     make eval-phrasing EVAL_RUN_NAME=gemma4-12b
#
# Scores QUESTIONS_PHRASING_MODEL, which is the model the pipeline asks, so
# swapping a 31B for a 12B and running this again is what decides it.
eval-phrasing:
	$(EVAL) --upload phrasing-golden
	$(EVAL) --score phrasing-golden

# ── Phoenix projects ───────────────────────────────────────────────────────
#
# A Phoenix project is created by the first span filed under it and
# removed by nothing. While a project meant a run somebody asked for that
# was fine; `run_id` mints a uuid per PROCESS, a --watch worker is a
# process per restart, and a credential that has expired restarts it every
# minute.
#
# Two changes stop the count growing - an unnamed run appends to its
# stage's own project, and the exporter is not installed until the
# preflight passes - and this takes back what the old arrangement left.
#
#   make phoenix-projects    what Phoenix holds, changing nothing
#   make phoenix-prune       delete the projects in which no work happened
#
# `prune` takes a project only when every span in it is a model call AND
# it could read every span. A project too big to read in one page is left
# alone: the first fifty spans of a run can be model calls too.

# What Phoenix holds, changing nothing.
phoenix-projects:
	$(LOADENV) && poetry run python -m telemetry.projects --list

# Irreversible, and asks nothing first: it names at most 25 of the projects
# it takes, then deletes them.
phoenix-prune:
	$(LOADENV) && poetry run python -m telemetry.projects --prune $(if $(filter 1,$(ALL_DATABASES)),--all-databases)

# Every project this database filed AND its datasets, whatever they hold;
# `ALL_DATABASES=1` takes every database's projects and any filed before names
# carried one. What `make wipe`
# runs: a trace of a run over documents that no longer exist is not worth
# keeping, and `prune` would leave all of them - they each recorded real
# work. The datasets are `make eval-upload`'s golden cases and the
# experiments under them; `KEEP=golden` spares those, see `wipe`.
phoenix-purge:
	@$(call CONFIRMED,phoenix-purge: it deletes this database's Phoenix projects and datasets)
	$(LOADENV) && poetry run python -m telemetry.projects --purge $(if $(filter 1,$(ALL_DATABASES)),--all-databases)
	@$(call SPARED,golden,the Phoenix datasets) || \
	  { $(LOADENV) && poetry run python -m telemetry.projects --purge-datasets $(if $(filter 1,$(ALL_DATABASES)),--all-databases); }

# ── Review ─────────────────────────────────────────────────────────────────
#
# Human review of what the models decided, through Argilla. Three things
# have somewhere for a person to disagree, and each already had a
# human-owned column before this: a fact's verdict, a topic's name and
# whether it is a subject, and whether a question is any good.
#
#   make review-push-facts      a sample, spread over the checker's verdicts
#   make review-pull-facts      write the submitted verdicts back
#
# Push, review in the UI at ARGILLA_API_URL, then pull. A pull takes only
# submitted answers: Argilla saves a draft the moment a record is touched,
# and a draft is somebody part-way through thinking.
#
# Runs on the host against the same database the workers use. Nothing in
# the pipeline calls it, and no container carries it.
REVIEW = $(call WITH,review.env) && \
         PYTHONPATH=backend poetry run python -m review.run

# How many rows in the database carry a person's verdict, and how often it
# matched the model's. Reads the database only: an answer submitted in
# Argilla and not yet pulled is not counted, so pull before deleting a dataset.
review-status:
	$(REVIEW) --status

# Delete the three datasets this tool pushes - facts, topic labels and
# questions - and nothing else in the workspace. What `make wipe` runs, and
# the one review target that throws an answer away: a push reuses the
# dataset it finds precisely so it never does. Pull first if a verdict
# still matters.
review-delete:
	@$(call CONFIRMED,review-delete: it deletes the Argilla review datasets and any answer not yet pulled)
	$(REVIEW) --delete

# Push a sample of facts, spread over the checker's verdicts.
review-push-facts:
	$(REVIEW) --push facts $(if $(ALL),--all)

# Write the submitted fact verdicts back to the database.
review-pull-facts:
	$(REVIEW) --pull facts

# Push each topic's name and whether it is a subject.
review-push-topics:
	$(REVIEW) --push topic-labels

# Write the submitted topic labels back to the database.
review-pull-topics:
	$(REVIEW) --pull topic-labels

# A stratified sample, or exactly the ids IDS names - which is how the
# disagreements the Assessment page marks reach a reviewer. A sample
# cannot find those: they are rare in every band and every verdict, which
# is the shape a proportional draw misses.
review-push-questions:
	$(REVIEW) --push questions $(if $(IDS),--ids $(IDS)) $(if $(ALL),--all)

# Write the submitted question judgements back to the database.
review-pull-questions:
	$(REVIEW) --pull questions

# ── Pipeline ───────────────────────────────────────────────────────────────

# The orchestrator decides when a stage should run; it never runs one. It
# posts to the stage routes and polls /status, which is the same surface
# the Start button and the targets above use, so nothing here can move a
# row in a way they could not.
#
# `make up` starts both, like every other service. There is no target to
# start them on their own and nothing to switch on here: the schedule and
# the sensor both ship STOPPED, so the webserver serves an asset graph and
# the daemon ticks nothing until somebody enables one in the UI.

# Runs the UI and the daemon on the host instead, against the
# containerised PostgreSQL and the containerised api.
#
# Only the database is named here now: it is reached on its published port
# rather than over the compose network, and nothing else needs to say so.
# BACKEND_URL used to be given here too, because the name held the
# container's address for everybody; it is the host's own by the time WITH
# is done, and the container's is BACKEND_CONTAINER_URL.
dagster-dev:
	$(call WITH,orchestration.env) && \
	  DAGSTER_HOME=$$PWD/configs/dagster \
	  DAGSTER_DB_HOST=localhost DAGSTER_DB_PORT=$$POSTGRES_PORT \
	  poetry run dagster dev


# ── Journeys ───────────────────────────────────────────────────────────────
#
# Fewer commands, each of which is several of the ones above in the order
# somebody runs them. Nothing here does anything the fine-grained targets
# cannot, and nothing here is required: every stage still has its own six.
#
# They exist because the common paths were six commands long and the order
# mattered, which is a thing to get wrong rather than a thing to decide.

# The whole of it: bring the stack up, wait until Dagster lists the corpus
# job, giving up after 30 tries, then run `pipeline`. The container workers
# drain each stage; `corpus` is the host drain.
all:
	@$(NOT_GO_LIVE)
	$(MAKE) up
	@for attempt in $$(seq 30); do \
	  $(call DAGSTER,job list) | grep -q "Job: corpus" && break; \
	  if [ $$attempt -eq 30 ]; then echo "Dagster did not list the corpus job" >&2; exit 1; fi; \
	  sleep 5; \
	done
	$(MAKE) pipeline

# Every stage, in the order a document moves through them, stopping at the
# first drain that exits non-zero: 3 is a failed row and 75 a drain that
# stopped itself (the model could not be reached, it answered nothing, or
# SPEND_CAP was reached), and neither lets the next stage run on what it left.
#
# Incremental, not a rebuild. Each `-start` queues only the rows never asked
# for, so a stage the corpus is already through queues nothing and its drain
# claims nothing. After one upload, parsing, chunking and extraction read
# that document alone; questions are written only for topics never asked
# for; the judge enrols only what has no assessment. `questions-balance`
# draws the release again over every accepted question each time, and asks
# the verifier about each released question and its nearest released
# neighbour, in up to three rounds, because the twin verdicts it gets are
# not stored.
#
# The topics are fitted when they have to be: a language that holds passages
# and no topic, or whose topics no longer fit its passages, is fitted between
# extraction and the bridges, and the run stops if a language still has no
# topic afterwards. A corpus whose topics are live is not refitted, because a
# fit replaces them; `make topics-discover` is the refit asked for on its own.
# A fit a resume returned to the queue is drained there all the same.
#
# A stage whose container worker is running is waited for, not drained: the
# go-live `make up` starts the parse and chunk workers, so the chain waits
# until each has emptied its queue, polling the counts, and goes on (see
# AWAIT); a stage whose worker is down is drained here.
#
# It names the database it acts on before it touches it, and every drain gets
# that name, the Hub switched off (HF_HUB_OFFLINE=1: the weights are in the
# cache or the run says so), and one spend ledger, because SPEND_CAP is
# counted in a process and a run is one process per drain. A fresh run starts
# the ledger again; RESUME=1 keeps it and first returns every stage's failed
# rows to the queue, which is what a run killed mid-row left.
#
# One `$(MAKE)` per line rather than a prerequisite list: prerequisites are
# ordered only while nothing runs in parallel, and this order is the point.
#
# The judge last, and unconditionally: `assessment.run` reads
# ASSESSMENT_ENABLED itself, says so and exits 0 when it is off. A `case`
# on the flag here would be a second reader of it, and the two would
# eventually disagree about which spellings mean yes.
corpus:
	@mkdir -p logs && { [ -n "$(RESUME)" ] || : > $(CORPUS_LEDGER); } && touch $(CORPUS_LEDGER)
	@$(LOADENV) && echo "corpus: database $$APP_DB_NAME, Hub off, spend carried in $(CORPUS_LEDGER)$${SPEND_CAP:+, stopping at USD $$SPEND_CAP}"
	$(if $(RESUME),$(foreach stage,$(CORPUS_RETRIES),$(MAKE) $(stage) $(CORPUS_PINS) &&) true)
	$(MAKE) parse-start $(CORPUS_PINS)     && $(MAKE) parse $(CORPUS_PINS)
	$(MAKE) chunk-start $(CORPUS_PINS)     && $(MAKE) chunk $(CORPUS_PINS)
	$(MAKE) extract-start $(CORPUS_PINS)   && $(MAKE) extract $(CORPUS_PINS)
	$(MAKE) extract-digests $(CORPUS_PINS)
	$(MAKE) topics-discover ENSURE=1 $(CORPUS_PINS)
	$(MAKE) topics-status $(CORPUS_PINS)
	$(MAKE) extract-bridge MISSING=1 $(CORPUS_PINS)
	$(MAKE) questions-start $(CORPUS_PINS) && $(MAKE) questions $(CORPUS_PINS)
	$(MAKE) questions-balance $(CORPUS_PINS)
	$(MAKE) assess-start $(CORPUS_PINS)    && $(MAKE) assess $(CORPUS_PINS)

# The corpus on the host, detached and supervised: scripts/corpus-hosted.sh
# runs `make corpus` in a process group of its own, recorded with its database
# in the pid file, and a second start is refused while a member of that group
# lives. The go-live profile's runner, and it needs that profile: the
# container workers drain the queues otherwise, and `make corpus` is the
# foreground run.
#
# A run that ends other than finished - stopped at SPEND_CAP, by a signal or
# by failed rows, or killed - keeps its record, so the next start resumes it:
# the stages' failed rows go back to the queue and the spend so far still
# counts against SPEND_CAP. A run that finished, or RESET=1, makes the next
# one fresh. A supervisor that restarts it for you (docs/operations.md has a
# launchd and a systemd unit) runs scripts/corpus-hosted.sh in the
# foreground instead, which exits with the stage's own code.
#
#   make corpus-hosted SPEND_CAP=50     stops at USD 50 for the whole run
#   make corpus-hosted RESET=1          a fresh run, not the stopped one's resume
corpus-hosted:
	@mkdir -p logs
	@scripts/corpus-hosted.sh --check $(HOSTED_ARGS)
	@$(LOADENV) && { $(GO_LIVE) || { echo "make corpus-hosted is the go-live profile's runner: set HOST_RUNNER=1 in .env. Without it the container workers drain the queues; make corpus runs them in the foreground." >&2; exit 1; }; }
	@$(LOADENV) && HF_HUB_OFFLINE=1 PYTHONPATH=backend poetry run python -c 'from api.doctor import preflight; raise SystemExit(preflight())'
	@nohup scripts/corpus-hosted.sh $(HOSTED_ARGS) >> $(HOSTED_LOG) 2>&1 & \
	  for i in $$(seq 50); do [ -f $(HOSTED_PID) ] && break; sleep 0.1; done; \
	  echo "corpus-hosted started: log $(HOSTED_LOG), pid file $(HOSTED_PID); stop it with make corpus-hosted-stop"

# Stop the hosted run: TERM to its whole process group, so the drain in hand
# finishes its row or gives it back and exits 75, then KILL to whatever is
# left after a model stage's grace, 300 seconds. The spend ledger and the
# record are kept, so the next `make corpus-hosted` resumes it.
corpus-hosted-stop:
	@scripts/corpus-hosted.sh --stop

# Every container, whether it is listening, and where to open it.
#
# Asked of the api rather than read out of a file, so this and the System
# health page cannot come to disagree about what is running. A worker
# serves no port and is shown as `-`: it reads a queue, and its own stage
# page is what says whether it is doing that.
#
# BACKEND_URL, which is the host's own: derived from BACKEND_PORT above.
# The container's is BACKEND_CONTAINER_URL and is not read here.
services:
	@$(LOADENV) && answer=$$(curl -sf $$BACKEND_URL/services) \
	  && printf '%s' "$$answer" | python3 -c 'import sys, json; [print("{:>4}  {:<20}  {}".format({True: "up", False: "DOWN", None: "-"}[r["ok"]], r["name"], r["url"] or "")) for r in json.load(sys.stdin)]' \
	  || echo "The api is not answering. Try: make up"

# The same, and open the application.
open: services
	@$(LOADENV) && url=http://localhost:$$STREAMLIT_PORT; \
	  if command -v open >/dev/null; then open $$url; \
	  elif command -v xdg-open >/dev/null; then xdg-open $$url; \
	  else echo "Open $$url"; fi

# Everything a person reviews, pushed to Argilla in one go.
review: review-push-facts review-push-topics review-push-questions

# Every artefact of every kind, each in its own dataset. Argilla then holds
# the corpus rather than a draw from it; `make review` is the sample.
review-all:
	$(MAKE) review ALL=1
	@$(LOADENV) && echo "Review at http://localhost:$$ARGILLA_PORT"

# Every decision made there, pulled back into the database.
pull: review-pull-facts review-pull-topics review-pull-questions

# ── The corpus as one thing ────────────────────────────────────────────────
#
# The three verbs above, over every stage at once, through the api rather
# than through six command lines. `/pipeline` is one route for the same
# reason this section is one heading: after a model outage the failures are
# spread over five queues, and visiting five of them is five chances to miss
# one.
#
# There is no `pipeline-start` here. `make corpus` above is the host's: it
# starts each stage AND waits for it to drain before the next, which is the
# whole difficulty, and the shell is what holds that wait.
# The Run button and `make pipeline` ask Dagster to hold it instead.
#
# BACKEND_URL like `services` above, which is the host's own address.

# Every stage's queue, the run in flight and what is set to start one, in one
# call. The whole-corpus answer to "where has this got to".
pipeline-status:
	@$(LOADENV) && curl -sf $$BACKEND_URL/pipeline \
	  | python3 -c 'import sys, json; d = json.load(sys.stdin); o = d["orchestration"]; r = o.get("running"); [print("{:>12}  {}".format(s["stage"], ", ".join(f"{n} {k}" for k, n in s["rows"].items()) or "nothing")) for s in d["stages"]]; print("\norchestrator:", "running " + r["id"][:8] if r else ("idle" if o["available"] else "not configured")); print("  automatic:", ", ".join(k for k in ("on_arrival", "nightly") if o["automation"].get(k)) or "no")' \
	  || echo "The api is not answering. Try: make up"

# Take back everything queued, in every stage, and stop the run behind it.
# Both halves: emptying the queues while a run is going means the run fills
# them again at its next stage.
pipeline-stop:
	@$(LOADENV) && curl -sf -X POST -H "X-API-Token: $$API_TOKEN" $$BACKEND_URL/pipeline/stop \
	  | python3 -c 'import sys, json; print(json.load(sys.stdin)["detail"])' \
	  || echo "The api is not answering. Try: make up"

# Return every stage's failures to the queue. What a model outage leaves
# behind, cleared in one command instead of five.
pipeline-retry:
	@$(LOADENV) && curl -sf -X POST -H "X-API-Token: $$API_TOKEN" $$BACKEND_URL/pipeline/retry \
	  | python3 -c 'import sys, json; print(json.load(sys.stdin)["detail"])' \
	  || echo "The api is not answering. Try: make up"

# ── Dagster, from here rather than from its own UI ─────────────────────────
#
# The asset graph already chains the stages: each waits for the one before
# it to drain, which is the order `corpus` above runs them in. What these
# decide is WHEN, which is the only thing an orchestrator was ever for.
#
# Run inside the webserver container, which is where DAGSTER_HOME and the
# workspace already are. Doing it from the host would need both again, and
# a second definition of either is a second thing to keep in step.
#
# A function rather than a prefix, because `-w` belongs after the
# subcommand and not before it:
#
#     $(call DAGSTER,sensor list)
#
# Its output is filtered at each call site rather than here. The compose
# shim hands back the container's two streams merged, so the interesting
# line arrives among the code server's startup logging and there is no
# redirection that separates them.
DAGSTER = $(COMPOSE_CMD) exec -T dagster-webserver dagster $(1) \
          -w /opt/dagster/dagster_home/workspace.yaml 2>&1

# What it is doing: the sensor, the schedule, and the last few runs.
#
# `run list` reads the instance and takes no `-w`, so it is not written
# through DAGSTER above. It asks the run storage what happened; the other
# two ask the code location what is defined.
#
# Matched without anchoring: the CLI colours its output, so a line starts
# with an escape sequence rather than with its own first word.
runs:
	-@$(call DAGSTER,sensor list)   | grep -E "Sensor: "
	-@$(call DAGSTER,schedule list) | grep -E "Schedule: "
	-@$(COMPOSE_CMD) exec -T dagster-webserver dagster run list --limit 5 2>&1 \
	  | grep -E "Run: |Job: |Status: "

# Every stage once, through Dagster instead of in the foreground. The stages
# `corpus` drains, without the bridge pass or the release draw and on the
# containers' model; it is recorded as a run, with a materialisation and a
# check per stage, and it survives this terminal closing.
pipeline:
	@$(NOT_GO_LIVE)
	@out=$$($(call DAGSTER,job launch -j corpus)) || { printf '%s\n' "$$out" >&2; exit 1; }
	@$(LOADENV) && echo "Launched. Follow it at http://localhost:$$DAGSTER_WEBSERVER_PORT or with make runs and make pipeline-status; make questions-balance draws the release once it ends."

# Hand it over: an upload starts a run on its own from now on.
#
# The sensor watches parsing for documents nobody has asked for, and the
# asset graph carries them the rest of the way. Stopped until this runs,
# because a pipeline that starts the moment the stack comes up is one
# nobody chose.
auto:
	@$(NOT_GO_LIVE)
	@out=$$($(call DAGSTER,sensor start arrivals)); \
	  printf '%s\n' "$$out" | grep -E "sensor arrivals|Error"; \
	  case "$$out" in *Error*) exit 1;; *"sensor arrivals"*) ;; *) exit 1;; esac
	@echo "An upload now starts the pipeline. 'make manual' hands it back."

# Take it back.
manual:
	@out=$$($(call DAGSTER,sensor stop arrivals)); \
	  printf '%s\n' "$$out" | grep -E "sensor arrivals|Error"; \
	  case "$$out" in *Error*) exit 1;; *"sensor arrivals"*) ;; *) exit 1;; esac
