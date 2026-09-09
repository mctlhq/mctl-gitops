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
# All three are REQUIRED, including the etcd pair. kube.tf reads it as
# optional -- `etcd_s3_backup = var.etcd_s3_access_key == "" ? {} : {...}` --
# which is true for a cluster that never had snapshots. This one has them, so
# an empty value is not "snapshots stay off", it is "turn snapshots off":
# measured, a plan with the pair blank proposes replacing
# module.kube-hetzner.terraform_data.control_plane_config, which rewrites the
# k3s configuration on the single control-plane node. Failing loudly here is
# the safer behaviour, and is deliberate.
#
# The first read of each item may raise a Keychain prompt. Grant "Always
# Allow" if you would rather not see it on every plan.
#
# Not exported here: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for the R2 state
# backend. Those are a DIFFERENT credential (bucket mctl-terraform-state,
# Keychain service mctl-terraform-state-local) and `terraform init` needs them
# before any variable is read. Export them yourself, or add them here if you
# get tired of doing so.

# Executed rather than sourced, the exports land in a subshell and vanish, but
# the success message below would still print -- so refuse instead of lying.
# Sourced, this file runs in whatever interactive shell the reader has, which
# on this machine is zsh, so nothing below may rely on bash-only behaviour.
_mctl_sourced=0
[ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]:-}" != "$0" ] && _mctl_sourced=1
case "${ZSH_EVAL_CONTEXT:-}" in *:file*) _mctl_sourced=1 ;; esac
if [ "$_mctl_sourced" -ne 1 ]; then
  unset _mctl_sourced
  echo "tfenv.sh: source this file, do not run it:  source ./tfenv.sh" >&2
  exit 1
fi
unset _mctl_sourced

# A leftover tfvars file silently wins over everything below. Terraform ranks
# environment variables LOWEST among variable sources, under terraform.tfvars
# and *.auto.tfvars -- measured, not assumed: with `probe = "FROM_TFVARS_FILE"`
# on disk and TF_VAR_probe=FROM_ENV_VAR exported, the output is
# FROM_TFVARS_FILE, and it becomes FROM_ENV_VAR only once the file is deleted.
# So a stale terraform.tfvars from before the Keychain move -- the exact file
# this replaced -- would quietly keep supplying its plaintext values with no
# error and no warning, and this script's success message would be a lie.
# `find` rather than a glob: an unmatched glob expands to itself in bash but is
# a fatal error in zsh (nomatch), and this file is sourced into the reader's
# shell. Checked against the current directory, because that is where Terraform
# looks for tfvars -- the documented usage is `cd` here first.
_mctl_stray=$(find . -maxdepth 1 \
  \( -name 'terraform.tfvars' -o -name '*.auto.tfvars' -o -name '*.auto.tfvars.json' \) \
  2>/dev/null | head -1)
if [ -n "$_mctl_stray" ]; then
  echo "tfenv.sh: $_mctl_stray exists and OVERRIDES these exports -- Terraform ranks" >&2
  echo "tfenv.sh: environment variables below tfvars files. Move its values into" >&2
  echo "tfenv.sh: the Keychain and delete it; see README.md." >&2
  unset _mctl_stray
  return 1 2>/dev/null || exit 1
fi
unset _mctl_stray

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
