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

# The detector prefixes each finding with the server id it is about
# (`api: mctl_get_lifecycle_ownership is upstream but not ...`). Anchored, so a
# server id appearing inside another server's message does not match.
mine=$(printf '%s\n' "$out" | grep -E "^[[:space:]]*${SERVER}:" || true)
if [ -n "$mine" ]; then
  echo "::error::catalogue drift exit ${code} names ${SERVER}. If new tools arrived, run scripts/portal-allowlist-apply.sh in the owning repository and re-run this check."
  exit "$code"
fi

# Red for somebody else. Surfaced, not swallowed -- and not this run's verdict.
echo "::warning::catalogue drift exit ${code}, but no finding names ${SERVER}: this re-snapshot is consistent and another server is stale. cloudflare-drift.yml owns that."
exit 0
