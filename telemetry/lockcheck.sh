#!/bin/sh
# The first thing every container of our images runs: refuses to start when the
# lock it installs from changed after the image was built.
#
# The hash of the lock is baked at build (LOCK_SHA) and the checkout's own
# copy is bind-mounted read-only (LOCK_FILE), so the two differ exactly when
# somebody edited the lock and did not run `compose build`. Without this the
# container starts on the old packages and fails at the first import the new
# lock was meant to supply, or worse, runs on versions nobody reviewed.
#
# A refusal waits before it exits. `restart: unless-stopped` restarts a
# container whatever its exit code, so the wait is what keeps a stale image to
# one line in the log every ten minutes and not a spin.
set -u
baked=$(cat "${LOCK_SHA:-}" 2>/dev/null || true)
live=$(sha256sum "${LOCK_FILE:-}" 2>/dev/null | cut -d' ' -f1)
if [ -z "$baked" ] || [ "$baked" != "$live" ]; then
  echo "${LOCK_FILE:-the lock} is not the one this image was built from: run compose build, then make up" >&2
  sleep "${LOCKCHECK_WAIT:-600}"
  exit 78
fi
exec "$@"
