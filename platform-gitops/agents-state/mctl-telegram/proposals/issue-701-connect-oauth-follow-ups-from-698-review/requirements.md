# connect/OAuth follow-ups from #698 review: AUTH_RESTART framing, reason accuracy, prefetch and 405 edge cases

## Context

Issue #701 collects nine P3 follow-ups from the review rounds on #698 (the fix
for #695). They fall into three groups. The first is user-visible: Telegram
returns `AUTH_RESTART` from `auth.signIn`, i.e. *after* the code is submitted,
so it lands in `handleEnableCode` — and that handler still wraps the message
with `"The code was not accepted: "` and `" Start again to get a fresh code."`,
producing a sentence that misattributes the failure to the code and repeats its
own instruction. #698 already added a `reason == "auth_restart"` guard to
`handleEnableStart` (`internal/oauth/enable_access.go:834`) but not to the code
or password steps.

The second group is operator-facing log and metric accuracy: `unknown_state` is
logged before the `alreadyConnected` recovery check in `HandleConnectDone`
(`internal/web/connect.go:281-292`), so a request that ends in a *successful*
redirect to `/manage` still emits a WARN counted against the failure it is
meant to measure; `expired_state` is unreachable on the DB-backed pending store
because `db.Store.ConsumeOAuthPending` collapses "never issued" and "past
CodeTTL" into `db.ErrOAuthNotFound` (`internal/db/store_oauth.go:187-198`),
which covers every Postgres deployment; and `internal/oauth/server.go:1690`
logs `reason` `"exchange_failed"` as a bare literal instead of a named const.
The third group is hardening and hygiene: `POST /` is registered
unconditionally from `cfg.MCPPath` (`cmd/server/main.go:410`) so an
`MCP_PATH=/` would shadow the MCP mount with a self-referential 405; the `Allow`
header `RootPostHint` sends (`GET`) disagrees with the one chi computes for
`PUT /` (`GET, POST`); one prefetch test is vacuous; and the reason vocabulary
is undocumented in `docs/runbook.md`.

None of these blocked the #698 merge. They matter because item 1 shows a
confusing sentence to a real user mid-login, and because items 2 and 6 make the
`reason` label — the thing an operator greps and alerts on — report the wrong
thing in production.

## User stories

- AS a user whose Telegram sign-in session is ended by `AUTH_RESTART` after
  submitting the SMS code I WANT one accurate sentence SO THAT I know my code
  was not the problem and what to do next.
- AS an already-connected user who reopens a used connect link I WANT the
  successful redirect to `/telegram/connect/manage` to be logged as a recovery
  SO THAT the operator's `unknown_state` count is not inflated by my success.
- AS an operator triaging a connect failure on Postgres I WANT `expired_state`
  and `unknown_state` to be distinguishable SO THAT I can tell a slow user from
  a replayed or forged link.
- AS an operator reading `docs/runbook.md` I WANT every `reason` token the code
  emits, plus the `auth provider init failed` startup headline, listed there SO
  THAT a log line I have never seen before is still actionable.
- AS a platform engineer I WANT `MCP_PATH=/` refused at config load SO THAT a
  typo cannot make every MCP request answer 405 pointing at itself.
- AS an MCP client author I WANT the `Allow` header on `/` to be the same
  whatever method I send SO THAT method discovery is not self-contradictory.
- AS a maintainer I WANT the callback prefetch test to exercise the state the
  prefetch actually carries SO THAT moving the guard below the activation
  dispatch breaks a test instead of production.

## Acceptance criteria (EARS)

### Item 1 — AUTH_RESTART framing at the code and password steps

- WHEN the login goroutine fails with `AUTH_RESTART` after the SMS code was
  submitted (`handleEnableCode`, `lf.done` with `lf.err != nil`) THE SYSTEM
  SHALL render the phone step carrying exactly `friendlyErr(lf.err)` — the
  string `"Telegram ended the sign-in session. Submit your phone number again
  to get a fresh code."` — and SHALL NOT include `"The code was not accepted"`
  nor any second restart instruction.
- WHEN the login goroutine fails with `AUTH_RESTART` after the 2FA password was
  submitted (`handleEnablePassword`, generic fallback arm) THE SYSTEM SHALL
  render the phone step carrying exactly `friendlyErr(lf.err)` and SHALL NOT
  include `"The password was not accepted"`.
- WHILE the error is anything other than `AUTH_RESTART` THE SYSTEM SHALL keep
  the existing wording of all three step handlers byte-for-byte, including the
  `db.ErrAccountModeConflict` terminal arms and `badPasswordRestartMsg`.
