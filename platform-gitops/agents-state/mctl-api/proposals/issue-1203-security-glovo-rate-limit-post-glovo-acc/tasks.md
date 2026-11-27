# Tasks: issue-1203-security-glovo-rate-limit-post-glovo-acc

- [ ] 1. Add `glovoAccessSelfStartsPerMinute = 10` and `(p *glovoAccessSelf) startLimit()` in `internal/api/glovo_access_self_page.go`. The limiter is `httprate.Limit` keyed by `keyByTrustedIP`, with a `Retry-After` response header and a limit handler that renders `p.failed(w, http.StatusTooManyRequests, ...)`. — DoD: compiles. The 429 body uses the page shell and CSP and contains no request data.
- [ ] 2. (depends on 1) In `internal/api/router.go`, mount the start route as `r.With(h.glovoAccessSelf.startLimit()).Post(glovoAccessSelfStartPath, h.handleGlovoAccessSelfStart)` inside the existing `if h.glovoAccessSelf != nil` block, with a comment on the per-process scope and on the other start routes staying on the group bucket. — DoD: the route still sits inside the 60-per-minute group, and its own limiter applies only to it.
- [ ] 3. (depends on 2) In `glovo_access_self_page_test.go`, let `selfEnv` set `Options.TrustedProxyCIDRs` (a new optional field on the setup struct) and let `do` take an optional `RemoteAddr` / `X-Forwarded-For`. — DoD: existing tests are unchanged and pass.
- [ ] 4. Run `go fmt`, `go vet`, `golangci-lint` and `go test -p 1 ./internal/api/...`. — DoD: all green. No existing test makes more than 10 starts on one router from one address (check the loops). If one does, give it distinct addresses.

## Tests
- [ ] T1. `TestGlovoAccessSelfStartIsRateLimitedPerAddress`: from one `RemoteAddr`, send 10 starts, each a 303 to ZITADEL. The 11th is 429 with a `Retry-After` header, no `Set-Cookie`, no `Location`, and `e.flow` holds exactly 10 `glovo-access-self-start` entries (unchanged by the 11th). This test fails if the `r.With(...)` limiter is removed, because the group limit is 60.
- [ ] T2. Same test, continued: a request from a second `RemoteAddr` right after the 429 gets 303 and writes one entry.
- [ ] T3. `TestGlovoAccessSelfStartLimitBehindTrustedProxy`: `TrustedProxyCIDRs=10.42.0.0/16`, peer `10.42.4.181`. Client A (`X-Forwarded-For: 198.51.100.1`) exhausts its 10, and its 11th is 429. Client B (`198.51.100.2`) through the same proxy still gets 303. A request from an untrusted peer that rotates `X-Forwarded-For` hits 429 after 10, so it cannot escape the bucket.
- [ ] T4. The existing `TestGlovoAccessSelfUnmountedIs404` still passes: with the page unconfigured, the start route is 404 and no limiter is mounted.

## Rollback
Revert the commit, or delete the `r.With(...)` wrapper in `router.go`. The route then falls back
to the shared 60-per-minute group limit it has today. There is no migration, no config and no
stored state to undo, and the in-memory counters disappear with the process.
