# Design: issue-94-local-bridge-m4-finish-community-release

## Current state

### What is fully implemented

The `internal/bridge/DESIGN.md` file describes the implementation as
"scaffolding only / stub binary". That is outdated. As of the current clone,
the following are fully implemented and tested:

**Protocol and hub** (`internal/bridge/`)
- `protocol.go` — `Envelope` struct, `TypeCall/TypeResponse/TypeError/TypePing/TypePong`,
  `DeadlinePingPong=30s`, `DeadlineCall=30s`, `EncodeCall/EncodeResponse/EncodeError`.
- `hub.go` — `Hub` with `Register`, `Unregister`, `UnregisterSend`, `Call`,
  `Deliver`, `HasDaemon`, `MarshalCall`. Register evicts any previous daemon
  for the same user (singleton invariant). Call uses a `sync.Map` of per-call
  reply channels. The send channel is buffered at cap 16.
- `hub_test.go` — unit tests covering register/eviction, call round-trip,
  `ErrNoDaemonConnected`, timeout, and no-pending-Deliver as no-op.

**Websocket server** (`internal/bridge/server.go`)
- `NewBridgeHandler` — authenticates with an `auth.Provider` enforcing
  `aud=bridge`, checks `store.GetAccountMode` to reject hosted-mode accounts,
  upgrades to websocket via `coder/websocket`, calls `hub.Register`, runs a
  reader goroutine (handles ping/respond-pong, routes TypeResponse/TypeError to
  `hub.Deliver`) and a writer goroutine (forwards hub-queued envelopes, sends
  server-initiated pings every `pingInterval=25s`). Cleanup uses
  `hub.UnregisterSend` to avoid evicting a newer daemon on reconnect.
- `server_test.go` — integration test verifying a round-trip call over a real
  websocket, and that hosted-mode accounts are rejected with HTTP 400.

**Bridge token handler** (`internal/bridge/tokenhandler.go`)
- `NewBridgeTokenHandler` — mints a `localjwt` HS256 JWT with `aud=bridge`,
  TTL 1h, carrying `tg_id` and `tg_username` so the bridge verifier can
  resolve the user via `EnsureUserByTelegramID`.

**Server wiring** (`cmd/server/main.go:204-218`)
- `POST /api/bridge/token` is mounted behind `auth.Middleware` (requires valid
  MCP JWT).
- `GET /bridge` is mounted with a separate `bridgeProvider` that enforces
  `aud=bridge`.
- `hub` is injected into the MCP server via `mcpSrv.WithHub(hub)`.

**MCP tool dispatch** (`internal/mcp/tools.go:82-148`)
- `bridgeCall` — marshals args, generates a UUID call ID, calls `hub.Call`,
  converts the response envelope to a `*mcplib.CallToolResult`.
- Every tool handler checks `store.GetAccountMode`; when `mode='local'`, it
  routes to `bridgeCall` and calls `s.audit(...)` with the bridge result error.
  All five tools are wired: `list_dialogs`, `get_unread_messages`, `get_messages`,
  `send_message`, `pin_message` (verified by reading the `toolListDialogs`
  pattern and the parallel patterns for other tools).

**Daemon binary** (`cmd/local/`)
- `config.go` — `localConfig` (JSON at `~/.config/mctl-telegram-local/config.json`),
  `bridgeTokenFile` (JSON at `bridge_token.json`), Argon2id KDF (`argon2.IDKey`,
  1 pass, 64 MiB, 4 threads), HMAC-SHA256 key-check, atomic file writes.
- `main.go` — subcommands `init` (prompts API creds + passphrase, derives key,
  saves config), `login` (full Telegram phone/SMS/2FA flow via `tg.Login`),
  `connect` (POST `/api/bridge/token` with MCP JWT, saves bridge token),
  `daemon` (loads config + token, opens encrypted SQLite, starts `runDaemon`
  with SIGINT/SIGTERM cancellation).
