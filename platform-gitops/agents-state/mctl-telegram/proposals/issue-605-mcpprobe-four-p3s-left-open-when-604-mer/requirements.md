# Close the four P3 review remnants left open when #604 merged

## Context

Issue #605 records four P3 review findings that were still open when PR #604
(the `internal/mcpprobe` compatibility probe) merged. None blocks the merge
gate and none is a security or correctness defect in production behaviour, but
each is a small gap between what the code claims and what it guarantees:
(1) the `WWW-Authenticate` challenge parser and escaped quoted-strings,
(2) the widened session observation on the modern path having no test,
(3) the redaction comment in `internal/mcpprobe/report.go` claiming an
exhaustive list of server-chosen string fields that is short by three, and
(4) a pre-registered OAuth client's `client_name` never reaching the
refresh-token record in `internal/oauth/server.go`.

Verification against the current clone (HEAD `29470b0`) changes the shape of
the work: finding 1 is **already fixed and pinned**. `splitChallengeParts` and
`unquoteChallengeValue` in `internal/mcpprobe/oauthprobe.go` honour backslash
escapes, and `TestParseChallengeParams_HonoursQuotedStringEscapes` in
`internal/mcpprobe/oauthprobe_test.go` covers the escaped-quote, odd-escape,
escaped-backslash, quoted-comma, bare-token, scheme-only and unterminated-quote
cases (`go test ./internal/mcpprobe/ -run TestParseChallengeParams` passes).
Findings 2, 3 and 4 are still live. This proposal therefore closes 1 by
recorded verification and by adding the one grammar case the existing table
does not carry, and implements 2, 3 and 4. The value is that the probe's two
loudest claims — "the modern path mints no session identifier" and "these are
the only server-chosen strings in the report" — stop being unpinned prose, and
an operator-configured Portal client stops producing a blank display name on a
refresh token.

## User stories

- AS a platform operator reading an `mcpprobe` report I WANT the "no session
  identifier" claim to be pinned by a fixture that would mint one on a later
  response SO THAT the claim describes the whole modern path and not just its
  first response.
- AS a reviewer of `internal/mcpprobe/report.go` I WANT the redaction
  comment's list of server-chosen fields to be complete and mechanically
  enforced SO THAT a newly added string field cannot silently fall outside a
  guarantee the comment states as exhaustive.
- AS an operator who seeded `OAUTH_PREREGISTERED_CLIENTS` (see
  `docs/cloudflare-portal-compat.md`) I WANT the configured `client_name` to
  appear on the refresh-token record SO THAT a token issued to the Portal
  client is attributable rather than blank.
- AS a maintainer triaging #605 I WANT each of the four findings to end in a
  recorded state — fixed, or verified already fixed and pinned — SO THAT the
  review loop that produced them terminates.

## Acceptance criteria (EARS)

Finding 1 — challenge parser (verify and harden)

- WHEN `parseChallengeParams` is given `Bearer realm="mctl \"labs\"",
  resource_metadata="<url>"` THE SYSTEM SHALL return `realm` = `mctl "labs"`
  and `resource_metadata` = `<url>`.
- WHEN `parseChallengeParams` is given a challenge whose quoted value contains
  an escaped comma-adjacent quote in odd number THE SYSTEM SHALL keep the
  parameter boundaries intact and SHALL NOT drop `resource_metadata`.
- WHEN the auth-param list contains a quoted value holding an escaped
  backslash immediately followed by the delimiter THE SYSTEM SHALL resolve the
  escape and terminate the value at the delimiter.
- IF the existing escape-aware implementation is found to already satisfy the
  criteria above THEN THE SYSTEM SHALL keep it unchanged and the proposal
  SHALL add only the missing grammar case (an escaped quote inside
  `resource_metadata`, i.e. the escape appearing in the parameter *after* the
  first quoted value) to
  `TestParseChallengeParams_HonoursQuotedStringEscapes`.

Finding 2 — modern-path session observation

- WHILE a fixture server mints an `Mcp-Session-Id` on the `tools/list`
  response only THE SYSTEM SHALL record `Report.Session.HeaderPresent = true`
  and `Report.Session.IDLength = len(id)`.
- WHILE a fixture server mints an `Mcp-Session-Id` on the `tools/call`
  response only THE SYSTEM SHALL record `Report.Session.HeaderPresent = true`.
