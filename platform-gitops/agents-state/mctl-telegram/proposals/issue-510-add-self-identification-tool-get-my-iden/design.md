# Design: issue-510-add-self-identification-tool-get-my-iden

## Current state

The MCP tool surface for self-service transparency lives in
`internal/mcp/tools.go`, registered in `internal/mcp/server.go`'s
`setupServer`/tool-registration block (each tool is built with a
`s.toolXxx()` constructor returning `(mcplib.Tool, mcpserver.ToolHandlerFunc)`
and wired via `s.addTool(srv, t, h)`, e.g. lines 231-238 for
`toolGetMyAuditLog` / `toolGetMySendStatus`).

Identity on an authenticated request is carried by `auth.Identity`
(`internal/auth/identity.go:14`), retrieved in every handler via
`auth.From(ctx)`. It already has the two fields this issue needs at the
credential level:

```go
type Identity struct {
    UserID           int64
    ...
    TelegramID       int64
    TelegramUsername string
    ...
}
```

`TelegramID`/`TelegramUsername` are populated by every `auth.Provider`
implementation (`internal/auth/sharedhmac/verifier.go:143`,
`internal/auth/localjwt/issuer.go:298-301`, `internal/auth/localdev/provider.go:29`)
from the token/claims that authenticated the call — this is exactly "the
identity that the currently authenticated session belongs to" the issue
asks for, and it requires no database read.

Richer, MTProto-sourced identity data (the account's current display name
and username, as seen by Telegram itself) lives in the `telegram_accounts`
table and is exposed today only through
`Store.GetActiveAccount(ctx, userID) (*db.AccountInfo, error)`
(`internal/db/store.go:714`):

```go
type AccountInfo struct {
    Connected   bool
    DisplayName string
    Username    string
    SendEnabled bool
    ConnectedAt time.Time
}
```

`AccountInfo` deliberately omits `telegram_user_id` — the comment at
`internal/db/store.go:38-40` states "PII like telegram_user_id stays hidden;
only connection-state fields are surfaced," because `AccountInfo` doubles as
the payload for `GET /api/account`, an HTTP-facing endpoint. `DisplayName`
and `Username` themselves are not secret — they are literally the Telegram
identity a `send_message` recipient already sees — they were captured once,
at connect time, from Telegram's own self-user object by `telegram.Login` /
`telegram.LoginQR` (`cmd/login/main.go:100-125`, referenced again in
`internal/oauth/enable_access.go:186-203`), and persisted by
`Store.SaveSession(ctx, userID, plaintext, telegramUserID, displayName,
username)` (`internal/db/store.go:431`).

`toolGetMySendStatus` (`internal/mcp/tools.go:854`) already shows the
established pattern for combining an identity-level fact
(`id.HasScope(...)`, `s.AllowSend`) with a single read of the active account
row (`s.Store.GetActiveAccount(ctx, id.UserID)`), including how to handle a
store read failure without silently reporting false data (comment block at
`internal/mcp/tools.go:894-929`): the account fields are typed as pointers
(`*bool`) so "could not read" is expressible as absence, never as a
confident false.

Every tool's output must declare an `outputSchema`
(`mcplib.WithOutputSchema[T]()`) — enforced by
`internal/mcp/output_schema_test.go`'s `TestToolOutputSchemas`, which lists
every tool name against `first(s.toolXxx())` — and every tool's read/write
annotations are locked in by `internal/mcp/annotations_test.go` the same
way. Both are simple table additions for a new tool, not new machinery.

The publicly documented tool list also lives in three places that describe
tool behavior for humans/agents: `README.md` (a table with annotations and
one-paragraph descriptions, e.g. lines 36-37), `LLMS.md`, and
`docs/public/llms.txt` — all three currently list `get_my_audit_log` and
`get_my_send_status` as the self-service transparency examples.

## Proposed solution

Add one new read-only MCP tool, `get_my_identity`, following the exact
shape of `toolGetMySendStatus`:

1. **New result type** in `internal/mcp/tools.go`, alongside the other
   `*Result` structs (near `sendStatusResult` / `identitiesResult`):

   ```go
   // identityResult is the success payload of get_my_identity.
   type identityResult struct {
       TelegramID  int64  `json:"telegram_id"`
       Username    string `json:"username,omitempty"`
       DisplayName string `json:"display_name,omitempty"`
       Connected   bool   `json:"connected"`
   }
   ```

   `Connected` is added beyond the issue's literal example payload because
   the acceptance criteria require distinguishing "never connected" from
   "connected" rather than silently returning an empty `display_name` for
   both — the same signal `get_my_send_status.connected` already gives, so
   a client that has already called one of these tools recognizes the
   field.

2. **New handler**, `func (s *Server) toolGetMyIdentity() (mcplib.Tool,
   mcpserver.ToolHandlerFunc)`, placed directly after `toolGetMySendStatus`
   (same self-service family):

   - `id := auth.From(ctx)`; if nil, `mcplib.NewToolResultError("authentication required")`,
     matching every other self-service tool.
   - Seed the result from the identity already on the context, which needs
     no I/O and can never be "unavailable":
     `out := identityResult{TelegramID: id.TelegramID, Username: id.TelegramUsername}`.
   - If `s.Store != nil`, call `s.Store.GetActiveAccount(ctx, id.UserID)`
     exactly once (same call `toolGetMySendStatus` makes). On success:
     - `out.Connected = acct.Connected`
     - if `acct.Connected`, prefer the MTProto-sourced fields, since they
       are the actual Telegram-side truth and may differ from the
       Login-Widget-time claim (`acct.Username` overrides `id.TelegramUsername`
       when non-empty; `out.DisplayName = acct.DisplayName`).
     - On a store error, log and fall back to the identity-only fields
       already seeded — mirroring `toolGetMySendStatus`'s
       "account read failed; reporting the verdict without account fields"
       branch — rather than failing the whole call, since `telegram_id` is
       always answerable from the credential alone.
   - No admin scope check, no `requireScope` call — self-service tools in
     this package specifically do not gate on scopes (their whole point is
     "operators cannot disable this for an authenticated user"); the
     credential's authentication is the only gate.
   - No `s.audit(...)` call, matching `get_my_audit_log` / `get_my_send_status`
     (see requirements.md Open questions).
   - Build the tool with the same annotation set as `get_my_send_status`:
     `WithTitleAnnotation`, `WithReadOnlyHintAnnotation(true)`,
     `WithDestructiveHintAnnotation(false)`, `WithOpenWorldHintAnnotation(false)`,
     `WithOutputSchema[identityResult]()`, and a `WithDescription` documenting
     the `connected=false` case explicitly (so a client does not mistake a
     missing `display_name` for a bug).
   - Return `jsonResult(out)`.

3. **Registration**: add
   ```go
   {
       t, h := s.toolGetMyIdentity()
       s.addTool(srv, t, h)
   }
   ```
   in `internal/mcp/server.go`, next to the `toolGetMySendStatus` block
   (line ~236), so the self-service tools stay grouped.

4. **Test coverage** (mirroring existing per-tool test files):
   - Add `{"get_my_identity", first(s.toolGetMyIdentity())}` to
     `internal/mcp/output_schema_test.go` and to
     `internal/mcp/annotations_test.go` (readOnly=true, destructive=false,
     openWorld=false), the same one-line-per-tool pattern already used for
     every other tool in both files.
   - New `internal/mcp/identity_test.go` (name mirrors
     `send_status_test.go`) covering: no identity on context (error);
     identity-only path when `s.Store` is nil or `GetActiveAccount` errors
     (returns `telegram_id`/`username` from the auth identity,
     `connected=false`, no error); connected path returning the
     `telegram_accounts` row's `display_name`/`username`; never-connected
     path (`Store.GetActiveAccount` returns `Connected:false`, empty
     strings) still returns `telegram_id` and the OIDC-claim `username`.

5. **Docs**: add one row/bullet each to `README.md`'s tool table, `LLMS.md`,
   and `docs/public/llms.txt`, following the existing one-line-per-tool
   style used for `get_my_audit_log` / `get_my_send_status`.

