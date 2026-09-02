# Design: issue-458-feat-mcp-set-account-mode-so-enabling-lo

## Current state

- `telegram_accounts.mode` is a `TEXT NOT NULL DEFAULT 'hosted'` column, added via the
  schema-evolution helper `addColumnIfMissing` in `internal/db/db.go:120-123` (both the SQLite and
  Postgres `CREATE TABLE` blocks also declare it directly, `internal/db/db.go:307` and `:367`). There
  is no separate migrations directory in this repo — schema changes are additive `ALTER TABLE`-style
  helpers applied idempotently at startup, so `mode` already exists everywhere; no schema change is
  needed for this proposal.
- The only reader is `Store.GetAccountMode` (`internal/db/store.go:1079-1098`):
  `SELECT mode FROM telegram_accounts WHERE user_id = $1 AND revoked_at IS NULL ORDER BY
  connected_at DESC LIMIT 1`, defaulting to `"hosted"` both when there is no active row and on query
  error. There is no writer anywhere in the Go codebase — `grep -rn "SET mode"` / `UPDATE
  telegram_accounts.*mode` returns nothing. The only writer in production has been a one-shot gitops
  `Job` doing the `UPDATE` directly against the database, per the issue.
- `internal/bridge/server.go:44-73` is the consumer: a Local Bridge daemon registering over the
  bridge websocket is rejected with HTTP 400 "account is in hosted mode" unless
  `GetAccountMode(ctx, id.UserID) == "local"`.
- The nearest precedent for a privileged single-column account write is `toolSetAccountSend`
  (`internal/mcp/tools.go:951-1005`) and its `Store.SetSendEnabled` (`internal/db/store.go:744-755`):
  - `requireScope(id, "admin:users")` gates the call.
  - `telegram_id` is resolved to the internal `user_id` via `Store.UserIDByTelegramID`
    (`internal/db/store.go:238`), which returns `db.ErrUserNotFound` when no `users` row exists for
    that Telegram id.
  - The actual write is a single `UPDATE ... WHERE user_id = $1 AND revoked_at IS NULL`, and the tool
    checks `RowsAffected()`: zero rows becomes a hard `toolErr`, not a cheerful `OK: true`. This is
    exactly the "fail loudly on a no-op" behavior the issue asks for, already established in this
    codebase for the sibling column.
  - `s.audit(ctx, id, "<tool_name>", "", err, startedAt)` is called unconditionally, both on the
    resolve step and the write step, matching every other admin tool.
- The idle-sweep hazard the issue calls out is real and independently verifiable in code:
  - `Store.MarkLastUsed` (`internal/db/store.go:782-788`) is the only writer of `last_used_at`, and
    it is called from `Pool.Borrow` on every successful tool dispatch (issue cites
    `internal/telegram/clientpool.go:167,460`) — a call relayed to a Local Bridge daemon does not go
    through `Pool.Borrow` the same way a hosted MTProto call does, so `last_used_at` goes stale for an
    account that is being used exclusively through the bridge.
  - `Store.SweepIdleSessions` (`internal/db/store.go:930-952`) revokes any row with `last_used_at`
    older than the idle TTL (30 days) unless the row's `telegram_user_id` is in the exemption set
    built from `ttlExemptClause` (`internal/db/store.go:115-...`), which is populated from
    `Store.ttlExempt`, which is populated once at startup by `WithAbsoluteTTLExempt(cfg.SessionTTLExemptTGIDs)`
    (`cmd/server/main.go:105`), which reads `SESSION_TTL_EXEMPT_TG_IDS` (`internal/config/config.go:315`) —
    an env var edited in gitops, per the issue.
  - Once a row is revoked, `GetAccountMode`'s `WHERE revoked_at IS NULL` no longer matches it, so the
    account falls back to the function's `"hosted"` default even though `mode` still literally reads
    `'local'` in storage — this is the "silent revert to hosted with a dead bridge" the issue
    describes.
  - `Store.ttlExempt` is an unexported `map[int64]bool` — there is currently no exported accessor to
    ask "is this Telegram id exempt", which the new tool needs.

