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

# Usage:  CLOUDFLARE_GUARD_SELF_TEST=1 cloudflare-assert-backend.sh
#
# NOT --self-test: $1 here is the dispatched root, so the flag would share a
# namespace with it and is refused like any other bad name.
#
# The suite builds synthetic resolved-backend files and checks each arm.
# Same reason as the sibling script: this code fails by ACCEPTING, and its
# endpoint check was a substring match until review caught that
# https://attacker.example/?q=<expected host> satisfied it.
# Environment-gated for the same reason as the sibling script: $1 here is the
# dispatched root, and a flag sharing that namespace makes this guard exit 0 on
# an input it should refuse.
if [ "${CLOUDFLARE_GUARD_SELF_TEST:-}" = "1" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/dd"
  fail=0
  host="6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com"

  fixture() { # fixture <type> <bucket> <key> <endpoint> <use_lockfile-json>
    printf '{"version":3,"backend":{"type":"%s","config":{"bucket":"%s","key":"%s","endpoints":{"s3":"%s"},"use_lockfile":%s}}}\n' \
      "$1" "$2" "$3" "$4" "$5" > "$tmp/dd/terraform.tfstate"
  }
  expect() { # expect <accept|reject> <root> <label>
    local want="$1" root="$2" label="$3" rc=0
    CLOUDFLARE_GUARD_SELF_TEST= "$self" "$root" "$tmp/dd" >/dev/null 2>&1 || rc=$?
    if [ "$want" = accept ] && [ "$rc" -ne 0 ]; then
      echo "self-test FAILED: $label — expected accept, got exit $rc" >&2; fail=1
    elif [ "$want" = reject ] && [ "$rc" -eq 0 ]; then
      echo "self-test FAILED: $label — expected reject, was ACCEPTED" >&2; fail=1
    fi
  }

  good_key="cloudflare/account/terraform.tfstate"
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host" true
  expect accept "infrastructure/cloudflare/account" "the correct backend"
  fixture s3 mctl-cloudflare-state "cloudflare/zones/mctl-me/terraform.tfstate" "https://$host" true
  expect accept "infrastructure/cloudflare/zones/mctl-me" "a nested zone root"

  fixture s3 mctl-cloudflare-state "cloudflare/acount/terraform.tfstate" "https://$host" true
  expect reject "infrastructure/cloudflare/account" "mistyped key plans from empty state"
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host" true
  expect reject "infrastructure/cloudflare/zones/mctl-ru" "key belonging to a different root"
  fixture s3 mctl-terraform-state "$good_key" "https://$host" true
  expect reject "infrastructure/cloudflare/account" "wrong bucket (the k3s state)"
  fixture local "" "" "https://$host" true
  expect reject "infrastructure/cloudflare/account" "backend is not s3"
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host" false
  expect reject "infrastructure/cloudflare/account" "use_lockfile explicitly false"
  printf '{"version":3,"backend":{"type":"s3","config":{"bucket":"mctl-cloudflare-state","key":"%s","endpoints":{"s3":"https://%s"}}}}\n' \
    "$good_key" "$host" > "$tmp/dd/terraform.tfstate"
  expect reject "infrastructure/cloudflare/account" "use_lockfile absent"

  # The endpoint arm. A substring match accepted all three of these.
  fixture s3 mctl-cloudflare-state "$good_key" "https://attacker.example/?q=$host" true
  expect reject "infrastructure/cloudflare/account" "expected host as a query parameter"
  fixture s3 mctl-cloudflare-state "$good_key" "https://evil-$host" true
  expect reject "infrastructure/cloudflare/account" "expected host as a suffix"
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host.evil.example" true
  expect reject "infrastructure/cloudflare/account" "expected host as a prefix"
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host/" true
  expect accept "infrastructure/cloudflare/account" "endpoint with a trailing slash"

  # The flag is no longer an entrypoint here either, so it has to be refused
  # like any other bad root name — same claim the header of this file makes.
  fixture s3 mctl-cloudflare-state "$good_key" "https://$host" true
  expect reject "--self-test" "the self-test flag as a root name"

  rm -f "$tmp/dd/terraform.tfstate"
  expect reject "infrastructure/cloudflare/account" "no resolved backend at all"

  [ "$fail" -eq 0 ] || exit 1
  echo "self-test OK"
  exit 0
fi

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
#
# Matched exactly, not as a substring. `*"$EXPECTED_ENDPOINT_HOST"*` would
# accept https://attacker.example/?q=<expected host>, and an apply pointed
# there hands SigV4-signed requests carrying the write credential to that
# server and then plans against whatever state it returns — a fabricated
# baseline is enough to make the real Cloudflare API calls destructive.
endpoint=$(jq -r '.backend.config.endpoints.s3 // .backend.config.endpoint // empty' "$state")
case "$endpoint" in
  "https://$EXPECTED_ENDPOINT_HOST" | "https://$EXPECTED_ENDPOINT_HOST/") ;;
  *) say "backend endpoint is '${endpoint:-<none>}', expected exactly https://$EXPECTED_ENDPOINT_HOST" ;;
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
