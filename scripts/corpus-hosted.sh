#!/bin/bash
# The hosted corpus run: `make corpus` in a process group of its own, which is
# recorded with the database it acts on in state/corpus-hosted.pid, its output
# appended to logs/corpus-hosted.log. state/, beside the spend ledgers, is no
# log folder: no log or wipe target walks it, so a record outlives them. `make corpus-hosted` runs this detached,
# `make corpus-hosted-stop` asks it to --stop, and a supervisor runs it in the
# foreground (docs/operations.md, "After a stop").
#
#   scripts/corpus-hosted.sh [--detach|--stop|--guard|--zero-on-stop] [VAR=value ...]
#
# The VAR=value words are `make corpus`'s command line; APP_DB_NAME among them
# is the database recorded, resolved as `make corpus` resolves it where none is
# given, and RESET=1 forgets a stopped run instead of resuming it. Every start
# proves what `make corpus-preflight` checks first - the go-live profile, no
# model worker or Dagster container up, the split, the password and the cache -
# and refuses with 3 where it does not. --detach is `make corpus-hosted`'s: it
# checks in the foreground, then runs the rest detached. --guard is what
# `make corpus` asks first: it refuses beside a hosted run of its database that
# is going, and, unless it resumes (RESUME=1), beside a stopped one, whose
# spend ledger a fresh run would start again.
#
# It exits with the code of the stage that ended the run, not make's 2: 0 when
# the run finished, 75 when a drain stopped itself (SPEND_CAP, a model that
# cannot be reached) or a signal stopped the run, 3 when rows failed or a start
# is refused, anything else for a crash. Neither 75 nor 3 is for a supervisor
# to restart: each wants the operator. --zero-on-stop turns both into 0, for
# launchd, which can only restart on every code but 0.
#
# The record outlives a run that ends other than finished, so the next start
# resumes it and keeps its spend ledger. Only a run that finished, or RESET=1,
# makes the next one fresh, and a fresh `make corpus` starts the ledger again.
set -u
cd "$(dirname "$0")/.." || exit 3
pid=state/corpus-hosted.pid
log=logs/corpus-hosted.log
mkdir -p state logs

# How long a stop waits for the drains after TERM before it kills what is
# left, in seconds: a model stage's grace and the time to give its row back
# (DEFAULT_GRACE_SECONDS and RELEASE_MARGIN in backend/stages/worker.py,
# which a test holds this to).
grace=${HOSTED_GRACE:-300}

mode=
case ${1:-} in --detach | --checked | --stop | --guard | --zero-on-stop) mode=$1; shift ;; esac
database=
named=
reset=
resuming=
given=()
for word in "$@"; do
  case $word in
    # A spelling of yes, as every setting reads one (settings/env.py's _TRUE):
    # RESET=0 resumes.
    RESET=*)
      case $(printf %s "${word#RESET=}" | tr '[:upper:]' '[:lower:]') in 1 | true | yes | on) reset=1 ;; esac
      continue
      ;;
    RESUME=?*) resuming=1 ;;
    APP_DB_NAME=*) database=${word#APP_DB_NAME=}; named=1 ;;
  esac
  given+=("$word")
done
# A start that names no database runs on the one `make corpus` would, which
# is the one its record must name: a record of none is a run any database's
# start would resume.
if [ -z "$named" ] && [ "$mode" != --stop ] && [ "$mode" != --guard ]; then
  database=$(make --no-print-directory -s corpus-database ${given[@]+"${given[@]}"})
  given+=("APP_DB_NAME=$database")
  set -- "$@" "APP_DB_NAME=$database"
fi

# Ends with `code`, as --zero-on-stop wants it told.
leave() {
  [ "$mode" != --zero-on-stop ] || case $1 in 3 | 75) exit 0 ;; esac
  exit "$1"
}

# Waits for the group to empty, killing what is left after `grace` seconds.
outlast() {
  local waited=0
  while kill -0 -- "-$1" 2>/dev/null; do
    if [ "$waited" -ge "$grace" ]; then
      echo "the run is still going after ${grace}s: killing what is left" >&2
      kill -KILL -- "-$1" 2>/dev/null
      return
    fi
    sleep 1
    waited=$((waited + 1))
  done
}

# The run recorded: its process group and database, and on a line of its own
# when the make leading the group started, which tells the run apart from
# another group given the same number later - the record outlives every stop,
# and a reboot or a wrapped pid count hands the number on.
group=
recorded=
started=
[ ! -f "$pid" ] || { read -r group recorded; read -r started; } < "$pid"

# When a process started, in one locale and one zone whoever asks: ps prints
# it in the caller's, so a run a launchd daemon (no LANG) started would not be
# found by a stop from a Terminal in the user's region.
started_at() {
  LC_ALL=C TZ=UTC0 ps -o lstart= -p "$1" 2>/dev/null | sed 's/ *$//'
}

# Whether a member of group $1 is a corpus run's: a make given a run's spend
# ledger on its command line, or a stage's drain. What tells a run whose make
# was killed from a group that took the number after a reboot or a wrap of the
# pid count and whose own leader has exited.
run_member() {
  ps -A -o pgid= -o command= 2>/dev/null | awk -v group="$1" '$1 == group' \
    | grep -qE 'SPEND_LEDGER=state/corpus-spend-|-m [a-z_.]+\.run( |$)'
}

