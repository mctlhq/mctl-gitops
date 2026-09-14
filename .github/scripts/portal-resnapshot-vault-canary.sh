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

jwt=$(curl -sS -H "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=vault" | jq -r '.value')
[ -n "$jwt" ] && [ "$jwt" != "null" ] || { echo "::error::no OIDC token"; exit 1; }

token=$(curl -sS --fail-with-body -X POST "${VAULT_ADDR}/v1/auth/jwt/login" \
  --json "$(jq -n --arg jwt "$jwt" '{role: "mctl-gitops", jwt: $jwt}')" \
  | jq -r '.auth.client_token')
[ -n "$token" ] && [ "$token" != "null" ] || { echo "::error::Vault JWT login failed"; exit 1; }
echo "::add-mask::${token}"
echo "VAULT_TOKEN=${token}" >> "$GITHUB_ENV"

path="platform/portal-resnapshot/${SERVER}"
canary="canary-$(date -u +%s)"
curl -sS --fail-with-body -H "X-Vault-Token: ${token}" \
  -X POST "${VAULT_ADDR}/v1/secret/data/${path}" \
  --json "$(jq -n --arg c "$canary" '{data: {canary: $c}}')" >/dev/null

read_back=$(curl -sS --fail-with-body -H "X-Vault-Token: ${token}" \
  "${VAULT_ADDR}/v1/secret/data/${path}" | jq -r '.data.data.canary')
[ "$read_back" = "$canary" ] || {
  echo "::error::wrote ${path} and read back something else; refusing to flip"; exit 1; }

echo "VAULT_BACKUP_PATH=${path}" >> "$GITHUB_ENV"
echo "backup path ${path} is writable"
