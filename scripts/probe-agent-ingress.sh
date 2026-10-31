#!/usr/bin/env bash
# Live two-pod ingress probe for agent isolation (mctl-gitops#2289, #2301).
# Operator-run, needs a cluster-admin kubeconfig; not CI. Starts one pod with
# the canonical agent labels and one platform-style workflow pod in
# argo-workflows, runs `nc -z` against every matrix destination, prints
# allow/deny, and deletes both pods.
#
# Usage: scripts/probe-agent-ingress.sh [--image IMAGE]
# Compare the output with the matrix in validate-agent-ingress-isolation.py.
# A deny that should be an allow (or the reverse) means the policy commit is
# not rolled out: revert it.
set -euo pipefail

NS=argo-workflows
IMAGE=${PROBE_IMAGE:-busybox:1.36}
[ "${1:-}" = "--image" ] && IMAGE=$2

# name host port
TARGETS=(
  "vault vault-active.vault.svc 8200"
  "backstage backstage.backstage.svc 7007"
  "mctl-api mctl-api.mctl-api.svc 8080"
  "platform-db shared-pg-rw.platform-db.svc 5432"
  "otel otel-collector.monitoring.svc 4318"
  "proxy agent-egress-proxy.mctl-agents-egress.svc 3128"
)

cleanup() { kubectl -n "$NS" delete pod probe-agent probe-platform --ignore-not-found --wait=false >/dev/null; }
trap cleanup EXIT

run_probe() { # name labels
  local name=$1 labels=$2
  kubectl -n "$NS" run "$name" --image="$IMAGE" --restart=Never --labels="$labels" \
    --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"'"$name"'","image":"'"$IMAGE"'","command":["sleep","300"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}' >/dev/null
  kubectl -n "$NS" wait --for=condition=Ready "pod/$name" --timeout=120s >/dev/null
  for t in "${TARGETS[@]}"; do
    read -r tname host port <<<"$t"
    if kubectl -n "$NS" exec "$name" -- sh -c 'nc -w 3 "$0" "$1" </dev/null' "$host" "$port" >/dev/null 2>&1; then r=allow; else r=deny; fi
    printf '%-15s -> %-12s %s:%s  %s\n' "$name" "$tname" "$host" "$port" "$r"
  done
}

run_probe probe-agent "app.kubernetes.io/name=mctl-agents,mctl.ai/team=admins,workflows.argoproj.io/workflow=probe-agent"
run_probe probe-platform "workflows.argoproj.io/workflow=probe-platform"
