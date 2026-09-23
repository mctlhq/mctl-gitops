# Design: issue-668-feat-observability-audit-rejected-client

## Current state

### 1. `/oauth/register` — `internal/oauth/server.go`

`handleClientRegistration` (line 2561) has a rate-limit gate, then a decode,
then five validation gates, then persistence. It writes exactly two audit
lines:

- line 2567: `slog.Info("oauth: client_registration audit", "outcome", "rate_limited")`
- line 2703: `slog.Info("oauth: client_registration audit", "outcome", "accepted", "client_name", …, "redirect_uri_count", …)`

Every other exit is a bare `writeTokenError(...)` and returns silently:

| line | condition | error code |
|---|---|---|
| 2585 | body will not JSON-decode | `invalid_client_metadata` |
| 2609/2617 | re-marshal or typed decode fails | `invalid_client_metadata` |
| 2621 | `len(RedirectURIs) == 0` | `invalid_client_metadata` |
| 2625 | over `MaxRedirectURIs` | `invalid_client_metadata` |
| 2630 | URI over `MaxRedirectURILength` | `invalid_redirect_uri` |
| 2643 | `validateImplicitRedirectURI` refused | `invalid_redirect_uri` |
| 2661 | `InsertClientReg` failed | `server_error` |

There *is* a per-request `oauth: client_registration request` INFO line
(line 2599) carrying `user_agent`, `keys`, `client_name`,
`redirect_uri_count` and `scope_in_request`, which is why the 464 Cursor
calls were countable at all — but it is emitted *before* validation and so
never says what happened next.

The refusal itself comes from two pure functions:
`validateRedirectURIShape` (line 2787) rejects backslashes, unparseable
URLs, userinfo, and any scheme that is not `https` or `http`-on-loopback;
`validateImplicitRedirectURI` (line 2753) then applies the
`AllowedImplicitHosts` allowlist with a loopback exception. Both return a
`fmt.Errorf`/`errors.New` free-text string, one of which embeds the raw
`redirect_uri` (line 2798: `redirect_uri %q is not a valid URL`). That
string is already returned to the caller as `error_description`, but is not
safe to use verbatim as a metric label or as a log field, for two separate
reasons — unbounded cardinality and, on line 2798, the raw URI.

### 2. `auth failed` — `internal/auth/middleware.go`

Line 96: `slog.Warn("auth failed", "err", err)`. That is the entire line.
Two lines later, `m.AuthFailuresTotal.WithLabelValues(classifyAuthError(err.Error()), providerLabel).Inc()`
already counts the failure with a nine-value closed `reason` set
(`jwt_expired`, `jwt_invalid_signature`, `jwt_invalid_issuer`,
`jwt_missing_audience`, `jwt_wrong_audience`, `token_revoked`,
`bearer_scheme_error`, `no_token`, `other`) and a `provider` label. **The
counter the issue asks for in item 2 already exists.**

The attribution gap is structural: `auth.Provider` is
`Authenticate(*http.Request) (*Identity, error)`
(`internal/auth/identity.go:69`), so a rejected request yields an error
string and nothing else. The claims exist — `localjwt.Verify`
(`internal/auth/localjwt/issuer.go:143`) parses them — but they are dropped
on the error return.

The ordering inside `Verify` matters and is the security hinge of this
change:

```
line 152  hmac.Equal(...)            -> "invalid JWT signature"
line 155  base64 decode payload      -> "malformed JWT payload"
line 160  json.Unmarshal into Claims -> "malformed JWT payload"
line 164  c.Issuer != expectedIssuer -> "unexpected JWT issuer: %q"
line 167  now > c.ExpiresAt          -> "JWT expired"
line 170  audienceList(...)          -> "invalid audience claim"
```

Everything at or above line 155 is an *unauthenticated* payload: an attacker
picks `sub`, `client_id` and `jti` freely. Only failures at line 164 and
below — plus `CheckAudience` (line 199) and the revocation check
(`Authenticate`, line 296) — concern claims the server's own HMAC key
vouched for. Any design that logs claims from a signature-failed token turns
the log into an attacker-writable channel.