- WHEN any of these arms runs THE SYSTEM SHALL keep writing the existing audit
  entry `connect:failed:<shortReason(err)>` unchanged.

### Item 2 — reason accuracy on `/telegram/connect/done`

- WHEN `HandleConnectDone` finds no pending session (or an expired one) AND
  `alreadyConnected(r)` reports true THE SYSTEM SHALL redirect to
  `/telegram/connect/manage` with 303 and SHALL log exactly one line at Info
  level carrying `reason=recovered_redirect`, and SHALL NOT log
  `reason=unknown_state` or `reason=expired_state` for that request.
- WHEN the same lookup fails AND `alreadyConnected(r)` reports false THE SYSTEM
  SHALL log one WARN carrying `reason=unknown_state` (state absent) or
  `reason=expired_state` (state present but past `codeTTL`) and render the
  reused-link page, unchanged from today.
- WHILE `s.identifier` is nil THE SYSTEM SHALL behave exactly as today (no
  redirect, WARN on the failure arm, no panic).

### Item 3 — callback prefetch test exercises the activation state

- WHEN a prefetch request (`Sec-Purpose: prefetch;prerender`, or legacy
  `Purpose: prefetch`) arrives at `/oauth/telegram/callback` carrying an
  activation's own `oidcState` THE SYSTEM SHALL answer 204 and SHALL leave that
  state indexed in `activationsByState`.
- WHEN the prefetch guard is moved below the activation dispatch THEN the test
  SHALL fail.

### Item 4 — `MCP_PATH=/` cannot shadow the MCP mount

- IF `MCP_PATH` trims to the empty string under `strings.Trim(v, "/")` THEN
  `config.Load` SHALL return an error naming `MCP_PATH`, and the server SHALL
  refuse to start.
- WHILE `cfg.MCPPath` trims to empty (a caller that constructed `Config`
  directly, bypassing `Load`) THE SYSTEM SHALL NOT register the `POST /` hint
  route.
- WHEN `MCP_PATH` is unset or any ordinary value (`/mcp`, `mcp`, `/v1/mcp`) THE
  SYSTEM SHALL behave exactly as today.

### Item 5 — consistent `Allow` on `/`

- WHEN a `POST /` reaches `RootPostHint` THE SYSTEM SHALL answer 405 with an
  `Allow` header whose method set is exactly `{GET, POST}`.
- WHEN `PUT /`, `DELETE /` or `HEAD /` reaches a chi router with both `GET /`
  and `POST /` registered THE SYSTEM SHALL answer 405 with the same `Allow`
  method set, and a test SHALL assert that set order-insensitively.
- WHILE this changes THE SYSTEM SHALL keep the 405 status, the
  `Cache-Control: no-store` header, the `application/json` content type and the
  JSON-RPC `-32600` body of `RootPostHint` unchanged.

### Item 6 — `expired_state` reachable on the DB-backed pending store

- WHEN `ConsumeOAuthPending` is called with a state whose row exists but whose
  `created_at` is older than `ttl` THE SYSTEM SHALL return an error that
  satisfies `errors.Is(err, db.ErrOAuthExpired)`.
- WHILE that error is returned THE SYSTEM SHALL also satisfy
  `errors.Is(err, db.ErrOAuthNotFound)`, so every existing caller
  (`internal/oauth/demo_login.go:187`, `internal/oauth/server.go:865`, `:2072`,
  `:3123`) keeps its current behaviour with no edit.
- WHEN a state was never issued THE SYSTEM SHALL return `db.ErrOAuthNotFound`
  and SHALL NOT satisfy `errors.Is(err, db.ErrOAuthExpired)`.
- WHEN `handleTelegramCallback` runs with `useDB` true and the pending row is
  expired THE SYSTEM SHALL log `reason=expired_state`; when it is absent, THE
  SYSTEM SHALL log `reason=unknown_state`. Both SHALL render the existing
  reused-link page.
- WHILE consuming an expired row THE SYSTEM SHALL still delete it, so the state
  stays single-use.

### Item 7 — prefetch guard: declared and documented limits

- WHEN either prefetch guard answers 204 (`internal/web/connect.go`
  `HandleConnectDone`, `internal/oauth/server.go` `handleTelegramCallback`) THE
  SYSTEM SHALL set `Vary: Sec-Purpose, Purpose` alongside the existing
  `Cache-Control: no-store`.
