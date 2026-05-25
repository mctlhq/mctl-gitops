# Design: issue-214-self-service-canonicalize-client-tier-in

## Current state

### Scope resolution

`internal/oauth/server.go` — `isClientTier` (line ~671) queries
`store.GetAccessTier(ctx, tgID)`. When the DB value is `NULL` / empty
(no explicit row), and `cfg.AutoApproveClients` is `true`, the function
returns `true` without writing anything to the DB. The flag alone is what
grants the client tier for every self-registered user.

### finishEnable

`internal/oauth/enable_access.go` — `finishEnable` (line 503–510):

```go
func (s *Server) finishEnable(w http.ResponseWriter, r *http.Request, es *enableSession, esTok string) {
    es.step = stepDone
    s.mu.Lock()
    delete(s.enables, esTok)
    s.mu.Unlock()
    s.store.LogToolCall(r.Context(), es.uid, "connect:success", "", "ok", "", "")
    s.issueAuthCode(w, r, es.oc)
}
```

`finishEnable` is called from three code paths inside
`handleEnableStart`, `handleEnableCode`, and `handleEnablePassword` once
`lf.done` is closed without an error. It consumes the enable session and
delegates to `issueAuthCode`. No DB write for the access tier happens here.

### DB layer

`internal/db/store.go` — `SetAccessTier` (line 176) and constants
`TierClient = "client"` / `TierNone = "none"` (line 158–160) already
exist. `SetAccessTier` issues a single `UPDATE users SET access_tier = $2
WHERE telegram_login_id = $1` and returns an error if zero rows are
affected. Since `finishEnable` is only reached after
`EnsureUserByTelegramID` was called in `handleTelegramCallback` (line
~1057), the row always exists by the time `finishEnable` fires, so a
zero-rows-affected error cannot occur in normal operation.

### enableSession

`enableSession` (line 48–63 of `enable_access.go`) carries `tgID int64`
(the OIDC-proven Telegram user id) and `uid int64` (the internal
`users.id`). Both are available inside `finishEnable` via `es.tgID` /
`es.uid`.

## Proposed solution

Add a single guarded call to `store.SetAccessTier` in `finishEnable`,
after the audit log write and before `issueAuthCode`:

```go
func (s *Server) finishEnable(w http.ResponseWriter, r *http.Request, es *enableSession, esTok string) {
    es.step = stepDone
    s.mu.Lock()
    delete(s.enables, esTok)
    s.mu.Unlock()
    s.store.LogToolCall(r.Context(), es.uid, "connect:success", "", "ok", "", "")
    if !s.cfg.AdminTelegramIDs[es.tgID] {
        if terr := s.store.SetAccessTier(r.Context(), es.tgID, db.TierClient); terr != nil {
            slog.Error("finishEnable: set client tier", "uid", es.uid, "err", terr)
            // Non-fatal: AUTO_APPROVE_CLIENTS still grants scopes; log and continue.
        }
    }
    s.issueAuthCode(w, r, es.oc)
}
```

Key properties:

- **Admin guard**: `cfg.AdminTelegramIDs[es.tgID]` is a map lookup, the
  same pattern used throughout `server.go`. Admins are governed by the env
  allowlist; no DB column is written.
- **Non-fatal error**: A transient DB error must not block the user from
  receiving their auth code. `AUTO_APPROVE_CLIENTS` remains a live fallback
  until the next successful `finishEnable` can write the row. The error is
  logged at `slog.Error` with `uid` and `err` fields consistent with the
  redact-handler conventions in `internal/audit/redact.go` (neither field
  is a sensitive value).
- **Idempotent**: `SetAccessTier` is a bare UPDATE; calling it for a user
  who already has `access_tier = 'client'` is a no-op with `n == 1`.
- **Import**: `db` is already imported in `enable_access.go`'s package
  (`internal/oauth`). `slog` is already imported in `server.go` but not
  yet in `enable_access.go`; it must be added to `enable_access.go`'s
  import block.

### Test