`Claims` (line 31) already carries `Subject`, `ClientID`, `Jti`, `ExpiresAt`
— all four fields the issue asks for. `edgectx.FromRequest(r)`
(`internal/edgectx/edgectx.go:75`) reads `Cf-Ray` and `Cf-Worker` straight
off the request headers, so the middleware can obtain `edge_request_id` and
`edge_route` without depending on any earlier middleware having populated
the context.

The `sharedhmac` provider (`internal/auth/sharedhmac/verifier.go:118`) has
the same shape and the same gap.

### 3. The digest — `internal/digest/digest.go`

`runDigest` (line 68) calls `store.ListIdentities(qctx)` once, filters to
rows with `CreatedAt` inside the 24 h `lookback`, and hands them to
`buildDigestMessage` (line 158). Line 172:

```go
session := "no session"
if r.HasSession { session = "session active" }
```

`db.IdentityRow` (`internal/db/store.go:290`) carries `TelegramID` but not
the internal `users.id`, and `ListIdentities` (line 427) resolves
`HasSession` with an `EXISTS` subquery over `telegram_accounts` — it never
touches `audit_logs`.

The onboarding steps the issue wants to surface are already being written.
`LogToolCall(ctx, uid, "connect:<step>", …)` is called from seventeen sites
in `internal/oauth/enable_access.go` and `internal/oauth/server.go:1765`:
`connect:oidc_callback`, `connect:phone_submitted`, `connect:code_submitted`,
`connect:2fa_submitted`, `connect:success`, `connect:demo_reviewer`, and
`connect:failed:<shortReason>` where `shortReason`
(`enable_access.go:1083`) maps to a closed set — `timeout`, `flood_wait`,
`phone_invalid`, `code_invalid`, `code_expired`, `local_mode_active`,
`identity_mismatch`, `identity_cleanup_timeout`, `mode_check`, `unknown`.
These are exactly the three stories the issue describes, already in the
table, already distinguishable. Nothing reads them back except
`ListAuditFor` (`internal/db/store.go:1469`), which is per-user and
user-facing.

`telegram_accounts` (`internal/db/db.go:551`) has `revoked_at` but **no
`revoked_reason`** — that column exists on `oauth_refresh_tokens`
(`db.go:594`) and `local_bridge_devices` (`db.go:627`).
`RevokeSessionByID` (`store.go:899`) takes a `reason` parameter and uses it
only as a `SessionsRevokedTotal` label before discarding it.

### 4. Abandoned onboarding — `internal/oauth/enable_access.go`

`startLoginFlow` (line 115) builds a `loginFlow` and a
`context.WithTimeout(context.Background(), s.cfg.CodeTTL)`. The goroutine's
deferred logger (line 160-171) is a two-arm branch:

```go
if lf.err != nil {
    slog.Error("enable: telegram login failed", "uid", uid, "want_tg_id", wantTgID,
        "elapsed", …, "err", lf.err)
} else {
    slog.Info("enable: telegram login succeeded", …)
}
```

`askCode`/`askPassword` (lines 126, 138) park on `lf.codeCh`/`lf.pwCh` and
return `ctx.Err()` when `bgCtx` expires — so a user who walks away produces
`context.DeadlineExceeded` wrapped by `telegram.Login`, surfacing as the
`query session: context canceled` / `elapsed=29m57s` ERROR in the issue.

Supersession collapses into the same errors: `es.flow.cancel()` is called at
lines 516 and 704 when a `/start` re-submission replaces a live flow, and
the comment at line 726 says so explicitly — "a superseded flow surfaces
here as context.DeadlineExceeded/Canceled". So error-value inspection alone
cannot separate "walked away" from "started over", and the current code
logs both at ERROR.

## Proposed solution

Four independent, additive changes. Nothing in the request path, the auth
decision, the OAuth policy or the digest schedule moves.