## Proposed solution

1. **New `Store` method: `SetAccountMode`.** In `internal/db/store.go`, next to `SetSendEnabled`:

   ```go
   // SetAccountMode flips telegram_accounts.mode ('hosted' or 'local') on the
   // user's active session row. Used by the set_account_mode admin tool so
   // enabling Local Bridge for an account is a runtime call instead of a
   // one-shot gitops Job. Returns the number of rows affected (0 when the
   // user has no active session) so the caller can distinguish a real update
   // from a silent no-op, matching SetSendEnabled.
   func (s *Store) SetAccountMode(ctx context.Context, userID int64, mode string) (int64, error) {
       res, err := s.DB.ExecContext(ctx,
           `UPDATE telegram_accounts SET mode = $2
            WHERE user_id = $1 AND revoked_at IS NULL`,
           userID, mode,
       )
       if err != nil {
           return 0, fmt.Errorf("set account mode: %w", err)
       }
       n, _ := res.RowsAffected()
       return n, nil
   }
   ```

   This is a direct copy of `SetSendEnabled`'s shape: same `WHERE` clause (so it can only ever touch
   the caller's currently-active row, never a revoked one — which is exactly what makes "the account
   must already have a session" hold structurally, since `session_encrypted NOT NULL` means no row
   exists without a completed login, and `revoked_at IS NULL` means only a live one is targeted), same
   `RowsAffected` return so the tool layer decides what a zero-row update means.

2. **New `Store` accessor: `IsModeExempt`.** Also in `internal/db/store.go`, next to
   `WithAbsoluteTTLExempt`:

   ```go
   // IsModeExempt reports whether tgID is on the idle/absolute TTL exemption
   // list. set_account_mode uses this to refuse mode="local" for an account
   // that would otherwise be silently reverted to hosted by SweepIdleSessions
   // once Local Bridge traffic stops refreshing last_used_at.
   func (s *Store) IsModeExempt(tgID int64) bool {
       return s.ttlExempt[tgID]
   }
   ```

   Reads the existing unexported map; no new state. Named `IsModeExempt` rather than a more generic
   `IsTTLExempt` to keep the doc comment's rationale attached to the one call site that exists today
   (grep-discoverable if a second caller shows up later; rename then).

