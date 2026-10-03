# Tasks: issue-668-feat-observability-audit-rejected-client

The four items are independent. 1-4 (registrations), 5-7 (auth attribution),
8-11 (digest) and 12 (abandonment) can be implemented and merged in any
order or as separate PRs. Nothing below changes request handling, an auth
decision, OAuth redirect policy, or the audit hash chain.

## Item 1 — rejected client registrations

- [ ] 1. Add `OAuthClientRegistrationsTotal *prometheus.CounterVec` to
      `metrics.Registry` in `internal/metrics/metrics.go`, registered as
      `mctl_oauth_client_registrations_total` with labels `outcome` and
      `reason`, and a doc comment stating both label sets are closed
      compile-time constants from `internal/oauth`.
      — DoD: `internal/metrics/metrics_test.go`'s registry-completeness
      assertion lists the new name; `go test ./internal/metrics/...` passes.

- [ ] 2. Add typed sentinel errors to `internal/oauth/server.go` and wrap the
      existing returns in `validateRedirectURIShape` (line 2787) and
      `validateImplicitRedirectURI` (line 2753): `errRedirectBackslash`,
      `errRedirectUserinfo`, `errRedirectScheme`, `errRedirectHost`. Wrap
      with `%w` so every message stays byte-identical on the wire.
      — DoD: `internal/oauth/redirect_hardening_test.go` passes unmodified;
      a new assertion confirms `errors.Is(err, errRedirectScheme)` for a
      `cursor://` URI and that `err.Error()` is unchanged from before.

- [ ] 3. Add `internal/oauth/registration_audit.go` (depends on 1, 2) with
      the `regReason` constant set, `classifyRegistrationError(err) regReason`
      built on `errors.Is`, `redirectOrigin(raw) (scheme, host string)`
      returning `u.Scheme` / `u.Hostname()` and `("","")` on parse failure,
      and `auditRegistration(...)` emitting the single
      `oauth: client_registration audit` line plus the counter increment.
      — DoD: package compiles; `redirectOrigin` unit-tested for a URI with
      path, query, fragment, port and userinfo, and for an unparseable one.

- [ ] 4. Route every exit of `handleClientRegistration`
      (`internal/oauth/server.go:2561`) through `auditRegistration` (depends
      on 3): the rate-limit gate (2567), the three decode failures
      (2585/2609/2617), the four validation gates (2621/2625/2630/2643), the
      persist failure (2661), and the accepted path (2703). The accepted and
      rate-limited lines keep their current attributes and gain `reason`.
      Wire the `*metrics.Registry` the `oauth.Server` already holds.
      — DoD: every `return` in the handler is preceded by exactly one
      `auditRegistration` call; `go vet ./...` and `golangci-lint run` clean.

## Item 2 — attributed auth failures

- [ ] 5. Add `internal/auth/attribution.go` with `TokenAttribution`,
      `AttributedError` (with `Error()` forwarding and `Unwrap()`), and
      `AttributionOf(err) (TokenAttribution, bool)`. Document that
      constructing one for a pre-signature failure is forbidden.
      — DoD: `classifyAuthError(wrapped.Error())` returns the same label as
      `classifyAuthError(inner.Error())` for all nine existing reasons —
      asserted by a table test.

- [ ] 6. Add `localjwt.VerifyWithClaims` (depends on 5) returning claims only
      for failures after the `json.Unmarshal` at
      `internal/auth/localjwt/issuer.go:160`; reduce `Verify` to a wrapper
      that nils the claims on error. Switch `Provider.Authenticate` (line
      253) to it and wrap the `Verify`, `CheckAudience` and revocation-check
      failures in `&auth.AttributedError{}`. Apply the same treatment to
      `sharedhmac.Provider.Authenticate`
      (`internal/auth/sharedhmac/verifier.go:118`) for its `checkAudience`
      and `AllowedGroups` paths.
      — DoD: `Verify`'s signature and every existing call site are unchanged;
      `go test ./internal/auth/...` passes with no test edits beyond new ones.

