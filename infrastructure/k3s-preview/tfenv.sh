#!/usr/bin/env bash
# Export the Terraform variables for this root from the macOS Keychain.
#
# Source it, do not run it:
#
#   source ./tfenv.sh && terraform plan
#
# Replaces terraform.tfvars, which held the same values in plaintext on disk.
# CI never used that file -- .github/workflows/terraform.yml passes the same
# values as TF_VAR_* from GitHub Actions secrets -- so this makes a local run
# and a CI run read their credentials the same way, from different stores.
#
# Keychain items (service/account), created with `security add-generic-password`:
#
#   mctl-hcloud-token/api-token              -> TF_VAR_hcloud_token
#   mctl-r2-etcd-snapshots/access-key-id     -> TF_VAR_etcd_s3_access_key
#   mctl-r2-etcd-snapshots/secret-access-key -> TF_VAR_etcd_s3_secret_key
#
# The R2 pair is the same credential the etcd snapshot job uses; it already
# lived in the Keychain before this script existed, and terraform.tfvars was
# a second copy of it.
#
# The first read of each item may raise a Keychain prompt. Grant "Always
# Allow" if you would rather not see it on every plan.
#
# Not exported here: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for the R2 state
# backend. Those are a DIFFERENT credential (bucket mctl-terraform-state,
# Keychain service mctl-terraform-state-local) and `terraform init` needs them
# before any variable is read. Export them yourself, or add them here if you
# get tired of doing so.

_mctl_kc() {
  local service="$1" account="$2" value
  if ! value=$(security find-generic-password -s "$service" -a "$account" -w 2>/dev/null); then
    echo "tfenv.sh: missing Keychain item ${service}/${account}" >&2
    echo "tfenv.sh: add it with: security add-generic-password -U -s ${service} -a ${account} -w" >&2
    return 1
  fi
  if [ -z "$value" ]; then
    echo "tfenv.sh: Keychain item ${service}/${account} is empty" >&2
    return 1
  fi
  printf '%s' "$value"
}

# Collect every failure before giving up, so a fresh machine is told about all
# three missing items at once rather than one per run. The cleanup below then
# runs on the failure path too -- an early `return` would leave _mctl_kc defined
# in the caller's shell.
_mctl_rc=0
TF_VAR_hcloud_token=$(_mctl_kc mctl-hcloud-token api-token) || _mctl_rc=1
TF_VAR_etcd_s3_access_key=$(_mctl_kc mctl-r2-etcd-snapshots access-key-id) || _mctl_rc=1
TF_VAR_etcd_s3_secret_key=$(_mctl_kc mctl-r2-etcd-snapshots secret-access-key) || _mctl_rc=1
unset -f _mctl_kc

if [ "$_mctl_rc" -ne 0 ]; then
  unset _mctl_rc TF_VAR_hcloud_token TF_VAR_etcd_s3_access_key TF_VAR_etcd_s3_secret_key
  # `return` when sourced, `exit` when run directly.
  return 1 2>/dev/null || exit 1
fi
unset _mctl_rc

export TF_VAR_hcloud_token TF_VAR_etcd_s3_access_key TF_VAR_etcd_s3_secret_key

echo "tfenv.sh: exported TF_VAR_hcloud_token, TF_VAR_etcd_s3_access_key, TF_VAR_etcd_s3_secret_key"
