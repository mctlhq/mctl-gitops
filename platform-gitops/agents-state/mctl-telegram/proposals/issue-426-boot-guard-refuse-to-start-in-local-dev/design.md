# Design: issue-426-boot-guard-refuse-to-start-in-local-dev

## Current state
- `internal/config/config.go:196-202` — `Load()` defaults `AUTH_MODE` to
  `"local-dev"` and `AUTH_REQUIRED` to `false` via `envOr`/`envBool`. There
  is no `ENV`/`ENVIRONMENT` variable anywhere in `Config` or `Load()` today.
- `internal/auth/localdev/provider.go` — `Provider.Authenticate` ignores the
  incoming request entirely and always returns a fixed identity with
  `Groups: []string{"platform-admins"}` and all four scopes including
  `admin:users`. Its package doc already says "not safe to mount in any
  environment a non-operator can reach," but nothing enforces that.
- `internal/crypto/aesgcm.go:43-50` — `New(key)` accepts a zero-length key
  and returns an `AESGCM` with `Enabled() == false`; `Seal`/`SealForUser`
  then prefix blobs with `VersionPlaintext` and store the plaintext
  unchanged. `cmd/server/main.go:88-95` only logs
  `slog.Warn("ENCRYPTION_KEY not set — session bytes stored UNENCRYPTED...")`
  and continues.
- `cmd/server/main.go:54-95` is the full boot sequence today: build the
  redacting slog handler, `config.Load()`, log a `"starting"` line, open the
  DB, migrate, init crypto (warn-only on missing key), then continue into
  metrics/store/queue/telegram-pool wiring and eventually
  `srv.ListenAndServe()` on `cfg.Addr` (`http.Server{Addr: cfg.Addr, ...}`
  at line ~521). There is no address-family/loopback check anywhere in this
  path.
- `cmd/server/main.go` already has an established "refusing to start"
  idiom used at five other call sites (agent profile import, OAuth init,
  `selectProvider`): log via `slog.Error(...)` with `err`, then
  `os.Exit(1)`. `TestSelectProviderUnknownModeIsError` and friends in
  `cmd/server/main_test.go` show the existing pattern for unit-testing a
  `main.go`-local pure function by constructing a bare `*config.Config{}}`
  and calling it directly — no server startup, no env vars, no I/O.
