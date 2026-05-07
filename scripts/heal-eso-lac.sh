#!/usr/bin/env bash
# heal-eso-lac.sh — strip stale kubectl.kubernetes.io/last-applied-configuration
# annotations from ExternalSecret objects whose annotation embeds both
# `apiVersion=external-secrets.io/v1` and a stale `metadata.resourceVersion`.
#
# Background: after an ESO chart 0.10.x → 2.x → 0.10.x roundtrip the legacy
# last-applied-configuration annotation can outlive its referenced apiVersion,
# making ArgoCD's 3-way merge compute a null-RV patch that the apiserver
# rejects with `Invalid value: 0x0: must be specified for an update`.
# Stripping the annotation is non-destructive: ArgoCD's next sync writes a
# fresh annotation with the current apiVersion and no embedded RV.
#
# Default mode is dry-run. Pass --apply to actually mutate.
# Idempotent: re-running on a clean cluster prints summary with 0 stripped.

set -euo pipefail

: "${KUBECONFIG:?set KUBECONFIG before running (e.g. mctl-preprod kubeconfig)}"

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --dry-run) APPLY=0 ;;
    -h|--help)
      sed -n '2,15p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

FIELD_MGR="storage-cleanup"
LAC_KEY="kubectl.kubernetes.io/last-applied-configuration"

echo "KUBECONFIG: $KUBECONFIG"
if [[ "$APPLY" == "1" ]]; then
  echo "Mode: APPLY (will strip annotations)"
else
  echo "Mode: DRY-RUN (use --apply to mutate)"
fi
echo

scanned=0
candidate=0
stripped=0
already=0
errored=0

while IFS=$'\t' read -r ns name has_v1 has_rv; do
  scanned=$((scanned+1))
  if [[ "$has_v1" != "true" || "$has_rv" != "true" ]]; then
    continue
  fi
  candidate=$((candidate+1))
  printf '  %s/%s\n' "$ns" "$name"

  if [[ "$APPLY" == "1" ]]; then
    if kubectl -n "$ns" annotate externalsecret "$name" \
        "${LAC_KEY}-" --overwrite \
        --field-manager="$FIELD_MGR" >/dev/null; then
      stripped=$((stripped+1))
    else
      errored=$((errored+1))
    fi
  fi
done < <(
  kubectl get externalsecrets.external-secrets.io -A -o json | jq -r '
    .items[]
    | . as $o
    | ($o.metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"] // "") as $lac
    | if $lac == "" then
        empty
      else
        ($lac | fromjson? // {}) as $j
        | [
            $o.metadata.namespace,
            $o.metadata.name,
            (($j.apiVersion // "") == "external-secrets.io/v1"),
            ($j.metadata.resourceVersion != null)
          ] | @tsv
      end
  '
)

# Healthy ESs (no LAC at all OR LAC without v1+RV) are counted as already-clean
already=$((scanned - candidate))

echo
echo "Summary:"
echo "  scanned:       $scanned"
echo "  candidates:    $candidate (v1 + RV in last-applied-configuration)"
if [[ "$APPLY" == "1" ]]; then
  echo "  stripped:      $stripped"
  echo "  errored:       $errored"
else
  echo "  would-strip:   $candidate (re-run with --apply)"
fi
echo "  already-clean: $already"
echo

if [[ "$APPLY" == "1" && "$errored" != "0" ]]; then
  exit 1
fi
