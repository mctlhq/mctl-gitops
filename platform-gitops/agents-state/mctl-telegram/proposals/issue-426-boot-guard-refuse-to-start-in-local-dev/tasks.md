# Tasks: issue-426-boot-guard-refuse-to-start-in-local-dev

- [ ] 1. Add `Environment string` field to `internal/config.Config` and
      populate it in `Load()` via `envOr("ENV", "")`, next to the other
      plain-string fields (near `LogLevel`). — DoD: `go build ./...`
      compiles; a doc comment on the field explains it feeds
      `cmd/server`'s boot guard and is compared case-insensitively against
      `"production"`.
- [ ] 2. Create `cmd/server/bootguard.go` with `checkBootGuard(cfg
      *config.Config) error`, `isLoopbackAddr(addr string) bool`,
      `insecureAuth(cfg *config.Config) bool`, and `isProductionEnv(env
      string) bool`, implementing the logic in design.md's "Proposed
      solution" section 2. (depends on 1) — DoD: functions are unexported,
      package-`main`-local (matching `selectProvider`'s existing pattern in
      `cmd/server/main.go`), take no dependency beyond `internal/config`,
      perform no I/O, and `go vet ./cmd/server/...` is clean.
- [ ] 3. Wire `checkBootGuard` into `cmd/server/main.go`'s `main()`
      immediately after `cfg, err := config.Load()` succeeds and before the
      existing `slog.Info("starting", ...)` call, using the file's existing
      `slog.Error(...); os.Exit(1)` idiom on failure. (depends on 2) — DoD:
      a fatal boot-guard error is logged and the process exits 1 before
      `db.Open` is ever called; `go build ./cmd/server` succeeds.
- [ ] 4. Update the local-dev quick-start snippets to bind loopback
      explicitly instead of the bind-all `ADDR=:8080`: `README.md`'s Quick
      Start (`ADDR=:8080` → `ADDR=127.0.0.1:8080`), `CONTRIBUTING.md`'s
      equivalent snippet, and `.env.example`'s `ADDR=:8080` line. (depends
      on 3) — DoD: `grep -n 'ADDR=:8080' README.md CONTRIBUTING.md
      .env.example` returns no matches; the documented `go run
      ./cmd/server` flow still starts successfully with the new `ADDR`.
- [ ] 5. Add a short note to `SECURITY.md`'s existing "Authentication-required
      mode" section (around line 107-110) stating that the loopback/`ENV`
      posture described there is now enforced by a boot-time fatal check in
      `cmd/server`, not just documented. (depends on 3) — DoD: the section
      references `checkBootGuard` by file (`cmd/server/bootguard.go`) so a
      future reader can find the enforcement code from the doc.
- [ ] 6. File or link a tracked follow-up (issue comment or a new backlog
      note referenced from this proposal) for `docker-compose.yml`'s
      local-dev flow, which inherits `AUTH_MODE=local-dev`/
      `AUTH_REQUIRED=false` defaults with a container port-published
      (non-loopback-inside-the-container) bind and will now fail the guard
      unless its `environment:`/`.env` explicitly sets a real auth mode or
      an exempting `ADDR`. (depends on 3) — DoD: the gap is written down
      somewhere durable (issue comment referencing this proposal's slug is
      sufficient); this proposal does not silently leave
      `docker-compose.yml` broken without a record of why.

## Tests
- [ ] T1. `cmd/server/bootguard_test.go`:
      `TestCheckBootGuardLoopbackLocalDevOK` — `ADDR="127.0.0.1:8080"`,
      `AuthMode="local-dev"`, `AuthRequired=false`, `EncryptionKey=nil`,
      `Environment=""` → `checkBootGuard` returns `nil`.
- [ ] T2. `TestCheckBootGuardPublicBindLocalDevFatal` — `ADDR="0.0.0.0:8080"`,
      same auth config as T1 → `checkBootGuard` returns a non-nil error
      whose message contains `AUTH_MODE` (or the configured mode value).
- [ ] T3. `TestCheckBootGuardEmptyHostTreatedAsPublicFatal` —
      `ADDR=":8080"`, same auth config as T1 → non-nil error (locks in the
      Open-questions interpretation that a bind-all address is not
      loopback).
- [ ] T4. `TestCheckBootGuardProductionNoKeyFatal` — `Environment="production"`,
      `ADDR="127.0.0.1:8080"`, `AuthMode="local-jwt"`, `AuthRequired=true`,
      `EncryptionKey=nil` → non-nil error whose message contains
      `ENCRYPTION_KEY`.
- [ ] T5. `TestCheckBootGuardProductionCaseInsensitive` —
      `Environment="Production"` and `"PRODUCTION"` behave identically to
      `"production"`.
- [ ] T6. `TestCheckBootGuardBothProblemsReportedTogether` —
      `ADDR="0.0.0.0:8080"`, `AuthMode="local-dev"`, `EncryptionKey=nil` →
      the single returned error's message contains both `AUTH_MODE` and
      `ENCRYPTION_KEY` substrings (verifies problems are joined, not
      truncated after the first).
- [ ] T7. `TestCheckBootGuardCorrectlyConfiguredPublicBindOK` —
      `ADDR="0.0.0.0:8080"`, `AuthMode="local-jwt"`, `AuthRequired=true`,
      `EncryptionKey` set to a 32-byte slice → `nil` (a real deployment on a
      public bind must not be blocked).
- [ ] T8. `TestCheckBootGuardIPv6AndHostnameLoopback` —
      `isLoopbackAddr` (or `checkBootGuard` via table cases) treats
      `"[::1]:8080"` and `"localhost:8080"` as loopback, and an unresolved
      hostname like `"internal.example:8080"` as non-loopback (fail
      closed).
- [ ] T9. Full existing suite: `go test ./...` — confirms the guard does
      not alter behavior for any existing test (in particular
      `cmd/server/main_test.go`'s `TestSelectProvider*` tests, which
      construct bare `*config.Config{}` values that never reach
      `checkBootGuard`) and that `internal/config`'s existing tests
      (`config_test.go`, `config_ttl_test.go`, `config_replicaid_test.go`)
      still pass with the new `Environment` field added.

## Rollback
Revert the commit(s) implementing tasks 1-6. The change is additive and
self-contained:
- `cmd/server/bootguard.go` / `bootguard_test.go` can be deleted outright.
- The single call site added to `cmd/server/main.go`'s `main()` (task 3)
  can be removed with a one-line diff revert, immediately restoring today's
  behavior (server boots regardless of `ADDR`/`AUTH_MODE`/`ENCRYPTION_KEY`
  combination).
- The `Environment` field addition to `internal/config.Config` (task 1) is
  inert on its own (nothing else reads it) and safe to leave in place even
  if the guard call site is reverted, or can be removed in the same revert.
- The doc/`ADDR` changes (task 4) are non-functional reverts (just text).
No data migration, no persisted state, and no external API contract is
touched by any part of this change, so rollback is a plain `git revert` with
no follow-up cleanup required. If a deployment is actively crash-looping on
the new guard, the immediate mitigation is fixing that deployment's
`ADDR`/`AUTH_MODE`/`AUTH_REQUIRED`/`ENCRYPTION_KEY` (per the guard's own
error message) rather than rolling back the code, since the guard is
reporting a real insecure configuration.