### A. `internal/oauth/registration_audit.go` (new file, same package)

A small closed-vocabulary classifier plus one emit helper, so every exit in
`handleClientRegistration` becomes a two-line change rather than a bespoke
`slog` call:

```go
// regReason is a closed set of registration-outcome tokens. Values are
// compile-time constants so a client-supplied error string can never
// become a Prometheus label and blow up cardinality.
type regReason string

const (
    regOK                   regReason = "ok"
    regRateLimited          regReason = "rate_limited"
    regMalformedBody        regReason = "malformed_body"
    regNoRedirectURIs       regReason = "no_redirect_uris"
    regTooManyRedirectURIs  regReason = "too_many_redirect_uris"
    regRedirectTooLong      regReason = "redirect_uri_too_long"
    regSchemeNotAllowed     regReason = "redirect_scheme_not_allowed"
    regHostNotAllowed       regReason = "redirect_host_not_allowed"
    regUserinfo             regReason = "redirect_userinfo"
    regBackslash            regReason = "redirect_backslash"
    regUnparseable          regReason = "redirect_unparseable"
    regPersistFailed        regReason = "persist_failed"
)
```

Rather than string-matching the free-text errors back into tokens — brittle,
and the hard-won lesson of `classifyAuthError` is that string matching only
works when the producer's literals are stable and local — the validators
gain typed sentinel errors (`errRedirectBackslash`, `errRedirectUserinfo`,
`errRedirectScheme`, and a wrapped `errRedirectHost`) and the classifier
uses `errors.Is`. `validateRedirectURIShape`'s existing free-text messages
stay exactly as they are on the wire, so the `error_description` contract to
clients is unchanged; only the wrapping is new.

`redirectOrigin(raw string) (scheme, host string)` parses the URI with
`url.Parse` and returns `u.Scheme` and `u.Hostname()` — never the path,
query or fragment, and `("", "")` when the parse fails. `Hostname()` rather
than `Host` deliberately drops the port, matching the "scheme and host only"
wording of the issue and keeping the field's cardinality low.

`auditRegistration(m *metrics.Registry, outcome string, reason regReason, clientName, userAgent, scheme, host string)`
emits the single `oauth: client_registration audit` line and increments the
counter, so producer and consumer can never diverge on the label set. The
existing accepted/rate-limited sites are routed through it too — the
resulting lines keep their current attributes, gaining only `reason`.

`user_agent` is logged as received. It is already logged verbatim at line
2600 on the request line, so this introduces no new class of data; it is
attacker-controlled free text, which is precisely why it is a *log attribute*
and never a *metric label*.

### B. `internal/metrics` — one new family

```go
// OAuthClientRegistrationsTotal counts /oauth/register outcomes, labeled by
// outcome (accepted, rejected, rate_limited, error) and reason. Both label
// values come from a closed compile-time set in internal/oauth — never from
// a client-supplied string.
OAuthClientRegistrationsTotal *prometheus.CounterVec
```

registered as `mctl_oauth_client_registrations_total`. The `mctl_` (not
`mctl_telegram_`) prefix follows the convention already established by
`mctl_oauth_pending_auth_size` and `mctl_auth_failures_total`; see
requirements.md's open question. Worst-case cardinality is 4 outcomes x 12
reasons = 48 series, and in practice far fewer since most pairs are
unreachable.

No second auth-failure counter is added: `mctl_auth_failures_total{reason,provider}`
already covers item 2.

### C. `internal/auth` — attributed failures

New file `internal/auth/attribution.go`:

