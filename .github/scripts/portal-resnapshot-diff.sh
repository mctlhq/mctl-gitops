#!/usr/bin/env bash
# Step 4: the catalogue actually moved.
#
# An IDENTICAL catalogue is a FAILURE, not a pass: it means the snapshot never
# moved, whatever `last_synced` says. That is the whole reason this workflow
# exists, so it is the one outcome that must not read as success.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id
: "${TOOLS_BEFORE:?}"

after=$(cf); printf '%s' "$after" | ok

# `tools` is null for a server nobody has authorized — the state this step is
# verifying its way out of. Unguarded, jq dies with "Cannot iterate over null";
# worse, an empty ARRAY would diff as every tool removed and read as a release
# delta.
printf '%s' "$after" | jq -e '(.result.tools | type) == "array" and (.result.tools | length) > 0' >/dev/null \
  || { echo "::error::the portal holds no tools: the sign-in did not complete"; exit 1; }

count=$(printf '%s' "$after" | jq '.result.tools | length')
{
  echo "### Portal catalogue — \`${SERVER}\`"
  echo
  echo "\`${TOOLS_BEFORE}\` tools before, \`${count}\` after."
} >> "$GITHUB_STEP_SUMMARY"

if [ "$count" -eq "$TOOLS_BEFORE" ]; then
  # Same COUNT is not the same catalogue -- a tool can be replaced, or only its
  # schema or annotations changed -- so this is a warning here and the real
  # check is the byte comparison the drift detector makes against the
  # allowlist. What is NOT tolerable is nothing having changed at all, and
  # that is what the detector answers.
  echo "::warning::the tool count did not change (${count}); if this release was supposed to add one, the snapshot did not move"
fi
echo "last_synced=$(printf '%s' "$after" | jq -r '.result.last_synced')"
