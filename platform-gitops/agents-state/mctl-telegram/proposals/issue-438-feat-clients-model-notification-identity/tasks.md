# Tasks: issue-438-feat-clients-model-notification-identity

- [ ] 1. Add the identity columns to `users` in `db.Migrate` (`internal/db/db.go`, alongside the
      existing block at L166-189): `telegram_first_name`, `telegram_last_name`,
      `telegram_language_code`, `identity_source`, `identity_captured_at`,
      `onboarding_completed_at`, `last_seen_at` — all via `addColumnIfMissing`, all nullable, no
      defaults. — DoD: `Migrate` is idempotent across two consecutive runs on both dialects; no
      column is added to `audit_logs`; `internal/db/store_migration_test.go`-style test asserts
      `access_tier`, `telegram_username`, `telegram_display_name`, `telegram_accounts` and
      `oauth_refresh_tokens` values are unchanged after migration.

- [ ] 2. Add the two new tables to both `pgSchema()` and `sqliteSchema()` in `internal/db/db.go`:
      `client_notification_prefs` (PK `(user_id, category)`) and `client_bot_reachability`
      (PK `user_id`), both `REFERENCES users(id) ON DELETE CASCADE`. (depends on 1) — DoD: tables
      exist after `Migrate` on in-memory SQLite and on Postgres when `TEST_DATABASE_URL` is set;
      names do not collide with the agent-domain `owner_notifications` table.

- [ ] 3. Add `db.AttributeProvenance` plus `db.ResolveIdentityProvenance` implementing the
      three-valued rule: `identity_captured_at IS NULL` -> `unknown`; set + empty attribute ->
      `not_supplied`; non-empty -> `supplied`. (depends on 1) — DoD: pure function, no DB access,
      table-driven test over all three cases for each of username / first name / last name /
      language code.

- [ ] 4. Add `db.TelegramIdentityCapture` and `Store.EnsureUserByTelegramCapture` in
      `internal/db/store.go`, reusing the existing `INSERT ... ON CONFLICT DO NOTHING` + `SELECT`
      race-safe shape and `COALESCE(NULLIF($1,''), col)` refresh. It writes `telegram_username`
      with **no** display-name fallback, derives `telegram_display_name` from
      `TrimSpace(FirstName+" "+LastName)`, and always stamps `identity_captured_at` /
      `identity_source` / `last_seen_at`. Leave `EnsureUserByTelegramID` untouched. (depends on 1,
      3) — DoD: existing `EnsureUserByTelegramID` tests still pass unmodified; a concurrent-call
      test shows no unique-index 500.

- [ ] 5. Switch the two call sites that already hold split names to the new capture:
      `internal/oauth/server.go:1597` (`identity_source = telegram_oidc`) and
      `internal/oauth/local_bridge_activate.go:1038` (`local_bridge_activation`). Leave
      `internal/auth/localjwt/issuer.go:293`, `internal/oauth/server.go:2018` and
      `internal/mcp/tools.go:1480` on the old function. (depends on 4) — DoD: after a fake-OIDC
      login in `internal/oauth`'s `newTestServer` harness, the `users` row has first and last name
      in their own columns and `identity_source = 'telegram_oidc'`.

- [ ] 6. Add the two idempotent backfill `UPDATE`s to `Migrate`, following the
      `last_used_at`/`expires_at` precedent at `internal/db/db.go:246-284`:
      `onboarding_completed_at` from `MIN(telegram_accounts.connected_at)` over non-revoked,
      finalised rows; `identity_source = 'backfill_legacy'` where NULL and
      `telegram_login_id IS NOT NULL`. Do **not** split `telegram_display_name`. (depends on 1) —
      DoD: a legacy row seeded before migration reports provenance `unknown` for first/last name,
      not `not_supplied`, and gains a non-NULL `onboarding_completed_at`.

