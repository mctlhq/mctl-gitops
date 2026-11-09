#!/usr/bin/env bash
# Read-only listing of Secret annotation METADATA for scripts/check-live-reflector-drift.py.
# Writes nothing to the cluster. Needs KUBECONFIG pointing at the target cluster.
#
# What is and is not protected: only metadata is WRITTEN to the output (the JSONPath below addresses
# .metadata fields only). kubectl itself still fetches the full Secret objects, data included, from the API
# server into this process's memory (kubectl cannot request PartialObjectMetadata for `get -o jsonpath`);
# nothing is logged or stored besides the output rows. Run it only where the operator may read Secrets.
#
# Output: a header "#CLUSTER context=<c> server=<s>" naming the cluster the rows came from (the checker
# refuses a listing whose identity it was not told to expect), then rows
# ns|name|allowed|auto|reflects|auto-reflects|reflected-version|reflected-at, then a trailer "#END rows=N".
# On any kubectl failure the exit code is kubectl's and NO header or trailer is printed (the checker reads
# that as UNKNOWN). All calls are pinned to the one context that was read first.
set -u
ctx=$(kubectl config current-context) || exit $?
srv=$(kubectl --context "$ctx" config view --minify -o 'jsonpath={.clusters[0].cluster.server}') || exit $?
case "$ctx$srv" in
  ""|*[[:space:]]*) echo "collector: empty or whitespace-containing context/server name" >&2; exit 1 ;;
esac
# Spelled in pieces so scripts/validate-reflector-sources.py never sees a literal annotation key in this file.
# kubectl JSONPath: a dot inside a map key must be written \. (dot notation below). Bracket form with unescaped
# dots does NOT address the key and silently returns empty, which a checker would read as "no annotation".
# tests/test_live_reflector_drift.py pins the exact argv and checks the template against the real kubectl.
P='reflector\.v1\.k8s\.'"emberstack"'\.com'
R='reflection-'
out=$(kubectl --context "$ctx" get secret -A -o jsonpath="{range .items[*]}{.metadata.namespace}|{.metadata.name}|{.metadata.annotations.${P}/${R}allowed}|{.metadata.annotations.${P}/${R}auto-enabled}|{.metadata.annotations.${P}/reflects}|{.metadata.annotations.${P}/auto-reflects}|{.metadata.annotations.${P}/reflected-version}|{.metadata.annotations.${P}/reflected-at}{\"\n\"}{end}") || exit $?
printf '#CLUSTER context=%s server=%s\n' "$ctx" "$srv"
printf '%s\n' "$out"
printf '#END rows=%s\n' "$(printf '%s\n' "$out" | grep -c . || true)"