- [ ] 7. Rewrite the `slog.Warn("auth failed", …)` at
      `internal/auth/middleware.go:96` (depends on 5, 6) to build attributes
      from `edgectx.FromRequest(r)`, `chi.RouteContext(...).RoutePattern()`,
      the shared `reason`, and `auth.AttributionOf(err)`. Compute `reason`
      once and reuse it for the counter on line 98. Add the decision comment
      to `internal/audit/redact.go` recording why `sub`/`client_id`/`jti`/`exp`
      are deliberately absent from `sensitiveKeys`.
      — DoD: no new counter is introduced; `mctl_auth_failures_total` name
      and labels are untouched; `go test ./internal/auth/... ./internal/audit/...`
      passes.

## Item 3 — onboarding stage in the digest

- [ ] 8. Add `telegram_accounts.revoked_reason TEXT` to both the SQLite
      (`internal/db/db.go:551`) and Postgres (`:786`) `CREATE TABLE`
      statements and to the `addColumnIfMissing` migration block, following
      the `call_path` precedent at `db.go:127`. Nullable, no default, no
      backfill.
      — DoD: a pre-change database opens, migrates and serves reads; a fresh
      one has the column; `go test ./internal/db/...` passes.

- [ ] 9. Persist the reason in the three revoke paths (depends on 8):
      `internal/db/store.go:676`, `:881`, and `RevokeSessionByID` at `:899`,
      which already takes `reason string` and discards it after the metric.
      — DoD: a revoke with reason `"disconnect"` stores it; a revoke with an
      empty reason stores NULL.

- [ ] 10. Add `db.ConnectStep` and `Store.LastConnectStepFor(ctx, tgIDs []int64)`
      (depends on 8, 9) using the correlated `MAX(id)` query from design.md
      plus the `revoked_reason` lookup, with the placeholder list built the
      way `ttlExemptClause` (`store.go:121`) builds one. Empty `tgIDs`
      short-circuits to an empty map with no query. Select only `tool_name`,
      `status` and `created_at` from `audit_logs` — never `peer_redacted` or
      `error`.
      — DoD: passes against both the SQLite and Postgres test harnesses;
      returns no entry for a user with only non-`connect:` audit rows.

- [ ] 11. Wire the digest (depends on 10): call `LastConnectStepFor` in
      `runDigest` (`internal/digest/digest.go:68`) with the Telegram ids of
      `newRows` only, pass the map into `buildDigestMessage`, and replace the
      `session := "no session"` branch at line 172 with `sessionSuffix`. A
      query error logs WARN and leaves the map nil. Update the exact-string
      assertions in `internal/digest/digest_test.go:62-68`.
      — DoD: a row with no session and a `connect:failed:flood_wait` row
      renders `no session — last: failed:flood_wait <HH:MM>`; a row with a
      session renders `session active` exactly as before.

## Item 4 — abandoned onboarding is not an ERROR

- [ ] 12. In `internal/oauth/enable_access.go`, add `step string` and
      `superseded atomic.Bool` to `loginFlow`; set `step` at the five points
      named in design.md (all on the login goroutine); set `superseded`
      before the two `es.flow.cancel()` calls at lines 516 and 704; replace
      the deferred two-arm logger at lines 160-171 with the four-arm switch
      and `isAbandonment(err)`. Leave every `LogToolCall("connect:failed:…")`
      site untouched.
      — DoD: ERROR is emitted only for errors that are neither
      `context.DeadlineExceeded` nor `context.Canceled`; `go test -race
      ./internal/oauth/...` passes.

## Docs

- [ ] 13. Update `docs/runbook.md` (depends on 4, 7, 11, 12): document
      `mctl_oauth_client_registrations_total` and its label set beside the
      existing metric sections; note the new `auth failed` attributes; note
      that `enable: telegram login failed` no longer fires for abandoned or
      superseded flows and that `enable: onboarding abandoned` replaces it;
      update the `grep -E` recipe at line 1532 to include the new message.
      Add the registration metric to the README metric list (line 254).
      — DoD: `go test ./deploy/alerts/... ./docs/...` passes (the repo's
      `runbook_links_test.go` and `runbook_test.go` guard these files).

## Tests