# Whether the recorded group is the run, going on: its leader alive with the
# start time recorded or, that make killed, a make or a drain of the run left
# in its group, finishing a row. A record with no start time names no run.
ours() {
  [ -n "$group" ] && [ -n "$started" ] || return 1
  if ps -p "$group" >/dev/null 2>&1; then
    [ "$(started_at "$group")" = "$started" ]
  else
    run_member "$group"
  fi
}
alive=
! ours || alive=1

if [ "$mode" = --stop ]; then
  [ -n "$alive" ] || { echo "no hosted run is going"; exit 0; }
  echo "stopping the hosted run (process group $group): each drain finishes or gives back its row, for up to ${grace}s"
  kill -TERM -- "-$group"
  outlast "$group"
  exit 0
fi
if [ "$mode" = --guard ]; then
  # Another database's run, or none, is not this one's business.
  [ -n "$group" ] || exit 0
  [ -z "$recorded" ] || [ -z "$database" ] || [ "$recorded" = "$database" ] || exit 0
  if [ -n "$alive" ]; then
    # The hosted run's own `make corpus`, which leads that group.
    [ "$(ps -o pgid= -p $$ | tr -d ' ')" != "$group" ] || exit 0
    echo "a hosted run on ${recorded:-this database} is going (process group $group):" \
      "a second chain would drain its queues and overwrite its spend ledger." \
      "Follow it: tail -f $log; stop it: make corpus-hosted-stop" >&2
    exit 3
  fi
  [ -z "$resuming" ] || exit 0
  echo "a stopped hosted run on ${recorded:-this database} is recorded, and a fresh" \
    "make corpus would start its spend ledger again: resume it with make corpus-hosted," \
    "or start afresh with make corpus-hosted RESET=1" >&2
  exit 3
fi
if [ -n "$alive" ]; then
  echo "corpus-hosted is already running (process group $group${recorded:+, database $recorded});" \
    "follow it: tail -f $log; stop it: make corpus-hosted-stop" >&2
  leave 3
fi
# A stopped run's failed rows and spend are its own database's.
if [ -z "$reset" ] && [ -n "$group" ] && [ -n "$recorded" ] && [ -n "$database" ] \
  && [ "$recorded" != "$database" ]; then
  echo "a stopped run on $recorded is recorded: resume it with APP_DB_NAME=$recorded," \
    "or start afresh on $database with RESET=1, which starts its spend again" >&2
  leave 3
fi
if [ "$mode" != --checked ] && ! make --no-print-directory corpus-preflight ${given[@]+"${given[@]}"}; then
  echo "corpus-hosted: the preflight refused the run" >&2
  leave 3
fi
if [ "$mode" = --detach ]; then
  # Checked here, in the caller's terminal; the run goes on without it.
  nohup "$0" --checked "$@" >> "$log" 2>&1 &
  for _ in $(seq 50); do [ -f "$pid" ] && break; sleep 0.1; done
  echo "corpus-hosted started: log $log, pid file $pid; stop it with make corpus-hosted-stop"
  exit 0
fi
[ -z "$reset" ] || { rm -f "$pid"; group=; }

# A record nobody holds is a run that stopped or died, so this one resumes it:
# the stages' failed rows go back to the queue first and the ledger is kept.
resume=
[ -z "$group" ] || resume=RESUME=1

start=0
[ ! -f "$log" ] || start=$(wc -c < "$log")
# Job control puts the run in a process group of its own, led by its make.
set -m
make --no-print-directory corpus $resume ${given[@]+"${given[@]}"} >> "$log" 2>&1 &
run=$!
printf '%s %s\n%s\n' "$run" "$database" "$(started_at "$run")" > "$pid"
# A stop asked of this script - a supervisor's - is passed to the whole run.
stopping=
trap 'stopping=1; kill -TERM -- "-$run" 2>/dev/null' TERM INT
wait "$run"
code=$?
while kill -0 "$run" 2>/dev/null; do
  wait "$run"
  code=$?
done
# What a signal to the group left: a drain finishing its row after the makes
# above it died. The record stands until the last of them has gone.
outlast "$run"

# make exits 2 whatever failed; the code of the recipe that failed first, which
# GNU make prints as `[target] Error NN`, is the stage's.
if [ "$code" -eq 2 ]; then
  # A log emptied meanwhile (make wipe ALL_DATABASES=1) is read whole.
  [ "$(wc -c < "$log")" -ge "$start" ] || start=0
  failed=$(tail -c +"$((start + 1))" "$log" | grep -m 1 -oE '\] Error [0-9]+$' | grep -oE '[0-9]+$')
  code=${failed:-2}
fi
# make ended by TERM or INT, or this script asked to stop: a stop.
case $code in 130 | 143) code=75 ;; esac
[ -z "$stopping" ] || [ "$code" -eq 0 ] || code=75

[ "$code" -ne 0 ] || rm -f "$pid"
echo "corpus-hosted: the run ended with exit $code"
leave "$code"
