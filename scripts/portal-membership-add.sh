#!/usr/bin/env bash
# Add a server that already exists as a
# cloudflare_zero_trust_access_ai_controls_mcp_server resource (Terraform,
# infrastructure/cloudflare/portal/mcp-servers.tf) as a member of the MCP
# portal, or check whether it already is one.
#
#   CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… \
#     scripts/portal-membership-add.sh <server_id> [--check|--dry-run]
#
# What this closes: infrastructure/cloudflare/portal/README.md documents that
# a server resource (Terraform) and a tool allowlist on an EXISTING member
# (scripts/portal-allowlist-apply.sh, one per owning repository) are both
# covered, but inserting a new server_id into the portal's own `servers[]`
# list never was -- seerrsense's addition was a one-off hand-run recipe in
# that README, and projects' addition on 2026-09-19 was a dashboard click with
# nothing committed at all. This script is that missing, reusable step.
#
# What it does NOT decide: which tools end up enabled. A newly added member
# is written with every tool it advertises set `enabled: false` -- the same
# state a server has immediately after being added through the dashboard --
# and the owning repository's own scripts/portal-allowlist-apply.sh (run
# afterwards, from a checkout of THAT repo) is what turns the committed
# decisions in its docs/portal-allowlist.json into live `enabled: true`
# entries. Splitting it this way keeps one concern per script: this one only
# ever adds a server_id to the mapping, never flips a tool.
#
# --check reports whether <server_id> is already a member and exits
# non-zero if it is not, without writing. --dry-run shows the body this
# script would send and exits before sending it.
#
# The token never appears on a command line: curl reads it from a config
# handed over a file descriptor, so it is in neither the process table nor
# the shell history.
set -euo pipefail

server="${1:-}"
# A server_id can never look like a flag, so ANY leading-dash first argument
# (not just the two known flags -- "--help", a typo, anything) is caught
# here rather than proceeding into apply mode against a bogus server_id.
case "$server" in
  -*|"") echo "usage: $0 <server_id> [--check|--dry-run]  (server_id is required and cannot start with '-')" >&2; exit 2 ;;
esac
mode=apply
case "${2:-}" in
  "")          mode=apply ;;
  --dry-run)   mode=dry-run ;;
  --check)     mode=check ;;
  *) echo "usage: $0 <server_id> [--check|--dry-run]  (unknown argument: $2)" >&2; exit 2 ;;
esac
[ $# -le 2 ] || { echo "usage: $0 <server_id> [--check|--dry-run]" >&2; exit 2; }

here=$(cd "$(dirname "$0")/.." && pwd)
tf_rel="infrastructure/cloudflare/portal/mcp-servers.tf"
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

git -C "$here" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "$here is not a git checkout; run this from a clone" >&2; exit 1; }