```go
// TokenAttribution carries the identifying claims of a token that VERIFIED
// its signature but was then rejected. Every field is safe to log: none is
// a secret, and all four were vouched for by this service's own HMAC key.
type TokenAttribution struct {
    Subject   string
    ClientID  string
    Jti       string
    ExpiresAt int64
}

// AttributedError wraps a post-signature verification failure with the
// claims that produced it. Providers MUST NOT construct one for a failure
// at or before the signature check: those claims are attacker-controlled.
type AttributedError struct {
    Attr TokenAttribution
    Err  error
}

func (e *AttributedError) Error() string { return e.Err.Error() }
func (e *AttributedError) Unwrap() error { return e.Err }

// AttributionOf extracts the attribution from err, if any.
func AttributionOf(err error) (TokenAttribution, bool)
```

`Unwrap` is what keeps this free: `classifyAuthError` operates on
`err.Error()`, which `AttributedError` forwards unchanged, so every existing
`reason` label and every `errors.Is` check at any call site keeps working
byte-for-byte.

In `localjwt`, `Verify` keeps its exact signature and behaviour; a new
`VerifyWithClaims(token string, secret []byte, expectedIssuer string) (*Claims, error)`
becomes the primitive, returning `(claims, err)` with **non-nil claims only
for failures after line 160's successful unmarshal**, and `Verify` becomes a
two-line wrapper that nils the claims on error. Existing callers of `Verify`
are untouched. `Provider.Authenticate` (line 253) switches to
`VerifyWithClaims` and wraps the three post-signature failure paths — the
`Verify` error, `CheckAudience`, and the revocation check — in
`&auth.AttributedError{Attr: attrFrom(c), Err: err}`. `attrFrom` copies only
the four fields; `TelegramUsername` and `Groups` are deliberately not
carried.

`sharedhmac` gets the identical treatment for the `checkAudience` and
`AllowedGroups` paths. Its payload has no `client_id` or `jti`, so those
fields are simply absent — `slog` attributes are built conditionally, so an
absent claim produces no key rather than an empty one.

`middleware.go`'s single `slog.Warn` becomes:

```go
ec := edgectx.FromRequest(r)
attrs := []any{"err", err, "provider", providerLabel, "reason", reason,
    "edge_request_id", ec.RequestID, "edge_route", ec.Route,
    "route", chi.RouteContext(r.Context()).RoutePattern()}
if a, ok := auth.AttributionOf(err); ok {
    attrs = append(attrs, "sub", a.Subject)
    if a.ClientID != "" { attrs = append(attrs, "client_id", a.ClientID) }
    if a.Jti != "" { attrs = append(attrs, "jti", a.Jti) }
    if a.ExpiresAt != 0 { attrs = append(attrs, "exp", a.ExpiresAt) }
}
slog.Warn("auth failed", attrs...)
```

`reason` is computed once and shared with the counter increment on the next
line, so the log line and the metric can never disagree about which bucket a
failure fell into — today they are computed from the same call but only the
metric records it.

`internal/audit/redact.go` needs no new keys: `sub`, `client_id`, `jti` and
`exp` are identifiers the service minted, not secrets, and the existing
`authorization`/`bearer` keys already cover the token itself. This is the
same reasoning the file records for `device_pubkey` and
`credential_domain_id`. A one-line comment is added there recording the
decision, so a future reader does not have to re-derive it.

### D. `internal/db` + `internal/digest` — onboarding stage

New store method, one query, portable across SQLite and Postgres (no window
functions — the correlated `MAX(id)` form works on both, and the repo's
existing `ttlExemptClause` at `store.go:121` is the precedent for building
the `IN` placeholder list):

```go
// ConnectStep is the last connect:* audit step observed for one user.
type ConnectStep struct {
    Step      string    // tool_name with the "connect:" prefix stripped
    Status    string    // "ok" or "error"
    At        time.Time
    RevokedReason string // latest telegram_accounts.revoked_reason, if any
}

// LastConnectStepFor returns, for each supplied Telegram id, the most recent
// connect:* audit row. Ids with no such row are absent from the map.
func (s *Store) LastConnectStepFor(ctx context.Context, tgIDs []int64) (map[int64]ConnectStep, error)
```

