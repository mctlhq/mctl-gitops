#!/usr/bin/env bash
# Assert that the backend `tofu init` resolved for $1 is the one this root is
# supposed to use — not merely that it is of type s3.
#
# Checking the type alone is not a check. A mistyped key resolves to an object
# that does not exist, so the plan is computed from empty state and proposes
# creating everything the root describes, against live Cloudflare, with no
# error anywhere. A wrong bucket does the same. use_lockfile = false silently
# removes the locking that cloudflare-apply.yml's whole no--lock=false argument
# depends on.
#
# Read from what init resolved rather than from backend.tf: a comment
# mentioning backend "s3" next to a live backend "local" satisfies any text
# match of the file.
#
# Usage: cloudflare-assert-backend.sh <root> <tf-data-dir>
set -euo pipefail

ROOT="${1:?usage: $0 <root> <tf-data-dir>}"
DATA_DIR="${2:?usage: $0 <root> <tf-data-dir>}"

EXPECTED_BUCKET="mctl-cloudflare-state"
EXPECTED_ENDPOINT_HOST="6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com"

# One state key per root, derived from the root's own path — which is the
# convention stated in infrastructure/cloudflare/README.md. Deriving it here
# rather than accepting whatever backend.tf says is what turns a typo into a
# failure instead of into an empty state.
rel="${ROOT#infrastructure/cloudflare/}"
if [ "$rel" = "$ROOT" ]; then
  echo "::error::'$ROOT' is not under infrastructure/cloudflare/"
  exit 1
fi
EXPECTED_KEY="cloudflare/${rel}/terraform.tfstate"

state="$DATA_DIR/terraform.tfstate"
if [ ! -f "$state" ]; then
  echo "::error::no resolved backend at $state — did tofu init run?"
  exit 1
fi

fail=0
say() { echo "::error::$1"; fail=1; }

type=$(jq -r '.backend.type // empty' "$state")
[ "$type" = "s3" ] || say "backend resolved to '${type:-<none>}', not s3"

bucket=$(jq -r '.backend.config.bucket // empty' "$state")
[ "$bucket" = "$EXPECTED_BUCKET" ] || say "backend bucket is '${bucket:-<none>}', expected '$EXPECTED_BUCKET'"

key=$(jq -r '.backend.config.key // empty' "$state")
[ "$key" = "$EXPECTED_KEY" ] || say "backend key is '${key:-<none>}', expected '$EXPECTED_KEY' for root '$ROOT'"

# Accept either shape the s3 backend records the endpoint in.
endpoint=$(jq -r '.backend.config.endpoints.s3 // .backend.config.endpoint // empty' "$state")
case "$endpoint" in
  *"$EXPECTED_ENDPOINT_HOST"*) ;;
  *) say "backend endpoint is '${endpoint:-<none>}', expected the R2 endpoint for this account" ;;
esac

# Native S3 conditional-write locking. Without it an apply takes no lock at
# all, which is the guarantee cloudflare-apply.yml claims by never passing
# -lock=false.
# `// empty` is wrong here: jq's alternative operator treats `false` as
# absent, so an explicitly disabled lock would be reported as missing. The
# difference matters — one is a typo, the other is a decision someone made.
lock=$(jq -r 'if (.backend.config | has("use_lockfile")) then (.backend.config.use_lockfile | tostring) else "<absent>" end' "$state")
[ "$lock" = "true" ] || say "backend use_lockfile is '$lock', expected true"

if [ "$fail" -ne 0 ]; then
  echo "resolved backend config, for comparison:"
  jq -S '.backend.config | {bucket, key, endpoints, endpoint, use_lockfile}' "$state" || true
  exit 1
fi

echo "backend for '$ROOT' is s3://$bucket/$key with locking"
