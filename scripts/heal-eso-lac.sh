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
# Exit: 0 done, 1 an annotate failed, 2 the scan itself could not be read
# (kubectl or jq failed: no summary at all; or an annotation is not JSON:
# the summary counts it as unreadable). A failed scan is never "clean".

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
unreadable=0

# Read the list and parse it as two checked steps, before the loop. The loop
# used to read from `< <(kubectl ... | jq ...)`: a process substitution's exit
# status is invisible to set -e and pipefail, so a kubectl that could not
# reach the cluster (or a jq that could not parse its answer) produced no
# rows, and the script printed "scanned: 0 ... already-clean: 0" and exited
# 0 -- a scan that never happened reported as a clean cluster (gitops bug
# report ch. 2). Capturing only kubectl would still hide a jq failure.
if ! es_json=$(kubectl get externalsecrets.external-secrets.io -A -o json); then
  echo "ERROR: cannot list ExternalSecrets; nothing was scanned" >&2
  exit 2
fi
if [[ -z "$es_json" ]]; then
  # jq reads an empty input as zero documents and exits 0 with no rows.
  echo "ERROR: kubectl returned an empty answer; nothing was scanned" >&2
  exit 2
fi
if ! rows=$(printf '%s' "$es_json" | jq -r '
    if (.items | type) != "array" then error("no .items array") else . end
    | .items[]
    | . as $o
    | ($o.metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"] // "") as $lac
    | (if $lac == "" then {ok: true, j: {}}
       else (try ($lac | fromjson | {ok: true, j: .}) catch {ok: false})
       end) as $p
    | [
        $o.metadata.namespace,
        $o.metadata.name,
        (if $p.ok then (($p.j.apiVersion // "") == "external-secrets.io/v1") else "unknown" end),
        (if $p.ok then ($p.j.metadata.resourceVersion != null) else "unknown" end)
      ] | @tsv
  '); then
  echo "ERROR: cannot parse the ExternalSecret list; nothing was scanned" >&2
  exit 2
fi

while IFS=$'\t' read -r ns name has_v1 has_rv; do
  [[ -z "$ns$name" ]] && continue  # an empty list gives one empty line
  scanned=$((scanned+1))
  if [[ "$has_v1" == "unknown" ]]; then
    # An annotation that is not JSON is neither stale nor clean: it is
    # unread. Counting it as already-clean is what `fromjson? // {}` did.
    unreadable=$((unreadable+1))
    printf '  %s/%s: last-applied-configuration is not JSON, not judged\n' "$ns" "$name" >&2
    continue
  fi
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
done <<< "$rows"

# Healthy ESs (no LAC at all OR LAC without v1+RV) are counted as already-clean
already=$((scanned - candidate - unreadable))

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
echo "  unreadable:    $unreadable (annotation is not JSON; not judged)"
echo

if [[ "$APPLY" == "1" && "$errored" != "0" ]]; then
  exit 1
fi
if [[ "$unreadable" != "0" ]]; then
  exit 2
fi
