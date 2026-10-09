#!/usr/bin/env bash
# Read the server as it stands, and publish what the later jobs compare against.
#
# Runs unprivileged and before the approval, so whoever approves the flip is
# approving a change to a state they can see rather than an intention.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id

summary=$(cf)
printf '%s' "$summary" | ok

status=$(printf '%s' "$summary" | jq -r '.result.status')
mode=$(printf '%s' "$summary" | jq -r '.result.auth_config_summary.auth_mode // "none"')
tools=$(printf '%s' "$summary" | jq '(.result.tools // []) | length')
last=$(printf '%s' "$summary" | jq -r '.result.last_synced // ""')

# A server with no registration has nothing to back up, and the flip would
# destroy nothing and restore nothing — it would just leave it as it was while
# reporting success.
if [ "$mode" != "manual" ]; then
  echo "::error::${SERVER} is auth_mode=${mode}, not manual; this procedure is only for manual-OAuth servers"
  exit 1
fi
# `tools` null is a server nobody has authorized. Re-snapshotting it is not
# what this is for, and step 5's "identical catalogue is a failure" check has
# nothing to compare against.
if [ "$tools" -eq 0 ]; then
  echo "::error::${SERVER} holds no tools; there is no catalogue to refresh"
  exit 1
fi

# No job outputs. This job exists to be READ before the approval, not to feed
# the later ones: the flip moves `last_synced` and rewrites the catalogue, so
# every value here is stale by the time anything compares against it. `verify`
# takes its baseline from the flip job, after the restore.

{
  echo "### Portal re-snapshot preflight — \`${SERVER}\`"
  echo
  echo "| field | value |"
  echo "| --- | --- |"
  echo "| status | \`${status}\` |"
  echo "| auth_mode | \`${mode}\` |"
  echo "| tools | \`${tools}\` |"
  echo "| last_synced | \`${last}\` |"
  echo
  echo "Approving the next job takes this server **offline** until a person signs it back in."
} >> "$GITHUB_STEP_SUMMARY"
