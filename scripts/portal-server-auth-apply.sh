#!/usr/bin/env bash
# Apply infrastructure/cloudflare/portal/mcp-portal-server-auth.json to the
# upstream servers of the Cloudflare MCP portal, or compare the two.
#
#   CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-server-auth-apply.sh [--check|--dry-run]
#
# What this file owns is the OAuth *scope* each upstream is asked for, plus
# the endpoints and client registration that scope travels with. Nothing
# else on the server object belongs to it.
#
# Why it exists. The scope is not a field of the MCP Server API: it lives
# inside `auth_credentials`, a write-only blob, surfaced back only as the
# read-only `auth_config_summary` projection. It was set by hand at creation
# (2026-09-10) to `telegram:dialogs:read telegram:messages:read`, and a
# too-narrow value there is invisible at every other layer: the portal's
# tools are all enabled, the identity holds the tier, the per-account send
# consent is on, and a send still comes back as a dry-run preview because
# mctl-telegram's narrowGrant drops what the client did not ask for
# (mctl-telegram internal/oauth/scopes.go). A hand-set value nobody records
# is exactly the drift this repository exists to remove.
#
# Measured before this script relied on any of it, against the live `tg`
# server on 2026-09-12:
#
#   * The endpoint is a PUT that merges: a field the body leaves out keeps
#     its stored value. A write naming only `description` left
#     `auth_credentials` (scope, endpoints, registration_info), `tools` (30)
#     and `has_client_secret` (v1) intact. The first attempt sent the
#     description it already had and proved nothing -- the API can answer 200
#     to a no-op -- so it was repeated with a value that actually changed and
#     then restored.
#   * `modified_at` did NOT move across that real write. It stays at creation
#     time, so it is not a change signal; drift is decided by comparing
#     fields, never timestamps.
#
# That merge is what lets the write send `auth_credentials` alone:
#
#   * `client_secret` is a separate top-level write-only field, not part of
#     the blob, so rewriting the blob does not have to know the secret. The
#     post-write check asserts `has_client_secret` survived anyway -- "did
#     not send it" and "it is still there" are different statements.
#   * `updated_tools` / `updated_prompts` are writable here and carry the
#     capability overrides owned by mctl-telegram, mctl-api and seerrsense.
#     Naming them would make every apply a read-modify-write over their
#     state: an allowlist applied between this script's read and its write
#     would be silently reverted, and the API would answer 200. A field that
#     is never sent cannot lose that race. The read does not echo them back
#     at all, which is the other reason not to try: there is nothing to
#     round-trip. What the read does carry is `tools`, the synced capability
#     catalogue -- no enabled flags, those live on the portal object -- and
#     the post-write check watches it one-sidedly: a sync landing in the same
#     window may add a capability, only losing one is a failure.
#
# The shape of `auth_credentials` is mirrored from the projection the API
# returns; it is not published in the OpenAPI schema. So the write is
# verified by reading the projection back and comparing every field, and a
# mismatch is a failure with the pre-write snapshot printed as the restore
# point -- not a warning.
#
# Applying a new scope does not widen a live session. mctl-telegram's
# boundRefreshGrant intersects a refresh with the family's original grant, so
# the upstream must be signed out and re-authorised in the portal before the
# new scope reaches a token.
#
# Run it from a checkout: what is applied is the committed blob, never the
# copy on disk.
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
rel="infrastructure/cloudflare/portal/mcp-portal-server-auth.json"
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

# Shape before address. An unknown key is a decision nobody reviewed under a
# name this script does not implement, and a missing one would be applied as
# null. Both are refused rather than guessed at. The scope is checked as a
# set, not as a string: the API stores it space-separated and the order it
# comes back in is not something this script has measured.
top='["portal","servers"]'
srv='["server_id","hostname","auth_mode","config","registration_info"]'
cfg='["issuer","authorization_endpoint","token_endpoint","revocation_endpoint"]'
reg='["client_id","redirect_uris","token_endpoint_auth_method","scope"]'
jq -e --argjson top "$top" --argjson srv "$srv" --argjson cfg "$cfg" --argjson reg "$reg" '
  (keys_unsorted | sort) == ($top | sort)
  and (.servers | type == "array") and (.servers | length > 0)
  and ([.servers[].server_id] | (length == (unique | length)))
  and all(.servers[];
        (keys_unsorted | sort) == ($srv | sort)
        and (.server_id | test("^[a-z0-9]+(-[a-z0-9]+)*$"))
        and (.hostname | startswith("https://"))
        and (.auth_mode == "manual")
        and (.config | (keys_unsorted | sort) == ($cfg | sort))
        and all(.config[]; type == "string" and startswith("https://"))
        and (.registration_info | (keys_unsorted | sort) == ($reg | sort))
        and (.registration_info.client_id | type == "string" and length > 0)
        and (.registration_info.redirect_uris | type == "array" and length > 0)
        and all(.registration_info.redirect_uris[]; startswith("https://"))
        and (.registration_info.token_endpoint_auth_method | type == "string" and length > 0)
        and (.registration_info.scope | type == "string")
        and ((.registration_info.scope | split(" ") | map(select(length > 0))) as $s
             | ($s | length) > 0 and ($s | length) == ($s | unique | length)))
