# Design: issue-1203-security-glovo-rate-limit-post-glovo-acc

## Current state
- `internal/api/glovo_access_self_page.go`, `handleGlovoAccessSelfStart`: after OIDC discovery it
  mints browser/state/nonce tokens and calls `p.put(..., glovoAccessSelfKindStart,
  basketStartKey(state, browser), entry, releaseChallengeTTL)`. That is one `Flow.Put`, meaning
  one `INSERT INTO oauth_flow_entries` in `internal/auth/flowstore/postgres.go`, for every call,
  without authentication. The handler then sets the `__Host-mctl_glovo_access_self` cookie and
  redirects with 303 to ZITADEL. `releaseChallengeTTL` is 10 minutes
  (`release_approval_page.go:99`). Expired rows are removed only by `Store.GC`.
- The only limiter inside this page is `glovoAccessSelf.requests`
  (`httprate.NewRateLimiter(glovoAccessSelfRequestsPerHour, time.Hour)`). It is per principal and
  applies only when an access request is opened in confirm, after sign-in.
- `internal/api/router.go` (around lines 604-678): the start route is mounted inside the public
  `r.Group` whose middleware is `httprate.Limit(60, 1*time.Minute,
  httprate.WithKeyFuncs(keyByTrustedIP))`. Because that is one `httprate.Limit` for the whole
  group, all `/.well-known/*`, `/oauth/*`, the identity link, DevLoop decide and every approval
  page share a single 60-per-minute bucket per address. The self start route is therefore
  limited today, but only loosely, and the bucket is shared with the routes the issue wants to
  protect.
- Client address: `clientMetaMiddleware(opts.TrustedProxyCIDRs)` runs globally
  (`router.go:567`). `keyByTrustedIP` (`internal/api/clientmeta.go`) reads the resolved IP from
  context. X-Forwarded-For is honoured only from a trusted peer, and then by walking right to left
  to the first untrusted hop. Otherwise the key falls back to `remoteHost(r.RemoteAddr)`. chi's
  `middleware.RealIP` is deliberately absent. `TRUSTED_PROXY_CIDRS` is parsed in
  `cmd/api/main.go` (around line 1441).
- Existing patterns to reuse: `glovo_basket.go:131` uses `httprate.Limit(120, time.Minute,
  httprate.WithKeyFuncs(keyByTrustedIP))`. `internal/glovojoin/http.go:102` uses
  `httprate.WithResponseHeaders(httprate.ResponseHeaders{RetryAfter: "Retry-After"})`.
  `clientmeta_test.go` has `buildLimitedRouter`, `TestRateLimit_SpoofedXFFCannotEscapeBucket` and
  `TestRateLimit_TrustedProxySeparatesClients`. Those tests cover the key function, not this
  route.
- Tests: `glovo_access_self_page_test.go` builds a full router through `NewRouter(Options{...
  GlovoAccessSelf: opts})` with an in-memory `memFlowStore` (`e.flow`). `selfEnv.do` sends
  through `e.router`, so a router-level limiter is exercised there. The helper `selfEnv.start()`
  posts to the start path. The heaviest existing loop, `TestGlovoAccessSelfLimiterCountsOnlyRealRequests`,
  makes `glovoAccessSelfRequestsPerHour+2` (5) sign-ins on one router, which is below the
  proposed limit of 10.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)`: error "service not found". mctl-api is
  not a catalogue service under admins.
- `mctl_list_services(team=admins)`: complete=true, 8 services, and mctl-api is not among them.
  The deployed replica count and `TRUSTED_PROXY_CIDRS` value of mctl-api could not be observed.
- `$MCTL_GITOPS_ROOT/services/*/mctl-api/values.yaml`: no such path in the checkout.
- `helm/values.yaml` in the clone: `replicaCount: 1` is the chart default, not proof of the
  deployed value. The issue says there are two replicas.

## Proposed solution
1. Add a constant `glovoAccessSelfStartsPerMinute = 10` in `glovo_access_self_page.go`, next to
   `glovoAccessSelfRequestsPerHour`, with a comment: per client address, per process, and the
   group limit of 60 still applies in front of it.
2. Add a method `(p *glovoAccessSelf) startLimit() func(http.Handler) http.Handler` that returns
   ```go
   httprate.Limit(glovoAccessSelfStartsPerMinute, time.Minute,
       httprate.WithKeyFuncs(keyByTrustedIP),
       httprate.WithResponseHeaders(httprate.ResponseHeaders{RetryAfter: "Retry-After"}),
       httprate.WithLimitHandler(func(w http.ResponseWriter, r *http.Request) {
           p.failed(w, http.StatusTooManyRequests, "Too many sign-in attempts from your network. Wait a minute and try again; nothing was changed.")
       }))
   ```
   Check the `failed` rendering against the page's no-PII rule (`selfEnv.do` asserts it). If
   `httprate` already sets `Retry-After` before calling the limit handler, keep it. Otherwise set
   it in the handler.
3. In `router.go`, inside the `if h.glovoAccessSelf != nil` block, mount the route with
   `r.With(h.glovoAccessSelf.startLimit()).Post(glovoAccessSelfStartPath,
   h.handleGlovoAccessSelfStart)`. `r.With` is evaluated once in `NewRouter`, so there is one
   limiter instance per router and process, in its own bucket that is not shared with the group.
   The limiter runs before the handler, which is what lets "429 writes nothing" hold by
   construction.
4. Add a short comment in the router stating that the limit is per process and that the other
   start routes intentionally remain on the group bucket (see Open questions in
   requirements.md).

Why this way: it reuses the exact keying (`keyByTrustedIP`) that the other public limited routes
use, so the trusted-proxy behaviour is already proven. It needs no new dependency. It is the
pattern already used in `glovo_basket.go`.

## Alternatives
- **Lower the shared group limit from 60.** Dropped. It would throttle `/oauth/token`,
  `/oauth/authorize` and the JWKS/metadata probes of MCP clients, which already needed a higher
  limit (see the comment at the `/oauth/register` group).
- **A limiter inside the handler, like `glovoAccessSelf.requests`.** Dropped. It works, but the
  middleware form keeps the "refused before any write" ordering structural, and it matches how
  every IP limit in `router.go` is expressed.
- **A distributed limit, or capping `oauth_flow_entries` rows per kind in Postgres.** Dropped for
  now. It needs a schema or store change and a counting query on the hot path. Per-process limits
  are the platform's existing convention, and the issue accepts that doubling.
- **Apply the dedicated limit to all page start routes now.** Deferred to a reviewer decision
  (Open questions). Those routes face owners rather than the public.

## Platform impact
- No migration, no config, no new env var or dependency (`github.com/go-chi/httprate` is already
  in `go.mod`).
- Backward compatible for real users: a person starts about one flow per 10 minutes.
- Risk: many customers behind one NAT or carrier-grade NAT could share a bucket. 10 per minute
  still allows ten fresh sign-ins a minute from one address, and the 429 page tells the person to
  retry.
- Risk: `TRUSTED_PROXY_CIDRS` misconfigured in production would put every client behind Traefik
  in one bucket. This is the existing behaviour of every IP limit, and the regression test below
  pins the correct keying. The deployed value could not be checked from this run.
- Resource: one in-memory `httprate` counter map per process, which is negligible.
- Effective ceiling = 10 x replicas per minute per address, documented in a comment.
