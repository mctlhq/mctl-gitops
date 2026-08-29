#!/usr/bin/env bash
# Validate the VMRule files under infra-components/observability/vm-rules.
#
# Two distinct checks, because they catch different things:
#
#   1. `promtool check rules` — syntax and structure. Catches a malformed
#      expression or a missing field, nothing about meaning.
#   2. `promtool test rules` — unit tests with seeded series and expected
#      alerts. This is the one that matters: HighToolErrorRate shipped a
#      mathematically impossible ratio (division without aggregation matches
#      on `status` too, so it evaluated errors/errors = 1) and lived for
#      months precisely because a syntax check has nothing to say about it.
#
# A VMRule's `.spec` is a Prometheus rule-group document, so the specs are
# extracted into tests/generated/ and both checks run against those. The
# generated files are build output, not source — CI regenerates them and they
# are gitignored.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULES_DIR="$ROOT/platform-gitops/infra-components/observability/vm-rules"
TESTS_DIR="$RULES_DIR/tests"
GEN_DIR="$TESTS_DIR/generated"

rm -rf "$GEN_DIR"
mkdir -p "$GEN_DIR"
# Build output must not outlive the check: the kubeconform step that runs
# after this script sweeps all of infra-components and chokes on these
# extracted rule-group documents (no `kind`), which turned validate red on
# every branch on 2026-08-29.
trap 'rm -rf "$GEN_DIR"' EXIT

shopt -s nullglob
fail=0

for f in "$RULES_DIR"/*.yaml; do
  kind=$(yq '.kind // ""' "$f")
  if [ "$kind" != "VMRule" ]; then
    echo "skip (kind=$kind): $(basename "$f")"
    continue
  fi
  out="$GEN_DIR/$(basename "$f")"
  yq '.spec' "$f" > "$out"
  echo "== promtool check rules $(basename "$f") =="
  if ! promtool check rules "$out"; then
    echo "::error file=${f#"$ROOT"/}::rule file failed promtool check"
    fail=1
  fi
done

for t in "$TESTS_DIR"/*_test.yaml; do
  echo "== promtool test rules $(basename "$t") =="
  if ! promtool test rules "$t"; then
    echo "::error file=${t#"$ROOT"/}::rule unit test failed"
    fail=1
  fi
done

exit "$fail"