```sql
SELECT u.telegram_login_id, a.tool_name, a.status, a.created_at
  FROM audit_logs a
  JOIN users u ON u.id = a.user_id
 WHERE u.telegram_login_id IN ($1,$2,…)
   AND a.tool_name LIKE 'connect:%'
   AND a.id = (SELECT MAX(a2.id) FROM audit_logs a2
                WHERE a2.user_id = a.user_id
                  AND a2.tool_name LIKE 'connect:%')
```

An empty `tgIDs` slice short-circuits to an empty map without touching the
database — building `IN ()` is a syntax error on both engines.

The revoke reason rides along as a second statement in the same method
(`SELECT telegram_login_id, revoked_reason ... ORDER BY revoked_at DESC`),
gated on a new `telegram_accounts.revoked_reason TEXT` column added through
the existing `addColumnIfMissing` helper (`internal/db/db.go:108` is the
pattern) and written by the three existing revoke paths
(`store.go:676`, `:881`, `:899`) — all of which already receive or can
trivially name a reason. `RevokeSessionByID` is the clearest case: it takes
`reason string` today and throws it away after the metric.

In `internal/digest`, `runDigest` calls `LastConnectStepFor` with the
Telegram ids of `newRows` only — bounded by the 24 h window, so typically
single digits — and passes the resulting map into `buildDigestMessage`. A
query error is logged at WARN and the map is left nil; `sessionSuffix`
handles a nil map by returning the plain `"no session"`, so a failing lookup
degrades to today's output rather than dropping the digest.

```go
// sessionSuffix renders the session column. Rows WITH a session are
// unchanged. Rows without one gain the last connect step, which is what
// separates "never started" from "stuck at the code prompt" from
// "FLOOD_WAIT" -- three stories that are identical in today's output.
func sessionSuffix(r db.IdentityRow, steps map[int64]db.ConnectStep) string {
    if r.HasSession { return "session active" }
    st, ok := steps[r.TelegramID]
    if !ok { return "no session — last: never started" }
    out := fmt.Sprintf("no session — last: %s %s", st.Step, st.At.UTC().Format("15:04"))
    if st.RevokedReason != "" { out += " — session revoked (" + st.RevokedReason + ")" }
    return out
}
```

Only `tool_name`, `status` and `created_at` cross the boundary. The audit
row's `peer_redacted` and `error` columns are never selected, so no Telegram
peer identifier or RPC error string can reach a Telegram message.

### E. `internal/oauth/enable_access.go` — abandonment is WARN

`loginFlow` gains one unsynchronised field and a `superseded` flag:

```go
// step is the last onboarding stage this flow reached. Written ONLY by the
// login goroutine (in askCode/askPassword and around loginFn), read only by
// that same goroutine's deferred logger -- so no mutex is needed and none
// should be added.
step string
// superseded is set by a /start re-submission before it calls cancel(), so
// the deferred logger can tell "user started over" from "user walked away".
// Both surface as context.Canceled/DeadlineExceeded and are otherwise
// indistinguishable (see the comment at line 726).
superseded atomic.Bool
```

`step` is set to `"phone_submitted"` before `loginFn`, `"code_requested"` at
the top of `askCode`, `"code_submitted"` after a receive on `lf.codeCh`,
`"password_requested"` in `askPassword`, `"password_submitted"` after a
receive on `lf.pwCh`. All five writes are on the login goroutine.
`superseded` is `atomic.Bool` because the two `es.flow.cancel()` call sites
(lines 516, 704) are on HTTP handler goroutines.

The deferred logger becomes a three-arm branch:

```go
switch {
case lf.err == nil:
    slog.Info("enable: telegram login succeeded", …)          // unchanged
case lf.superseded.Load():
    slog.Info("enable: login flow superseded", "uid", uid, "step", lf.step,
        "elapsed", …)
case isAbandonment(lf.err):
    slog.Warn("enable: onboarding abandoned", "uid", uid, "step", lf.step,
        "elapsed", …)
default:
    slog.Error("enable: telegram login failed", …)             // unchanged
}
```