' >/dev/null <<<"$vetted" || {
  echo "$rel does not have the expected shape: top-level exactly $top; each server exactly $srv with auth_mode \"manual\", config exactly $cfg (https URLs), registration_info exactly $reg, a non-empty scope with no repeated token, and no repeated server_id" >&2
  jq -c 'keys_unsorted, [.servers[]?.server_id]' <<<"$vetted" >&2 || true
  exit 1
}

portal=$(jq -r .portal <<<"$vetted")
# The file names its own target, and this script writes to a shared surface:
# a file naming another portal would rewrite upstreams this repository does
# not own.
[ "$portal" = mcp ] \
  || { echo "$rel targets portal=$portal; expected mcp" >&2; exit 1; }

base="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/ai-controls/mcp"
cf() { curl -sS -K <(printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$CLOUDFLARE_API_TOKEN") "$@"; }
must_succeed() { # $1 = label, stdin = API envelope; prints the envelope on success
  local body; body=$(cat)
  if ! jq -e .success >/dev/null 2>&1 <<<"$body"; then
    echo "$1 failed: $(jq -c '.errors // .' 2>/dev/null <<<"$body" || echo "$body")" >&2; exit 1
  fi
  printf '%s' "$body"
}

# Compares one server's committed record against the live projection and
# prints one line per differing field. Scope is compared as a set.
drift_for() { # $1 = committed server record, $2 = live envelope
  jq -r --argjson want "$1" '
    .result.auth_config_summary as $s
    | ($want.registration_info.scope | split(" ") | map(select(length > 0)) | sort) as $wscope
    | (($s.registration_info.scope // "") | split(" ") | map(select(length > 0)) | sort) as $lscope
    | [ (if $s.auth_mode != $want.auth_mode
           then "auth_mode: live=\($s.auth_mode | tojson) committed=\($want.auth_mode | tojson)" else empty end),
        (["issuer","authorization_endpoint","token_endpoint","revocation_endpoint"][]
          | select(($s.config[.] // null) != $want.config[.])
          | "config.\(.): live=\(($s.config[.] // null) | tojson) committed=\($want.config[.] | tojson)"),
        (["client_id","token_endpoint_auth_method"][]
          | select(($s.registration_info[.] // null) != $want.registration_info[.])
          | "registration_info.\(.): live=\(($s.registration_info[.] // null) | tojson) committed=\($want.registration_info[.] | tojson)"),
        (if (($s.registration_info.redirect_uris // []) | sort) != ($want.registration_info.redirect_uris | sort)
           then "registration_info.redirect_uris: live=\(($s.registration_info.redirect_uris // []) | tojson) committed=\($want.registration_info.redirect_uris | tojson)" else empty end),
        (if $lscope != $wscope
           then "registration_info.scope: live=\($lscope | join(" ") | tojson) committed=\($wscope | join(" ") | tojson)" else empty end) ]
    | .[]' <<<"$2"
}

rc=0
count=$(jq '.servers | length' <<<"$vetted")
for i in $(seq 0 $((count - 1))); do
  want=$(jq -c ".servers[$i]" <<<"$vetted")
  id=$(jq -r .server_id <<<"$want")
  hostname=$(jq -r .hostname <<<"$want")

  current=$(cf "$base/servers/$id" | must_succeed "read server '$id'")

  # The hostname is checked against the live server too, not only against the
  # file: the id is what the API routes on, and an id that has been pointed
  # at a different upstream is a server this record was not written for.
  live_host=$(jq -r '.result.hostname' <<<"$current")
  [ "$live_host" = "$hostname" ] \
    || { echo "server '$id' points at $live_host, but $rel is written for $hostname; refusing" >&2; exit 1; }
  # auth_type is the mode of the whole server. Rewriting the OAuth blob of a
  # bearer or unauthenticated upstream is not a scope change, it is a
  # different decision, and this file cannot express it.
  live_auth_type=$(jq -r '.result.auth_type' <<<"$current")
  [ "$live_auth_type" = oauth ] \
    || { echo "server '$id' has auth_type=$live_auth_type; this file only pins the OAuth registration of an oauth upstream" >&2; exit 1; }
  # Likewise dcr: a DCR server negotiates its own registration, and writing a
  # manual blob over it would silently convert it.
  live_auth_mode=$(jq -r '.result.auth_config_summary.auth_mode // "unset"' <<<"$current")
  [ "$live_auth_mode" = manual ] \
    || { echo "server '$id' is auth_mode=$live_auth_mode live, but $rel pins a manual registration; converting a DCR upstream is not a scope change and this script will not do it implicitly" >&2; exit 1; }

  drift=$(drift_for "$want" "$current")

  if [ "$mode" = check ]; then
    if [ -n "$drift" ]; then
      echo "server '$id' has drifted from $rel:" >&2
      echo "$drift" >&2
      rc=1
    else
      echo "in sync: $id scope=$(jq -r '.registration_info.scope' <<<"$want")"
    fi
    continue
  fi

  # Only the blob. Not client_secret (a separate field this script must not
  # need to know), not updated_tools/updated_prompts (owned by the upstream
  # repositories), not hostname/name/description.
  creds=$(jq -c '{auth_mode, config, registration_info}' <<<"$want")
  body=$(jq -cn --arg c "$creds" '{auth_credentials: $c}')

  if [ "$mode" = dry-run ]; then
    if [ -n "$drift" ]; then echo "would change $id:"; echo "$drift"; else echo "no change: $id"; fi
    echo "would send for $id:"; jq . <<<"$body"
    continue
  fi

  # The restore point, printed before the write rather than after it fails.
  # The blob is write-only: if this write stores something the projection
  # does not echo back, the previous value is only recoverable from here.
  echo "pre-write auth_config_summary for '$id' (restore point):"
  jq -c '.result.auth_config_summary' <<<"$current"
  secret_before=$(jq -r '.result.auth_config_summary.has_client_secret // false' <<<"$current")
  tools_before=$(jq '[.result.tools // [] | .[]] | length' <<<"$current")

  cf -X PUT "$base/servers/$id" --data "$body" | must_succeed "update server '$id'" >/dev/null

  # Read back rather than trust the response: the field written is write-only
  # and the shape sent is mirrored from the projection, not from a published
  # schema. A server that accepted the call and stored something else would
  # otherwise read as a clean apply, which is the whole failure this check
  # exists to make impossible.
  after=$(cf "$base/servers/$id" | must_succeed "re-read server '$id'")
  left=$(drift_for "$want" "$after")
  secret_after=$(jq -r '.result.auth_config_summary.has_client_secret // false' <<<"$after")
  tools_after=$(jq '[.result.tools // [] | .[]] | length' <<<"$after")

  if [ -n "$left" ]; then
    echo "update of '$id' returned success but the stored registration does not match what was sent:" >&2
    echo "$left" >&2
    echo "restore from the pre-write snapshot printed above before touching anything else" >&2
    exit 1
  fi
  if [ "$secret_before" = true ] && [ "$secret_after" != true ]; then
    echo "update of '$id' dropped the stored client_secret (has_client_secret $secret_before -> $secret_after); the blob is not supposed to carry it, so this write did more than it was asked to -- restore from the pre-write snapshot above" >&2
    exit 1
  fi
  # One-sided, and by count: a tool allowlist apply landing in the same
  # window is legitimate now that this write cannot revert it, so gaining or
  # keeping tools is fine and only losing them is a failure.
  if [ "$tools_after" -lt "$tools_before" ]; then
    echo "update of '$id' lost tools across the write ($tools_before -> $tools_after); those lists are owned by the upstream repositories -- compare them before touching anything else" >&2
    exit 1
  fi

  echo "applied: $id scope=$(jq -r '.result.auth_config_summary.registration_info.scope' <<<"$after") tools=$tools_after client_secret=$secret_after"
  echo "note: a live session keeps its old grant -- sign the upstream out and back in in the portal for the new scope to reach a token"
done

exit $rc
