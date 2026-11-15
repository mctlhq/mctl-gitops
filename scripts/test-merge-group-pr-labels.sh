#!/usr/bin/env bash
# Tests for .github/scripts/merge-group-pr-labels.sh (mctlhq/.github#351).
# Builds a throwaway repository shaped like a merge queue commit and stubs the
# gh CLI, then checks that labels are returned only when they are bound to the
# queued commit, and that every failed or mismatched read fails closed.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
script="$root/.github/scripts/merge-group-pr-labels.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

repo="$work/repo"
stub="$work/bin"
mkdir -p "$repo" "$stub"
git -C "$repo" init -q -b main
git -C "$repo" config user.email test@example.invalid
git -C "$repo" config user.name test
g() { git -C "$repo" "$@"; }
g commit -q --allow-empty -m base
base=$(g rev-parse HEAD)
g checkout -q -b pr
g commit -q --allow-empty -m change
pr_head=$(g rev-parse HEAD)
g checkout -q main
g merge -q --no-ff -m queued pr
queued=$(g rev-parse HEAD)
# A second pull request queued behind the first: a group of two.
g checkout -q -b pr2 "$base"
g commit -q --allow-empty -m change2
g checkout -q main
g merge -q --no-ff -m queued2 pr2
group2=$(g rev-parse HEAD)
g checkout -q -b other "$base"
g commit -q --allow-empty -m unrelated
other=$(g rev-parse HEAD)

# gh stub: prints $GH_STUB_BODY, or fails when GH_STUB_FAIL is set.
cat > "$stub/gh" <<'EOF'
#!/usr/bin/env bash
[ -z "${GH_STUB_FAIL:-}" ] || { echo "stub: HTTP 502" >&2; exit 1; }
printf '%s' "$GH_STUB_BODY"
EOF
chmod +x "$stub/gh"

fails=0
run() { # name expect(ok|fail) want_stdout head ref body [gh_fail]
  local name=$1 expect=$2 want=$3 head=$4 ref=$5 body=$6 ghfail=${7:-}
  g checkout -q --detach "$head"
  local out rc=0
  out=$(cd "$repo" && PATH="$stub:$PATH" HEAD_REF="$ref" BASE_SHA="$base" REPO=o/r \
        GH_STUB_BODY="$body" GH_STUB_FAIL="$ghfail" bash "$script" 2>/dev/null) || rc=$?
  if [ "$expect" = ok ] && [ "$rc" -eq 0 ] && [ "$out" = "$want" ]; then echo "ok   $name"; return; fi
  if [ "$expect" = fail ] && [ "$rc" -ne 0 ] && [ -z "$out" ]; then echo "ok   $name"; return; fi
  echo "FAIL $name: rc=$rc out='$out'"; fails=$((fails + 1))
}

ref="refs/heads/gh-readonly-queue/main/pr-7-$pr_head"
good="{\"head\":{\"sha\":\"$pr_head\"},\"labels\":[{\"name\":\"cloudflare-root-removal\"},{\"name\":\"x\"}]}"

run "labels of the queued pull request" ok '["cloudflare-root-removal","x"]' "$queued" "$ref" "$good"
run "no labels" ok '[]' "$queued" "$ref" "{\"head\":{\"sha\":\"$pr_head\"},\"labels\":[]}"
run "group of two prints []" ok '[]' "$group2" "$ref" "$good"
run "API read fails" fail '' "$queued" "$ref" "$good" yes
run "malformed API body" fail '' "$queued" "$ref" "not json"
run "labels field missing" fail '' "$queued" "$ref" "{\"head\":{\"sha\":\"$pr_head\"}}"
run "pull request moved to another head" fail '' "$queued" "$ref" \
    "{\"head\":{\"sha\":\"$other\"},\"labels\":[{\"name\":\"cloudflare-root-removal\"}]}"
run "ref names another pull request head" fail '' "$queued" \
    "refs/heads/gh-readonly-queue/main/pr-7-$other" \
    "{\"head\":{\"sha\":\"$other\"},\"labels\":[{\"name\":\"cloudflare-root-removal\"}]}"
run "head is not a merge commit" fail '' "$other" "refs/heads/gh-readonly-queue/main/pr-7-$other" \
    "{\"head\":{\"sha\":\"$other\"},\"labels\":[]}"
run "ref is not a queue ref" fail '' "$queued" "refs/heads/feature" "$good"
run "branch shaped like a queue ref elsewhere" fail '' "$queued" "refs/heads/someone/pr-7-$pr_head" "$good"
run "ref without a sha" fail '' "$queued" "refs/heads/gh-readonly-queue/main/pr-7" "$good"

[ "$fails" -eq 0 ] || { echo "$fails case(s) failed"; exit 1; }
echo "all merge-group label cases pass"