- [ ] 7. Create `internal/notify` with `DeliveryOutcome`, `APIError{StatusCode, Description}` and the
      pure `ClassifyDelivery(httpStatus int, description string) DeliveryOutcome`, mirroring the
      offline-testable style of `telegramoidc.parseIdentity`. 200 -> `reachable`; 403 blocked /
      deactivated -> `blocked`; 403 can't-initiate and 400 `chat not found` -> `cannot_initiate`;
      429 / 5xx / transport error -> `Conclusive=false`. — DoD: table-driven test covering every
      row of the mapping plus at least three unrecognised descriptions, all non-conclusive.

- [ ] 8. Add `Store.RecordBotReachability(ctx, userID, notify.DeliveryOutcome, source string)` —
      an upsert that writes only when `Conclusive` is true, persisting `state`, `reason_code`,
      `observed_at`, `source`. (depends on 2, 7) — DoD: a non-conclusive outcome against an
      existing `reachable` row leaves state and `observed_at` unchanged.

- [ ] 9. Change `digest.sendTelegramMessage` (`internal/digest/digest.go:147`) to return
      `*notify.APIError` while keeping the `*url.Error` unwrap that prevents the bot token reaching
      logs, and have `runDigest` (L88-93) resolve the recipient chat id via
      `Store.UserIDByTelegramID` and call `RecordBotReachability` with source `digest_delivery`.
      (depends on 8) — DoD: a stubbed HTTP transport returning 403 `bot was blocked by the user`
      results in a `blocked` row; a 500 results in no row; no test log line contains the bot token.

- [ ] 10. Add `db.NotificationCategory` constants (`product_updates`, `maintenance`, `security`),
      `db.ResolvedPref{Category, State, Explicit, Classification, Source, DecidedAt}`,
      `Store.ResolveNotificationPrefs(ctx, userID)` and
      `Store.SetNotificationPrefs(ctx, userID, map[string]string, source string)`. Defaults are
      computed in Go, never written as rows: `product_updates` -> `unsubscribed`/`explicit=false`;
      `maintenance` and `security` -> `subscribed`/`explicit=false`/`classification=operational`.
      (depends on 2) — DoD: a user with zero rows resolves all three categories with
      `Explicit=false`; an unknown category or state returns an error and writes nothing.

- [ ] 11. Add `GET` and `PUT /api/account/notifications` to `internal/web/account.go`, extending
      `AccountHandlers.Register`'s structural router interface (L47-53) with `Put`. 401 when
      `auth.From` is nil, 400 on unknown category/state, partial update semantics, audited via the
      existing `h.audit(...)` helper with source `account_api`. (depends on 10) — DoD:
      `httptest`-driven handler tests for 200/400/401; the audit row records only tool name and
      status.

- [ ] 12. Render the three categories on `/telegram/connect/manage`
      (`internal/web/manage.go`, `managePageData` + `manageTemplate`) with plain HTML form posts to
      a new `POST /telegram/connect/manage/notifications`, source `self_service_web`, wired in
      `cmd/server/main.go` next to the existing `manage/toggle-send` route. No JavaScript and no
      external assets — the page CSP at `internal/web/manage.go:244` is
      `default-src 'none'; style-src 'unsafe-inline'; img-src https://ui.mctl.ai; form-action 'self'`.
      (depends on 10) — DoD: the rendered page contains all three categories and their current
      state; the CSP header is unchanged.

- [ ] 13. Add MCP tools `get_my_notification_preferences` and `set_my_notification_preferences` in
      `internal/mcp/tools.go`, registered in `newMCPServer` (`internal/mcp/server.go:198`),
      gated on the existing `account:manage` scope with `requireScope` (the same gate
      `set_send_consent` uses at `tools.go:1232`) — never on `admin:users:read`. Source
      `mcp_tool`. Update `docs/portal-allowlist.json` with name, `enabled`, `upstream_gates` and
      `reason`. (depends on 10) — DoD: `internal/mcp/portal_allowlist_test.go`,
      `annotations_test.go` and `output_schema_test.go` pass without being weakened.

