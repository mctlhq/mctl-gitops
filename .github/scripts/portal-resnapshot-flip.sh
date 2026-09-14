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

work=$(mktemp -d)

# WHETHER A MUTATION HAPPENED, recorded on the way rather than inferred after.
#
# A cancelled run — the operator hitting the button, a runner evicted — takes
# the script mid-procedure, and "the job was cancelled" says nothing about
# which side of the flip it was on. The two need opposite responses: before it,
# nothing was touched; after it, the server has no registration and the Vault
# copy is the only way back. So the marker is written BEFORE the destructive
# PUT and survives into the trap, which reports it on every exit path
# including the signals a cancellation actually arrives as.
flipped=no
on_exit() {
  rc=$?
  if [ "$flipped" = yes ] && [ "$restored" != yes ]; then
    echo "::error::the run ended (rc=${rc}) between the flip and the restore. ${SERVER} has NO registration; restore from Vault at ${VAULT_BACKUP_PATH}."
  elif [ "$flipped" = no ]; then
    echo "nothing was written: the run ended before the flip"
  fi
  rm -rf "$work"
}
restored=no
trap on_exit EXIT
trap 'exit 130' INT TERM HUP

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

# Through STDIN: the restoration body carries the whole registration and a
# live client_secret, and a command line is world-readable in /proc.
jq -n --slurpfile r "$work/restore.json" --arg run "${RUN_ID}" \
  '{data: {restore: ($r[0] | tojson), run_id: $run}}' \
  | curl -sS --fail-with-body -H "X-Vault-Token: ${VAULT_TOKEN}" \
      -H 'content-type: application/json' \
      -X POST "${VAULT_ADDR}/v1/secret/data/${VAULT_BACKUP_PATH}" --data-binary @- >/dev/null
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
flipped=yes
cf -X PUT --json '{"auth_type":"bearer","auth_credentials":"resnapshot-not-a-token"}' | ok
gone=$(cf); printf '%s' "$gone" | ok
printf '%s' "$gone" | jq -e '.result.auth_config_summary == null' >/dev/null

# 2. restore, and read back that manual OAuth is in place and the server is
#    waiting for its first authorization.
cf -X PUT --json "@$work/restore.json" | ok
cf | jq -e '.result.status == "waiting" and .result.auth_config_summary.auth_mode == "manual"' >/dev/null
restored=yes

# 2a. and that it is the SAME registration, field for field. status+auth_mode
#     only say a manual-OAuth registration exists; this API is on record
#     answering 200 while keeping a field it was told to change, and for `api`
#     and `seerrsense` nothing declarative would catch a narrowed scope or a
#     moved endpoint later.
#     Compared by FIELD NAME, never by printing the values. A `diff -u` of the
#     two blobs puts endpoints, client id and scope into the run log — readable
#     by everyone with repository access, and outliving the run. The whole
#     reason the backup goes to Vault rather than an artifact is that this blob
#     must not land somewhere durable and broadly readable, and a log is both.
#
#     A null `auth_config_summary` reports all three as changed rather than
#     comparing as equal-to-nothing, which is the shape a failed read takes.
(umask 077; cf | jq -S '.result.auth_config_summary' > "$work/restored.json")
changed=$(jq -r -n --slurpfile a "$work/summary.json" --slurpfile b "$work/restored.json" '
  ($a[0] | {auth_mode, config, registration_info}) as $before
  | ($b[0] // {}) as $after
  | ["auth_mode", "config", "registration_info"]
  | map(select(($before[.] // null) != ($after[.] // null)))
  | join(", ")')
if [ -n "$changed" ]; then
  echo "::error::registration changed across the flip in: ${changed}. Restore from Vault at ${VAULT_BACKUP_PATH} by hand — the values are deliberately not printed here."
  exit 1
fi

# The catalogue as it was, for `verify` to prove the snapshot actually moved.
# An artifact, unlike the registration: this is tool names, schemas and
# annotations, which already live in each owning repository's
# docs/portal-allowlist.json. The registration does not.
mkdir -p "${RUNNER_TEMP:-/tmp}/portal-resnapshot"
cp "$work/before.json" "${RUNNER_TEMP:-/tmp}/portal-resnapshot/before.json"

# The baseline `verify` waits to move, and it has to be taken HERE.
#
# The bearer flip moves `last_synced` itself — the README records that as the
# sign it worked — so a baseline read before the flip is already stale by the
# time the restore lands, and `verify` comparing against it would find the
# value "moved" the instant the job starts. The only value that moving proves a
# SIGN-IN is the one the server holds after the restoration.
restored_synced=$(cf | jq -r '.result.last_synced // ""')
echo "last_synced_after_restore=${restored_synced}" >> "$GITHUB_OUTPUT"

echo "restored: waiting for a user sign-in (baseline last_synced=${restored_synced:-none})"
