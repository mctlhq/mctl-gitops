#!/usr/bin/env bash
# Step 4: prove the snapshot actually moved.
#
# An IDENTICAL catalogue is a FAILURE, not a pass. That is the outcome this
# whole procedure exists to prevent — `last_synced` moving while the stored
# tools do not is exactly what a flip that did nothing looks like — so it is
# the one result that must not read as success.
#
# The first version of this script compared the tool COUNT and printed a
# warning, on the reasoning that "the real check is the drift detector". That
# was wrong: the detector compares the snapshot's tool NAMES against each
# owning repository's allowlist, so it is blind to a tool whose schema or
# annotations changed under an unchanged name — and blind to nothing having
# changed at all whenever the allowlist already agrees with the old snapshot.
# A warning is also not a verdict, and the pull request describing this
# workflow claimed a failure. Two answers to one question, which is the defect
# this repository keeps finding.
#
# WHOLE tool objects, because annotations travel in the snapshot and
# `readOnlyHint` is a structural claim this platform acts on: a projection down
# to names and schemas would call a changed annotation "no change".
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id
: "${BEFORE_JSON:?the pre-flip catalogue from the flip job}"
if [ ! -s "$BEFORE_JSON" ]; then
  # The artifact is missing, which its own upload step tolerates on purpose:
  # failing that step would skip this job, and this job is the only bound on
  # the outage. So the comparison is lost and the run is red for it -- but the
  # WAIT above has already happened, which is the part that mattered.
  echo "::error::the pre-flip catalogue is missing, so it cannot be proved the snapshot moved. The sign-in completed (the wait above passed); compare ${SERVER}'s tools against the previous run by hand."
  exit 1
fi

after=$(cf); printf '%s' "$after" | ok

# `tools` is null for a server nobody has authorized — the state this step is
# verifying its way out of. Unguarded, jq dies with "Cannot iterate over null";
# worse, an empty ARRAY would diff as every tool removed and read as a release
# delta.
printf '%s' "$after" | jq -e '(.result.tools | type) == "array" and (.result.tools | length) > 0' >/dev/null \
  || { echo "::error::the portal holds no tools: the sign-in did not complete"; exit 1; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
printf '%s' "$after" | jq -S '[.result.tools[]] | sort_by(.name)' > "$work/after.json"

before_n=$(jq 'length' "$BEFORE_JSON")
after_n=$(jq 'length' "$work/after.json")
last=$(printf '%s' "$after" | jq -r '.result.last_synced')

if cmp -s "$BEFORE_JSON" "$work/after.json"; then
  echo "::error::the catalogue is byte-identical to the pre-flip snapshot (${after_n} tools, last_synced=${last}). The snapshot did not move: whoever signed in was shown the same tools/list, or the sign-in landed on a different server."
  exit 1
fi

# Names only in the summary. The full objects carry schemas, which are long and
# are already in the owning repository's allowlist; what an operator wants here
# is which tools arrived and which left.
added=$(jq -r -n --slurpfile a "$BEFORE_JSON" --slurpfile b "$work/after.json" \
  '($b[0] | map(.name)) - ($a[0] | map(.name)) | join(", ")')
removed=$(jq -r -n --slurpfile a "$BEFORE_JSON" --slurpfile b "$work/after.json" \
  '($a[0] | map(.name)) - ($b[0] | map(.name)) | join(", ")')

{
  echo "### Portal catalogue — \`${SERVER}\`"
  echo
  echo "\`${before_n}\` tools before, \`${after_n}\` after. \`last_synced=${last}\`"
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| added | ${added:-_none_} |"
  echo "| removed | ${removed:-_none_} |"
  [ -z "$added" ] && [ -z "$removed" ] && echo && echo "No name changed; something in a tool's schema or annotations did."
} >> "$GITHUB_STEP_SUMMARY"

echo "catalogue moved: ${before_n} -> ${after_n} tools, last_synced=${last}"
