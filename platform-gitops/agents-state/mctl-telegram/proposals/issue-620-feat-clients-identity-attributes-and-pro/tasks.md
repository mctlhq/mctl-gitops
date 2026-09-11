# Tasks: issue-620-feat-clients-identity-attributes-and-pro

- [ ] 1. Add the five nullable columns to `users` in `Migrate`
      (`internal/db/db.go`), next to the existing `telegram_username` /
      `telegram_display_name` / `access_tier` block: `telegram_first_name`,
      `telegram_last_name`, `telegram_language_code` (`TEXT`/`TEXT`),
      `identity_captured_at` and `onboarding_completed_at`
      (`TIMESTAMPTZ`/`DATETIME`). No `DEFAULT` on any of them.
      — DoD: `addColumnIfMissing` calls land in the additive pass with a comment
      explaining that `identity_captured_at IS NULL` means "capture never ran";
      `go build ./...` passes; `Migrate` is still idempotent when run twice
      against the same connection.

- [ ] 2. Add the `onboarding_completed_at` backfill to `Migrate`'s backfill block
      (depends on 1) — one statement shared by both dialects, setting it to
      `MIN(telegram_accounts.connected_at)` over the user's rows with
      `telegram_user_id IS NOT NULL`, only `WHERE onboarding_completed_at IS NULL`.
      — DoD: no `INTERVAL` / `datetime()` dialect split; re-running `Migrate`
      updates zero rows the second time; users with no finalised session keep
      NULL.

- [ ] 3. Add the provenance vocabulary and helper to `internal/db/store.go`
      (depends on 1): constants `ProvenanceVerified`, `ProvenanceDerived`,
      `ProvenanceNotSupplied`, `ProvenanceNotCaptured`, the
      `IdentityProvenance` struct, and unexported
      `attrProvenance(capturedAt sql.NullTime, value string) string`.
      — DoD: `attrProvenance` returns `not_captured` for a NULL timestamp
      regardless of value, `verified` for a set timestamp with a non-empty value,
      `not_supplied` for a set timestamp with an empty value; documented next to
      the existing `TierNone`/`TierClient` block.

- [ ] 4. Add `TelegramIdentityAttrs` and
      `Store.CaptureTelegramIdentity(ctx, userID, attrs)` to
      `internal/db/store.go` (depends on 1, 3). One `UPDATE users` using the
      `COALESCE(NULLIF($n,''), column)` shape `EnsureUserByTelegramID` already
      uses, stamping `identity_captured_at` unconditionally.
      — DoD: a partial snapshot never erases a previously captured value; a
      snapshot with every optional field empty still stamps the timestamp;
      `EnsureUserByTelegramID`'s signature and its four call sites are unchanged.

- [ ] 5. Add `LanguageCode` to `telegramoidc.Identity` and `language_code` to
      `idTokenClaims`, copied through `parseIdentity`
      (`internal/auth/telegramoidc/oidc.go`).
      — DoD: an id_token with no `language_code` claim still parses and yields an
      empty string; no change to signature, issuer, nonce or expiry verification.

- [ ] 6. Change `telegram.Login` and `telegram.LoginQR`
      (`internal/telegram/login.go`) to return `(LoginResult, error)`, populating
      `FirstName`, `LastName` and `LangCode` from the `*tg.User` that
      `client.Self(ctx)` already returns, while keeping the composed
      `DisplayName` exactly as it is built today.
      — DoD: `oauth.LoginFunc` (`internal/oauth/server.go:113`),
      `internal/oauth/enable_access.go:204` and `cmd/login/main.go` compile
      against the new shape; the display-name fallback to `me.Username` when both
      names are empty is preserved.

- [ ] 7. Wire `CaptureTelegramIdentity` into the three verified-source call sites
      (depends on 4, 5, 6): `internal/oauth/server.go` right after the OIDC
      callback's `EnsureUserByTelegramID`; `internal/oauth/local_bridge_activate.go`
      after its `EnsureUserByTelegramID`; and `internal/oauth/enable_access.go`
      after the `wantTgID` match check and a successful `SaveSession`.
      — DoD: capture is best-effort and logged at warn on failure, never turning a
      valid sign-in into a 500 (matching the surrounding tier-persistence block);
      an aborted or id-mismatched enable_access flow performs no capture; the
      `localjwt` issuer and auth-code redemption paths do NOT call it.

- [ ] 8. Extend `db.IdentityRow` and `Store.ListIdentities`
      (`internal/db/store.go`) with `FirstName`, `LastName`, `LanguageCode`,
      `LastSeenAt`, `OnboardingCompletedAt` and `Provenance` (depends on 1, 2, 3).
      `LastSeenAt` is the later of `MAX(telegram_accounts.last_used_at)` and
      `MAX(oauth_refresh_tokens.created_at)` for the user, computed in the first
      query; `Provenance` is filled via `attrProvenance`, with `derived` for
      `last_seen_at` and `onboarding_completed_at` when present and
      `not_captured` when absent.
      — DoD: still two round-trips; the `has_session` `EXISTS` sub-query and its
      `ttlExemptClause` splice are byte-for-byte unchanged; the `connected_via`
      second query and map merge are unchanged; `internal/digest/digest.go`
      compiles and behaves identically.

- [ ] 9. Replace `Store.GetLoginIdentity` with
      `Store.GetIdentity(ctx, userID) (*IdentityRow, error)` (depends on 8),
      running the same projection filtered to one `users.id` and returning
      `(nil, nil)` when the row is absent.
      — DoD: `GetLoginIdentity` is deleted, not deprecated; provenance is produced
      by the same `attrProvenance` helper as `ListIdentities`; no caller outside
      `internal/mcp/tools.go` remains.

