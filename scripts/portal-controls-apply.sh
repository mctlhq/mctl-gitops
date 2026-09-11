#!/usr/bin/env bash
# Apply infrastructure/cloudflare/portal/mcp-portal-controls.json to the
# Cloudflare MCP portal, or compare the two.
#
#   CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh [--check|--dry-run]
#
# --check compares live against the committed file and exits non-zero on
# drift, printing the fields that differ. It never writes. It exists because
# cloudflare-drift.yml cannot watch this portal: the portal is not an
# OpenTofu root yet (#1092) and CI holds no Cloudflare identity (#1111).
#
# Run it from a checkout: what is applied is the committed blob, never the
# copy on disk. The two are identical by the check just above it, so this
# changes nothing in the ordinary case -- it removes the race between the
# check and the read by construction, which no test here can observe because
# the read happens before any network call. It is written this way because
# the guarantee should not rest on how close together two lines happen to be.
#
# The write sends only the fields this file owns. The endpoint is a PUT but
# behaves as a merge: a field left out keeps its value. Measured against the
# live portal before relying on it -- a PUT omitting `description` left it
# intact, and a PUT omitting `servers` left all three upstream mappings at
# 74/5/30 tools with `default_disabled` untouched.
#
# That is what makes this safe to run beside the allowlist applies in
# mctl-telegram, mctl-api and seerrsense. Sending the body back as read would
# be a read-modify-write over `servers`: an allowlist applied between this
# script's GET and its PUT would be silently reverted, and the API would
# answer 200. Not sending the field cannot lose that race.
#
# Both Code Mode fields are sent, as a pair the shape check has already
# proved consistent. The API refuses only a *disagreeing* pair -- measured:
# `{code_mode:"off", allow_code_mode:true}` answers `7001: code_mode and
# allow_code_mode disagree. Send only code_mode, or a consistent pair.`,
# while the agreeing pair is accepted. Sending both is what makes the write
# converge: on a portal someone left at `opt_in`/`true`, a `code_mode`-only
# write would leave the stored `allow_code_mode` true under the merge
# semantics above, so `--check` would stay red on it and the apply could
# never settle. Stating both values removes the question of whether the API
# recomputes the second one, which is not something this script has measured.
#
# The token never appears on a command line: curl reads it from a config
# handed over a file descriptor, so it is in neither the process table nor
# the shell history.
set -euo pipefail

mode=apply
case "${1:-}" in
  "")          mode=apply ;;
  --dry-run)   mode=dry-run ;;
  --check)     mode=check ;;
  *) echo "usage: $0 [--check|--dry-run]  (unknown argument: $1)" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: $0 [--check|--dry-run]" >&2; exit 2; }

here=$(cd "$(dirname "$0")/.." && pwd)
rel="infrastructure/cloudflare/portal/mcp-portal-controls.json"
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

git -C "$here" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "$here is not a git checkout, so the file cannot be compared against the committed one; run this from a clone" >&2; exit 1; }
# Tracked first, then unchanged. `git diff HEAD -- <path>` compares a path
# HEAD has; it says nothing about one HEAD does not, so a file removed from
# the index and left on disk sails through the comparison below whatever it
# contains.
git -C "$here" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1 \
  || { echo "$rel is not tracked in $here; what is applied must be the committed file" >&2; exit 1; }
# HEAD, not the index: a staged edit is as unreviewed as an unstaged one, and
# the bare `git diff` form compares against the index and would pass it.
if ! git -C "$here" diff --quiet HEAD -- "$rel"; then
  echo "$rel differs from HEAD; commit it (and let it be reviewed) before applying" >&2; exit 1
fi

vetted=$(git -C "$here" show "HEAD:$rel")

# Shape before address: an unknown key is a decision nobody reviewed under a
# name this script does not implement, and a missing one would be applied as
# null. Both are refused rather than guessed at.
known='["portal","hostname","secure_web_gateway","code_mode","allow_code_mode"]'
jq -e --argjson known "$known" '
  (keys_unsorted | sort) == ($known | sort)
  and (.secure_web_gateway | type == "boolean")
  and (.allow_code_mode | type == "boolean")
  and (.code_mode | IN("off", "opt_in", "default_on", "enforced"))
  and (.allow_code_mode == (.code_mode != "off"))
' >/dev/null <<<"$vetted" || {
  echo "$rel does not have the expected shape: exactly $known; secure_web_gateway and allow_code_mode boolean; code_mode one of off|opt_in|default_on|enforced; allow_code_mode must agree with code_mode (the API answers 400 when they disagree)" >&2
  jq -c 'keys_unsorted' <<<"$vetted" >&2 || true
  exit 1
}

