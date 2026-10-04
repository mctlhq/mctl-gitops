#!/usr/bin/env bash
# Refuse a k3s-preview plan that would do more than a routine apply (#1534).
#
#   k3s-plan-guard.sh plan.json
#
# Inputs (environment): ALLOW_DESTROY, ALLOW_REPROVISION ("true" to permit).
#
# Two classes, checked separately because they fail differently:
#
#   destroy     -- any delete (destroy or replace) of a resource that is not
#                  terraform_data or a local file: servers, network, load
#                  balancer, firewall, the Hetzner SSH key. Needs ALLOW_DESTROY.
#
#   reprovision -- a replacement of terraform_data. In kube-hetzner these carry
#                  the SSH provisioners: control_plane_config and agent_config
#                  rewrite /etc/rancher/k3s/config.yaml and restart k3s (on
#                  the SINGLE control plane, for the former), registries,
#                  kubelet_config and friends restart it too. The previous
#                  guard counted every terraform_data as bookkeeping, so it
#                  would have let exactly the dangerous replace through.
#                  Needs ALLOW_REPROVISION.
#
# Routine, always allowed: local_file / local_sensitive_file (a fresh runner
# re-creates the kubeconfig and kustomization backup on every run) and the
# kustomization resources, which re-apply manifests that are reviewed in Git
# (extra-manifests, the Cloudflare origin allowlist).
#
# Fail closed: an unreadable plan is a refusal, not an empty list.
set -euo pipefail

plan=${1:?usage: k3s-plan-guard.sh plan.json}

# A plan JSON always carries format_version; resource_changes is absent only
# when nothing changes. Anything else is not a plan we can judge.
if ! jq -e '(.format_version | type == "string") and ((.resource_changes // []) | type == "array")' "$plan" > /dev/null 2>&1; then
  echo "::error::cannot read $plan as an OpenTofu plan; refusing"
  exit 1
fi

routine='^(local_file|local_sensitive_file)$'
routine_data='^terraform_data\.(kustomization|kustomization_user|kustomization_user_deploy)$'

destroy=$(jq -r --arg routine "$routine" '
  [ .resource_changes[]?
    | select(.change.actions | index("delete"))
    | select(.type == "terraform_data" | not)
    | select(.type | test($routine) | not)
    | "\(.address) (\(.change.actions | join(",")))" ] | .[]' "$plan")

reprovision=$(jq -r --arg routine "$routine_data" '
  [ .resource_changes[]?
    | select(.change.actions | index("delete"))
    | select(.type == "terraform_data")
    | select("\(.type).\(.name)" | test($routine) | not)
    | "\(.address) (\(.change.actions | join(",")))" ] | .[]' "$plan")

fail=0
if [ -n "$destroy" ]; then
  echo "::error::this plan destroys or replaces real infrastructure:"
  printf '%s\n' "$destroy" | sed 's/^/  /'
  if [ "${ALLOW_DESTROY:-false}" = "true" ]; then
    echo "::warning::allow_destroy was set; continuing"
  else
    echo "::error::re-dispatch with allow_destroy: true only if every address above is meant to go"
    fail=1
  fi
fi
if [ -n "$reprovision" ]; then
  echo "::error::this plan re-runs node provisioners (k3s config rewrite / restart):"
  printf '%s\n' "$reprovision" | sed 's/^/  /'
  if [ "${ALLOW_REPROVISION:-false}" = "true" ]; then
    echo "::warning::allow_reprovision was set; continuing"
  else
    echo "::error::re-dispatch with allow_reprovision: true only if restarting k3s on those nodes is intended"
    fail=1
  fi
fi
[ "$fail" = 0 ] && echo "guard: no destroy, no reprovision"
exit "$fail"