3. **New MCP tool: `set_account_mode`**, in `internal/mcp/tools.go` immediately after
   `toolSetAccountSend` (so the two admin per-account toggles stay adjacent, matching how
   `toolSetAccess` and `toolSetAccountSend` already sit next to each other):

   ```go
   func (s *Server) toolSetAccountMode() (mcplib.Tool, mcpserver.ToolHandlerFunc) {
       tool := mcplib.NewTool("set_account_mode",
           mcplib.WithTitleAnnotation("Set a user's Telegram account mode"),
           mcplib.WithReadOnlyHintAnnotation(false),
           mcplib.WithDestructiveHintAnnotation(true),
           mcplib.WithOpenWorldHintAnnotation(false),
           mcplib.WithOutputSchema[setAccountModeResult](),
           mcplib.WithDescription(`Admin only (requires the admin:users scope). Switch a Telegram
   user's active session between "hosted" (server-side MTProto, default) and "local" (Local Bridge:
   MTProto runs on the user's own machine, tg.mctl.ai relays only).

   Inputs:
     telegram_id — int, required. The Telegram user id (see list_telegram_identities).
     mode        — string, required. "local" or "hosted".

   The user must have an active session (a completed hosted login) before mode can be changed.
   Setting mode="local" for a telegram_id that is not in SESSION_TTL_EXEMPT_TG_IDS is refused: without
   that exemption, SweepIdleSessions revokes the account 30 days after Local Bridge traffic stops
   refreshing last_used_at (bridge calls never stamp it), which silently reverts the account to
   hosted with a dead daemon. Add the id to SESSION_TTL_EXEMPT_TG_IDS first, then retry.`),
           mcplib.WithNumber("telegram_id",
               mcplib.Required(),
               mcplib.Description("Telegram user id to change the mode for (required).")),
           mcplib.WithString("mode",
               mcplib.Required(),
               mcplib.Description(`"local" or "hosted" (required).`)),
       )
       handler := func(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
           startedAt := time.Now()
           id := auth.From(ctx)
           if err := requireScope(id, "admin:users"); err != nil {
               return mcplib.NewToolResultError(err.Error()), nil
           }
           args := req.GetArguments()
           tgID := int64(intArg(args, "telegram_id", 0))
           mode := stringArg(args, "mode", "")
           if tgID <= 0 {
               return mcplib.NewToolResultError("telegram_id is required and must be a positive integer"), nil
           }
           if mode != db.ModeLocal && mode != db.ModeHosted {
               return mcplib.NewToolResultError(`mode must be "local" or "hosted"`), nil
           }
           if mode == db.ModeLocal && !s.Store.IsModeExempt(tgID) {
               return toolErr("telegram id %d is not in SESSION_TTL_EXEMPT_TG_IDS — setting mode=local "+
                   "without that exemption will silently revert to hosted after 30 days idle "+
                   "(Local Bridge calls do not refresh last_used_at); add it to "+
                   "SESSION_TTL_EXEMPT_TG_IDS first, then retry", tgID), nil
           }
           targetUID, err := s.Store.UserIDByTelegramID(ctx, tgID)
           if err != nil {
               s.audit(ctx, id, "set_account_mode", "", err, startedAt)
               if errors.Is(err, db.ErrUserNotFound) {
                   return toolErr("no user with telegram id %d — they must sign in once first", tgID), nil
               }
               return toolErr("set_account_mode: %v", err), nil
           }
           rows, err := s.Store.SetAccountMode(ctx, targetUID, mode)
           s.audit(ctx, id, "set_account_mode", "", err, startedAt)
           if err != nil {
               return toolErr("set_account_mode: %v", err), nil
           }
           if rows == 0 {
               return toolErr("no active Telegram session for telegram id %d — they must connect an "+
                   "account first", tgID), nil
           }
           return jsonResult(setAccountModeResult{TelegramID: tgID, Mode: mode, OK: true})
       }
       return tool, handler
   }
   ```

   Registered in the tool wiring next to `toolSetAccountSend` (grep for where that is added to the
   server's tool list, likely `internal/mcp/server.go` or similar registration site, and add the new
   tool there under the same admin-tool grouping).

4. **New constants `db.ModeLocal` / `db.ModeHosted`**, in `internal/db/store.go` next to the existing
   `TierNone` / `TierClient` constants (`internal/db/store.go:267-271`), so the tool and any future
   caller validate against named constants instead of bare string literals, matching the existing
   `tier` precedent in `toolSetAccess`. `GetAccountMode`'s existing `"hosted"` literal is left as-is
   (out of scope: a pure refactor with no behavior change is not bundled into this proposal, but is a
   natural one-line follow-up).

5. **New result type `setAccountModeResult`**, in `internal/mcp/tools.go` next to
   `setAccountSendResult`:

   ```go
   // setAccountModeResult is the success payload of set_account_mode.
   type setAccountModeResult struct {
       TelegramID int64  `json:"telegram_id"`
       Mode       string `json:"mode"`
       OK         bool   `json:"ok"`
   }
   ```

6. **Docs**: `docs/local-bridge.md` and `docs/runbook.md` both currently describe enabling Local
   Bridge via the gitops `Job` / manual `UPDATE` path (the runbook explicitly references
   `ttlExemptClause`, per the earlier grep). Update the enable-account section of both to point at
   `set_account_mode` as the primary path, keeping the manual-`UPDATE` / `SESSION_TTL_EXEMPT_TG_IDS`
   gitops edit only as what it now is: the still-required prerequisite step for the exemption, not
   the mode flip itself.

No database migration, no config change, no new environment variable. The exemption list stays
env-var-driven exactly as it is today — this proposal reads that state, it does not restructure it.

## Alternatives

