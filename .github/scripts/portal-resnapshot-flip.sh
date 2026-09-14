#!/usr/bin/env bash
# Steps 0, 0a, 0b, 1, 2 and 2a of the README recipe, in one job.
#
# ONE job on purpose. From step 1 the live server no longer holds the
# registration, so every command between the flip and the read-back that
# confirms the restoration has to run without a job boundary in it — a boundary
# is a place the run can stop with the server in a state nothing records.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id
: "${VAULT_ADDR:?}" ; : "${VAULT_TOKEN:?}" ; : "${VAULT_BACKUP_PATH:?}"

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT

# 0. back up the registration, and refuse to go on without one.
summary=$(cf)
printf '%s' "$summary" | ok
printf '%s' "$summary" | jq -e '.result.auth_config_summary != null' >/dev/null
(umask 077; printf '%s' "$summary" | jq '.result.auth_config_summary' > "$work/summary.json")
test -s "$work/summary.json"

# 0a. and the catalogue, as WHOLE tool objects. Annotations travel in the
#     snapshot and readOnlyHint is a structural claim this platform acts on, so
#     a projection down to names and schemas would call a changed annotation
#     "no change".
printf '%s' "$summary" | jq -e '(.result.tools | type) == "array" and (.result.tools | length) > 0' >/dev/null
printf '%s' "$summary" | jq -S '[.result.tools[]] | sort_by(.name)' > "$work/before.json"

# 0b. build the ENTIRE restoration body now, while the server still works, and
#     put it somewhere that outlives this runner. A shell that dies after step
#     1 otherwise takes the only copy of the registration with it, and for
#     `api` and `seerrsense` nothing else records it.
CREDS=$(jq -ce '{auth_mode, config, registration_info}' "$work/summary.json")
SECRET=$(openssl rand -hex 24); test -n "$SECRET"
(umask 077; CREDS="$CREDS" SECRET="$SECRET" \
  jq -n '{auth_type:"oauth", auth_credentials:env.CREDS, client_secret:env.SECRET}' \
  > "$work/restore.json")
test -s "$work/restore.json"
echo "::add-mask::${SECRET}"

curl -sS --fail-with-body -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -X POST "${VAULT_ADDR}/v1/secret/data/${VAULT_BACKUP_PATH}" \
  --json "$(jq -n --slurpfile r "$work/restore.json" --arg run "${RUN_ID}" \
             '{data: {restore: ($r[0] | tojson), run_id: $run}}')" >/dev/null
# Read back, because a write this one depends on must not be believed on a 2xx.
curl -sS --fail-with-body -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/${VAULT_BACKUP_PATH}" \
  | jq -e '.data.data.restore | fromjson | .auth_credentials != null' >/dev/null
echo "registration backed up to ${VAULT_BACKUP_PATH}"

# 1. flip to bearer, then READ BACK that the registration is really gone.
#    Envelope FIRST: on success:false `.result` is null and
#    `.result.auth_config_summary == null` is then true — a failed read
#    reporting the flip as done.
echo "::warning::${SERVER} is now going offline until someone signs it back in"
cf -X PUT --json '{"auth_type":"bearer","auth_credentials":"resnapshot-not-a-token"}' | ok
gone=$(cf); printf '%s' "$gone" | ok
printf '%s' "$gone" | jq -e '.result.auth_config_summary == null' >/dev/null

# 2. restore, and read back that manual OAuth is in place and the server is
#    waiting for its first authorization.
cf -X PUT --json "@$work/restore.json" | ok
cf | jq -e '.result.status == "waiting" and .result.auth_config_summary.auth_mode == "manual"' >/dev/null

# 2a. and that it is the SAME registration, field for field. status+auth_mode
#     only say a manual-OAuth registration exists; this API is on record
#     answering 200 while keeping a field it was told to change, and for `api`
#     and `seerrsense` nothing declarative would catch a narrowed scope or a
#     moved endpoint later.
rc=0
diff -u <(jq -S '{auth_mode, config, registration_info}' "$work/summary.json") \
        <(cf | jq -S '.result.auth_config_summary | {auth_mode, config, registration_info}') || rc=$?
test "$rc" -eq 0 || { echo "::error::registration changed across the flip; restore from ${VAULT_BACKUP_PATH} by hand"; exit 1; }

echo "restored: waiting for a user sign-in"
