#!/usr/bin/env bash
# The bounded wait for the human half.
#
# #1258 proposed a second approval gate here, meaning "I have signed in". This
# MEASURES the same claim instead: `ready` with a moved `last_synced` is what
# that approval would be asserting, and it fails on a timeout — which an
# approval nobody clicks does not. The failure state being waited out is a
# portal server that is down, so the wait has to end in an alert rather than in
# a job sitting in `waiting` for up to thirty days.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id

: "${LAST_SYNCED_BEFORE:?}"
DEADLINE_S=${DEADLINE_S:-1800}
INTERVAL_S=${INTERVAL_S:-20}

started=$(date -u +%s)
while :; do
  now=$(cf) || true
  status=$(printf '%s' "$now" | jq -r '.result.status // "unreadable"')
  last=$(printf '%s' "$now" | jq -r '.result.last_synced // ""')

  # BOTH, not just status. A server can read `ready` off the pre-flip snapshot
  # in a race, and `last_synced` is the only field this API moves on a real
  # re-authorization — the README records it as the single honest signal.
  if [ "$status" = "ready" ] && [ -n "$last" ] && [ "$last" != "$LAST_SYNCED_BEFORE" ]; then
    echo "signed in: status=ready last_synced=${last} (was ${LAST_SYNCED_BEFORE})"
    exit 0
  fi

  elapsed=$(( $(date -u +%s) - started ))
  if [ "$elapsed" -ge "$DEADLINE_S" ]; then
    echo "::error::${SERVER} is still status=${status} after ${elapsed}s; it is UNUSABLE until someone signs it out and back in on the portal server-selection page"
    exit 1
  fi
  echo "waiting: status=${status} last_synced=${last:-none} (${elapsed}s of ${DEADLINE_S}s)"
  sleep "$INTERVAL_S"
done
