#!/bin/bash
# The hosted corpus run: `make corpus` in a process group of its own, which is
# recorded with the database it acts on in logs/corpus-hosted.pid, its output
# appended to logs/corpus-hosted.log. `make corpus-hosted` runs this detached
# and `make corpus-hosted-stop` signals the group it records.
#
#   scripts/corpus-hosted.sh [--check] [VAR=value ...]
#
# The VAR=value words are `make corpus`'s command line; APP_DB_NAME among them
# is the database recorded. --check stops after what a start refuses, which
# `make corpus-hosted` asks before it pays for the preflight.
set -u
cd "$(dirname "$0")/.." || exit 3
pid=logs/corpus-hosted.pid
log=logs/corpus-hosted.log
mkdir -p logs

check=
[ "${1:-}" != --check ] || { check=1; shift; }
database=
for word in "$@"; do
  case $word in APP_DB_NAME=*) database=${word#APP_DB_NAME=} ;; esac
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
[ -z "$check" ] || exit 0

# A record nobody holds is a run that died - a restart, a kill - so this one
# resumes it: the stages' failed rows go back to the queue first.
resume=
[ -z "$group" ] || resume=RESUME=1

# Job control puts the run in a process group of its own, led by its make.
set -m
make --no-print-directory corpus $resume "$@" >> "$log" 2>&1 &
run=$!
echo "$run $database" > "$pid"
wait "$run"
code=$?
# What a signal to the group left: a drain finishing its row after the makes
# above it died. The record stands until the last of them has gone.
while kill -0 -- "-$run" 2>/dev/null; do sleep 1; done
rm -f "$pid"
exit "$code"
