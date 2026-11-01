# Design: issue-1072-feat-onboarding-record-acquisition-sourc

## Current state

User creation
- `internal/oauth/server.go` `handleTelegramCallback` consumes the pending-auth entry, exchanges the Telegram OIDC code, then calls `s.store.EnsureUserByTelegramCapture(..., Source: "telegram_oidc")`. `internal/oauth/local_bridge_activate.go` (around line 1043) calls the same function for Local Bridge activations.
- `internal/db/identity_capture.go` `EnsureUserByTelegramCapture` runs `INSERT INTO users(...) ... ON CONFLICT DO NOTHING`, then a SELECT, then an UPDATE refresh, each directly on `s.DB` with no transaction. The INSERT's `RowsAffected()` is currently discarded. It is the only reliable "this call created the user" signal.
- Other paths create users through `EnsureUserByTelegramID` (`internal/auth/localjwt`, the worker-token path, `internal/mcp/tools.go`). They are out of scope.

OAuth pending state
- `/oauth/authorize` (`handleAuthorize`) builds a `pendingAuth` (`server.go`, `type pendingAuth struct`). With `UseDBForOAuth`, which is true when `DATABASE_URL` is `postgres://`, i.e. production, it is persisted as `db.OAuthPendingAuth` in the `oauth_pending_auth` table (`internal/db/db.go` pgSchema, `store_oauth.go` `InsertOAuthPending`/`ConsumeOAuthPending`). Otherwise it is kept in the `s.pending` map. Both modes must carry the new field.
- `internal/connectfunnel/connectfunnel.go` `ClientLabel(redirectURI)` already maps a redirect URI to a bounded label (`claude`, `chatgpt`, `other`) used by `connect_first_call`.

Pages and cookies
- Public content pages are rendered by `chromePage` (`internal/web/security.go`), which sets `chromeCSP`. The landing page is also served by `RootMCP` (`internal/web/landing.go`). `SecurityHeaders` sets `Referrer-Policy: strict-origin-when-cross-origin` on our responses. That policy affects only Referers we send. For inbound traffic, other sites' default policy also yields at least the origin, which is all the host-only design needs.
- Existing first-party cookies (`mctl_connect_token` in `internal/web/connect.go`, the activation-state cookie in `local_bridge_activate.go`) establish the HttpOnly/HMAC pattern.
- `internal/web/privacy.html` "Website analytics" section states "Umami sets no cookies" and describes no sign-up attribution. It must change.

Schema and deletion
- Tables are declared twice, in `sqliteSchema()` and `pgSchema()` in `internal/db/db.go`. Column additions use `addColumnIfMissing`. Example: `connect_first_call`, `user_id ... REFERENCES users(id) ON DELETE CASCADE`.
- `HardDeleteAccount` (`internal/db/store.go`, around lines 1100-1230) does **not** delete the `users` row. It anonymises it and explicitly purges dependent tables (`purgeAgentData`, `purgeNotificationState`) in one transaction. `ON DELETE CASCADE` alone would therefore leave an acquisition row behind after account deletion. An explicit purge is required.

