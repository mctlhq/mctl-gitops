# shellcheck shell=bash
# Shared by the portal-resnapshot steps. Sourced, never executed.
#
# Two things here are load-bearing, both measured rather than assumed:
#
#   `ok` — `--fail-with-body` catches HTTP errors, and this API answers 200
#   with `success: false`, and has been measured answering 200 while silently
#   keeping a field it was told to change. The ENVELOPE is the truth, and after
#   every write the server is read back rather than trusted to have changed.
#
#   the token on a file descriptor — a command line is world-readable in
#   /proc. The runner is single-tenant, but this file is also what an operator
#   copies when running the procedure by hand, and the habit is the point.

# shellcheck disable=SC2120  # called with no args on read paths, with -X PUT on writes
cf() {
  curl -sS --fail-with-body \
    -K <(printf 'header = "Authorization: Bearer %s"\n' "$CF_TOKEN") \
    "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/access/ai-controls/mcp/servers/${SERVER}" "$@"
}

ok() { jq -e '.success' >/dev/null; }

# The server id is an input, so it is shape-checked before it reaches a URL.
# `workflow_dispatch` type:choice constrains the UI, not the API: a dispatch
# through `gh api` can send anything.
assert_server_id() {
  case "$SERVER" in
    api|tg|seerrsense) ;;
    *) echo "::error::unknown portal server: ${SERVER}"; exit 1 ;;
  esac
}
