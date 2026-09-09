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

# --self-test exercises every arm of this file against the real tree plus one
# temporary fixture. It exists because these checks fail by ACCEPTING, and each
# of them has been silently wrong at least once while reading as correct: the
# guard that ran inside an `if` and swallowed errexit, the list path resolved
# against the caller's cwd, and the canonical-form case that closed `*/` while
# `*/.` and `*//*` walked past it. None were found by running the script.
if [ "${1:-}" = "--self-test" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  repo="$(cd "$(dirname "$self")/../.." && pwd)"
  fail=0
  expect() { # expect <accept|reject> <root> <label>
    local want="$1" root="$2" label="$3" rc=0
    ( cd "$repo" && "$self" "$root" ) >/dev/null 2>&1 || rc=$?
    if [ "$want" = accept ] && [ "$rc" -ne 0 ]; then
      echo "self-test FAILED: $label — expected accept, got exit $rc" >&2; fail=1
    elif [ "$want" = reject ] && [ "$rc" -eq 0 ]; then
      echo "self-test FAILED: $label — expected reject, was ACCEPTED" >&2; fail=1
    fi
  }

  expect accept "infrastructure/cloudflare/account"          "a real root on the remote backend"
  # The root on .local-state-roots — the case that list exists to refuse.
  expect reject "infrastructure/cloudflare/zones/mctl-ru"    "root listed in .local-state-roots"
  # Non-canonical spellings the whole-line list match would not recognise.
  expect reject "infrastructure/cloudflare/account/"         "trailing slash"
  expect reject "infrastructure/cloudflare/account/."        "trailing /."
  expect reject "infrastructure/cloudflare//account"         "doubled separator"
  expect reject "./infrastructure/cloudflare/account"        "leading ./"
  expect reject "infrastructure/cloudflare/zones/mctl-ru/"   "listed root, trailing slash"
  expect reject "infrastructure/cloudflare/zones/mctl-ru/."  "listed root, trailing /."
  expect reject "infrastructure/cloudflare//zones/mctl-ru"   "listed root, doubled separator"
  # Outside the tree, parent traversal, a module rather than a root.
  expect reject "../etc"                                     "outside infrastructure/cloudflare"
  expect reject "infrastructure/cloudflare/../../etc"        "parent traversal"
  expect reject "infrastructure/cloudflare/modules/zone-baseline" "a module is not a root"
  # A directory that exists but carries no versions.tf.
  tmp_root="infrastructure/cloudflare/.self-test-not-a-root"
  mkdir -p "$repo/$tmp_root"
  expect reject "$tmp_root"                                  "directory with no versions.tf"
  rmdir "$repo/$tmp_root"

  [ "$fail" -eq 0 ] || exit 1
  echo "self-test OK"
  exit 0
fi

ROOT="${1:?usage: $0 <root>}"

# Rejected rather than stripped, so this script, cloudflare-assert-backend.sh
# and the token chain in the workflow all reason about the same string.
#
# The .local-state-roots check below is `grep -qxF`, a whole-line match, so ANY
# non-canonical spelling of a path walks past it — a trailing slash is only the
# most obvious. `.../mctl-ru/.` and `.../cloudflare//zones/mctl-ru` reach the
# same place: the prefix test passes, there is no `..`, the versions.tf probe
# resolves through the extra separators, and then the string does not equal the
# list entry, so the one root that list exists to refuse is accepted. The same
# spellings make assert-backend.sh derive a key like
# `cloudflare/account//terraform.tfstate` and refuse a perfectly good root with
# a message about the backend rather than about the dispatch form.
#
# So this rejects the class, not the one spelling that was reported.
case "$ROOT" in
  */ | */. | */./* | *//* | ./*)
    echo "::error::name the root in canonical form — no trailing slash, no './' or '/.', no doubled separator: $ROOT"
    exit 1 ;;
esac

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
