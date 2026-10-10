#!/usr/bin/env bash
# Fail if a metric dropped by the kubeApiServer scrape in monitoring.yaml is
# referenced by a repo VMRule or Grafana dashboard (it would silently go empty).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MON="${MON:-$ROOT/platform-gitops/bootstrap/templates/observability/monitoring.yaml}"
OBS="${OBS:-$ROOT/platform-gitops/infra-components/observability}"

if [ "${1:-}" = "--selftest" ]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/vm-rules" "$tmp/grafana-dashboards"
  cat > "$tmp/mon.yaml" <<'F'
                        action: drop
                        regex: "foo_bucket|bar_bucket"
F
  echo 'expr: rate(bar_bucket[5m])' > "$tmp/vm-rules/x.yaml"
  if MON="$tmp/mon.yaml" OBS="$tmp" "$0" >/dev/null 2>&1; then
    echo "selftest FAILED: fixture referencing a dropped metric was accepted" >&2; exit 1
  fi
  echo 'expr: rate(baz_bucket[5m])' > "$tmp/vm-rules/x.yaml"
  MON="$tmp/mon.yaml" OBS="$tmp" "$0" >/dev/null
  echo "selftest ok"; exit 0
fi

# Drop regex line: the one following `action: drop` / preceding it, in a block.
names="$(grep -E '^\s*regex: "[a-z0-9_|]+_bucket[a-z0-9_|]*"' "$MON" | sed -E 's/.*regex: "([^"]+)".*/\1/' | tr '|' '\n' | sort -u)"
[ -n "$names" ] || { echo "no dropped metric names found in $MON" >&2; exit 1; }

rc=0
for n in $names; do
  if grep -rlw --include='*.yaml' -e "$n" "$OBS/vm-rules" "$OBS/grafana-dashboards" 2>/dev/null; then
    echo "::error::dropped metric $n is referenced above" >&2; rc=1
  fi
done
exit $rc
