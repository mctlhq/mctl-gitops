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

if [ ! -f "$ROOT/versions.tf" ] && [ ! -f "$ROOT/versions.tf.json" ]; then
  echo "::error::'$ROOT' is not a root — no versions.tf"
  exit 1
fi

# A root on local state has no remote state on a fresh runner, so its plan is
# computed from nothing and proposes creating everything the root describes.
# That is the most destructive shape this workflow could take, and it is
# silent — the plan looks ordinary.
if .github/scripts/cloudflare-local-state-roots.sh | grep -qxF -- "$ROOT"; then
  echo "::error::'$ROOT' is listed in .local-state-roots — it has no remote state to apply against"
  exit 1
fi

echo "root '$ROOT' accepted"
