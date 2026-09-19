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
mode=apply
case "${2:-}" in
  "")          mode=apply ;;
  --dry-run)   mode=dry-run ;;
  --check)     mode=check ;;
  *) echo "usage: $0 <server_id> [--check|--dry-run]  (unknown argument: $2)" >&2; exit 2 ;;
esac
[ -n "$server" ] || { echo "usage: $0 <server_id> [--check|--dry-run]" >&2; exit 2; }
[ $# -le 2 ] || { echo "usage: $0 <server_id> [--check|--dry-run]" >&2; exit 2; }

here=$(cd "$(dirname "$0")/.." && pwd)
tf_rel="infrastructure/cloudflare/portal/mcp-servers.tf"
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

git -C "$here" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "$here is not a git checkout; run this from a clone" >&2; exit 1; }

# The server this script is about to add to the portal must already be a
# reviewed, committed Terraform resource -- otherwise it is being invented
# here rather than declared in the one place this repository says a server
# is declared.
git -C "$here" show "HEAD:$tf_rel" 2>/dev/null \
  | grep -qE '^resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "'"$server"'"' \
  || { echo "no cloudflare_zero_trust_access_ai_controls_mcp_server resource named '$server' in $tf_rel@HEAD; add and merge that first" >&2; exit 1; }

base="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp"
cf() { curl -sS -K <(printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$CLOUDFLARE_API_TOKEN") "$@"; }
must_succeed() { # $1 = label, stdin = API envelope; prints the envelope on success
  local body; body=$(cat)
  if ! jq -e .success >/dev/null 2>&1 <<<"$body"; then
    echo "$1 failed: $(jq -c '.errors // .' 2>/dev/null <<<"$body" || echo "$body")" >&2; exit 1
  fi
  printf '%s' "$body"
}

portal=mcp
before=$(cf "$base/portals/$portal" | must_succeed "read portal")
already=$(jq -e --arg s "$server" '.result.servers // [] | any(.server_id == $s)' <<<"$before" || true)

if [ "$mode" = check ]; then
  if [ "$already" = true ]; then
    echo "'$server' is already a member of portal '$portal'"
    exit 0
  fi
  echo "'$server' is NOT a member of portal '$portal'" >&2
  exit 1
fi

if [ "$already" = true ]; then
  echo "'$server' is already a member of portal '$portal'; nothing to add"
  exit 0
fi

# The new server's own capability catalogue -- this is what a manual-OAuth
# server's dashboard login (or a DCR server's automatic sync) has already
# populated on the server resource itself, independent of any portal. Adding
# it to the portal with no tools listed is not the same as "all disabled":
# an empty updated_tools is undefined behaviour this script has not measured,
# so every advertised tool gets an explicit, disabled entry instead.
server_obj=$(cf "$base/servers/$server" | must_succeed "read server $server")
tools=$(jq -c '[.result.tools // [] | .[].name]' <<<"$server_obj")
[ "$(jq 'length' <<<"$tools")" -gt 0 ] \
  || { echo "server '$server' has no tools in its catalogue yet (authentication_status is probably 'waiting'); nothing to enable, refusing to add an empty member" >&2; exit 1; }

# Shape copied from an existing member rather than invented, same rationale
# as the hand-run recipe this replaces: it carries whatever fields this API
# actually stores that are not documented anywhere.
donor=$(jq -e '.result.servers[0]' <<<"$before") \
  || { echo "portal '$portal' has no existing members to copy a shape from; this script assumes at least one" >&2; exit 1; }
on_behalf=$(jq '.on_behalf' <<<"$donor")
default_disabled=$(jq '.default_disabled' <<<"$donor")

new_entry=$(jq -c -n \
  --arg server_id "$server" \
  --argjson on_behalf "$on_behalf" \
  --argjson default_disabled "$default_disabled" \
  --argjson tools "$tools" \
  '{server_id: $server_id, on_behalf: $on_behalf, default_disabled: $default_disabled,
    updated_tools: [$tools[] | {name: ., enabled: false}], updated_prompts: []}')

if [ "$mode" = dry-run ]; then
  echo "would add to portal '$portal':"; jq . <<<"$new_entry"
  exit 0
fi

servers_before=$(jq -cS '[.result.servers // [] | .[] | .server_id] | sort' <<<"$before")

# Re-read immediately before the write, to narrow (not close -- there is no
# conditional write on this API) the window in which an allowlist apply
# landing on an existing member would be silently reverted by sending the
# array back. See infrastructure/cloudflare/portal/README.md's re-snapshot
# recipe for the same reasoning applied to an existing member's tool list.
fresh=$(cf "$base/portals/$portal" | must_succeed "read portal")
[ "$(jq -cS '[.result.servers // [] | .[] | .server_id] | sort' <<<"$fresh")" = "$servers_before" ] \
  || { echo "the portal's membership moved while this script was reading; start again" >&2; exit 1; }

body=$(jq -c --argjson new "$new_entry" '{servers: (.result.servers + [$new])}' <<<"$fresh")
echo "adding:"; jq . <<<"$new_entry"

res=$(cf -X PUT "$base/portals/$portal" --data "$body" | must_succeed "update portal")

jq -er --arg s "$server" --argjson before "$servers_before" '.result
  | ([.servers // [] | .[] | .server_id] | sort) as $after
  | ($before - $after) as $lost
  | select(($after | index($s)) != null and ($lost | length) == 0)
  | "added: server_id=\($s) mappings=\($after | join(","))"' <<<"$res" \
  || { echo "update returned success but the portal does not match: either '$server' is not in the result, or an existing mapping was lost across the write" >&2; exit 1; }

echo "next: run scripts/portal-allowlist-apply.sh from a checkout of the repository that owns '$server' to enable its allowed tools (see docs/portal-allowlist.json there)"
