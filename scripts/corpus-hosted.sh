#!/bin/bash
# The hosted corpus run: `make corpus` in a process group of its own, which is
# recorded with the database it acts on in logs/corpus-hosted.pid, its output
# appended to logs/corpus-hosted.log. `make corpus-hosted` runs this detached
# and `make corpus-hosted-stop` signals the group it records.
#
#   scripts/corpus-hosted.sh [--check] [VAR=value ...]
#
# The VAR=value words are `make corpus`'s command line; APP_DB_NAME among them
# is the database recorded, and RESET=1 forgets a stopped run instead of
# resuming it. --check stops after what a start refuses, which
# `make corpus-hosted` asks before it pays for the preflight.
#
# The record outlives a run that ends other than finished - stopped at
# SPEND_CAP, by a signal or by failed rows, or a crash - so the next start
# resumes it and keeps its spend ledger. Only a run that finished, or RESET=1,
# makes the next one fresh, and a fresh `make corpus` starts the ledger again.
set -u
cd "$(dirname "$0")/.." || exit 3
pid=logs/corpus-hosted.pid
log=logs/corpus-hosted.log
mkdir -p logs

check=
[ "${1:-}" != --check ] || { check=1; shift; }
database=
reset=
given=()
for word in "$@"; do
  case $word in
    RESET=?*) reset=1; continue ;;
    APP_DB_NAME=*) database=${word#APP_DB_NAME=} ;;
  esac
  given+=("$word")
done

# The run recorded: its process group and its database. A group with a member
# alive is a run going on, whoever led it: a kill of the make at its head
# leaves the drain under it running.
group=
recorded=
[ ! -f "$pid" ] || read -r group recorded < "$pid"
if [ -n "$group" ] && kill -0 -- "-$group" 2>/dev/null; then
  echo "corpus-hosted is already running (process group $group${recorded:+, database $recorded});" \
    "follow it: tail -f $log; stop it: make corpus-hosted-stop" >&2
  exit 3
fi
# A stopped run's failed rows and spend are its own database's.
if [ -z "$reset" ] && [ -n "$group" ] && [ -n "$recorded" ] && [ -n "$database" ] \
  && [ "$recorded" != "$database" ]; then
  echo "a stopped run on $recorded is recorded: resume it with APP_DB_NAME=$recorded," \
    "or start afresh on $database with RESET=1, which starts its spend again" >&2
  exit 3
fi
[ -z "$check" ] || exit 0
[ -z "$reset" ] || { rm -f "$pid"; group=; }

# A record nobody holds is a run that stopped or died, so this one resumes it:
# the stages' failed rows go back to the queue first and the ledger is kept.
resume=
[ -z "$group" ] || resume=RESUME=1

# Job control puts the run in a process group of its own, led by its make.
set -m
make --no-print-directory corpus $resume ${given[@]+"${given[@]}"} >> "$log" 2>&1 &
run=$!
echo "$run $database" > "$pid"
wait "$run"
code=$?
# What a signal to the group left: a drain finishing its row after the makes
# above it died. The record stands until the last of them has gone.
while kill -0 -- "-$run" 2>/dev/null; do sleep 1; done
[ "$code" -ne 0 ] || rm -f "$pid"
echo "corpus-hosted: the run ended with exit $code"
exit "$code"