Add `TestFinishEnable_WritesClientTier` to
`internal/oauth/enable_access_test.go`, placed near
`TestResolveScopes_AutoApprove`. The test drives the full happy-path flow
for a **non-admin** user:

1. Build an `enableSession` for a non-admin client Telegram ID (e.g.
   `888000999`) using `newEnableTestServer` with that ID in
   `ClientTelegramIDs`.
2. Inject a `stubLoginAs(888000999)` variant of `LoginFunc` that returns
   the non-admin ID (unlike the existing `stubLogin` which always returns
   the admin ID `210408407`).
3. Drive the flow through `driveToPhone`-equivalent → `/start` (phone) →
   `/code` (code) → expect 302 (auth code redirect).
4. Call `srv.store.GetAccessTier(ctx, 888000999)` and assert it equals
   `db.TierClient`.

The test also asserts that the existing admin happy-path
(`TestEnableAccess_HappyPath_NoTwoFA`, which uses Telegram ID `210408407`
that is in `AdminTelegramIDs`) does NOT write a tier: call
`store.GetAccessTier(ctx, 210408407)` and assert it returns `""` (no
row / NULL). This can be added as an assertion to the existing test rather
than a new test.

The existing `stubLogin` always returns `210408407`; a new helper
`stubLoginAs(tgID int64) LoginFunc` is needed that persists the session
blob and returns the given tgID. The `fakeAuthenticator.identity` must also
be set to the non-admin ID so the OIDC callback resolves the correct
identity and the identity-binding check (`tgID != wantTgID` in
`startLoginFlow`) passes.

## Alternatives

### Alternative 1: Write the tier in `handleTelegramCallback` at the point where enable_access is entered

Write `TierClient` immediately when the callback decides to route the user
into the enable_access phone screen. This fires before the user actually
completes MTProto login. Rejected because it would grant a permanent DB
tier to users who enter their phone but never complete the SMS code step
(abandoned flows), creating ghost DB grants that are never backed by a real
session.

### Alternative 2: Write the tier in `startLoginFlow` after `SaveSession` succeeds

`startLoginFlow` already calls `store.SaveSession` once MTProto completes.
A `SetAccessTier` call there would be symmetric. Rejected because
`startLoginFlow` runs in a background goroutine with a `context.Background`
-based context, not the request context. More importantly, it does not have
access to `cfg.AdminTelegramIDs`, requiring either a wider refactor or a
field addition. `finishEnable` is already the single convergence point that
all three success paths call, has both `es.tgID` and the request context,
and is on the HTTP handler goroutine where the config is naturally in scope.

### Alternative 3: Trigger a backfill migration for existing users

Run a one-time `UPDATE users SET access_tier = 'client' WHERE
access_tier IS NULL AND telegram_login_id IS NOT NULL` at deploy time.
This was explicitly excluded from scope by the issue. It would also race
with concurrent logins and is harder to test or roll back.

## Platform impact

### Migrations

None. `users.access_tier` column already exists (added in a prior
migration). `db.SetAccessTier` and `db.TierClient` are already in the
`internal/db/store.go` public API.

### Backward compatibility

The change is purely additive. Deployments where `AUTO_APPROVE_CLIENTS` is
`false` and `TG_LOGIN_CLIENTS` is used for env-based bootstrap are
unaffected: `finishEnable` is only reached by users who already passed the
`isClientTier` gate in `handleTelegramCallback`, so writing their DB tier
is a confirmation of existing access, not an escalation.

### Resource impact

One additional SQL `UPDATE` per successful enable_access completion. This
is a very infrequent operation (user onboarding) and has negligible load.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `SetAccessTier` fails for a new user whose `users` row was not created yet | Cannot happen: `EnsureUserByTelegramID` is called unconditionally in `handleTelegramCallback` before the enable session is created. By the time `finishEnable` fires, the row exists. |
| DB error on `SetAccessTier` blocks user login | Mitigated by the non-fatal pattern: error is logged, `issueAuthCode` still fires. The user gets their token; the operator sees the error in logs. |
| Admin accidentally gets `TierClient` written | Mitigated by the `AdminTelegramIDs` guard in `finishEnable`. |