- `daemon.go` — `runDaemon` with exponential backoff (base 2s, cap 60s, resets
  after sessions longer than 60s); `refreshBridgeToken` (5-minute advance
  refresh); `daemonSession` (single websocket connection lifetime: reader
  goroutine, ping ticker goroutine, dispatcher goroutine per TypeCall);
  `dispatchCall` dispatches all five tools via `pool.Borrow`. Graceful
  shutdown sends `StatusNormalClosure` on ctx cancellation.

**Schema** (`internal/db/db.go:89-103`)
- `telegram_accounts.mode TEXT NOT NULL DEFAULT 'hosted'` (addColumnIfMissing).
- `telegram_accounts.bridge_token_hash BYTEA` (addColumnIfMissing).

### What is missing

The following items from the issue are absent from the codebase:

1. **Audit `call_path` column** — `audit_logs` has no `call_path` column.
   `Store.LogToolCall` takes `tool, peerRedacted, status, errMsg` but not a
   path marker. `s.audit()` in `tools.go` does not pass any via-marker; all
   audit rows look identical regardless of bridge vs. hosted dispatch.

2. **Server-side pong deadline enforcement** — `server.go` sends pings every
   25s but the reader goroutine does not enforce a deadline for receiving a
   pong; a daemon that never answers pings will hold a hub slot indefinitely
   until the TCP connection times out at the OS level.

3. **Backpressure on pending calls per daemon** — the Hub's `pending sync.Map`
   is unbounded. There is no cap on concurrent in-flight `Hub.Call` goroutines
   for a single daemon.

4. **Bridge metrics** — `internal/metrics/metrics.go` defines no
   `mctl_bridge_*` metrics. The `Registry` struct has no bridge-specific fields.

5. **Alert rule** — `deploy/alerts/` directory is empty; there is no
   `MctlBridgeDaemonsFlapping` PrometheusRule.

6. **`/security` Local Bridge section** — `internal/web/security.html` mentions
   Local Bridge only as a "planned" mode in a warning banner; it has no
   dedicated section explaining the `mode='local'` data flow.

7. **`DESIGN.md` accuracy** — `internal/bridge/DESIGN.md` still describes the
   implementation as "stub binary" and lists the websocket transport, daemon
   subcommands, and MCP dispatch as remaining work, all of which are done.

8. **OS keychain integration** — `cmd/local/config.go` stores the
   `bridgeTokenFile` (including the MCP token) and the passphrase key salt as
   plain JSON files under `~/.config/mctl-telegram-local/`. No `99designs/keyring`
   or equivalent is used.

9. **GoReleaser / distribution** — no `.goreleaser.yml` exists at the repo root.
   No Homebrew formula, install script, or auto-update mechanism.

10. **Cross-repo OAuth scope** — `cmd/local/main.go connect` uses a manual
    `--token` flag to paste an MCP JWT. The issue's Slice 3 OAuth PKCE flow
    through `mctl-api`'s new `local-bridge` scope does not exist yet (cross-repo).

11. **`docs/local-bridge.md`** — no end-user documentation file exists.

---

## Proposed solution

### Slice 1 — Server-side polish

#### 1a. Audit `call_path` column

Add a new column `call_path TEXT DEFAULT 'hosted'` to `audit_logs` via
`addColumnIfMissing` in `internal/db/db.go`. Update:

- `Store.LogToolCall(ctx, userID, tool, peerRedacted, status, errMsg, callPath string)` —
  add the `callPath` parameter and include it in the INSERT.
- `AuditEntry` struct — add `CallPath string json:"call_path,omitempty"`.
- `ListAuditFor` — add `call_path` to the SELECT and Scan.
- `hashAuditEntry` in `internal/db/audit_chain.go` — include `callPath` in the
  canonical hash input (append after `errMsg`, separated by `\x00`) so the
  chain covers the new field.
