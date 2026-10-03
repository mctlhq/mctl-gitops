# Design: issue-701-connect-oauth-follow-ups-from-698-review

## Current state

### The three-step hosted login handlers (`internal/oauth/enable_access.go`)

`handleEnableStart`, `handleEnableCode` and `handleEnablePassword` each end in a
`select` over the login goroutine's channels. On `<-lf.done` with `lf.err != nil`
each writes an audit row `connect:failed:<shortReason(err)>` and renders a page.

- `handleEnableStart` (lines 791-845) computes `reason := shortReason(lf.err)`
  once, builds `msg := "Telegram rejected the request: " + friendlyErr(lf.err) +
  " Try again."`, then overrides it when `reason == "auth_restart"` with bare
  `friendlyErr(lf.err)` — the guard #698 added, with the comment "AUTH_RESTART is
  not a rejection and friendlyErr already carries the full instruction; the
  generic wrapper would frame it twice" (lines 834-839).
- `handleEnableCode` (lines 938-953) does **not** compute `reason` into a
  variable; it inlines `shortReason(lf.err)` in the audit call and then renders
  `"The code was not accepted: " + friendlyErr(lf.err) + " Start again to get a
  fresh code."` (line 950) for everything that is not
  `db.ErrAccountModeConflict`. `friendlyErr(AUTH_RESTART)` is `"Telegram ended
  the sign-in session. Submit your phone number again to get a fresh code."`
  (line 1169), so the rendered sentence is the triple-clause string quoted in
  the issue.
- `handleEnablePassword` (lines 1026-1060) computes `reason`, special-cases
  `db.ErrAccountModeConflict` (terminal) and `reason == "bad_password"` (renders
  `badPasswordRestartMsg`), and falls back to `"The password was not accepted: "
  + friendlyErr(lf.err) + " Start again."` — the same double-framing for
  `AUTH_RESTART`.

`AUTH_RESTART` is mapped in both `friendlyErr` (line 1168) and `shortReason`
(line 1211). Existing coverage lives in
`internal/oauth/enable_access_classification_test.go`: line 49 pins the
`shortReason` mapping, line 67 the `friendlyErr` string, and lines 167-203 pin
the **phone step** page (asserting the absence of the double wrapper and the
presence of the audit entry `connect:failed:auth_restart`). There is no
equivalent at the code or password step.

### `/telegram/connect/done` (`internal/web/connect.go`)

`HandleConnectDone` (line 239) refuses prefetches first (lines 243-251: Info log
with `reasonPrefetchRefused`, `Cache-Control: no-store`, 204), then validates
`error`/`code`/`state`, then consumes `s.sessions[state]` under the mutex. The
failure arm (lines 281-293) is:

```go
if !ok || s.clock().Sub(sess.createdAt) > s.codeTTL {
        reason := reasonUnknownState
        if ok { reason = reasonExpiredState }
        logConnectReject(r, reason)          // <-- logged before the recovery check
        if s.alreadyConnected(r) {
                http.Redirect(w, r, "/telegram/connect/manage", http.StatusSeeOther)
                return
        }
        renderConnectReused(w, s.issuer+"/telegram/connect")
        return
}
```

`logConnectReject` (line 76) is `slog.Warn` with `route`, `reason` and
`prefetch: isPrefetch(r)`. Because the prefetch guard returns at line 250, that
boolean is always `false` on this line. The reason consts are at lines 51-59 and
include `reasonExchangeFailed`, used at line 299 on the exchange failure.
`alreadyConnected` (line 175) is nil-safe.

### `/oauth/telegram/callback` (`internal/oauth/server.go`)

`handleTelegramCallback` (line 1557) mirrors the structure: prefetch guard (1562),
`state` presence (1574), **Local Bridge activation dispatch** (1585-1617), then
the pending consume (1621-1665). On the `useDB` branch (1622-1633) a
`db.ErrOAuthNotFound` logs `reasonUnknownState`; only the in-memory branch has an
`else` with a real TTL check that can reach `reasonExpiredState` (1660-1664).
The const block (1523-1530) lacks `exchange_failed` — line 1690 uses the bare
literal `"exchange_failed"` — and carries a "Known limit" comment (1518-1522)
stating precisely the gap item 6 closes.

