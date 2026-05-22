# Tasks: issue-94-local-bridge-m4-finish-community-release

> ## Accepted scope (2026-05-22)
> This proposal is accepted **scoped to M4 only — Slices 1 and 2** (tasks 1–14
> plus tests T1–T8 and the Slice-1/Slice-2 rollback notes). The implementer MUST
> implement ONLY those tasks in this PR.
> **Do NOT implement Slices 3–6 (M4.1):** no cross-repo OAuth (tasks 15–17), no
> GoReleaser/Homebrew/install script (18–22), no OS keychain (23–26), no
> `docs/local-bridge.md` / landing cross-link (27–28). Those are deferred to a
> separate M4.1 acceptance. Tests T9/T10 belong to M4.1 and are out of scope here.

Tasks are grouped by slice. The slices map onto two accept/PR milestones (see
design.md "Milestone split: M4 vs M4.1"):

- **M4 — Production-ready bridge:** Slices 1–2 (this repo only). Land first.
- **M4.1 — Community distribution:** Slices 3–6 (cross-repo OAuth, GoReleaser/
  Homebrew, OS keychain, docs). Accept and PR separately, after M4.

Slices 1 and 2 are self-contained to this repo and should be landed first.
Slices 3, 4, 5, 6 can proceed in parallel after Slice 1. The `connect --token`
manual path remains supported throughout, so Slice 3 (cross-repo OAuth) is an
opt-in convenience, not a release blocker.

---

## Slice 1 — Server-side polish (~3 days)

- [ ] 1. Update `internal/bridge/DESIGN.md` to reflect actual implementation
  state: mark all implemented components as done, list remaining gaps
  (pong deadline, backpressure, keychain, distribution, cross-repo OAuth,
  docs). Remove "stub binary" and "scaffolding only" language.
  DoD: the file accurately describes what is implemented and what is not;
  `git diff` shows substantive changes; no contradictions with code.

- [ ] 2. Add `call_path TEXT DEFAULT 'hosted'` column to `audit_logs` via
  `addColumnIfMissing` in `internal/db/db.go`.
  DoD: `db.Migrate` succeeds on both SQLite and Postgres without error;
  existing rows are unaffected (column is NULL, treated as 'hosted').

- [ ] 3. (depends on 2) Update `internal/db/audit_chain.go` `hashAuditEntry`
  to include `callPath` in the canonical hash input (appended after `errMsg`,
  separated by `\x00`).
  DoD: existing `TestVerifyAuditChain` still passes; new rows written with
  a non-empty `callPath` produce a different hash than rows with empty
  `callPath`, verified by a unit test.

- [ ] 4. (depends on 2, 3) Update `Store.LogToolCall` signature:
  `LogToolCall(ctx, userID, tool, peerRedacted, status, errMsg, callPath string)`.
  Update the INSERT in `internal/db/store.go` to include `call_path`.
  Update `AuditEntry` to add `CallPath string json:"call_path,omitempty"`.
  Update `ListAuditFor` SELECT and Scan to include `call_path`.
  DoD: `store_audit_test.go` covers both `callPath=""` (stored as NULL / 'hosted')
  and `callPath="local"` round-trips; `get_my_audit_log` response includes
  `call_path` field.

- [ ] 5. (depends on 4) Update `s.audit()` in `internal/mcp/tools.go` to
  accept a `callPath string` parameter. Pass `"local"` from the bridge dispatch
  path and `""` from the hosted path in every tool handler.
  DoD: bridge calls write `call_path='local'`; hosted calls write
  `call_path=NULL` (treated as 'hosted'); all five tools updated; no hosted
  call accidentally passes `"local"`.

- [ ] 6. Add `BridgeActiveDaemons prometheus.Gauge` and
  `BridgeCallsTotal *prometheus.CounterVec{tool,status}` to
  `internal/metrics/metrics.go` `Registry` struct and `New()`.
  DoD: `metrics_test.go` constructs a Registry, writes to both new metrics,
  and reads them back without panic or duplicate-registration error.

- [ ] 7. (depends on 6) Add optional metrics wiring to `internal/bridge/hub.go`:
  add `func (h *Hub) WithMetrics(m *metrics.Registry) *Hub`; increment
  `BridgeActiveDaemons` in `Register`, decrement in `Unregister` and
  `UnregisterSend`.
  DoD: `hub_test.go` gains a test that wires a metrics Registry, registers and
  unregisters a daemon, and verifies the gauge value.