- WHEN the `noteSession` call is removed from either `probeToolsList` or
  `probeReadOnlyCall` in `internal/mcpprobe/modern.go` THE SYSTEM SHALL fail at
  least one test.
- WHILE a session identifier is observed on any modern response THE SYSTEM
  SHALL NOT serialize or log the identifier value itself.

Finding 3 — redaction comment enumeration

- WHEN the doc comment on `Report` in `internal/mcpprobe/report.go` enumerates
  the fields carrying server-chosen text THE SYSTEM SHALL name every such
  field: `Server.Name`, `Server.Version`, `Server.SupportedVersions`,
  `Tools[].Name`, `OAuth.AuthorizationServer.Issuer`,
  `OAuth.AuthorizationServer.TokenEndpointAuthMethods`,
  `OAuth.Unauthenticated.Realm` and `OAuth.Unauthenticated.ErrorCode`.
- WHEN a new `string` or `[]string` field is added anywhere in the `Report`
  tree THE SYSTEM SHALL fail a guard test until that field is classified in
  the test's explicit origin table (package / caller / server).
- IF completing the enumeration is judged undesirable THEN THE SYSTEM SHALL
  instead drop the sentence's claim to be exhaustive — but not both, and this
  proposal chooses to complete it and add the guard.

Finding 4 — pre-registered client display name

- WHEN an authorization_code exchange completes for a client that exists only
  in the in-memory `Server.clients` map (built-in `ConnectClientID` or an entry
  from `cfg.PreregisteredClients`) THE SYSTEM SHALL persist that client's
  configured `ClientName` on the `db.RefreshToken` record.
- WHEN a client registration exists in the store THE SYSTEM SHALL keep using
  the stored `ClientName`, so persisted registrations win over the in-memory
  map.
- IF neither the store nor the in-memory map knows the `client_id` (an
  implicit client accepted via `AllowImplicitClient`) THEN THE SYSTEM SHALL
  persist an empty `ClientName`, exactly as today.
- WHILE resolving a display name THE SYSTEM SHALL NOT fail the token exchange
  on a store lookup error: a missing display name is cosmetic and must not
  deny a token.

## Out of scope

- Any change to refresh-token rotation semantics, grace-window behaviour,
  reuse detection or TTL handling in `internal/oauth/server.go`. Finding 4
  touches only how `ClientName` is resolved before `issueRefreshToken`.
- Backfilling `client_name` on refresh-token rows already persisted with an
  empty value; no data migration is proposed.
- Adding fields to `mcpprobe.Report` or changing `ReportSchema`.
- Any credential-bearing behaviour in `internal/mcpprobe` — the probe stays an
  unauthenticated observer; the guards in `internal/mcpprobe/guard_test.go`
  continue to hold.
- Changes to the merge gate, the Portal allowlist, or `docs/reports` artifacts.

## Open questions

- The issue says the redaction comment is "short by three fields". A field
  walk of the current `Report` tree finds four unlisted server-origin string
  fields: `Server.SupportedVersions`, `AuthorizationServer.Issuer`,
  `Unauthenticated.Realm` and `Unauthenticated.ErrorCode`. The likely intended
  three are `Issuer`, `Realm` and `ErrorCode`, with `SupportedVersions`
  treated as protocol identifiers rather than free text. This proposal names
  all four, because the enumeration exists to be exhaustive and a protocol
  version string is still a string the server chose. A reviewer who disagrees
  can drop `SupportedVersions` from the comment; the guard test's origin table
  still has to classify it either way.
- Finding 1 is already fixed at HEAD (`29470b0`) and the shallow clone carries
  no history to attribute the fix to a specific PR. If the reviewer wants #605
  closed with a traceable reference, the implementer should link the commit
  that introduced `splitChallengeParts`'s escape handling rather than claim a
  new fix.
- `internal/oauth` test helpers (`stateFromAuthorize`, `authCodeTokens` in
  `internal/oauth/refresh_test.go` and `internal/oauth/server_test.go`)
  hard-code `client_id=claude.ai`. Finding 4's test needs a client-parameterized
  path; whether to generalize the shared helpers or add a portal-local helper
  in `internal/oauth/preregistered_test.go` is left to the implementer, with a
  preference for generalizing.
