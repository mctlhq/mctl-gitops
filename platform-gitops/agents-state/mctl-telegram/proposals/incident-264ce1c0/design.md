# Design: incident-264ce1c0

## Diagnosis
The `MctlTelegramToolAvailabilitySlowBurn` alert (6x burn rate over 6h) fired
for tenant `labs` / service `mctl-telegram` because a single caller,
`user_id 9980`, repeatedly failed two distinct MCP tool calls across the alert
window: `get_media` failed 11 times with "confirmation not found, expired, or
already used", and `get_messages` failed 4 times with "PEER_ID_INVALID: ...
not in your dialog list". No other user or tool showed errors in the sampled
window, and the synthetic canary (`tg_user_id 924671154`, exercising
`mcp_init`/`list_dialogs`/`get_unread_messages`) reported `ok:true` on every
run — the canary does not exercise `get_media` or `get_messages` against real
per-user dialog/media state, so it stayed green while the real-traffic
tool-availability SLO burned. No skill matched because the incident type is
generic and no diagnostic rule exists yet for this alert.

Both failure modes look like client-side staleness rather than a live server
outage. `get_media`'s "not found, expired, or already used" is the documented
terminal response for a `confirmation_id` that is genuinely expired (10-minute
TTL) or was already consumed by a prior completed download. A related bug —
retries during a slow in-flight download being misreported as "not found" —
was already fixed in mctl-telegram issue #282 / PR #284 (merged
2026-07-15); that fix introduced a distinct "download already in progress"
response for the in-flight case and left "not found, expired, or already
used" as the correct terminal response for a truly stale id. The errors seen
here use that terminal wording, so this is consistent with the caller
retrying with a `confirmation_id` after it expired or was already consumed,
rather than a regression of #282. `get_messages`'s PEER_ID_INVALID similarly
indicates the caller supplied a peer id not present in its current dialog
list, rather than re-fetching via `list_dialogs` first.

## Confidence: LOW
This responder has no mctl-telegram source checkout available (only
mctl-gitops is mounted) and could not read the current `internal/mcp/*.go`
files directly. The diagnosis is built from live log evidence plus the
previously-merged issue-282 proposal text (requirements.md/design.md), not a
fresh code read, so exact line numbers below are inferred, not confirmed.
The identity of the client integration behind `user_id 9980` is unknown, so
the true trigger (why that client is retrying with a stale id) cannot be
fixed from this side — only the server's observability of the failure can be
improved.

## Proposed Fix
`internal/mcp/confirm.go` / `internal/mcp/media_tools.go` in the mctl-telegram
repo: the `ConfirmStore.Claim`/`Finalize` path added by PR #284 collapses
three distinct causes into one generic `ErrConfirmationNotFound` /
"confirmation not found, expired, or already used" response: (a) the id was
never issued, (b) the id hard-expired via the 10-minute TTL, (c) the id was
already consumed by a completed download. That collapsing is why this
responder — and any operator reading these logs — cannot tell which sub-case
recurred 11 times for `user_id 9980` without this level of manual log
archaeology.

Minimal change: when `ConfirmStore.Finalize(id)` deletes an entry after a
completed download, retain a short-lived tombstone (e.g. 30s, well under the
10-minute TTL) recording that the id was consumed. Add a lookup in `Claim` so
a request against a tombstoned id returns a distinct message, e.g.
"confirmation_id already used — call prepare_get_media again", and have
`toolGetMedia`'s existing `s.audit(...)` call in its error switch log that
outcome distinctly from the "never issued" and "hard-expired" cases. This
makes future occurrences of this alert attributable from logs alone.

No corresponding server-side bug was identified for the `get_messages`
PEER_ID_INVALID errors; they match expected behavior when a caller uses a
stale peer id, and require no server change.

## Scope
Minimal. Only the not-found/expired/already-used branch of
`ConfirmStore`/`toolGetMedia` in mctl-telegram — no other flows
(`send_message`, `pin_message`, `list_dialogs`) are touched.