- `s.audit()` in `internal/mcp/tools.go` — add a `callPath string` parameter.
  Callers after `bridgeCall` pass `"local"`; all hosted-path callers pass `""`.
  The store treats `""` identically to `"hosted"`.
- All tool handler call sites in `tools.go` that currently call `s.audit(...)`.

Do not change the existing `get_my_audit_log` tool's JSON field list; append
`call_path` as an additive field so the response is backward-compatible.

#### 1b. Security page update

Add a new `<h2>Local Bridge mode</h2>` section to `internal/web/security.html`
between "What the server sees" and "What the server NEVER persists", containing:

- Explicit statement: "In `mode='local'`, the server never receives, stores, or
  decrypts your Telegram session bytes. The `session_encrypted` column in
  Postgres is NULL for local-mode accounts."
- Explicit statement about what the relay does see: "MCP tool arguments and
  responses (the JSON-RPC payload) pass through the relay's memory for the
  duration of one call. The relay does not log message content."
- Replace the existing "track the planned Local Bridge mode" warning banner
  with a pointer to the new section (the mode is no longer planned, it is
  available).

#### 1c. Update DESIGN.md

Rewrite `internal/bridge/DESIGN.md` to:
- State the current implementation status accurately (all server-side and
  daemon-side components are implemented).
- Document the remaining gaps: pong deadline on server, backpressure,
  OS keychain, distribution, cross-repo OAuth, docs.
- Remove references to "stub binary" and "scaffolding only".

#### 1d. Bridge metrics

Add to `internal/metrics/metrics.go` `Registry`:
```go
BridgeActiveDaemons prometheus.Gauge          // mctl_bridge_active_daemons
BridgeCallsTotal    *prometheus.CounterVec    // mctl_bridge_calls_total{tool,status}
```
Register both in `New()`.

Wire `BridgeActiveDaemons` into `internal/bridge/hub.go`:
- Add an optional `metrics` field to `Hub` (set via `hub.WithMetrics(m)`).
- Increment in `Register`, decrement in `Unregister`/`UnregisterSend`.

Wire `BridgeCallsTotal` into `internal/mcp/tools.go` `bridgeCall()`:
- After the Hub.Call returns, call
  `s.Metrics.BridgeCallsTotal.WithLabelValues(tool, status).Inc()`.

#### 1e. Alert rule

Create `deploy/alerts/mctl-telegram.rules.yaml`:
```yaml
groups:
  - name: mctl-telegram
    rules:
      - alert: MctlBridgeDaemonsFlapping
        expr: changes(mctl_bridge_active_daemons[10m]) > 20
        labels:
          severity: warning
        annotations:
          summary: "Bridge daemons connecting/disconnecting abnormally"
          description: "mctl_bridge_active_daemons changed more than 20 times in 10 minutes."
```
This depends on the PrometheusRule CRD pattern established by issue #86.

---

### Slice 2 — Websocket hardening

#### 2a. Server-side pong deadline

In `internal/bridge/server.go`, the reader goroutine currently blocks on
`wsjson.Read(ctx, conn, &env)` indefinitely between frames. After sending
each ping in the writer goroutine, set a short read deadline on the connection
via `conn.SetReadDeadline(time.Now().Add(5*time.Second))` (or equivalently,
derive a short sub-context for the next read). If the deadline fires, the
read returns an error, the reader goroutine exits, `done` is notified, and
`cancel()` is called — causing the writer to stop and `UnregisterSend` to
fire. The daemon's reader then gets a close/EOF and triggers reconnect.

`coder/websocket` exposes `(*Conn).SetReadDeadline`. Reset the deadline to
zero after each successful non-ping read so the deadline applies only to the
pong window.

#### 2b. Backpressure

Add a `pendingCount int64` atomic counter to `daemonConn` (alongside `send`
and `pending sync.Map`). In `Hub.Call`:
- Before storing into `pending`, atomically increment `pendingCount`.
- If the new value exceeds `maxPendingCalls` (constant: 100), atomically
  decrement and return a new sentinel error `ErrDaemonOverloaded`.