### `db.Store.ConsumeOAuthPending` (`internal/db/store_oauth.go:182`)

```go
cutoff := time.Now().UTC().Add(-ttl)
err := s.DB.QueryRowContext(ctx,
        `DELETE FROM oauth_pending_auth
          WHERE state = $1 AND created_at >= $2
        RETURNING ...`, state, cutoff).Scan(...)
if errors.Is(err, sql.ErrNoRows) { return nil, ErrOAuthNotFound }
```

The `created_at >= $2` predicate is what collapses the two cases: an expired row
does not match, so `sql.ErrNoRows` is indistinguishable from "no such state".
`ErrOAuthNotFound` (line 15) is checked by four other call sites
(`internal/oauth/demo_login.go:187`, `internal/oauth/server.go:865`, `:2072`,
`:3123`), so its identity must not change.

### `POST /` and the `Allow` header

`cmd/server/main.go:409-410` registers `mux.Get("/", web.Landing(...))` and
`mux.Post("/", web.RootPostHint(cfg.MCPPath))` unconditionally. `RootPostHint`
(`internal/web/landing.go:130`) normalises `mcpPath` to a leading slash, then
sets `Allow: GET` with the comment "Only GET / is registered (no GetHead
middleware), so that is the list" — which stopped being true the moment
`POST /` was registered on the next line. `cfg.MCPPath` comes from
`envOr("MCP_PATH", "/mcp")` (`internal/config/config.go:347`) with no
validation; `Load` (line 342) already returns errors for other invalid env
values (lines 445, 458, 522). `MCPPath` is also used for the
`/.well-known/oauth-protected-resource` alias (main.go:404) and the MCP mount
(`mux.Mount(cfg.MCPPath, ...)`, main.go:650), so `/` breaks more than the hint
route — but the hint route is the one that answers with a misleading 405.

### The vacuous prefetch test (`internal/oauth/server_test.go:1038`)

`TestHandleTelegramCallback_PrefetchDoesNotConsumeState` seeds an activation at
`act.oidcState = "prefetch-test-activation-state"` (line 1054) but sends both
prefetch requests with `state` — the `pendingAuth` state from
`stateFromAuthorize` (line 1060, 1065). The assertion at line 1074 that
`activationsByState[act.oidcState]` is still indexed therefore cannot fail: no
request ever named that key. `callbackWithStateHeaders` (line 880) already takes
an arbitrary state string, so the fix needs no new helper.

### Runbook

`docs/runbook.md` is anchor-per-alert with a table of contents at line 20 and a
Go doc test at `docs/runbook_test.go` (`TestRunbookAnchorsPresent`,
`TestRunbookMetricNamesRegistered`). The connect/callback `reason` vocabulary
appears nowhere. `internal/oauth/troubleshooting_doc_test.go` is the in-package
precedent for pinning a doc against real symbols.

## Proposed solution

Nine independent edits, grouped by file. Nothing shares state; each can be
reverted alone.

### 1. One framing helper for all three step handlers

Add to `internal/oauth/enable_access.go`, next to `friendlyErr`:

```go
// framedLoginErr renders a login failure for a step page, wrapping
// friendlyErr in prefix/suffix except for AUTH_RESTART, which friendlyErr
// already renders as a complete instruction ("Telegram ended the sign-in
// session. Submit your phone number again to get a fresh code."). Wrapping
// that both misattributes the failure to the step the user just completed and
// repeats the instruction. Telegram raises AUTH_RESTART from auth.signIn, so
// the code step is the step that actually sees it.
func framedLoginErr(prefix string, err error, suffix string) string {
        if shortReason(err) == "auth_restart" {
                return friendlyErr(err)
        }
        return prefix + friendlyErr(err) + suffix
}
```

Then:

- `handleEnableStart` (line 833-839) becomes
  `msg := framedLoginErr("Telegram rejected the request: ", lf.err, " Try again.")`,
  deleting the inline guard. Byte-identical output for every input, pinned by
  the existing test at `enable_access_classification_test.go:167-203`.