`isAbandonment(err)` is `errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled)`.
No `err` attribute on the abandonment arm: `"query session: context canceled"`
is the deadline restated, and dropping it is what stops a log-scraper
alerting on the word. The existing `connect:failed:timeout` audit rows are
untouched — this changes the pod log only, so the audit chain is unaffected.

## Alternatives

**Write rejected registrations to `audit_logs` instead of the pod log.**
Rejected. `/oauth/register` is unauthenticated, so there is no `user_id` to
key a row on, and `LogToolCall` (`store.go:1715`) is a per-user hash-chained
writer with a `SELECT … FOR UPDATE` on the user's latest `entry_hash`.
Giving an unauthenticated endpoint a path into any user's chain would let a
flood of registrations serialise every authenticated write for that user —
the exact contention the `allowRegister` limiter exists to prevent — and
would put attacker-supplied `client_name` inside a tamper-evident structure
whose whole point is that its contents are the service's own observations.
The pod log plus a counter gives the operator the same answer with none of
that.

**Derive the rejection `reason` by string-matching the validator's error.**
Rejected. It is what `classifyAuthError` does, and it works there only
because those error literals are defined two files away in the same module
and are covered by tests. Here the string on line 2798 embeds the raw
client-supplied URI, so matching on it is both fragile and a disclosure
risk, and any new validation rule would silently fall into a catch-all
bucket. Typed sentinels plus `errors.Is` make a new rule a compile-visible
decision.

**Change `auth.Provider.Authenticate` to return a richer result type.**
Rejected. Four implementations (`localjwt`, `sharedhmac`, `localdev`,
`telegramoidc`) plus the bridge websocket handler that calls
`auth.ClassifyAuthError` directly would all need editing, and the
`(*Identity, error)` contract is used well beyond the middleware. Wrapping
the error is strictly additive: `AttributedError.Error()` forwards the
original string, so every existing classifier, `errors.Is` check and test
assertion keeps passing untouched, and a provider that never wraps loses
nothing.

**Log the claims for every failed token, including signature failures.**
Rejected outright, and it is the trap this issue's phrasing invites. Line
152 of `internal/auth/localjwt/issuer.go` is the HMAC check; a token that
fails it has a payload the attacker wrote. Logging `sub` and `client_id`
from one turns the production log into an attacker-controlled write channel
— log injection, cardinality attacks if anyone later promotes a field to a
label, and a stream of fabricated identities that makes the very
correlation this issue asks for worse than the status quo. Hence the
"parsed *and signature-verified*" gate, which is a stricter reading than the
issue's "parsed-but-rejected" and is the only safe one.

**Extend `ListIdentities` with a `LEFT JOIN` onto `audit_logs` instead of a
second query.** Rejected. `ListIdentities` is unbounded (every user ever) and
is on the `list_telegram_identities` MCP tool path, the manage page and the
digest; adding a correlated per-user `MAX(id)` scan over `audit_logs` there
would make every caller pay for something only the digest reads. The issue
itself proposes the second query, and keeping it separate also means a
failure degrades one line of one Telegram message instead of breaking an MCP
tool.

**Reclassify abandonment by matching `"context canceled"` in the error
string.** Rejected: it cannot distinguish a genuine downstream cancellation
from the deadline, and it silently reclassifies any future error that
happens to wrap a cancelled context. `errors.Is` plus an explicit
`superseded` flag set by the code that actually does the superseding states
the intent instead of guessing it.

## Platform impact

### Migrations

One additive column: `telegram_accounts.revoked_reason TEXT`, via the
existing `addColumnIfMissing(ctx, dbConn, pg, …)` helper used for
`prev_hash`, `entry_hash`, `call_path` and the `edge_*` columns
(`internal/db/db.go:105-147`). Nullable, no default, no backfill — a NULL
means "revoked before this column existed, or revoked by a path that names
no reason", which is a true statement and the same convention the file
already uses for `call_path`. Both the SQLite `CREATE TABLE` (`db.go:551`)
and the Postgres one (`db.go:786`) gain the column for fresh installs.

