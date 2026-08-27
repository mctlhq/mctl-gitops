# Boot-guard: refuse to start in local-dev auth or without ENCRYPTION_KEY on non-loopback/production

## Context
`mctl-telegram` defaults to `AUTH_MODE=local-dev` + `AUTH_REQUIRED=false`
(`internal/config/config.go:196-202`), a mode in which every HTTP request is
granted platform-admin, send, and admin scopes with no credential check
(`internal/auth/localdev/provider.go`). Separately, when `ENCRYPTION_KEY` is
unset, `crypto.New` returns a disabled `AESGCM` and `cmd/server/main.go:93-95`
persists Telegram session blobs in plaintext, only logging a warning
(`internal/crypto/aesgcm.go:44-50,110-113`). Both are legitimate, working
defaults for a developer running `go run ./cmd/server` on their own laptop
(see the documented Quick Start in `README.md:45-53` and
`CONTRIBUTING.md`), and today's production deployment (labs) is configured
correctly (`local-jwt` + a Vault-sourced key). But nothing in the code
enforces that pairing — a future preview environment, a misconfigured Helm
values file, or a copy-pasted `.env` could boot the same wide-open defaults
on a publicly reachable bind, silently handing out platform-admin access to
anyone who can reach the port and persisting Telegram session material in
plaintext. `SECURITY.md:109-110` already documents this as a MUST
("`AUTH_REQUIRED=false` is for local development only... `local-dev`... MUST
NOT be reachable from a non-localhost production interface") but nothing
today turns that sentence into an enforced invariant. This proposal adds a
boot-time guard that turns the documented posture into a fatal startup check.

## User stories
- AS an operator deploying mctl-telegram to a new or preview environment
  I WANT the process to refuse to start when it would boot wide-open
  (local-dev auth bypass or no session encryption, on a non-loopback bind or
  in production) SO THAT a misconfiguration is caught at deploy time with a
  clear error instead of silently exposing platform-admin access or
  plaintext Telegram sessions.
- AS a developer running the server locally on 127.0.0.1
  I WANT the existing local-dev workflow to keep working exactly as
  documented SO THAT the added safety check does not get in the way of the
  normal inner dev loop.
- AS an on-call engineer reading a crash-looping pod's logs
  I WANT the fatal boot-guard message to name exactly which setting is wrong
  and how to fix it SO THAT the incident is resolved by a config change, not
  a code archaeology session.

## Acceptance criteria (EARS)
- WHEN the process starts with `AUTH_MODE=local-dev` (or
  `AUTH_REQUIRED=false`) AND the configured listen address (`ADDR`) is not
  restricted to a loopback interface THE SYSTEM SHALL log a fatal error
  naming the offending setting and exit with a non-zero status before
  opening the database connection or binding the listener.
- WHEN the process starts with `ENCRYPTION_KEY` unset AND the configured
  listen address is not restricted to a loopback interface THE SYSTEM SHALL
  log a fatal error and exit with a non-zero status, for the same reasons as
  above.
- WHEN the process starts with `ENV=production` (case-insensitive) AND
  either `AUTH_MODE=local-dev`/`AUTH_REQUIRED=false` OR `ENCRYPTION_KEY` is
  unset THE SYSTEM SHALL log a fatal error and exit with a non-zero status,
  regardless of the configured `ADDR`.
- IF both the insecure-auth condition and the missing-encryption-key
  condition are true at once THEN THE SYSTEM SHALL report both problems in a
  single fatal message rather than exiting after only the first check.
- WHILE `ADDR` resolves to a loopback interface (`127.0.0.1:<port>`,
  `[::1]:<port>`, or `localhost:<port>`) AND `ENV` is not `production` THE
  SYSTEM SHALL start normally with `AUTH_MODE=local-dev`,
  `AUTH_REQUIRED=false`, and/or no `ENCRYPTION_KEY`, unchanged from today's
  behavior.
- WHEN `AUTH_MODE` is `local-jwt` or `shared-hmac`/`shared-hmac-legacy` with
  `AUTH_REQUIRED=true` and `ENCRYPTION_KEY` is set THE SYSTEM SHALL start
  normally regardless of `ADDR` or `ENV` — the guard only fires on the
  specific insecure combinations above, never on a correctly configured
  deployment.
- IF the guard fires THEN THE SYSTEM SHALL exit before any other fatal-error
  exit path in `main()` (DB open/migrate, crypto init, OAuth init, etc.) so
  the failure is reported as fast and unambiguously as every other
  "refusing to start" check already in `cmd/server/main.go`.

## Out of scope
- The SSRF / CGNAT range fix referenced in the issue (separate issue).
- The OAuth implicit-client default and the bridge 401 body (separate
  backlog issue).
- Changing the *default* values of `AUTH_MODE`, `AUTH_REQUIRED`, or
  `ENCRYPTION_KEY` themselves — the defaults stay developer-friendly; only a
  non-loopback/production posture combined with those defaults becomes
  fatal.
- Any guard on `/bridge`, `/api/agent/v1`, or other sub-surfaces beyond what
  already exists (`selectBridgeProvider`/`selectAgentProvider` already fail
  closed to `rejectAllProvider` when a JWT mode is missing its secret); this
  proposal only adds the top-level boot-time check the issue asks for.
- Detecting "public" via cloud-metadata / reachability probes. The guard is
  a static, deterministic check over `ADDR`, `ENV`, `AUTH_MODE`,
  `AUTH_REQUIRED`, and `ENCRYPTION_KEY` only — no network calls at boot.

## Open questions
- The issue's guard matrix names `0.0.0.0` and `127.0.0.1` explicitly but
  does not say what to do with the *documented* local-dev default
  `ADDR=:8080` (empty host), which in Go's `net.Listen` binds all
  interfaces identically to `0.0.0.0:8080` — i.e., the exact "Quick start"
  command in `README.md:49` and `CONTRIBUTING.md:15` is, strictly, already a
  non-loopback bind. Interpretation taken here: treat an empty/omitted host
  as non-loopback (fail closed, matching real `net.Listen` semantics) and
  update the Quick Start docs and `.env.example` to use
  `ADDR=127.0.0.1:8080` instead of `ADDR=:8080`. This keeps "local
  development on 127.0.0.1" working exactly as the issue requires, while
  closing the same laptop-on-a-shared-network exposure the issue is about,
  rather than quietly special-casing the bind-all default as "close enough
  to loopback."
- The issue does not define where `ENV` is sourced from — no such variable
  exists in `internal/config/config.go` today. Taken as a new `Environment`
  config field read from `ENV` (unset/empty otherwise), matching this
  repo's existing `envOr` helper pattern. `ENV=production` is compared
  case-insensitively, consistent with how `AUTH_MODE` is compared elsewhere
  in `cmd/server/main.go` (`strings.EqualFold`/`strings.ToLower`).
  `platform-gitops` values for the labs deployment are not modified by this
  proposal since the labs pod already uses `local-jwt`/`AUTH_REQUIRED=true`
  with a Vault-sourced key, so the guard is a no-op there even without
  `ENV` ever being set; setting `ENV=production` there is a recommended
  follow-up, not a blocking requirement of this change.
- Whether an operator should be able to opt out of the guard for an
  intentionally-open demo/reviewer deployment. No override flag is added:
  the issue's acceptance criteria are unconditional ("must refuse to
  start"), and `DemoReviewerEnabled` in `internal/config/config.go:111-122`
  already requires `local-jwt`-style real auth around the demo path, so it
  does not conflict with this guard.