- `handleEnableCode` (line 948-951) renders
  `framedLoginErr("The code was not accepted: ", lf.err, " Start again to get a fresh code.")`.
- `handleEnablePassword` (line 1056-1059) renders
  `framedLoginErr("The password was not accepted: ", lf.err, " Start again.")`.
  Its `reason == "bad_password"` and `ErrAccountModeConflict` arms are untouched
  and keep returning before this line.

`shortReason` is called twice per failure in the code step after this change
(once for the audit label, once inside the helper). That is a pure-function
string comparison on an already-materialised error; no measurable cost, and it
keeps the three call sites symmetric. The `"auth_restart"` literal stays a
literal because `shortReason` itself has no const for it; introducing one is
gold-plating in a P3 change.

### 2. Log the connect failure after the recovery check

In `internal/web/connect.go`, add `reasonRecoveredRedirect = "recovered_redirect"`
to the const block and restructure the arm:

```go
if !ok || s.clock().Sub(sess.createdAt) > s.codeTTL {
        if s.alreadyConnected(r) {
                // Not a failure: the browser still holds a valid
                // mctl_connect_token, so a reopened single-use link lands on
                // /manage. Logged at Info under its own reason so the
                // unknown_state count keeps measuring only real failures.
                slog.Info("connect: request recovered",
                        "route", "/telegram/connect/done",
                        "reason", reasonRecoveredRedirect,
                        "prefetch", isPrefetch(r))
                http.Redirect(w, r, "/telegram/connect/manage", http.StatusSeeOther)
                return
        }
        reason := reasonUnknownState
        if ok {
                reason = reasonExpiredState
        }
        logConnectReject(r, reason)
        renderConnectReused(w, s.issuer+"/telegram/connect")
        return
}
```

`alreadyConnected` moves before the reason computation but its own WARN
("session credential rejected on reused link", line 186) is unchanged, so a
sent-and-rejected credential is still attributable *and* still lands on the
`unknown_state`/`expired_state` arm.

### 3. Send the callback prefetch with the activation state

In `internal/oauth/server_test.go`, keep the two existing prefetch requests
(they prove the pending state survives) and add two more sent with
`act.oidcState`. The `stillIndexed` assertion then has a request that actually
named the key. A comment records why both states are exercised.

### 4. Reject `MCP_PATH=/`

In `internal/config/config.go`, after `MCPPath` is read, add:

```go
if strings.Trim(c.MCPPath, "/") == "" {
        return nil, fmt.Errorf("MCP_PATH must name a path below the origin, got %q: "+
                "mounting MCP at the root would shadow the landing page and the POST / hint route", c.MCPPath)
}
```

and in `cmd/server/main.go`, guard the registration so a `Config` built
directly in a test or another binary cannot reintroduce the shadow:

```go
if strings.Trim(cfg.MCPPath, "/") != "" {
        mux.Post("/", web.RootPostHint(cfg.MCPPath))
}
```

Both, not one: `Load` is the single place an operator's typo is caught, and the
guard is the place a programmatic `Config` is caught. `strings` is already
imported in both files.

### 5. `Allow: GET, POST` on the root

In `internal/web/landing.go`, `RootPostHint` sets
`w.Header().Set("Allow", "GET, POST")` and its comment is corrected to say that
`POST /` is registered alongside `GET /` (main.go:409-410), so chi's own 405 for
`PUT`/`DELETE`/`HEAD` lists both and this handler must agree. Listing `POST` in
`Allow` while answering 405 to `POST` is intentional: the method *is* routed,
this handler just refuses it with a hint, and RFC 9110 15.5.6 asks for the
methods the *target resource* supports, which is what chi reports.

### 6. Split the TTL case in the pending store

In `internal/db/store_oauth.go`:

```go
// ErrOAuthExpired is returned by ConsumeOAuthPending when the row existed but
// was older than the caller's ttl. It wraps ErrOAuthNotFound so every existing
// errors.Is(err, ErrOAuthNotFound) caller is unaffected; check ErrOAuthExpired
// FIRST when the two need distinguishing.
var ErrOAuthExpired = fmt.Errorf("oauth: expired: %w", ErrOAuthNotFound)
```