portal=$(jq -r .portal <<<"$vetted")
hostname=$(jq -r .hostname <<<"$vetted")
# The file names its own target, and this script writes to a shared surface:
# a file naming another portal would rewrite a mapping this repository does
# not own.
[ "$portal" = mcp ] && [ "$hostname" = mcp.mctl.ai ] \
  || { echo "$rel targets portal=$portal hostname=$hostname; expected mcp/mcp.mctl.ai" >&2; exit 1; }

base="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp"
cf() { curl -sS -K <(printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$CLOUDFLARE_API_TOKEN") "$@"; }
must_succeed() { # $1 = label, stdin = API envelope; prints the envelope on success
  local body; body=$(cat)
  if ! jq -e .success >/dev/null 2>&1 <<<"$body"; then
    echo "$1 failed: $(jq -c '.errors // .' 2>/dev/null <<<"$body" || echo "$body")" >&2; exit 1
  fi
  printf '%s' "$body"
}

current=$(cf "$base/portals/$portal" | must_succeed "read portal")
# The hostname is checked against the live portal too, not only against the
# file: the id is what the API routes on, and an id that has been pointed at
# a different hostname is a portal this file was not written for.
live_host=$(jq -r '.result.hostname' <<<"$current")
[ "$live_host" = "$hostname" ] \
  || { echo "portal '$portal' serves $live_host, but $rel is written for $hostname; refusing" >&2; exit 1; }

# No `//` here: jq's alternative operator substitutes on false as well as
# null, and both switches are committed false. `($live[.] // null) != $want[.]`
# therefore read `null != false` and reported the baseline as drifted against
# itself -- a detector that could only ever go red. A missing key already
# indexes to null, so the plain comparison is both correct and shorter.
drift=$(jq -r --argjson want "$vetted" '
  .result as $live
  | ["secure_web_gateway", "code_mode", "allow_code_mode"]
  | map(select($live[.] != $want[.])
        | "\(.): live=\($live[.] | tojson) committed=\($want[.] | tojson)")
  | .[]' <<<"$current")

if [ "$mode" = check ]; then
  if [ -n "$drift" ]; then
    echo "portal '$portal' has drifted from $rel:" >&2
    echo "$drift" >&2
    exit 1
  fi
  echo "in sync: $(jq -c '{secure_web_gateway, code_mode, allow_code_mode}' <<<"$vetted")"
  exit 0
fi

body=$(jq -c '{secure_web_gateway, code_mode, allow_code_mode}' <<<"$vetted")

if [ "$mode" = dry-run ]; then
  if [ -n "$drift" ]; then echo "would change:"; echo "$drift"; else echo "no change"; fi
  echo "would send:"; jq . <<<"$body"
  exit 0
fi

# The mappings as they were read, by id only. This script does not send the
# field; the check is here because "did not send it" and "they are still
# there" are different statements, and only the second is the guarantee the
# upstream repositories need. Ids, not contents: an allowlist apply landing
# in the same window is legitimate now that this write cannot revert it, and
# holding the tool lists identical across the write would turn that into a
# spurious failure.
servers_before=$(jq -cS '[.result.servers // [] | .[] | .server_id] | sort' <<<"$current")

res=$(cf -X PUT "$base/portals/$portal" --data "$body" | must_succeed "update portal")
# The response must carry the three switches that were sent, and no mapping
# may have gone missing.
# A portal that accepted the call and stored something else would otherwise
# read as a clean apply, which is the whole failure this script exists to
# make impossible.
jq -er --argjson want "$vetted" --argjson before "$servers_before" '.result
  | ([.servers // [] | .[] | .server_id] | sort) as $after
  | select(.secure_web_gateway == $want.secure_web_gateway
           and .code_mode == $want.code_mode
           and .allow_code_mode == $want.allow_code_mode
           and $after == $before)
  | "applied: secure_web_gateway=\(.secure_web_gateway) code_mode=\(.code_mode) allow_code_mode=\(.allow_code_mode) mappings=\($after | join(","))"' <<<"$res" \
  || { echo "update returned success but the portal does not match: either a switch is not the one sent, or a server mapping was lost across the write (those mappings carry the tool allowlists of mctl-telegram, mctl-api and seerrsense -- compare them before touching anything else)" >&2; exit 1; }