- [ ] 8. (depends on 6) Wire `BridgeCallsTotal` into `bridgeCall()` in
  `internal/mcp/tools.go`: after `hub.Call` returns, increment
  `s.Metrics.BridgeCallsTotal.WithLabelValues(tool, status).Inc()` where
  `status` is `"ok"` for TypeResponse and `"error"` for TypeError or any
  returned Go error. Guard with `if s.Metrics != nil`.
  DoD: unit test in `tools_test.go` using a fake hub verifies the counter is
  incremented on success and on error.

- [ ] 9. Add `MctlBridgeDaemonsFlapping` to the existing
  `deploy/alerts/mctl-telegram.rules.yaml` (created by #86; already holds the
  pool/flood-wait/OAuth and burn-rate alerts — append a rule to the existing
  group, do not recreate the file): `changes(mctl_bridge_active_daemons[10m]) > 20`,
  severity `warning`.
  DoD: file is valid YAML, `promtool check rules deploy/alerts/mctl-telegram.rules.yaml`
  exits 0; alert name and expression match the requirements; the pre-existing
  alerts remain intact.

- [ ] 10. Add "Local Bridge mode" section to `internal/web/security.html`.
  Replace the "track the planned Local Bridge mode" warning banner with a
  reference to the new section. Include: session bytes never stored for
  mode='local'; tool arguments/responses pass through relay memory per call;
  relay does not log message content.
  DoD: section exists in rendered HTML; "planned" language removed from
  warning banner; no broken links; existing content untouched.

---

## Slice 2 — Websocket hardening (~1 week)

- [ ] 11. Enforce server-side pong deadline in `internal/bridge/server.go`.
  After the writer goroutine sends a ping, set a read deadline of 5s on the
  connection. Reset the deadline to zero after each successful non-ping frame
  in the reader goroutine.
  DoD: unit test in `server_test.go` connects a fake daemon that never answers
  pings; verifies the server drops the connection within ~5s and the hub entry
  is removed; no goroutine leak.

- [ ] 12. Add backpressure to `internal/bridge/hub.go`. Add
  `maxPendingCalls = 100` constant and an atomic `pendingCount int64` field to
  `daemonConn`. In `Hub.Call`, atomically increment before enqueuing to
  `pending`; if the new count exceeds the limit, decrement and return
  `ErrDaemonOverloaded`. Decrement on all exit paths.
  DoD: `hub_test.go` gains a test that fires 101 concurrent `Hub.Call`
  goroutines against a daemon that never responds; at least one must return
  `ErrDaemonOverloaded`; the hub does not deadlock; goroutine count returns to
  baseline after test cleanup.

- [ ] 13. (depends on 12) Map `ErrDaemonOverloaded` to a clean error message in
  `bridgeCall()` in `internal/mcp/tools.go`.
  DoD: `errors.Is(err, bridge.ErrDaemonOverloaded)` returns a
  `*mcplib.CallToolResult` with a human-readable error string rather than
  propagating a Go error.

- [ ] 14. (depends on 11, 12) Add integration test for connection drop and
  reconnect in `internal/bridge/` (new file `server_reconnect_test.go` or
  added to `server_test.go`):
  1. Connect a fake daemon; verify round-trip call succeeds.
  2. Force-close the server-side connection.
  3. Connect a new fake daemon; verify round-trip call succeeds on the new
     connection.
  4. Verify no goroutine leak after the test (use `goleak.VerifyTestMain` or
     `runtime.NumGoroutine` baseline check).
  DoD: test passes with `go test -race ./internal/bridge/...`; no goroutine
  count increase after test completion; documented in test comments.

---

## Slice 3 — Cross-repo OAuth scope (~3-5 days, cross-repo dependency)

- [ ] 15. [mctl-api] Add OAuth scope `local-bridge` and endpoint
  `POST /oauth/local-bridge/authorize` that emits a JWT with `aud="bridge"`,
  TTL 1h, bound to the caller's OIDC session.
  DoD: endpoint exists; integration test verifies JWT claims.

- [ ] 16. [mctl-web] Handle `?for=local-bridge` redirect target in the Worker.
  DoD: redirect lands on the correct page; CORS allows localhost redirect URIs.