`ConsumeOAuthPending` drops `AND created_at >= $2` from the `DELETE` and does
the TTL comparison in Go on the returned `created_at`:

```go
err := s.DB.QueryRowContext(ctx,
        `DELETE FROM oauth_pending_auth WHERE state = $1 RETURNING ...`, state).Scan(...)
if errors.Is(err, sql.ErrNoRows) { return nil, ErrOAuthNotFound }
if err != nil { return nil, fmt.Errorf("consume oauth_pending_auth: %w", err) }
if p.CreatedAt.Before(cutoff) { return nil, ErrOAuthExpired }
```

Atomicity and single-use are preserved — it is still one `DELETE ... RETURNING`.
The one behavioural change is that an expired row is now deleted on the attempt
rather than waiting for the sweeper; that is strictly better (the row was
unusable) and means a second replay of the same expired state reports
`unknown_state`. Documented in the method's doc comment.

In `internal/oauth/server.go`'s `useDB` branch, check the expired case first:

```go
if errors.Is(err, db.ErrOAuthExpired) {
        logCallbackReject(r, reasonExpiredState)
        renderEnableReused(w, ...)
        return
}
if errors.Is(err, db.ErrOAuthNotFound) {
        logCallbackReject(r, reasonUnknownState)
        ...
}
```

and the stale "Known limit" paragraph at lines 1518-1522 is replaced with a
sentence saying both stores now distinguish the two. `internal/oauth/demo_login.go:187`
keeps its single `ErrOAuthNotFound` check and keeps working through the wrap.

### 7. `Vary` on the prefetch refusals, and documented limits

Both 204 arms (`internal/web/connect.go:248`, `internal/oauth/server.go:1567`)
gain `w.Header().Set("Vary", "Sec-Purpose, Purpose")` — one `Set`, not two
`Add`, to avoid the duplicate-token bug `internal/auth/middleware.go:256`
already records. Both `isPrefetch` doc comments gain:

> Best-effort. Safari sends no prefetch-purpose header at all, and Firefox's
> legacy `X-moz: prefetch` is not matched, so a 204 here proves a prefetch but
> a 200 does not prove a real navigation.

### 8. Vocabulary hygiene

- `reasonExchangeFailed = "exchange_failed"` joins the const block in
  `internal/oauth/server.go` and replaces the literal at line 1690; the block
  comment's "connect.go additionally has exchange_failed" sentence is dropped.
- `logConnectReject` / `logCallbackReject` doc comments gain: "`prefetch` is
  always false here — the guard above returns 204 before any reject path — and
  is retained deliberately so one `prefetch=` query matches every line both
  routes emit."
- `friendlyErr`'s `isBadPasswordErr` arm gains: "Live 2FA rejections never reach
  this arm: `handleEnablePassword` renders `badPasswordRestartMsg` instead,
  because the login goroutine has already exited. Kept for `friendlyErr`'s own
  contract and pinned by `enable_access_friendly_test.go`."

### 9. Runbook section plus a doc test per package

A new `## Connect and OAuth callback rejection reasons` section in
`docs/runbook.md` with `id="connectrejectionreasons"`, linked from the table of
contents, containing a table of the eight tokens (route that emits it, level,
meaning, first action) and a short "Startup failures" subsection for
`auth provider init failed` (`cmd/server/main.go:437`) noting that the process
exits rather than serving degraded.

Two doc tests, modelled on `internal/oauth/troubleshooting_doc_test.go`, iterate
each package's own const slice and assert every value appears in
`../../docs/runbook.md`: `TestRunbookDocumentsConnectReasons` in `internal/web`
(the seven consts plus `reasonRecoveredRedirect`) and
`TestRunbookDocumentsCallbackReasons` in `internal/oauth` (its six plus
`reasonExchangeFailed`). Keeping one test per package means a new const added on
either side fails in its own package, which is the only mechanism that keeps the
two deliberately-duplicated blocks and the doc in sync.

