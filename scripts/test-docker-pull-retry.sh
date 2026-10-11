#!/usr/bin/env bash
# Self-test for scripts/lib/docker-pull-retry.sh with a stubbed `docker`:
#   - succeeds after transient failures and stops pulling once it has succeeded
#   - fails (non-zero) when every attempt fails, after exactly ATTEMPTS pulls
#   - does not pull an image that is already present
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/docker-pull-retry.sh
source "$ROOT/scripts/lib/docker-pull-retry.sh"
sleep() { :; }

PULLS=0 FAIL_FIRST=0 PRESENT=0
docker() {
  case "$1" in
    image) [ "$PRESENT" = 1 ] ;;
    pull) PULLS=$((PULLS + 1)); [ "$PULLS" -gt "$FAIL_FIRST" ] ;;
    *) echo "unexpected docker $*" >&2; return 99 ;;
  esac
}

fail() { echo "FAIL: $*" >&2; exit 1; }

PULLS=0 FAIL_FIRST=2 PRESENT=0
docker_pull_retry img 5 1 2>/dev/null || fail "transient failures must be retried to success"
[ "$PULLS" = 3 ] || fail "expected 3 pulls (2 failures + 1 success), got $PULLS"

PULLS=0 FAIL_FIRST=99 PRESENT=0
if docker_pull_retry img 4 1 2>/dev/null; then fail "a pull that always fails must fail"; fi
[ "$PULLS" = 4 ] || fail "expected exactly 4 attempts, got $PULLS"

PULLS=0 FAIL_FIRST=99 PRESENT=1
docker_pull_retry img 4 1 2>/dev/null || fail "a present image must not need a pull"
[ "$PULLS" = 0 ] || fail "a present image must not be pulled, got $PULLS pulls"

echo "OK: docker_pull_retry"