base="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp"
cf() { curl -sS -K <(printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$CLOUDFLARE_API_TOKEN") "$@"; }
must_succeed() { # $1 = label, stdin = API envelope; prints the envelope on success
  local body; body=$(cat)
  if ! jq -e .success >/dev/null 2>&1 <<<"$body"; then
    echo "$1 failed: $(jq -c '.errors // .' 2>/dev/null <<<"$body" || echo "$body")" >&2; exit 1
  fi
  printf '%s' "$body"
}
is_member() { jq -e --arg s "$server" '.result.servers // [] | any(.server_id == $s)' <<<"$1" || true; }

portal=mcp
early=$(cf "$base/portals/$portal" | must_succeed "read portal")

if [ "$mode" = check ]; then
  if [ "$(is_member "$early")" = true ]; then
    echo "'$server' is already a member of portal '$portal'"
    exit 0
  fi
  echo "'$server' is NOT a member of portal '$portal'" >&2
  exit 1
fi

if [ "$(is_member "$early")" = true ]; then
  echo "'$server' is already a member of portal '$portal'; nothing to add"
  exit 0
fi

# The server this script is about to WRITE to the portal must already be a
# reviewed, committed Terraform resource -- otherwise it is being invented
# here rather than declared in the one place this repository says a server
# is declared. That is a property of the write, not of asking a question:
# `api` and `seerrsense` are both members of portal `mcp` today with no
# Terraform resource at all, by design (they are DCR servers registered
# out-of-band; see portal-auth-credentials-drift.py's DCR_SERVERS and the
# README), so the --check branch above never reaches this gate.
#
# A literal match, not a regex: $server can contain characters ('.', '*',
# '[') that an ERE would treat as metacharacters and match loosely against a
# resource this is not meant to find.
tf_declared() { git -C "$here" show "HEAD:$tf_rel" 2>/dev/null \
  | grep -qF "resource \"cloudflare_zero_trust_access_ai_controls_mcp_server\" \"$server\""; }
tf_declared \
  || { echo "no cloudflare_zero_trust_access_ai_controls_mcp_server resource named '$server' in $tf_rel@HEAD; add and merge that first" >&2; exit 1; }

# The new server's own capability catalogue -- this is what a manual-OAuth
# server's dashboard login (or a DCR server's automatic sync) has already
# populated on the server resource itself, independent of any portal. Adding
# it to the portal with no tools (or no prompts) listed is not the same as
# "all disabled": an empty updated_tools/updated_prompts is undefined
# behaviour this script has not measured, so every advertised tool and prompt
# gets an explicit, disabled entry instead. A nameless entry is refused
# rather than silently written as {"name": null}, which the portal has not
# been measured to accept or reject.
server_obj=$(cf "$base/servers/$server" | must_succeed "read server $server")
tools=$(jq -c '[.result.tools // [] | .[].name]' <<<"$server_obj")
prompts=$(jq -c '[.result.prompts // [] | .[].name]' <<<"$server_obj")
jq -e 'all(.[]; . != null)' >/dev/null <<<"$tools" \
  || { echo "server '$server' advertises a tool with no name; refusing" >&2; exit 1; }
jq -e 'all(.[]; . != null)' >/dev/null <<<"$prompts" \
  || { echo "server '$server' advertises a prompt with no name; refusing" >&2; exit 1; }
[ "$(jq 'length' <<<"$tools")" -gt 0 ] \
  || { echo "server '$server' has no tools in its catalogue yet (authentication_status is probably 'waiting'); nothing to enable, refusing to add an empty member" >&2; exit 1; }

# Everything from here on must come from ONE read, taken as close to the
# write as this script gets: the donor fields below and the servers[] array
# the write is built from must agree with each other, or a member edited
# between two separate reads (on_behalf flipped by hand, say) would derive
# its donor value from a snapshot older than the one actually being written
# back -- silently reintroducing the "wrong value, no error" failure the
# agreement/type checks below exist to prevent. `early` above is allowed to
# be stale (it only ever gates an early exit); `fresh` is not.
fresh=$(cf "$base/portals/$portal" | must_succeed "read portal")
if [ "$(is_member "$fresh")" = true ]; then
  echo "'$server' is already a member of portal '$portal' (added by something else just now); nothing to add"
  exit 0
fi

# Shape copied from an existing member rather than invented, same rationale
# as the hand-run recipe this replaces: it carries whatever fields this API
# actually stores that are not documented anywhere. But this portal already
# mixes registration styles (tg/projects are Terraform-declared OAuth
# resources, api/seerrsense are DCR added out-of-band), and nothing here has
# measured whether on_behalf/default_disabled vary by registration type --
# so copying whichever entry happens to sort first is only safe once every
# existing member is checked to agree on both fields, AND both fields are
# actually present as booleans (not this API having quietly stopped
# projecting them, which `unique` would otherwise let through as "one
# element" of null/null and this script would then send as explicit nulls --
# exactly the wrong-value-silently case this check exists to prevent).
[ "$(jq '.result.servers // [] | length' <<<"$fresh")" -gt 0 ] \
  || { echo "portal '$portal' has no existing members to copy a shape from; this script assumes at least one" >&2; exit 1; }
donor_values=$(jq -c '[.result.servers // [] | .[] | {on_behalf, default_disabled}] | unique' <<<"$fresh")
[ "$(jq 'length' <<<"$donor_values")" -eq 1 ] \
  || { echo "existing portal members do not agree on on_behalf/default_disabled, so there is no single safe default to copy for a new one: $(jq -c . <<<"$donor_values")" >&2; exit 1; }
jq -e '.[0] | (.on_behalf | type) == "boolean" and (.default_disabled | type) == "boolean"' \
  >/dev/null <<<"$donor_values" \
  || { echo "existing portal members agree, but not on a boolean value, for on_behalf/default_disabled: $(jq -c . <<<"$donor_values"); refusing to copy a non-boolean shape" >&2; exit 1; }
donor=$(jq '.result.servers[0]' <<<"$fresh")
on_behalf=$(jq '.on_behalf' <<<"$donor")
default_disabled=$(jq '.default_disabled' <<<"$donor")

new_entry=$(jq -c -n \
  --arg server_id "$server" \
  --argjson on_behalf "$on_behalf" \
  --argjson default_disabled "$default_disabled" \
  --argjson tools "$tools" \
  --argjson prompts "$prompts" \
  '{server_id: $server_id, on_behalf: $on_behalf, default_disabled: $default_disabled,
    updated_tools: [$tools[] | {name: ., enabled: false}],
    updated_prompts: [$prompts[] | {name: ., enabled: false}]}')

if [ "$mode" = dry-run ]; then
  echo "would add to portal '$portal':"; jq . <<<"$new_entry"
  exit 0
fi

# One last freshness check immediately before the write: everything above
# this line since `fresh` was read is pure local computation (no network
# calls), so this narrows the unavoidable window between a read and the PUT
# to as little as bash allows -- it does not close it, since this API has no
# conditional write.
just_before=$(cf "$base/portals/$portal" | must_succeed "read portal")
[ "$(jq -cS '[.result.servers // [] | .[] | .server_id] | sort' <<<"$just_before")" \
  = "$(jq -cS '[.result.servers // [] | .[] | .server_id] | sort' <<<"$fresh")" ] \
  || { echo "the portal's membership moved while this script was reading; start again" >&2; exit 1; }

body=$(jq -c --argjson new "$new_entry" '{servers: (.result.servers + [$new])}' <<<"$fresh")
echo "adding:"; jq . <<<"$new_entry"

res=$(cf -X PUT "$base/portals/$portal" --data "$body" | must_succeed "update portal")

# id-only would pass a write that reverted somebody else's tool decisions: this
# script, unlike portal-controls-apply.sh, sends the whole `servers` array
# back, so a `tg`/`api`/`seerrsense` allowlist apply landing between this
# script's read and its write is a legitimate concurrent change this script
# must not silently undo -- but if it DID undo one, the id set alone would
# still look clean (the mapping is still there, just reverted). The hand-run
# recipe this replaces diffs decision-for-decision against what was SENT for
# exactly this reason (README: "this API is on record answering 200 while
# keeping a field it was told to change"), and this script already has both
# sides of that comparison in hand.
#
# Scoped to entries OTHER than $server: the new entry legitimately gains
# fields the API computes (id, authentication_status, tools, timestamps) that
# were never in $body, so comparing it here would fail on every successful
# apply, not just a broken one. Its own shape is asserted separately below.
if ! diff -q <(jq -S --arg s "$server" '.servers | map(select(.server_id != $s)) | sort_by(.server_id)' <<<"$body") \
             <(jq -S --arg s "$server" '.result.servers | map(select(.server_id != $s)) | sort_by(.server_id)' <<<"$res") >/dev/null; then
  echo "the portal does not match what was sent: an existing mapping was altered or lost across the write -- those entries carry the tool allowlists of mctl-telegram, mctl-api and seerrsense; compare them before touching anything else" >&2
  diff -u <(jq -S --arg s "$server" '.servers | map(select(.server_id != $s)) | sort_by(.server_id)' <<<"$body") \
          <(jq -S --arg s "$server" '.result.servers | map(select(.server_id != $s)) | sort_by(.server_id)' <<<"$res") >&2 || true
  exit 1
fi

# The new entry's own mapping, checked against what was sent -- id presence
# alone would pass a 200 that stored the new member with, say, every tool
# left off updated_tools entirely (the insert half of the same "200 but not
# what was sent" API behaviour the check above exists for on the other
# half). Compared on exactly the fields this script sets; extra fields the
# API computes on insert (id, authentication_status, tools, timestamps) are
# not part of what was asked for and are not asserted here.
if ! diff -q <(jq -cS '{server_id, on_behalf, default_disabled, updated_tools, updated_prompts}' <<<"$new_entry") \
             <(jq -cS --arg s "$server" '.result.servers[] | select(.server_id == $s) | {server_id, on_behalf, default_disabled, updated_tools, updated_prompts}' <<<"$res") >/dev/null; then
  echo "'$server' was not written as sent -- comparing the requested entry against what the portal now reports for it:" >&2
  diff -u <(jq -cS '{server_id, on_behalf, default_disabled, updated_tools, updated_prompts}' <<<"$new_entry") \
          <(jq -cS --arg s "$server" '.result.servers[] | select(.server_id == $s) | {server_id, on_behalf, default_disabled, updated_tools, updated_prompts}' <<<"$res") >&2 || true
  exit 1
fi

echo "added: server_id=$server mappings=$(jq -r '[.result.servers // [] | .[] | .server_id] | sort | join(",")' <<<"$res")"
echo "next: run scripts/portal-allowlist-apply.sh from a checkout of the repository that owns '$server' to enable its allowed tools (see docs/portal-allowlist.json there)"
