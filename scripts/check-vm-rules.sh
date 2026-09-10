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
# Overridable so --selftest below can point the real code path at a fixture
# directory. Nothing else sets these.
RULES_DIR="${RULES_DIR:-$ROOT/platform-gitops/infra-components/observability/vm-rules}"
TESTS_DIR="${TESTS_DIR:-$RULES_DIR/tests}"
GEN_DIR="$TESTS_DIR/generated"

# --selftest: prove the kind guard below actually rejects something, then exit.
#
# It exists because a VMPodScrape sat unnoticed in vm-rules/ for three months,
# scraping the pushgateway a second time and doubling every alert over a pushed
# metric (#1159). A guard that has never been seen to fail is not known to
# work — the same reason every other detector in validate-manifests.yml runs
# --selftest before its real pass.
#
# This re-runs THIS script against a throwaway RULES_DIR rather than
# reimplementing the check, so it tests the guard rather than a copy of it. The
# accept case asserts only on the absence of the annotation, not on the exit
# code: a minimal VMRule fixture has no real rule groups, so promtool further
# down is entitled to reject it, and that is not what is under test.
if [ "${1:-}" = "--selftest" ]; then
  st_dir=$(mktemp -d)
  trap 'rm -rf "$st_dir"' EXIT
  mkdir -p "$st_dir/tests"
  st_fail=0

  printf 'apiVersion: operator.victoriametrics.com/v1beta1\nkind: VMPodScrape\nmetadata:\n  name: selftest\n' \
    >"$st_dir/fixture.yaml"
  st_out=$(RULES_DIR="$st_dir" TESTS_DIR="$st_dir/tests" "$0" 2>&1) && st_rc=0 || st_rc=$?
  if [ "${st_rc:-0}" -eq 0 ]; then
    echo "self-test FAILED: a VMPodScrape under vm-rules/ exited 0" >&2
    st_fail=1
  fi
  case "$st_out" in
    *"non-VMRule object (kind=VMPodScrape)"*) ;;
    *) echo "self-test FAILED: no ::error annotation naming the kind. Got:" >&2
       echo "$st_out" >&2
       st_fail=1 ;;
  esac

  printf 'apiVersion: operator.victoriametrics.com/v1beta1\nkind: VMRule\nmetadata:\n  name: selftest\nspec:\n  groups: []\n' \
    >"$st_dir/fixture.yaml"
  st_out=$(RULES_DIR="$st_dir" TESTS_DIR="$st_dir/tests" "$0" 2>&1) || true
  case "$st_out" in
    *"non-VMRule object"*)
       echo "self-test FAILED: a VMRule was rejected by the kind guard. Got:" >&2
       echo "$st_out" >&2
       st_fail=1 ;;
  esac

  [ "$st_fail" -eq 0 ] && echo "check-vm-rules.sh self-test: kind guard rejects non-VMRule, accepts VMRule"
  exit "$st_fail"
fi

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
    echo "::error file=${f#"$ROOT"/}::non-VMRule object (kind=$kind) found under vm-rules/; move it to infra-components/observability/<component>/ instead"
    fail=1
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