- On return from Call (success, timeout, or context cancel), atomically
  decrement.

In `internal/mcp/tools.go` `bridgeCall()`, map `ErrDaemonOverloaded` to
`toolErr("local-bridge daemon overloaded — too many concurrent calls")`.

#### 2c. Integration test with network drop

Add a test in `internal/bridge/server_test.go` (or a new
`server_reconnect_test.go`) that:
1. Connects a fake daemon.
2. Verifies a round-trip call succeeds.
3. Forcibly closes the server-side connection (simulating a network drop) by
   calling `srv.CloseClientConnections()` on the httptest.Server.
4. Starts a new fake daemon connection to the same server.
5. Verifies a subsequent call succeeds on the new connection.
6. Uses `goleak.VerifyNone(t)` (or manual goroutine counting via
   `runtime.NumGoroutine`) to confirm no goroutine leak after test cleanup.

---

### Slice 3 — Cross-repo OAuth scope

This slice requires PRs in `mctlhq/mctl-api` and `mctlhq/mctl-web`; it cannot
be landed in this repo alone.

In-repo change: once the `mctl-api` endpoint `POST /oauth/local-bridge/authorize`
exists, update `cmd/local/main.go` `runConnect()` to use a PKCE OAuth2 flow
(open system browser to the authorize URL, listen on `127.0.0.1:<random>` for
the redirect, exchange the code for a bridge JWT) instead of the current
manual `--token` flag. Keep the `--token` flag as a fallback during transition.

---

### Slice 4 — Cross-platform distribution

Add `.goreleaser.yml` at the repo root targeting `cmd/local`:
- `builds`: GOOS: [darwin, linux, windows], GOARCH: [amd64, arm64] (skip
  windows/arm64 initially).
- `archives`: include the binary as `mctl-telegram-local`.
- `checksum`: sha256.
- `signs` block for macOS notarization (Apple Developer ID, `gon` tool or
  `codesign` + `xcrun altool`); document the certificate requirement. Windows
  code signing deferred to follow-on (community can install unsigned with
  SmartScreen warning).
- `brews`: tap `mctlhq/homebrew-tap` (requires creating the
  `mctlhq/homebrew-tap` repo with a `Formula/` directory).

Auto-update: add a `checkLatestVersion(ctx context.Context)` function that at
daemon startup performs a GitHub Releases API call to
`https://api.github.com/repos/mctlhq/mctl-telegram/releases/latest`, compares
the tag name to the `version` constant in `cmd/local/main.go`, and logs a
one-line `slog.Info` hint if a newer version is available. No download.
Timeout: 5s. Failure is silently swallowed.

---

### Slice 5 — OS keychain integration

Add `github.com/99designs/keyring v1.x` to `go.mod`.

Add a `keychain.go` file in `cmd/local/` implementing:
- `saveSecret(service, key, value string) error`
- `loadSecret(service, key string) (string, error)`
- `deleteSecret(service, key string) error`

backed by `keyring.Open(keyring.Config{ServiceName: "mctl-telegram-local"})`.
Linux headless fallback: `keyring.Config.KeychainTrustApplication = false` +
`FileDir` pointing to the existing `~/.config/mctl-telegram-local/` so
headless servers transparently fall back to encrypted-file storage.

Migrate `bridgeTokenFile` storage: `saveBridgeToken`/`loadBridgeToken` in
`config.go` call `saveSecret`/`loadSecret("bridge-token", "bridge_token_json")`.

Migrate passphrase key-check: `localConfig.KeySalt` and `localConfig.KeyCheck`
remain in `config.json` (non-secret metadata); the actual derived key is not
stored — it is re-derived from the passphrase on each run. If the user wants
to avoid re-entering the passphrase on every `daemon` start, optionally store
the key hex in the keychain under `saveSecret("passphrase-key", "key_hex")`.
This is opt-in (flag `--keychain-passphrase`).