- [ ] 10. Extend the MCP surface (depends on 8, 9): add the new fields and
      `provenance` to `myIdentityResult` and to the `identitiesResult` payload via
      `IdentityRow`; migrate `toolGetMyIdentity` to `GetIdentity`; rewrite both
      tool descriptions to enumerate the four provenance values.
      — DoD: `toolGetMyIdentity` still falls back to the `auth.Identity` in context
      when the store has no row and still returns "no Telegram identity on this
      session" when everything is empty; `list_telegram_identities` still requires
      `admin:users` or `admin:users:read` and still audits via `s.audit`;
      `TestToolOutputSchemas` passes.

- [ ] 11. Add `first_name`, `last_name`, `telegram_first_name`,
      `telegram_last_name` and `display_name` to `sensitiveKeys` in
      `internal/audit/redact.go`, with a comment recording that `language_code` is
      deliberately excluded as a non-identifying locale.
      — DoD: no existing slog call site regresses to `[redacted len=N]` for a field
      it legitimately logs (verified by `go test ./...`).

- [ ] 12. Update the docs surface (depends on 10): the `get_my_identity` reason
      string in `docs/portal-allowlist.json` (still `enabled: true`), the tool
      rows in `README.md`, and the `list_telegram_identities` references in
      `docs/runbook.md`.
      — DoD: `docs/runbook_test.go` passes; no emoji; English only.

## Tests

- [ ] T1. `internal/db` SQLite: legacy-row schema test in the style of
      `drop_legacy_columns_test.go` — open an in-memory DB, run `Migrate`, insert a
      user with `access_tier='client'`, a finalised `telegram_accounts` row and an
      `oauth_refresh_tokens` row, hand-`UPDATE` the five new columns back to NULL to
      simulate a pre-change row, re-run `Migrate`, and assert: `access_tier`,
      `telegram_login_id`, the session row and the refresh-token row are unchanged,
      and `onboarding_completed_at` is now the account's `connected_at`.
- [ ] T2. `internal/db` Postgres: the same scenario behind
      `os.Getenv("TEST_DATABASE_URL")` with `t.Skip` when unset, a synthetic
      Telegram id, and a `t.Cleanup` that deletes the rows — matching
      `store_access_tier_test.go`'s pattern.
- [ ] T3. `attrProvenance` table test covering all three states per attribute, both
      dialect-independent.
- [ ] T4. `CaptureTelegramIdentity`: a full snapshot sets all attributes and the
      timestamp; a later snapshot with empty first/last name does not erase them; a
      snapshot with every optional field empty still stamps `identity_captured_at`
      so the attributes read `not_supplied` rather than `not_captured`.
- [ ] T5. `internal/auth/telegramoidc`: `parseIdentity` with a `language_code` claim
      present, and with it absent (empty string, no error) — extending the existing
      offline claims tests.
- [ ] T6. `ListIdentities` (SQLite and, gated, Postgres): a captured user reads
      `verified` for supplied attributes and `not_supplied` for the absent ones; a
      never-captured legacy user reads `not_captured` for all of them while keeping
      its `access_tier`, `has_session` and `connected_via`; `last_seen_at` picks the
      later of the session and refresh-token timestamps and reads `derived`; a user
      with neither reads `not_captured`.
- [ ] T7. `internal/mcp`: extend `get_my_identity_test.go` so the tool returns the
      new attributes and the provenance object for a captured user, `not_captured`
      provenance for a legacy user, and still errors with "no Telegram identity on
      this session" when nothing is known. Confirm `output_schema_test.go` and
      `annotations_test.go` still pass.
- [ ] T8. `internal/audit`: a `slog` record carrying `first_name`, `last_name` and
      `display_name` attributes is redacted by `RedactingHandler`, and
      `language_code` passes through.
- [ ] T9. Negative logging test: drive an OIDC capture with a fake authenticator
      against a `slog` handler capturing to a buffer, and assert the buffer contains
      none of the captured name values; assert the `audit_logs` row written for
      `list_telegram_identities` contains only the tool name.
- [ ] T10. Run `go fmt ./...`, `go vet ./...` and `golangci-lint run` clean, per
      `CLAUDE.md`.

All fixtures use the existing synthetic personas (`Alice`, `Bob`, `Carol`,
`Dana`) and synthetic numeric ids; `git grep <id>` before reusing any id. No real
account name, handle or id in any fixture.

## Rollback

Revert the feature commit and redeploy the previous image tag; the service runs
`strategy: Recreate` with a single replica, so no mixed-version pod pair exists.
The five `users` columns and the `onboarding_completed_at` backfill survive the
revert and are simply unread by the older binary — every column is nullable with
no `DEFAULT`, participates in no index or constraint, and the older code's
`SELECT` lists name their columns explicitly, so nothing breaks. Unlike the
`idx_local_bridge_devices_idem_live` change recorded in `internal/db/db.go`, this
migration is not forward-only and needs no manual repair on rollback.

If the columns must be removed as well (they should not), add matching
`dropColumnIfPresent` calls to `dropLegacyColumns` in `internal/db/db.go` rather
than running ad-hoc DDL, so the removal converges the same way on every replica.

Partial rollback is available without a revert: reverting only task 7 (the three
`CaptureTelegramIdentity` call sites) stops all new capture while leaving the
schema and the read path intact — every attribute then reads `not_captured`,
which is the correct and honest state rather than a broken one.