- THE SYSTEM SHALL document, in the doc comment of both `isPrefetch` helpers,
  that Safari sends no prefetch-purpose header and that Firefox's legacy
  `X-moz: prefetch` is not matched, so the guard is best-effort.

### Item 8 — vocabulary hygiene

- WHEN the Telegram OIDC token exchange fails in `handleTelegramCallback` THE
  SYSTEM SHALL log `reason` from a named const `reasonExchangeFailed` declared
  in `internal/oauth/server.go`, and a test SHALL assert the emitted line
  carries `reason=exchange_failed`.
- THE SYSTEM SHALL keep the `prefetch` attribute on `logConnectReject` and
  `logCallbackReject` as a documented schema-stability guarantee (one comment
  stating it is always false by construction and retained so a single
  `prefetch=` query matches every line of both routes), and a test in each
  package SHALL assert the attribute is present on a reject line.
- THE SYSTEM SHALL carry a one-line comment on `friendlyErr`'s bad-password arm
  naming the live path that supersedes it (`handleEnablePassword` renders
  `badPasswordRestartMsg`) and the test that keeps it live
  (`internal/oauth/enable_access_friendly_test.go`).

### Item 9 — runbook

- THE SYSTEM's `docs/runbook.md` SHALL list every reason token the two routes
  emit — `missing_state`, `missing_code`, `unknown_state`, `expired_state`,
  `exchange_failed`, `oidc_error`, `prefetch_refused` and the new
  `recovered_redirect` — each with its meaning and first operator action, under
  a section reachable from the table of contents and carrying an HTML anchor.
- THE SYSTEM's `docs/runbook.md` SHALL document the startup headline
  `auth provider init failed` (`cmd/server/main.go:437`) and that the process
  refuses to start.
- WHEN a new `reason*` const is added to `internal/web/connect.go` or
  `internal/oauth/server.go` without being added to the runbook THEN a doc test
  SHALL fail.

## Out of scope

- Adding a rate limiter to `/telegram/connect/done` or
  `/oauth/telegram/callback`. The existing `audit.RateLimiter.Middleware()`
  (`internal/audit/ratelimit.go:132`) is keyed by authenticated identity, so it
  does not apply to these unauthenticated routes; an IP-keyed limiter is a
  separate design with its own proxy-header trust question.
- Demoting `unknown_state` to Debug. Item 2 is satisfied by not logging a
  failure on a successful request; the level of the genuine failure arm stays
  WARN so existing alerting is untouched.
- Detecting Firefox's `X-moz: prefetch` or any other prefetch signal. Item 7
  asks for documentation of the limit, not a wider guard.
- Splitting the TTL case in `ConsumeOAuthCode` or `ConsumeOAuthRefresh`. Only
  `ConsumeOAuthPending` feeds a `reason` label.
- Any change to `finishActivation`, the Local Bridge activation flow, PKCE
  handling, token TTLs, or the DB schema.
- Deduplicating the two copies of the reason-const block. The duplication is
  deliberate (`internal/web` must not import `internal/oauth`; see the comment
  at `internal/web/connect.go:48-50`) and item 9's doc test is what keeps them
  honest.

## Open questions

- Item 4 chooses a hard `config.Load` error for `MCP_PATH=/` over silently
  falling back to `/mcp`. A hard failure matches how `Load` already treats
  `MCP_TOOL_FILTER` and `ENCRYPTION_KEY` (`internal/config/config.go:445`,
  `:522`), and an operator who set `MCP_PATH=/` has no working deployment
  either way — but it does turn a currently-booting misconfiguration into a
  refusal to start. Proceeding with the hard error plus the belt-and-braces
  registration guard.
- Item 2 uses `recovered_redirect` as the new token. The issue offers "log
  after the check" as an alternative that emits nothing on the redirect arm.
  Proceeding with the explicit token, because a silent success arm makes the
  redirect unattributable when a user reports it.
- Item 8's `prefetch` attribute: the issue allows either dropping it or
  documenting it. Documenting is chosen because dropping changes a log schema
  operators may already query and because the acceptance criterion ("a test
  that fails when the change is reverted") is satisfiable either way.
- Item 6's Postgres-backed test requires `TEST_DATABASE_URL`; it skips
  otherwise, exactly like the existing `db-backed` subtest at
  `internal/oauth/server_test.go:934`. That means CI without a database proves
  the new branch only through the in-memory path and the `internal/db` unit
  test. Accepted, consistent with the repo's current posture.
- Item 5's chi-side `Allow` value: chi builds the header from its internal
  method map, so the string order is not contractual. The test asserts the
  parsed method set, not the literal string.
