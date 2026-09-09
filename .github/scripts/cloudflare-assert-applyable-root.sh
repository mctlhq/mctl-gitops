#!/usr/bin/env bash
# Assert that $1 is a root cloudflare-apply.yml is allowed to act on.
#
# Lives in a script rather than inline in the workflow because both the plan
# job and the apply job have to make exactly the same judgement, and a check
# that is duplicated in two YAML blocks is a check that will eventually differ
# between them.
#
# Shape only. Whether a write credential exists for the root is a separate
# question, answered in the apply job where that credential is in scope.
set -euo pipefail

# Resolved from this script's own location, not the caller's cwd. Two jobs call
# it now, and a relative path would make its correctness depend on both of them
# having cd'd to the workspace first — true today, enforced by nothing.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ROOT="${1:?usage: $0 <root>}"

case "$ROOT" in
  infrastructure/cloudflare/*) ;;
  *) echo "::error::'$ROOT' is not under infrastructure/cloudflare/"; exit 1 ;;
esac

case "$ROOT" in
  *..*) echo "::error::'$ROOT' contains a parent reference"; exit 1 ;;
esac

# A shared module is not a root: planning one fails on its required inputs,
# and applying one is meaningless.
case "$ROOT" in
  infrastructure/cloudflare/modules/*)
    echo "::error::'$ROOT' is a module, not a root"; exit 1 ;;
esac

if [ ! -f "$REPO_ROOT/$ROOT/versions.tf" ] && [ ! -f "$REPO_ROOT/$ROOT/versions.tf.json" ]; then
  echo "::error::'$ROOT' is not a root — no versions.tf"
  exit 1
fi

# A root on local state has no remote state on a fresh runner, so its plan is
# computed from nothing and proposes creating everything the root describes.
# That is the most destructive shape this workflow could take, and it is
# silent — the plan looks ordinary.
#
# The helper runs in an assignment rather than inside the `if`. Bash suspends
# errexit for a command evaluated as a condition, so `if helper | grep -q` would
# read every failure of the helper — renamed, not executable, unreadable list —
# as "not listed", and accept the root. That is the same silent-acceptance shape
# the check exists to prevent. cloudflare-drift.yml already does it this way.
# The list path is passed explicitly, absolute. The helper defaults it to a
# path relative to the CALLER's cwd and treats a missing file as "no local
# roots" with exit 0 — so from the wrong directory the helper is found, reads
# nothing, succeeds, and the root is accepted. Resolving the helper by
# BASH_SOURCE fixed how it is found, not what it reads; this fixes the rest.
# An absent list is still legitimate and still means no local-state roots —
# what is removed is the possibility of looking in the wrong place for it.
local_roots="$("$SCRIPT_DIR/cloudflare-local-state-roots.sh" \
                 "$REPO_ROOT/infrastructure/cloudflare/.local-state-roots")"
if printf '%s\n' "$local_roots" | grep -qxF -- "$ROOT"; then
  echo "::error::'$ROOT' is listed in .local-state-roots — it has no remote state to apply against"
  exit 1
fi

echo "root '$ROOT' accepted"