No change to `audit_logs`, and therefore **no change to the hash chain**.
`hashAuditEntry` (`internal/db/audit_chain.go:29`) is untouched, no new
column feeds it, and `VerifyAuditChain` keeps verifying pre-change rows
byte-identically. This is the single most important compatibility property
of the change and is asserted directly by test T9.

### Backward compatibility

- `oauth: client_registration audit` gains a `reason` attribute on its two
  existing outcomes and a third `outcome=rejected` value. A consumer
  filtering on `outcome=accepted` is unaffected; one counting *all* audit
  lines as accepted-or-rate-limited will now see more. The runbook is
  updated accordingly.
- `auth failed` gains attributes; its message string is unchanged, so
  existing log queries match as before.
- `mctl_auth_failures_total` is untouched — same name, same labels, same
  values.
- `mctl_oauth_client_registrations_total` is new. Nothing scrapes it yet;
  `/metrics` output grows by up to 48 series.
- `localjwt.Verify` and `sharedhmac`'s exported surface keep their exact
  signatures. `VerifyWithClaims` is additive.
- The digest message text changes for `no session` rows. The only automated
  consumer is `internal/digest/digest_test.go`, which asserts on the exact
  string at lines 62-68 and is updated in the same commit. A human reading
  the Telegram message sees a longer line.
- `enable: telegram login failed` stops appearing for abandoned and
  superseded flows. Anyone alerting on that string sees the rate drop — which
  is the point, and is called out in the runbook change.

### Resource impact

- One extra `slog.Info` per rejected registration. At the observed rate (464
  in 48 h from the one persistent client) that is under 250 lines/day.
- One `CounterVec.Inc()` per registration; negligible.
- Per failed auth: one `edgectx.FromRequest` (two header reads plus a
  bounded sanitize) and one `errors.As`. Both on an already-failing path
  that is about to write a 401.
- Per digest run (once per day): one extra query over `audit_logs`, keyed on
  `user_id` via the `MAX(id)` subquery, with an `IN` list bounded by the
  24 h new-client count. `audit_logs` is swept by `SweepAuditLog`
  (`store.go:1677`) so the table stays bounded. Add an index only if this
  shows up — at one query per day on a table this size it will not.
- No change to the hot MCP path, the Telegram client pool, or memory.

### Risks and mitigations

| risk | mitigation |
|---|---|
| Claims logged from an unverified token become an attacker write channel | `AttributedError` is constructed only after the HMAC check; `VerifyWithClaims` returns nil claims at or before line 160. Test T5 asserts a tampered-signature token logs no claim. |
| A client-supplied string reaches a Prometheus label and explodes cardinality | Both labels are `regReason`/outcome constants; no code path passes a dynamic string. Test T3 enumerates the reachable label set. |
| The full redirect URI leaks into a log line | `redirectOrigin` returns only `Scheme` and `Hostname()`; the raw URI never becomes a log attribute. Test T2 asserts path and query are absent for a URI carrying both. |
| The digest's extra query slows or fails the daily send | 30 s context already wraps `runDigest` (line 69); a nil map degrades to today's `"no session"`. Test T7 covers the failure path. |
| A Telegram peer identifier reaches the digest via an audit row | Only `tool_name`, `status` and `created_at` are selected — `peer_redacted` and `error` are never in the projection. Asserted by T8. |
| Reclassifying to WARN hides a real login failure | `isAbandonment` matches only `context.DeadlineExceeded`/`Canceled`; every other error keeps its ERROR arm. Test T10 asserts a FLOOD_WAIT failure still logs ERROR. |
| The new `step` field races | Written only on the login goroutine, read only by that goroutine's own deferred logger; `superseded` is `atomic.Bool` because its writers are handler goroutines. Test T11 runs the flow under `-race`. |
| Rollback leaves the new column behind | The column is nullable and unread by pre-change code, so a binary rollback is clean with no schema step. |
