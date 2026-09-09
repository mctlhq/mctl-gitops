# Add self-identification tool (get_my_identity)

## Context

Issue #510 observes that none of the existing self-service MCP tools answer
the basic question "who am I on Telegram?" for the currently authenticated
caller:

- `list_telegram_identities` requires `admin:users` and lists every user,
  not "me" (`internal/mcp/tools.go:1004`).
- `get_my_send_status` returns only send-gate booleans, no identity fields
  (`internal/mcp/tools.go:854`).
- `get_my_audit_log` returns call history with peer values redacted at write
  time by `RedactPeer` (`internal/mcp/tools.go:948`, `internal/db/store.go`
  audit insert path) — never the caller's own identity.
- `list_dialogs` / `get_messages` return the *other* party (the peer), never
  the current user (`internal/mcp/tools.go` dialog/message tools).

Without a direct answer, a connected agent has to guess self-identity via
heuristics (e.g. treating the Saved Messages dialog title as "me"), which is
unreliable and occasionally wrong (a renamed Saved Messages dialog, or an
account with no messages yet). This proposal adds a dedicated, low-risk
read-only tool, `get_my_identity`, that returns the caller's own
`telegram_id`, `username`, and `display_name` directly from data the server
already holds, consistent with the other `get_my_*` self-service
transparency tools that operators cannot disable for an authenticated user.

## User stories

- AS an MCP client (agent or human operator) I WANT a single tool call that
  returns my own Telegram identity (id, username, display name) SO THAT I
  can answer "who am I?" without inferring it from dialog titles or message
  authorship heuristics.
- AS a platform operator I WANT this tool scoped strictly to the caller's
  own identity (no admin scope, no other users' data) SO THAT it is safe to
  leave permanently enabled, the same way `get_my_send_status` and
  `get_my_audit_log` are.
- AS a developer integrating a new client SO THAT I can distinguish "I am
  authenticated but never connected an MTProto session" from "I am fully
  connected" WANT the tool to say which mode I am in, since `username` /
  `display_name` may be genuinely unavailable in the former case.

## Acceptance criteria (EARS)

- WHEN an authenticated caller with any valid credential invokes
  `get_my_identity` THE SYSTEM SHALL return `telegram_id` sourced from the
  caller's verified identity (`auth.Identity.TelegramID`, populated by every
  `auth.Provider` — shared-hmac, local-jwt, local-dev — from the token that
  authenticated the request).
- WHEN the caller holds an active, connected MTProto session (the same
  session `get_my_send_status`'s `connected` field and `GetActiveAccount`
  report) THE SYSTEM SHALL return `username` and `display_name` sourced from
  that session's `telegram_accounts` row, i.e. the values captured from
  Telegram itself at connect time by `telegram.Login` / `telegram.LoginQR`.
- IF the caller has no active MTProto session (never connected, or the
  session was revoked/expired) THEN THE SYSTEM SHALL still return
  `telegram_id` and a best-effort `username` (falling back to
  `auth.Identity.TelegramUsername`, populated from the Login Widget /
  OIDC claim at sign-in) AND SHALL report `connected=false` rather than
  fabricating a `display_name` for an account it cannot currently see.
- WHEN there is no authenticated identity on the request context THE SYSTEM
  SHALL return an error result ("authentication required"), matching every
  other self-service tool's unauthenticated-call behavior.
- WHILE reading the active account row fails for an infrastructure reason
  (store unavailable) THE SYSTEM SHALL still return the identity-level
  fields it already has (`telegram_id`, and `username` from the auth
  identity) rather than failing the whole call outright, mirroring
  `get_my_send_status`'s "answer what you can, never manufacture a false
  negative" pattern.
- IF an operator inspects the tool's annotations THEN THE SYSTEM SHALL
  advertise it as `readOnly=true`, `destructive=false`, `openWorld=false`,
  with an `outputSchema`, consistent with every other tool in
  `internal/mcp/output_schema_test.go` and `internal/mcp/annotations_test.go`.
- THE SYSTEM SHALL NOT require any scope beyond ordinary authentication
  (no `admin:users`, no `telegram:messages:send`) — this is a self-service
  transparency tool operators cannot disable for an authenticated user, the
  same posture as `get_my_send_status` and `get_my_audit_log`.

## Out of scope

- Returning any other user's identity (that remains `list_telegram_identities`,
  admin-only).
- Returning phone number, bio, profile photo, or other MTProto user-profile
  fields not named in the issue — the issue's example payload is exactly
  `telegram_id` / `username` / `display_name`.
- Changing `get_my_send_status`, `get_my_audit_log`, or `AccountInfo`'s
  existing PII-hiding contract (`internal/db/store.go` comment: "PII like
  telegram_user_id stays hidden" is deliberate for the `GET /api/account`
  HTTP response; this proposal adds a new MCP-only read path, it does not
  loosen that HTTP-facing struct).
- Auditing the call. The two existing `get_my_*` tools take different
  stances (`get_my_audit_log` explicitly skips self-audit to avoid a
  recursive audit-of-audit row; `get_my_send_status` also does not audit).
  This proposal follows that precedent and does not add an audit row for
  `get_my_identity` either — see Open questions.
- Local Bridge (`internal/bridge/`) specific wiring beyond whatever the
  generic self-service tool path already provides.

## Open questions

- Should `get_my_identity` write an audit row? `get_my_audit_log` and
  `get_my_send_status` (the two closest precedents) both skip it. This
  proposal follows that precedent (no audit row) since a pure identity
  lookup carries no security-relevant state change and the existing
  precedent already favors omission for this class of self-transparency
  tool. If reviewers disagree, add `s.audit(ctx, id, "get_my_identity", "",
  err, startedAt)` following the `list_telegram_identities` pattern — this
  is a one-line change, not a design fork.
- Should `username`/`display_name` prefer the MTProto-captured
  `telegram_accounts` row (freshest at connect time, may go stale if the
  user later renames themselves on Telegram) or force a live
  `users.GetFullUser`/self round-trip to Telegram on every call? This
  proposal chooses the stored row (no live API call) for the same reason
  `get_my_send_status` reads its account row once: predictable latency, no
  new outbound Telegram RPC on a pure status/identity check, and it is the
  same data other tools already trust. Fully live self-lookup is recorded
  as a possible future enhancement, not required by the issue.
- What should `username` fall back to when there is no active session at
  all (never connected) and no OIDC username claim either (e.g. a
  local-dev identity)? This proposal returns an empty/omitted `username` in
  that case rather than erroring, consistent with `omitempty` handling
  elsewhere in this package (`db.AccountInfo`, `db.IdentityRow`).