Migration path: on first `loadBridgeToken()` after upgrade, if the keychain
entry is absent but the plain file exists, read from the file, write to
keychain, delete the plain file, log `slog.Info("migrated bridge token to
system keychain")`.

---

### Slice 6 — User-facing documentation

Create `docs/local-bridge.md`:
- Sections: What is Local Bridge, When to use it vs. hosted mode, Threat model
  (what the relay sees and does not see), Installation per OS, Setup guide
  (init, login, connect, daemon), Troubleshooting, FAQ.
- Cross-link to `/security` page for the cryptographic detail.
- No screenshots (they go stale); use annotated terminal transcripts instead.

---

## Alternatives

### A. tool_name suffix instead of new call_path column

Append `/local` to the `tool_name` value in `LogToolCall` (e.g.,
`list_dialogs/local`) instead of adding a column. Rejected: breaks existing
callers that filter audit logs by exact tool name, and forces the suffix into
the hash-chain canonical encoding, complicating verification for rows written
before the change.

### B. Embed the pending-call limit in the Hub send channel cap

Increase the send-channel buffer from 16 to 100 and rely on the channel block
as backpressure. Rejected: the send-channel depth bounds the server-to-daemon
write queue, not the number of in-flight calls waiting for a response. Calls
whose envs have already been sent (and are sitting in `pending`) are not
bounded by the send channel.

### C. Full OCI/container release instead of native binaries for M4

Package `cmd/local` as a container and tell users to `docker run`. Rejected:
the daemon needs access to the host filesystem (`~/.config/`) and the OS
keychain, both of which are cumbersome from inside a container. Native
binaries are the correct distribution unit for a local daemon.

---

## Platform impact

### Migrations

- `audit_logs.call_path TEXT DEFAULT 'hosted'` — additive `addColumnIfMissing`
  column. All existing rows get `NULL` (treated as `'hosted'`). No downtime.
  The `hashAuditEntry` change is additive (new rows gain the field; old rows
  with NULL are already outside the verifiable hash chain if they pre-date
  `entry_hash`). No VerifyAuditChain regression for pre-existing rows.

### Backward compatibility

- `LogToolCall` signature change: the new `callPath` parameter is added at the
  end. All internal callers are in one package (`internal/mcp/tools.go`); there
  are no external callers. The change is mechanical.
- `get_my_audit_log` response gains a new `call_path` field. Additive JSON
  field; clients that do not recognize it ignore it.
- `mctl_bridge_active_daemons` and `mctl_bridge_calls_total` are new metric
  names; no existing dashboard panel is affected.

### Resource impact

- `BridgeActiveDaemons` gauge: one atomic inc/dec per daemon connect/disconnect.
  Negligible.
- `BridgeCallsTotal` counter: one WithLabelValues call per bridge tool call.
  Negligible.
- `checkLatestVersion` at daemon startup: one outbound HTTPS request to GitHub
  API with a 5s timeout. Fails silently. No impact on the tool-call path.

### Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| `hashAuditEntry` change invalidates existing hash chains | The hash function only applies to new rows. Old rows pre-date `entry_hash` and `VerifyAuditChain` skips them (documented in existing code). |
| OS keychain migration deletes plain file before confirming keychain write | `saveSecret` is called before `os.Remove`; only delete on success. |
| GoReleaser macOS notarization requires Apple Developer account | Document the certificate requirement; ship unsigned macOS binary for community release with a README note; notarize in follow-on. |
| Slice 3 cross-repo dependency blocks community release | Keep the `--token` manual path working; Slice 3 is an enhancement, not a gate. |
| `conn.SetReadDeadline` on pong timeout also fires on slow tool responses | The read deadline is reset after each successful pong; it is only active during the pong window. Tool-call responses are server-to-daemon writes (not reads), so this path is unaffected. |
