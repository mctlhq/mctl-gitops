#!/usr/bin/env bash
# The end state, checked by the same detector that found the problem — but
# scoped in its VERDICT to the server this run touched.
#
# `portal-catalogue-drift.py` is account-wide and takes no server filter, so a
# successfully re-snapshotted `api` would go red because `seerrsense` is stale
# for reasons this run never touched. Worse than noise: the alert names one
# server, so the operator reads "the re-snapshot failed" about a server whose
# re-snapshot worked.
#
# Account-wide drift is `cloudflare-drift.yml`'s job and it runs nightly. This
# gate owns one question — did THIS server end up consistent — and says the
# rest out loud rather than either failing on it or hiding it.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id

out=$(python3 scripts/portal-catalogue-drift.py 2>&1) && code=0 || code=$?
printf '%s\n' "$out"

if [ "$code" -eq 0 ]; then
  echo "catalogue drift is clean account-wide"
  exit 0
fi

# GLOBAL BAIL-OUTS FIRST. The detector exits 2 before its per-server loop for
# a missing token or a portal it cannot read, and prints no `{server}:` line at
# all -- so a per-server grep finds nothing and the "red for somebody else"
# branch below would report green on a check that made no comparison. That is
# the final gate of this workflow saying the end state is good having measured
# nothing.
#
# The detector marks them itself: every global bail-out starts a line with
# `[2] `, and no per-server message does.
if printf '%s\n' "$out" | grep -qE '^\[2\] '; then
  echo "::error::the catalogue detector could not run (exit ${code}): it never compared ${SERVER}. Fix the detector's own inputs and re-run; nothing here has been verified."
  exit "$code"
fi

# The detector prefixes each finding with the server id it is about
# (`api: mctl_get_lifecycle_ownership is upstream but not ...`). Anchored, so a
# server id appearing inside another server's message does not match.
mine=$(printf '%s\n' "$out" | grep -E "^[[:space:]]*${SERVER}:" || true)
if [ -n "$mine" ]; then
  # ONE REMEDY PER CODE. The detector's exits mean different things and send an
  # operator to different places: 2 is "re-snapshot", 3 is a waiver chore that
  # cloudflare-drift.yml separates precisely so nobody is sent through this
  # recipe for it, and 4 is an upstream that vanished from the portal.
  case "$code" in
    1) remedy="new tools arrived: run scripts/portal-allowlist-apply.sh in the owning repository, then re-run this check" ;;
    3) remedy="a waiver matches nothing or is wider than what fires: delete or narrow it. This is NOT a re-snapshot" ;;
    4) remedy="${SERVER} is missing from the portal entirely: this is not a catalogue problem" ;;
    *) remedy="see the detector output above" ;;
  esac
  echo "::error::catalogue drift exit ${code} names ${SERVER} -- ${remedy}."
  exit "$code"
fi

# Red for somebody else. Surfaced, not swallowed -- and not this run's verdict.
echo "::warning::catalogue drift exit ${code}, but no finding names ${SERVER}: this re-snapshot is consistent and another server is stale. cloudflare-drift.yml owns that."
exit 0