- [ ] 17. (depends on 15, 16) Update `cmd/local/main.go` `runConnect()` to
  support OAuth PKCE flow: open browser to authorize URL, listen on
  `127.0.0.1:<random-port>` for redirect, exchange code for bridge JWT, save
  to keychain (after Slice 5) or file. Keep `--token` flag for manual/headless
  use.
  DoD: `connect` without `--token` opens the browser and completes the flow;
  `connect --token <jwt>` still works; headless environments use `--token`.

---

## Slice 4 — Cross-platform distribution (~1 week)

- [ ] 18. Create `.goreleaser.yml` at repo root targeting `cmd/local`.
  Targets: darwin/amd64, darwin/arm64, linux/amd64, linux/arm64,
  windows/amd64. Archive as `mctl-telegram-local_<version>_<os>_<arch>.tar.gz`
  (zip for Windows). Include SHA-256 checksums.
  DoD: `goreleaser check` exits 0; a dry-run build (`goreleaser build --snapshot
  --clean`) produces binaries for all five targets.

- [ ] 19. (depends on 18) Create `mctlhq/homebrew-tap` repo with
  `Formula/mctl-telegram-local.rb` sourcing the GoReleaser archive.
  DoD: `brew install mctlhq/tap/mctl-telegram-local` installs the binary on
  macOS; `mctl-telegram-local version` prints the expected version.

- [ ] 20. (depends on 18) Create `install.sh` for macOS/Linux (detects OS/arch,
  downloads the matching tarball from GitHub Releases, verifies checksum,
  installs to `/usr/local/bin`).
  DoD: `curl -fsSL https://install.mctl.ai/local | sh` (or equivalent)
  installs the binary; script is idempotent; no arbitrary code execution beyond
  the declared install path.

- [ ] 21. (depends on 18) Add `checkLatestVersion(ctx context.Context)` to
  `cmd/local/daemon.go` (or a new `cmd/local/update.go`): on daemon startup,
  call GitHub Releases API with 5s timeout; compare tag to `version` constant;
  if newer, `slog.Info("new version available", "current", version, "latest",
  latest)`. Swallow all errors silently.
  DoD: function is unit-tested with a mock HTTP server; failure (network error,
  non-200) does not prevent daemon startup.

- [ ] 22. Document macOS notarization and Windows code signing process in
  `CONTRIBUTING.md` or a new `docs/release-signing.md`.
  DoD: a new contributor can follow the steps to obtain and configure the
  required certificates; notes that community releases may ship unsigned.

---

## Slice 5 — OS keychain integration (~1 week)

- [ ] 23. Add `github.com/99designs/keyring` to `go.mod` / `go.sum`.
  DoD: `go mod tidy` succeeds; no import cycle; `go build ./cmd/local/...`
  succeeds on macOS, Linux, and Windows (use `//go:build` tags if the library
  requires platform-specific stubs).

- [ ] 24. (depends on 23) Add `cmd/local/keychain.go` with `saveSecret`,
  `loadSecret`, `deleteSecret` wrappers over `keyring.Open`. Configure Linux
  headless fallback via `keyring.Config.AllowedBackends` (include file backend
  when D-Bus is unavailable).
  DoD: unit tests stub `keyring.Open` via dependency injection; `saveSecret` +
  `loadSecret` round-trip; headless path uses file backend without panic.

- [ ] 25. (depends on 24) Migrate `bridgeTokenFile` storage to keychain in
  `cmd/local/config.go`: `saveBridgeToken` calls `saveSecret`; `loadBridgeToken`
  calls `loadSecret`. On load, if keychain entry is absent but plain file
  exists, migrate (read file, write keychain, delete file, log migration).
  DoD: `mctl-telegram-local connect` stores the token in the keychain, not in
  `~/.config/mctl-telegram-local/bridge_token.json`; migration test verifies
  that a pre-existing plain file is migrated and deleted on first `loadBridgeToken`.

- [ ] 26. (depends on 24) Optionally support `--keychain-passphrase` flag on
  `daemon` subcommand: if set, store the derived key hex in the keychain after
  a successful passphrase derivation, and load it on subsequent runs without
  prompting. Default remains the interactive passphrase prompt.
  DoD: `--keychain-passphrase` flag is documented in `help` output; storing and
  loading the key hex round-trips on macOS and Linux; the flag has no effect if
  the keychain is unavailable (graceful degradation to prompt).