- [ ] T1. `internal/oauth`: a `POST /oauth/register` with
      `cursor://anysphere.cursor-retrieval/oauth/callback` produces exactly
      one `outcome=rejected` audit line with
      `reason=redirect_scheme_not_allowed`, `redirect_scheme=cursor`,
      `redirect_host=anysphere.cursor-retrieval`, the supplied `client_name`
      and `user_agent`. Use a synthetic client name, never a real product's.
- [ ] T2. The same test asserts the emitted record contains neither the full
      redirect URI nor its path or query, for a URI carrying both.
- [ ] T3. A table test drives one request per terminal exit of
      `handleClientRegistration` and asserts the `(outcome, reason)` pair on
      both the log line and the counter, proving the label set is exactly the
      closed constant set and that each request increments the counter once.
- [ ] T4. An accepted registration still emits `outcome=accepted` with its
      existing `client_name` and `redirect_uri_count` attributes, and a
      rate-limited one still emits `outcome=rate_limited` carrying no IP.
- [ ] T5. `internal/auth`: a token whose signature was tampered with produces
      an `auth failed` line with **no** `sub`, `client_id` or `jti`
      attribute, while an expired but correctly signed one produces all of
      them. This is the security assertion of item 2.
- [ ] T6. `auth failed` carries `edge_request_id` and `edge_route` for a
      request bearing `Cf-Ray` and `Cf-Worker`, and carries the `direct`
      route with an empty request id when neither header is present.
- [ ] T7. `internal/digest`: when `LastConnectStepFor` returns an error the
      digest is still sent and every `no session` row renders the plain
      pre-change text.
- [ ] T8. `internal/db`: `LastConnectStepFor` never returns `peer_redacted`
      or `error` content — assert against a seeded audit row whose
      `peer_redacted` holds a synthetic `@handle` and whose `error` holds a
      distinctive marker, and confirm neither appears in the result or in
      the rendered digest message.
- [ ] T9. `internal/db`: `VerifyAuditChain` returns OK for a chain written
      before this change and for one written after — proving no new column
      feeds `hashAuditEntry`.
- [ ] T10. `internal/oauth`: a login flow failing with a synthetic
      `FLOOD_WAIT_300` still logs `enable: telegram login failed` at ERROR;
      one failing on the `CodeTTL` deadline logs `enable: onboarding
      abandoned` at WARN with the step reached; one cancelled by a `/start`
      re-submission logs `enable: login flow superseded` at INFO.
- [ ] T11. `go test -race ./internal/oauth/...` with a login flow that is
      superseded mid-code-wait, covering the `step`/`superseded` access
      pattern.
- [ ] T12. `internal/db`: `LastConnectStepFor(ctx, nil)` issues no query and
      returns an empty map.

All fixtures use the existing synthetic personas (`Alice`, `Bob`, `Carol`,
`Dana`) and their existing numeric ids per `.claude/CLAUDE.md`; run
`git grep <id>` before reusing one. No real Telegram id, name or handle in
any fixture, and no real product's client name in the registration tests.

## Rollback

Each item is independently revertable; there is no ordering dependency
between them at runtime.

- **Items 1, 2, 4 (log/metric only):** `git revert` the commit and redeploy.
  No state, no schema, no config. A stale dashboard panel for
  `mctl_oauth_client_registrations_total` goes flat; nothing breaks.
- **Item 3:** `git revert` and redeploy. The added
  `telegram_accounts.revoked_reason` column is nullable and unread by the
  reverted binary, so it can be left in place — dropping it is optional
  cleanup, not a rollback step. `audit_logs` is untouched, so the hash chain
  needs no repair and `VerifyAuditChain` keeps returning OK across the
  revert.
- **Partial rollback of item 2:** reverting only task 7 (the middleware log
  line) is safe on its own; `AttributedError` is inert if nothing calls
  `AttributionOf`, since `Error()` forwards the wrapped string unchanged and
  every existing classifier keeps working.
- **Verification after rollback:** confirm `/metrics` still serves,
  `mctl_auth_failures_total` still increments on a deliberately expired
  token, a `/oauth/register` with an `https` redirect still returns 201, and
  the next digest sends.