- [ ] 14. Extend `db.IdentityRow` (`internal/db/store.go:288`) with the new `omitempty` fields and
      extend `Store.ListIdentities` (L409-488) from two queries to four, merging
      `client_bot_reachability` and `client_notification_prefs` through the same
      `idx map[int64]int` by `TelegramID` that `connected_via` already uses. (depends on 3, 8, 10) —
      DoD: no per-user query is issued for N users; existing `TestListIdentities` and
      `TestListIdentities_ConnectedVia` pass unmodified.

- [ ] 15. Update `toolListIdentities` (`internal/mcp/tools.go:1054-1084`) — description only, plus
      the auto-derived `outputSchema[identitiesResult]()`. The
      `requireAnyScope("admin:users","admin:users:read")` gate stays byte-identical. Add a
      reachability suffix to `digest.buildDigestMessage` for rows whose state is not `unknown`.
      (depends on 14) — DoD: `lookup_admin_scope_test.go` still proves the read scope reaches this
      tool and no write tool; the digest test asserts the new suffix and its absence for `unknown`.

- [ ] 16. Add `purgeNotificationState(ctx, tx, userID)` and call it from
      `Store.HardDeleteAccount` (`internal/db/store.go:769-814`) immediately after the existing
      `purgeAgentData` call, in the same transaction, deleting from both new tables explicitly
      rather than relying on `ON DELETE CASCADE` — the `users` row survives deletion. (depends on 2)
      — DoD: after `HardDeleteAccount`, both tables have zero rows for that user;
      `RevokeActiveSession` leaves preference rows intact.

- [ ] 17. Add `first_name` and `last_name` to `audit.sensitiveKeys`
      (`internal/audit/redact.go:30-74`) and audit every new log statement for PII. Do not touch
      `hashAuditEntry`'s field order (`internal/db/audit_chain.go:17-57`). (depends on 5) — DoD:
      `internal/audit/redact_test.go` covers the two new keys; a grep of the new code shows only
      ids, categories, states, reason codes and sources in `slog` attributes.

- [ ] 18. Document the model in `README.md` / `docs/runbook.md`: the four reachability states and
      what `unknown` does and does not mean, the per-category defaults and why `product_updates`
      defaults to `unsubscribed`, and the fact that a preference confers no scope. (depends on 15)
      — DoD: `docs/runbook_test.go` still passes; the claims match
      `internal/web/privacy.html`'s existing statements.

## Tests

- [ ] T1. `Migrate` idempotence and non-destructiveness: seed a store with users at every tier, an
      active session and a live refresh token; run `Migrate` twice; assert every pre-existing column
      value is unchanged and `VerifyAuditChain` still reports OK. (`internal/db`, `newTestStore`
      harness at `store_test.go:198`.)
- [ ] T2. OIDC claims present: fake `Exchange` returns username + first + last name; assert the
      `users` row has each in its own column, `identity_source='telegram_oidc'` and a non-NULL
      `identity_captured_at`. (`internal/oauth`, `newTestServer` + `fakeAuthenticator`.)
- [ ] T3. OIDC claims absent: fake `Exchange` returns only a Telegram id; assert `telegram_username`
      is empty (no display-name fallback) and provenance resolves to `not_supplied`, not `unknown`.
- [ ] T4. Legacy-row backfill: insert a `users` row by raw SQL before the new columns are populated;
      run `Migrate`; assert `identity_source='backfill_legacy'`, `identity_captured_at` NULL,
      provenance `unknown`, and `onboarding_completed_at` derived from the seeded
      `telegram_accounts.connected_at`.
- [ ] T5. `ClassifyDelivery` table test: every mapping row plus 429, 500, 502 and three unknown
      descriptions asserted non-conclusive.
- [ ] T6. Blocked bot end to end: stub the Bot API transport to return
      403 `{"description":"Forbidden: bot was blocked by the user"}`; run `runDigest`; assert
      `client_bot_reachability.state='blocked'`, a normalised `reason_code`, and that no log line
      contains the bot token or the raw response body.