---

## Slice 6 — User-facing documentation (~3 days)

- [ ] 27. Create `docs/local-bridge.md` with sections: What is Local Bridge,
  When to use it, Threat model, Installation (macOS/Linux/Windows), Setup
  guide (init, login, connect, daemon), Troubleshooting, FAQ.
  DoD: all five setup steps are covered; troubleshooting addresses: daemon
  won't start, websocket connection refused, session re-auth required; FAQ
  covers "where is my session stored", "moving to a new computer", "running
  daemon on a VPS"; cross-links to `/security` page and landing page.

- [ ] 28. (depends on 10, 27) Cross-link `docs/local-bridge.md` from the
  `/security` page Local Bridge section and from the landing page
  (`internal/web/landing.html`).
  DoD: links are present and resolve; no dead links in the rendered pages.

---

## Tests

- [ ] T1. `internal/db/store_audit_test.go` — verify that `LogToolCall` with
  `callPath="local"` writes `call_path='local'` and `ListAuditFor` returns
  it in `AuditEntry.CallPath`; verify `callPath=""` returns `call_path=""`.

- [ ] T2. `internal/db/audit_chain_test.go` — verify that `hashAuditEntry`
  produces a different hash when `callPath` differs (regression guard for the
  chain encoding change).

- [ ] T3. `internal/mcp/tools_test.go` — verify `bridgeCall` increments
  `BridgeCallsTotal{tool="list_dialogs", status="ok"}` on success and
  `status="error"` on a TypeError response.

- [ ] T4. `internal/metrics/metrics_test.go` — verify `New()` registers
  `mctl_bridge_active_daemons` and `mctl_bridge_calls_total` without error;
  verify `BridgeActiveDaemons.Set(3)` is readable.

- [ ] T5. `internal/bridge/hub_test.go` — verify `WithMetrics` wires the
  gauge correctly: Register increments, Unregister decrements.

- [ ] T6. `internal/bridge/hub_test.go` — verify `ErrDaemonOverloaded` is
  returned when 101 concurrent calls are in flight against a non-responding
  daemon.

- [ ] T7. `internal/bridge/server_test.go` (or `server_reconnect_test.go`) —
  connection drop and reconnect integration test with goroutine leak check.

- [ ] T8. `internal/bridge/server_test.go` — pong deadline test: daemon that
  ignores pings gets disconnected within 5s + margin; hub entry is removed.

- [ ] T9. `cmd/local/` — keychain round-trip test (using stub keyring backend);
  bridge-token migration from plain file to keychain.

- [ ] T10. `promtool check rules deploy/alerts/mctl-telegram.rules.yaml` in CI
  (add to `Makefile` or `.github/workflows/`).

---

## Rollback

**Slice 1 — Audit column**
The `call_path` column is additive and has `DEFAULT 'hosted'`. Rolling back the
code (reverting `LogToolCall` signature) leaves the column in place with no
ill effect; old code ignores it. The column can be dropped separately with
`ALTER TABLE audit_logs DROP COLUMN call_path` at operator discretion. The
hash-chain change only affects rows written after deployment; pre-rollback rows
are unaffected and `VerifyAuditChain` skips rows without `entry_hash`.

**Slice 1 — Metrics**
Metrics are additive Prometheus counters/gauges. Rolling back removes them from
the registry; existing dashboards that reference them will show "no data" rather
than an error. No data is lost.

**Slice 1 — Security page / DESIGN.md**
Plain HTML and Markdown changes. Revert via `git revert`; no data migration
required.

**Slice 2 — Websocket hardening**
Server-side pong deadline and backpressure are behavioral changes; rolling back
restores the previous unlimited behavior. No persistent state is affected.

**Slice 4 — GoReleaser / distribution**
A faulty GoReleaser config can be corrected and re-tagged. The Homebrew formula
can be rolled back by reverting the tap repo commit; existing installs are
unaffected.

**Slice 5 — OS keychain**
If the keychain migration causes problems, users can re-run `connect --token`
to write a fresh plain file. The migration path is one-way (file to keychain)
but the plain-file path is preserved as a fallback.

**Cross-cutting**
All changes in this proposal are backward-compatible with the existing `mode='hosted'`
behavior. A partial rollback (reverting Slices 1-2 while keeping the daemon
binary) leaves the system in the pre-issue-94 state with no data loss.