- **Warn instead of refuse when the target is not TTL-exempt.** Considered and dropped: the issue
  itself frames the exemption gap as a "30-day time bomb" whose whole danger is that it is silent and
  easy to forget about; a warning string embedded in an otherwise-successful tool result is exactly
  the kind of thing an operator skims past under time pressure (the same failure mode the issue's
  Job-based flow already had). A hard refusal costs nothing extra: the operator already has to touch
  gitops to add the exemption, so the ordering (exemption first, then mode) does not add a
  gitops round-trip that wasn't already necessary — it just makes the tool's error message the thing
  that reminds them, instead of nothing reminding them.
- **Auto-add the Telegram id to the exemption list from the tool itself**, e.g. by having the tool
  write to a database-backed exemption table instead of requiring the env var to already list the
  id. Dropped as out of scope for this issue: it would mean introducing a second, database-backed
  source of truth for TTL exemption alongside the existing env-var one (or migrating the whole
  mechanism off env vars), which is a materially bigger change than "give mode a writer" and was not
  asked for. It is a reasonable follow-up if the env-var edit-and-redeploy step turns out to still be
  the dominant cost after this proposal ships.
- **Have `Pool.Borrow`-equivalent logic stamp `last_used_at` for Local Bridge relay calls too**,
  removing the need for the exemption check entirely by keeping local-mode accounts naturally fresh.
  Dropped as out of scope: that is a change to the bridge relay's request path
  (`internal/bridge/server.go`), a different subsystem than "add a writer for one column", and
  changes sweep behavior for every Local Bridge account rather than giving the operator an explicit
  tool-level decision point. Worth a separate issue if the manual exemption step remains painful.
- **Fold the mode flip into `set_account_send`** (add a `mode` parameter to the existing tool)
  instead of a new tool. Dropped: `send_enabled` and `mode` are orthogonal privilege axes (dry-run vs
  real sends; server-side vs local execution) with independent failure semantics (the TTL-exemption
  refusal only applies to `mode`), and the issue explicitly asks for a `set_account_mode` tool
  "alongside" `toolSetAccountSend`, not a parameter added to it.

## Platform impact

- **Migrations**: none. `mode` already exists on both SQLite and Postgres schemas via
  `addColumnIfMissing`; no new column, table, or index.
- **Backward compatibility**: fully additive — one new `Store` method, one new accessor, one new MCP
  tool, one new result type, two new constants. No existing tool's input/output schema changes.
  `GetAccountMode`'s default-to-`"hosted"` behavior for accounts nobody has touched is unaffected.
- **Resource impact**: negligible — one more single-row `UPDATE` on an already-indexed table
  (`idx_telegram_accounts_user_active`), same shape and cost as the existing `SetSendEnabled` write.
- **Risks + mitigations**:
  - *Risk*: an operator sets `mode=local` for an account that then gets revoked for an unrelated
    reason (e.g. the user signs out from another device) between the tool call and the daemon's next
    connect attempt. *Mitigation*: this is not new risk introduced by this proposal — `mode`'s
    interaction with `revoked_at` is unchanged from today's gitops-`Job` behavior; the bridge
    endpoint's own `GetAccountMode` check at connect time (`internal/bridge/server.go:65-73`) already
    catches it and rejects the daemon, same as it does today.
  - *Risk*: the TTL-exemption refusal blocks a legitimate operator who already added the id to
    `SESSION_TTL_EXEMPT_TG_IDS` in gitops but the deploy carrying that env-var change has not rolled
    out yet, since `SessionTTLExemptTGIDs` is only read at process startup
    (`cmd/server/main.go:105`). *Mitigation*: this is an inherent property of the env-var-based
    exemption mechanism, not something this proposal makes worse — the operator gets a clear,
    actionable error ("not in SESSION_TTL_EXEMPT_TG_IDS") rather than a silent bad state, and can
    retry once the rollout completes. Documented as an open question rather than solved here.
  - *Risk*: privilege escalation via the new tool — mitigated identically to `set_telegram_access` /
    `set_account_send`: gated on `admin:users`, audited unconditionally, no new scope introduced.