## Alternatives

**Item 1: duplicate the `reason == "auth_restart"` guard at each site instead of
extracting `framedLoginErr`.** Exactly what the issue literally asks for, and a
smaller diff. Dropped because the guard would then exist three times with three
chances to drift, and the extraction leaves the phone step's output provably
unchanged while making the next special case a one-line edit in one place.

**Item 2: move `logConnectReject` below the check and emit nothing on the
redirect arm.** Smallest possible diff, and the issue's first suggestion.
Dropped because a successful-but-unusual path that logs nothing is
unattributable when a user reports "it sent me to manage"; the explicit
`recovered_redirect` token costs one const and one Info line.

**Item 6: keep the SQL predicate and issue a second `SELECT` on the not-found
path to ask whether the row merely expired.** Dropped: two round trips, and it
is racy against the sweeper — the row can vanish between the `DELETE` and the
`SELECT`, silently reporting `unknown_state` again. **Or:** add a separate
`ConsumeOAuthPendingExpiring` method and leave the existing one alone. Dropped
as pure duplication: the wrapped sentinel gives every existing caller identical
behaviour with no signature change.

**Item 4: normalise `MCP_PATH=/` to `/mcp` with a WARN instead of failing
`Load`.** Dropped because silently serving MCP somewhere other than where the
operator configured it is worse than not starting, and `Load` already refuses on
`MCP_TOOL_FILTER`, `OAUTH_ACCESS_TOKEN_TTL` and `ENCRYPTION_KEY`. Recorded in
requirements' Open questions.

**Item 5: a custom chi `MethodNotAllowed` handler for the root so `PUT /` also
returns the JSON-RPC hint.** Dropped as larger than the problem: chi's
`MethodNotAllowed` is router-wide, so scoping it to `/` means a sub-router or a
path check, and the issue only asks the two `Allow` values to agree.

## Platform impact

- **Migrations:** none. No schema change; `oauth_pending_auth` is read and
  deleted exactly as today.
- **Backward compatibility (API/HTML):** no route, status code or redirect
  changes. Two user-visible strings change, both only for `AUTH_RESTART`. The
  `Allow` header on `/` gains `POST`; MCP clients key on the 405 status and the
  JSON-RPC body, both unchanged.
- **Backward compatibility (logs):** `reason=recovered_redirect` is a new token
  on `/telegram/connect/done`; `reason=expired_state` starts appearing on
  `/oauth/telegram/callback` in Postgres deployments where previously only
  `unknown_state` did. Any dashboard that treated `unknown_state` as "all
  callback state failures" will under-count after this change. Mitigation: the
  runbook section documents the full closed set and the change, and both tokens
  were already declared consts before this change.
- **Backward compatibility (config):** `MCP_PATH=/` becomes a startup failure.
  No known deployment sets it (`deploy/` and the GitOps values use `/mcp`), and
  such a deployment is already broken. Mitigation: the error message names the
  variable and the reason.
- **Resource impact:** nil. One extra `shortReason` call per failed login step,
  one extra response header on two 204 paths, one fewer SQL predicate.
- **Risks:**
  - *`framedLoginErr` changes the phone step's wording.* Mitigated by the
    existing pinning test (`enable_access_classification_test.go:167-203`) plus
    a table test over all three prefixes.
  - *The expired-row-now-deleted change in `ConsumeOAuthPending` surprises a
    caller that relied on a second attempt still finding the row.* Grep shows
    only two callers (`server.go:1623`, `demo_login.go:186`), neither retries.
  - *Item 6's Postgres test skips without `TEST_DATABASE_URL`, so CI may not
    exercise the new branch.* Mitigated by an `internal/db` unit test of
    `ConsumeOAuthPending` (same skip, but a much narrower assertion) and by the
    `errors.Is` wrap test, which needs no database at all.
  - *The runbook doc tests couple `internal/web` and `internal/oauth` to a file
    two directories up.* Already the established pattern
    (`internal/oauth/troubleshooting_doc_test.go`); the failure mode is a clear
    test message, not a runtime break.
