#!/usr/bin/env bash
# Prove the backup path is writable BEFORE anything destructive happens.
#
# A workflow that assumed the policy exists would discover it was wrong
# immediately after the flip — the one moment there is no way back. So this
# writes and reads back a canary, and the run dies here if it cannot.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id

: "${VAULT_ADDR:?}"
: "${ACTIONS_ID_TOKEN_REQUEST_URL:?id-token: write is required}"

# The audience this repository's other workflow already uses. A JWT role binds
# the audience, so an invented one is refused at login — and being refused here
# is cheap only because nothing destructive has run yet.
jwt=$(curl -sS --max-time 30 -H "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=https%3A%2F%2Fgithub.com%2Fmctlhq" \
  | jq -r '.value')
[ -n "$jwt" ] && [ "$jwt" != "null" ] || { echo "::error::no OIDC token"; exit 1; }

# Through STDIN, not argv: a command line is world-readable in /proc, and this
# one would carry the OIDC assertion. The same habit the `cf` helper follows
# for the API token, and the reason it is worth following in a script an
# operator also copies.
# `github-actions`, the role build-image.yaml logs in with. Inventing a role
# name would fail at login for a reason indistinguishable, in the output, from
# a missing policy.
token=$(jq -n --arg jwt "$jwt" '{role: "github-actions", jwt: $jwt}' \
  | curl -sS --fail-with-body --max-time 30 -X POST "${VAULT_ADDR}/v1/auth/jwt/login" \
      -H 'content-type: application/json' --data-binary @- \
  | jq -r '.auth.client_token')
[ -n "$token" ] && [ "$token" != "null" ] || { echo "::error::Vault JWT login failed"; exit 1; }
echo "::add-mask::${token}"
echo "VAULT_TOKEN=${token}" >> "$GITHUB_ENV"

# The backup path, and a SEPARATE path for the canary.
#
# Writing the canary to the backup path would bury a previous run's
# registration: KV v2 versions rather than deletes, so the older value survives
# as a prior version, but `.data.data.restore` on the CURRENT one becomes null
# — and the current one is what a recovery reads. A run that starts while an
# earlier run's restore is still unrecovered would hide exactly the thing the
# backup exists for.
backup_path="platform/portal-resnapshot/${SERVER}"
path="platform/portal-resnapshot/_canary/${SERVER}"
canary="canary-$(date -u +%s)"
jq -n --arg c "$canary" '{data: {canary: $c}}' \
  | curl -sS --fail-with-body --max-time 30 -H "X-Vault-Token: ${token}" \
      -H 'content-type: application/json' \
      -X POST "${VAULT_ADDR}/v1/secret/data/${path}" --data-binary @- >/dev/null

read_back=$(curl -sS --fail-with-body --max-time 30 -H "X-Vault-Token: ${token}" \
  "${VAULT_ADDR}/v1/secret/data/${path}" | jq -r '.data.data.canary')
[ "$read_back" = "$canary" ] || {
  echo "::error::wrote ${path} and read back something else; refusing to flip"; exit 1; }

# The canary proves the MOUNT and the policy prefix are writable; the backup
# goes to its own path under the same prefix, which is what the policy grants.
echo "VAULT_BACKUP_PATH=${backup_path}" >> "$GITHUB_ENV"
echo "vault ${VAULT_ADDR} is writable under platform/portal-resnapshot/; backup will go to ${backup_path}"