No new scope, no new database column, no new table, no new migration. The
tool reads two things that already exist: the authenticated request's own
`auth.Identity` and one already-existing `Store.GetActiveAccount` call
that `toolGetMySendStatus` already makes on every invocation.

## Alternatives

1. **Extend `get_my_send_status` to also return identity fields**, instead
   of adding a new tool. Dropped: `get_my_send_status`'s docstring and
   `sendStatusResult` schema are already tightly scoped to the send-gate
   verdict ("Report whether send_message would deliver..."); folding
   identity fields in would conflate two unrelated questions ("can I send?"
   vs "who am I?") in one payload and break existing consumers that treat
   `sendStatusResult`'s shape as stable via the locked-in output-schema
   test. The issue also asks for a distinctly named tool
   (`get_my_identity`), matching how `list_telegram_identities` already has
   a dedicated tool separate from the send/audit tools.

2. **Perform a live MTProto self round-trip** (e.g. `users.GetFullUser`
   against `InputUserSelf`, similar to how `sendself.go` uses
   `tg.InputPeerSelf{}`) on every call instead of reading the stored
   `telegram_accounts` row. Dropped for the initial version: it requires an
   active `telegram.Client` from the pool
   (`internal/telegram/clientpool.go`) for a lookup whose answer barely
   changes between calls, adds real Telegram RPC latency and a new failure
   mode (DC dial failure, flood-wait) to a tool whose entire value
   proposition is a fast, reliable answer, and none of the other `get_my_*`
   tools make a live Telegram call for their status data (`get_my_send_status`
   explicitly reads a stored row instead). Recorded in requirements.md as an
   open question / future enhancement, not ruled out permanently.

3. **Derive identity purely from `auth.Identity` (no `GetActiveAccount`
   call at all)**, since `TelegramID`/`TelegramUsername` are already on the
   context and require no I/O. Dropped: `TelegramUsername` on `Identity` is
   an OIDC/Login-Widget-time claim, and the issue's example payload also
   wants `display_name`, which does not exist anywhere on `auth.Identity` —
   only in `telegram_accounts` (populated from Telegram's own self-user
   object at MTProto-connect time). Without a `GetActiveAccount` read there
   is no `display_name` to return at all, which would silently violate the
   issue's example JSON shape. This is why the design reads the account row
   the same way `toolGetMySendStatus` does, rather than skipping it.

## Platform impact

- **Migrations**: none. No schema change; the tool reads existing columns
  (`telegram_accounts.display_name`, `.username`) through the existing
  `GetActiveAccount` method and existing `auth.Identity` fields.
- **Backward compatibility**: purely additive — one new tool name, one new
  result struct, one new registration line. No existing tool's schema,
  behavior, or annotations change.
- **Resource impact**: negligible. One additional `SELECT` against
  `telegram_accounts` per call (the same query `get_my_send_status` already
  issues on every invocation), no new Telegram RPC, no new background work.
- **Risks + mitigations**:
  - *Risk*: leaking another user's identity through a scoping bug.
    *Mitigation*: the handler only ever reads `id.UserID`/`id.TelegramID`
    from the caller's own verified `auth.Identity` and calls
    `GetActiveAccount(ctx, id.UserID)` with that same id — structurally
    identical to `get_my_send_status`, which has the same shape and no
    such history.
  - *Risk*: a store outage makes the tool return an error where the issue
    expects "always answerable." *Mitigation*: per the design above,
    `telegram_id`/`username` from `auth.Identity` are returned even when
    `GetActiveAccount` fails or `s.Store` is nil; only `display_name` and
    the accuracy of `connected` can degrade, and the failure path already
    matches `toolGetMySendStatus`'s precedent (log a warning, do not fail
    the call).
  - *Risk*: documentation drift if `README.md`/`LLMS.md`/`docs/public/llms.txt`
    are not all updated together. *Mitigation*: tasks.md tracks all three
    doc files explicitly as separate checklist items.