- [ ] T7. Transient failure does not downgrade: seed `reachable`, deliver a 429 and a 500, assert
      state and `observed_at` unchanged.
- [ ] T8. Reachability is independent: a user with a valid refresh token and an active MTProto
      session still reports `unknown` until a delivery is recorded.
- [ ] T9. Default resolution: zero preference rows resolves `product_updates=unsubscribed`,
      `maintenance=subscribed`, `security=subscribed`, all `Explicit=false`, with `security` and
      `maintenance` classified `operational`.
- [ ] T10. Unsubscribe records provenance: `PUT /api/account/notifications`
      `{"product_updates":"unsubscribed"}` writes `decided_at`, `source='account_api'` and
      `Explicit=true`, and leaves the other two categories without rows.
- [ ] T11. Partial update and validation: a body naming only `maintenance` leaves `product_updates`
      untouched; an unknown category and an unknown state each return 400 and write nothing;
      anonymous request returns 401.
- [ ] T12. Consent grants nothing: a user with `product_updates=subscribed` and no `access_tier`
      still resolves to zero scopes through `oauth.Server.ResolveScopes`, and every MCP tool 403s.
- [ ] T13. Account deletion: seed preferences and a reachability row, call `HardDeleteAccount`,
      assert zero rows in both tables and that the `users` row still exists (existing contract).
- [ ] T14. Disconnect is not deletion: `RevokeActiveSession` leaves both tables untouched.
- [ ] T15. Admin projection: `list_telegram_identities` with `admin:users:read` returns the new
      fields; with no admin scope returns the existing scope error; the JSON round-trips for a
      consumer that knows only today's fields.
- [ ] T16. Structural guards unchanged: `portal_allowlist_test.go`, `annotations_test.go`,
      `output_schema_test.go`, `lookup_admin_scope_test.go` and `zero_admin_e2e_test.go` pass with
      the two new tools registered.
- [ ] T17. Redaction: `first_name` and `last_name` slog attributes are replaced with
      `[redacted len=N]`.

All fixtures use the repo's synthetic personas (`Alice`, `Bob`, `Carol`, `Dana`) and their existing
numeric ids; run `git grep <id>` before introducing any new one, per `.claude/CLAUDE.md`.

## Rollback

The change is additive in every layer, so rollback is a code revert with no schema step.

1. **Code.** Revert the merge commit. The columns and the two tables stay behind, unreferenced and
   harmless: `Migrate` re-adds them on the next boot only if the code is rolled forward again, and
   the reverted binary never selects them. Because the PR must be merged with a merge commit
   (`gh pr merge <N> --merge --delete-branch`, per `.claude/CLAUDE.md`), `git revert -m 1` is the
   single-command undo.
2. **Schema.** Do not drop anything on rollback. Nothing in the revert reads the new columns, and
   `dropLegacyColumns` (`internal/db/db.go:348`) is the deliberate, separate mechanism if the
   columns are ever genuinely retired.
3. **Partial rollback of just the reachability writes.** Revert task 9 alone: `runDigest` stops
   recording, `sendTelegramMessage` returns a plain error again, and the stored states simply go
   stale. No other subsystem reads them except the admin projection, which renders `unknown`.
4. **Partial rollback of just the self-service surface.** Unregister the routes in
   `cmd/server/main.go` and the two MCP tools in `internal/mcp/server.go`, and remove their entries
   from `docs/portal-allowlist.json`. Stored preferences remain readable by the admin projection.
5. **Data.** No user data is destroyed by this change other than by `HardDeleteAccount`, which only
   ever deletes more. There is nothing to restore.
6. **Verification after rollback.** `go test ./...`, then `Store.VerifyAuditChain` against a
   representative user — the audit chain is the one thing a schema mistake in this repo can corrupt
   irreversibly, and this proposal deliberately never touches `audit_logs` or `hashAuditEntry`.