- `README.md:45-53` / `CONTRIBUTING.md` document the local-dev quick start
  as `ADDR=:8080 AUTH_MODE=local-dev AUTH_REQUIRED=false ... go run
  ./cmd/server` — an *empty host* address, which Go's `net.Listen("tcp",
  ":8080")` binds identically to `0.0.0.0:8080` (all interfaces), not just
  loopback. `docker-compose.yml` also exposes the container's `:8080` via
  `ports: ["8080:8080"]`, which likewise requires an all-interfaces bind
  inside the container.
- `SECURITY.md:107-110` documents the intended invariant in prose
  ("`AUTH_REQUIRED=false` is for local development only... `local-dev`...
  MUST NOT be reachable from a non-localhost production interface") but
  today it is unenforced.

## Proposed solution
Add a small, dependency-free, synchronously-testable boot guard in the
`cmd/server` package (same package as `main`, following the existing
`selectProvider`/`selectBridgeProvider` pattern of pure functions over
`*config.Config` that `main_test.go` already exercises without booting a
server):

1. **New config field.** Add `Environment string` to `internal/config.Config`,
   populated in `Load()` via `envOr("ENV", "")`. This is the only change to
   `internal/config/config.go`. No validation is added there — `ENV` is
   advisory input to the boot guard, not a value other subsystems consume,
   so it belongs with the other plain string fields near `LogLevel`.

2. **New pure function `checkBootGuard(cfg *config.Config) error` in a new
   `cmd/server/bootguard.go`.** Logic:
   - `exposed := isProductionEnv(cfg.Environment) || !isLoopbackAddr(cfg.Addr)`
   - If `!exposed`, return `nil` immediately — loopback + non-production is
     always allowed, matching today's behavior exactly.
   - Otherwise collect every violated invariant into a slice of problem
     strings: `insecureAuth(cfg)` (true when `AUTH_MODE` is `local-dev`,
     case-insensitively, or `AUTH_REQUIRED` is `false`) and
     `len(cfg.EncryptionKey) == 0`.
   - If the slice is empty (a correctly configured deployment on a public
     bind or in production), return `nil`.
   - Otherwise return one `fmt.Errorf` joining every problem with the
     current `ADDR`/`ENV` values and a one-line remediation hint (set
     `ADDR` to a loopback address for local dev, or fix
     `AUTH_MODE`/`AUTH_REQUIRED`/`ENCRYPTION_KEY` for a real deployment).
     Reporting every violated invariant in one message (not exiting after
     the first) mirrors this repo's existing `DemoReviewerEnabled` and
     `AgentProfilePath` validation blocks in `config.Load()`, which already
     favor a single actionable error over a fail-fast-on-first-field style.
   - `isLoopbackAddr(addr string) bool` is a second pure helper: splits
     `addr` with `net.SplitHostPort` (falling back to treating the whole
     string as the host if `SplitHostPort` errors, e.g. a bare hostname with
     no port), then:
     - empty host → `false` (bind-all, same as `0.0.0.0`)
     - `strings.EqualFold(host, "localhost")` → `true`
     - `net.ParseIP(host)` succeeds → `ip.IsLoopback()`
     - otherwise (an unresolvable/unknown hostname) → `false` (fail closed;
       the guard does not perform DNS resolution at boot)

3. **Wire it into `main()`.** Call `checkBootGuard(cfg)` immediately after
   `cfg, err := config.Load()` succeeds, before the existing `slog.Info("starting", ...)`
   line and before `db.Open`. On error, `slog.Error("boot guard", "err", err)`
   then `os.Exit(1)`, matching the exact idiom already used five times in
   this file. This is deliberately the *first* possible fatal exit in
   `main()` — a wide-open boot should never get far enough to touch the
   database or bind a socket.

4. **Docs/config-template alignment**, so the guard does not regress the
   documented dev loop (see Open questions in requirements.md for why an
   empty-host `ADDR` is treated as non-loopback): update the `ADDR=:8080`
   line in `README.md`'s Quick Start, `CONTRIBUTING.md`'s equivalent
   snippet, and `.env.example`'s `ADDR=:8080` to `ADDR=127.0.0.1:8080`.
   `docker-compose.yml` is left untouched — read carefully, its `app`
   service does not set `AUTH_MODE`/`AUTH_REQUIRED` at all, so it inherits
   the same `local-dev`/`false` defaults and, absent an env override, would
   also trip the guard once `Dockerfile`'s `EXPOSE`/`ADDR` default binds
   all interfaces inside the container. That combination (Docker Compose +
   default auth) is called out explicitly as a known follow-up in tasks.md
   rather than silently patched here, since changing `docker-compose.yml`'s
   effective bind touches Docker's own port-publishing model, not just an
   env var default, and is easy to get subtly wrong without a running
   Docker daemon to verify against in this environment.

## Alternatives
- **Enforce the check inside `config.Load()` itself**, returning an error
  from `Load()` when the insecure/exposed combination is detected. Rejected:
  `config.Load()` is a pure env-parsing function reused by `cmd/login` and
  `cmd/local` (interactive CLIs that have no `ADDR`/listener concept at
  all — see `cmd/login/main.go`), so folding a server-specific "is this
  bind loopback" concern into the shared config package would either force
  those binaries to satisfy an irrelevant invariant or require a new
  `Config` flag threaded through every caller to opt out. Keeping the guard
  in `cmd/server` (the only binary that actually calls `ListenAndServe`)
  keeps the blast radius to the one binary the issue is actually about.
- **A middleware/runtime check instead of a boot-time check** (e.g. reject
  requests at the HTTP layer when the server detects it is bound
  non-loopback). Rejected: the issue explicitly asks for a boot-time fatal
  exit ("the process must refuse to start"), which is also strictly safer
  — a runtime check still opens the listening socket and accepts TCP
  connections before rejecting anything, and depends on every future route
  remembering to call it. A boot guard fails before `net.Listen` is ever
  reached.
- **Detect "public" by inspecting actual network interfaces** (iterate
  `net.Interfaces()`/`net.InterfaceAddrs()` and check whether `ADDR`'s host,
  once resolved, is reachable from outside the host) instead of a static
  string check on the configured `ADDR`. Rejected: far more complex, adds
  real I/O and platform-dependent behavior to a boot-time check that should
  be simple and deterministic, and does not match what the issue's
  acceptance criteria actually test (`ADDR` string in, exit code out). The
  configured bind address is also the actual security-relevant signal — a
  loopback resolves the same everywhwere.

## Platform impact
- **Migrations:** none. No schema or data change.
- **Backward compatibility:** correctly configured deployments (production
  labs: `local-jwt`, `AUTH_REQUIRED=true`, `ENCRYPTION_KEY` set) are
  unaffected — `checkBootGuard` returns `nil` for them regardless of `ENV`
  or `ADDR`. The documented local-dev loopback flow is unaffected once the
  doc/`ADDR` update in this proposal lands (see Open questions). Any
  deployment that today boots with `local-dev`/`AUTH_REQUIRED=false` or no
  `ENCRYPTION_KEY` on a non-loopback `ADDR` — which by definition should not
  exist outside of a misconfiguration, per `SECURITY.md`'s existing MUST —
  will now fail to start instead of silently serving traffic. That is the
  intended behavior change; there is no known such deployment on this
  platform today (labs is `local-jwt`).
- **Resource impact:** negligible — one extra pure function call at boot,
  no network or disk I/O.
- **Risks + mitigations:**
  - *Risk:* a preview/CI environment that intentionally runs `local-dev` on
    a non-loopback bind (e.g. a container health-checked from outside its
    own network namespace) starts failing. *Mitigation:* the fatal error
    message names the exact `ADDR`/`ENV`/`AUTH_MODE` values and the fix
    (bind loopback, or set real auth mode + key), so this surfaces as an
    actionable, loud failure in deploy logs rather than a silent security
    gap — which is exactly the trade the issue asks for. If a legitimate
    non-loopback preview need emerges, the follow-up is to give that
    preview real `local-jwt` auth and a key, not to bypass the guard.
  - *Risk:* `docker-compose.yml`'s local-dev flow (no `AUTH_MODE` override,
    container binds all interfaces for port publishing) now also fails
    fast. *Mitigation:* called out as a known, tracked gap in tasks.md
    rather than silently left broken or silently patched without
    verification; `go run ./cmd/server` remains the documented/tested local
    workflow this proposal keeps green.
  - *Risk:* hostname `ADDR` values that are not IP literals and not
    `"localhost"` (e.g. a Kubernetes-internal DNS name) are treated as
    non-loopback even if they would resolve to a loopback address.
    *Mitigation:* this is the fail-closed direction — worst case is an
    over-eager fatal exit with a clear log line, never a silent bypass, and
    no real deployment in this repo's `deploy/`/gitops values uses a
    hostname `ADDR` today (they use `:8080` semantics via the Helm chart's
    default and rely on `AUTH_MODE`, not on `ADDR`, for the security
    boundary — the guard adds defense in depth on top).