Reporting
- `internal/digest/digest.go` `runDigest` filters `ListIdentities` to the last 24h, does one bounded extra lookup (`LastConnectStepFor`), and renders one line per client in `buildDigestMessage` (plain text via `botapi.Client.SendMessage`). Per-row suffixes follow the `sessionSuffix`/`reachabilitySuffix` pattern.
- Admin tools live in `internal/mcp/tools.go`. Example: `toolListIdentities` (`list_telegram_identities`), gated by `requireAnyScope(id, "admin:users", "admin:users:read")` and registered in `internal/mcp/server.go`.
- Tool calls are recorded in `audit_logs(user_id, tool_name, status, created_at)`, which provides the "made a tool call" and "active days" figures.
- `internal/sanitize` exposes `UserContent`/`Name` for untrusted text.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`. Ingress hosts are `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`, so the content pages and `/oauth/*` share one origin and a first-party SameSite=Lax cookie reaches `/oauth/authorize`. `PUBLIC_BASE_URL`/`OAUTH_ISSUER_URL` = `https://tg.mctl.ai`. `AUTO_APPROVE_CLIENTS: "true"`. `OAUTH_CODE_TTL: "30m"`. The `DATABASE_URL` is from a secret (Postgres, per the psql jobs in the same file), so the DB-backed pending-auth path is the production path. There is one replica.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/` exists as a preview service and was not inspected in detail.
- mctl MCP tools were not called in this run. Live pod and env state was not observed beyond gitops.

## Proposed solution

### 1. Acquisition value type and cookie codec (`internal/acquisition`, new package)
- `type Snapshot struct { State string; UTMSource, UTMMedium, UTMCampaign, UTMContent, UTMTerm, ReferrerHost, LandingPath, MCPClient string; CapturedAt time.Time }`. `State` is one of `attributed`, `direct`, `unknown`.
- `Capture(r *http.Request, selfHost string, now time.Time) Snapshot` reads exactly the five UTM keys from `r.URL.Query()`. Each value is put through `clean`: strip `unicode.IsControl` and bidi override runes, trim, truncate to 100 runes. Empty values after cleaning count as absent. `ReferrerHost` comes from `url.Parse(r.Referer()).Hostname()`, lowercased. It is empty when parsing fails, when the host equals `selfHost`, or when the host exceeds 253 chars. `LandingPath` is `r.URL.Path` truncated to 200. State is `attributed` if any UTM or referrer host is present, else `direct`.
- `Encode(key, Snapshot) string` and `Decode(key, raw string, now) (Snapshot, error)`. The cookie payload is base64url(JSON) followed by `.` and base64url(HMAC-SHA256). Decode rejects raw values over 2048 bytes, checks the MAC with `hmac.Equal`, rejects `CapturedAt` older than the TTL (24h) or more than 5 minutes in the future, and re-applies `clean` to every field. A cookie with a valid MAC that was minted with longer values is truncated, not trusted.
- The key is `HKDF-SHA256(JWTSecret, info="mctl-telegram/acquisition-cookie/v1")`. It is derived once at startup and passed to both the web layer and the OAuth server, so neither shares the raw JWT secret's purpose.

### 2. First-touch capture on content pages (`internal/web`)
- Wrap `chromePage` (and the landing handler used by `RootMCP`) with `acquisition.Middleware(key, selfHost)`. On GET only, if the request has no `mctl_acq` cookie that decodes successfully, it calls `Capture` and sets the cookie (`HttpOnly`, `Secure` when https, `SameSite=Lax`, `Path=/`, `MaxAge=86400`). If a valid cookie exists it does nothing (first touch wins). An invalid cookie is replaced by a fresh capture of the current page. A tampered cookie therefore never survives, but the replacement does not overwrite a valid first touch.
- No capture on `/oauth/*`, `/telegram/connect`, `/local-bridge/activate`. Those pages run after or outside creation, and the privacy page already promises they carry no analytics.

### 3. Carry through `/oauth/authorize`
- `handleAuthorize` reads `mctl_acq`. A successful `Decode` gives the snapshot. Any failure (missing, bad MAC, oversized, expired, malformed) gives `Snapshot{State: "unknown"}`. In both cases `MCPClient = connectfunnel.ClientLabel(redirectURI)`. The failure reason (`missing`, `invalid`, `expired`) is counted on a metric `mctl_acquisition_capture_total{state,reason}`.
- Add `Acquisition string` (the JSON of the snapshot, max 2KB) to `pendingAuth` and `db.OAuthPendingAuth`. Add column `acquisition TEXT NOT NULL DEFAULT ''` to `oauth_pending_auth` via `addColumnIfMissing` and include it in `InsertOAuthPending`/`ConsumeOAuthPending`. An empty value on consume (a pending row minted by the previous image during rollout) decodes as `unknown`.
- The cookie is not cleared at authorize. The first touch should survive an abandoned attempt. The 24h TTL bounds it.

### 4. Persist at creation (`internal/db`)
- New table in both schemas:
  ```
  user_acquisition (
    user_id      INTEGER/BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    state        TEXT NOT NULL CHECK (state IN ('attributed','direct','unknown')),
    referrer_host TEXT NOT NULL DEFAULT '',
    utm_source, utm_medium, utm_campaign, utm_content, utm_term TEXT NOT NULL DEFAULT '',
    landing_path TEXT NOT NULL DEFAULT '',
    mcp_client   TEXT NOT NULL DEFAULT '',
    captured_at  DATETIME/TIMESTAMPTZ NOT NULL,
    recorded_at  DATETIME/TIMESTAMPTZ NOT NULL
  )
  ```
  plus a single-row `acquisition_capture_epoch(id=1 CHECK, enabled_at)`. It is seeded at `Migrate` with `INSERT ... ON CONFLICT DO NOTHING`, so reports can tell `unknown (pre-capture)` (user created before `enabled_at`) apart from `unknown (not recorded)`.
- `TelegramIdentityCapture` gains `Acquisition *Acquisition`. `nil` means the caller has no capture and nothing is written. That keeps any future caller from accidentally writing `direct`.
- `EnsureUserByTelegramCapture` wraps the INSERT in `s.DB.BeginTx`. If `RowsAffected()==1` and `Acquisition != nil`, it runs `SAVEPOINT acq`, then `INSERT INTO user_acquisition ... ON CONFLICT (user_id) DO NOTHING`. On error it runs `ROLLBACK TO SAVEPOINT acq`, logs `slog.Warn("acquisition: write failed", "err", err)` without field values, and increments `mctl_acquisition_write_failures_total`. Then `COMMIT`. The SELECT/UPDATE refresh keeps its current semantics, either inside the same tx or after commit. Both Postgres and SQLite support SAVEPOINT. A returning user (`RowsAffected()==0`) never touches the table. There is no UPDATE statement for `user_acquisition` anywhere.
- `handleTelegramCallback` passes the decoded pending snapshot. `local_bridge_activate.go` passes `&Acquisition{State: "unknown", MCPClient: "local-bridge"}`.
- `HardDeleteAccount` adds `DELETE FROM user_acquisition WHERE user_id = $1` next to `purgeNotificationState`.

### 5. Reporting
- `Store.AcquisitionLabelsFor(ctx, tgIDs []int64) (map[int64]string, error)` does one bounded query joining `users` (telegram_login_id, created_at) to `user_acquisition` and `acquisition_capture_epoch`. It returns the label `utm_source` > `referrer_host` > `direct` | `unknown` | `unknown (pre-capture)` | `unknown (not recorded)`. Labels are passed through `sanitize.Name(label, 60)`.
- `runDigest` calls it next to `LastConnectStepFor`. `buildDigestMessage` gains an `src map[int64]string` parameter and appends ` — src=<label>`. A lookup error degrades to omitting the suffix, the same degradation rule as `steps == nil`, and is logged, never sent as `unknown`.
- `Store.AcquisitionReport(ctx, since time.Time) ([]AcquisitionBucket, error)` groups users created at or after `since` by label: `signups`, `tool_call_users` (EXISTS `audit_logs` row for the user), and `active_2plus_days` (COUNT DISTINCT calendar day of `audit_logs.created_at` >= 2, using a dialect switch: `date(created_at)` on SQLite, `(created_at AT TIME ZONE 'UTC')::date` on Postgres, via the Store's cached dialect).
- New MCP tool `get_acquisition_report` in `internal/mcp/tools.go`. It is read-only, takes `days` (default 7, 1..90), is gated like `list_telegram_identities`, is audited via `s.audit`, and returns a JSON output schema. It is registered in `internal/mcp/server.go` and added to any tool catalogs and annotation tests that enumerate tools.

### 6. Disclosure
- `internal/web/privacy.html`: in "Website analytics" or a new "Sign-up attribution" subsection, describe the `mctl_acq` first-party cookie (24h, signed, HttpOnly). List what is stored once at account creation: UTM keys, referring site host, landing path and MCP client type. State that no IP or user agent is stored and that the record is deleted with the account. Correct the "sets no cookies" sentence so it stays accurate (Umami sets none; this service sets one). Update `landing_privacy_test.go` expectations if they pin that copy.

## Alternatives

1. **Carry UTM through `/oauth/authorize` query parameters only, no cookie.** Rejected. MCP clients build the authorize URL themselves and never forward landing-page parameters, so almost every sign-up would be `unknown`.
2. **Read the Referer at the callback or at authorize.** Rejected. At the callback it is always Telegram, and at authorize it is the MCP client's host or nothing. That is what `mcp_client` already records.
3. **Separate best-effort INSERT after `EnsureUserByTelegramCapture` returns, with a `created bool` result.** Viable and simpler, but it is not "the same transaction" the issue asks for, and a crash between the two statements silently drops the row. The SAVEPOINT design keeps atomicity and still never fails sign-in. This option is kept as the fallback if the reviewer objects to the tx refactor (see the requirements open question).
4. **Join against Umami.** Rejected. Umami deliberately carries no account identifier (privacy page), and linking it would contradict that disclosure.

## Platform impact

- Migrations: two new tables and one new column (`oauth_pending_auth.acquisition`). All are additive and idempotent (`IF NOT EXISTS`, `addColumnIfMissing`). No backfill. The epoch row is stamped at first migration, so it records the deploy time on the existing production DB.
- Backward compatibility: pending rows minted by the old image are consumed as `unknown`. The new image writes a column the old image ignores, so rollback is safe. Digest lines gain a suffix. `list_telegram_identities` output is unchanged.
- Transaction change in `EnsureUserByTelegramCapture`: this is the sign-in hot path. Risk: the tx or SAVEPOINT misbehaves on SQLite (single writer). Mitigation: tests on both drivers (the existing Postgres test harness if present, plus SQLite), and the acquisition insert is the only statement inside the savepoint.
- Resources: one cookie of at most 2KB, one small row per sign-up (about 5 per day), and one extra bounded query per daily digest.
- Privacy and security: host-only referrer, whitelisted and bounded values, HMAC-signed cookie with a dedicated derived key, no IP or UA, explicit purge in `HardDeleteAccount`, values sanitized at render. Values set by a user about themselves are accepted as self-reported. Signing only prevents a forged cookie from being minted server-side for a value the server never saw. It cannot attach to another user, because the cookie lives in the visitor's own browser and is bound to their own sign-in.
- Logging: no cookie values or UTM values in logs. If new slog attribute names are introduced (`utm_*`, `referrer_host`), add them to `internal/audit/redact.go`.
