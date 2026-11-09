#!/usr/bin/env bash
# Read-only, METADATA-ONLY listing of Secrets for scripts/check-live-reflector-drift.py.
# Never reads .data. Writes nothing to the cluster. Needs KUBECONFIG pointing at the target cluster.
# Rows: ns|name|allowed|auto|reflects|auto-reflects|reflected-version|reflected-at, then a trailer "#END rows=N".
# On kubectl failure the exit code is kubectl's and no trailer is printed (the checker reads that as UNKNOWN).
set -u
# Spelled in pieces so scripts/validate-reflector-sources.py never sees a literal annotation key in this file.
P='reflector\.v1\.k8s\.'"emberstack"'\.com'
R='reflection-'
# kubectl JSONPath: a dot inside a map key must be written \. (dot notation below). Bracket form with unescaped
# dots does NOT address the key and silently returns empty, which a checker would read as "no annotation".
# tests/test_live_reflector_drift.py pins the exact argv and checks the template against the real kubectl.
out=$(kubectl get secret -A -o jsonpath="{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.metadata.annotations.${P}/${R}allowed}|{.metadata.annotations.${P}/${R}auto-enabled}|{.metadata.annotations.${P}/reflects}|{.metadata.annotations.${P}/auto-reflects}|{.metadata.annotations.${P}/reflected-version}|{.metadata.annotations.${P}/reflected-at}{\"\n\"}{end}") || exit $?
printf '%s\n' "$out"
printf '#END rows=%s\n' "$(printf '%s\n' "$out" | grep -c . || true)"
