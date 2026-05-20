# Local Bridge (M4) — finish and community release

## Context

Local Bridge gives users an alternative trust model: the MTProto session lives
on the user's machine inside a local daemon (`mctl-telegram-local`), and
`tg.mctl.ai` acts only as a relay. The server never stores or decrypts the
user's Telegram session bytes; it persists only a principal mapping and an audit
trail of tool calls. This mode is critical for community adoption because a
significant portion of users are unwilling to trust any third party with a
server-side Telegram session.

The implementation is materially further along than `internal/bridge/DESIGN.md`
claims. The websocket transport (`internal/bridge/server.go`), the hub router
(`internal/bridge/hub.go`), the protocol envelope (`internal/bridge/protocol.go`),
the bridge token handler (`internal/bridge/tokenhandler.go`), and the full daemon
binary (`cmd/local/`) — including reconnect with exponential backoff, ping/pong,
graceful SIGTERM shutdown, token refresh, and dispatch for all five MCP tools —
are already implemented. The remaining work is observability polish, backpressure
hardening, OS keychain integration, cross-platform distribution, cross-repo OAuth
scope, and user-facing documentation.

## User stories

- AS a privacy-conscious user I WANT to run the daemon on my own machine SO THAT
  the server never holds my Telegram session bytes.
- AS a user I WANT `get_my_audit_log` to show `via=local` for bridge-dispatched
  calls SO THAT I can verify which execution path each tool invocation used.
- AS a user I WANT the daemon to survive a 5-minute network outage (laptop sleep,
  WiFi change) without manual restart SO THAT my MCP setup stays functional.
- AS an operator I WANT a `mctl_bridge_active_daemons` gauge and alert SO THAT
  I can detect abnormal daemon-connect/disconnect patterns early.
- AS a new community user I WANT to install the daemon with a single `brew install`
  command SO THAT I do not need CLI or Kubernetes access to the server.
- AS a user I WANT the bridge token and passphrase salt stored in the OS keychain
  SO THAT secret material is not left as plain files under `~/.config/`.
- AS a user I WANT the `/security` page to explicitly describe the local-bridge
  data flow SO THAT I can make an informed decision before switching modes.

## Acceptance criteria (EARS)

### Audit marker (Slice 1)

- WHEN a MCP tool call is dispatched via the Local Bridge (account
  `mode='local'`), THE SYSTEM SHALL store `call_path='local'` in the
  `audit_logs` row for that call.
- WHEN a MCP tool call is dispatched via the hosted MTProto path (account
  `mode='hosted'`), THE SYSTEM SHALL store `call_path='hosted'` (or NULL,
  treated as hosted) in the `audit_logs` row.
- WHEN a user invokes `get_my_audit_log`, THE SYSTEM SHALL include a
  `call_path` field in every returned entry.

### Security page (Slice 1)

- WHEN a user visits `/security`, THE SYSTEM SHALL display a distinct
  "Local Bridge mode" section that explicitly states: in `mode='local'`, the
  server never receives or stores the user's Telegram session bytes, and that
  MCP JSON-RPC payloads (tool arguments and responses) do pass through the
  relay's memory for the duration of a single call.

### DESIGN.md (Slice 1)

- WHILE the `internal/bridge/DESIGN.md` file exists in the repo, IT SHALL
  accurately reflect the implemented state of all bridge components, not the
  scaffolding-era description.

### Bridge metrics (Slice 1)

- WHILE the server is running, THE SYSTEM SHALL expose a
  `mctl_bridge_active_daemons` Prometheus gauge equal to the number of
  currently registered daemon websocket connections.
- WHEN a bridge tool call completes, THE SYSTEM SHALL increment
  `mctl_bridge_calls_total{tool, status}` where `status` is `ok` or `error`.
- WHEN `mctl_bridge_active_daemons` changes more than 20 times in 10 minutes,
  THE SYSTEM SHALL fire a `MctlBridgeDaemonsFlapping` Prometheus alert at
  severity `warning`.

### Backpressure (Slice 2)

- WHEN a daemon has more than 100 in-flight calls pending simultaneously, THE
  SYSTEM SHALL return a `daemon_overloaded` error envelope for any additional
  call rather than queuing it unboundedly.
- WHILE the pending-call limit is reached, THE SYSTEM SHALL NOT block the
  caller goroutine; the overload response MUST be returned immediately.

### Reconnect resilience (Slice 2)

- WHEN the websocket connection between daemon and relay drops for any reason,
  THE SYSTEM SHALL attempt to reconnect with exponential backoff starting at 2s,
  doubling each attempt, capped at 60s.
- WHEN a daemon reconnects successfully after a session that lasted at least
  60s, THE SYSTEM SHALL reset the backoff to the 2s base.
- WHEN the relay does not receive a pong within 5 seconds of sending a ping,
  THE SYSTEM SHALL drop the connection and trigger reconnect on the daemon side.

  Note: exponential backoff and graceful SIGTERM shutdown are already implemented
  in `cmd/local/daemon.go`. The 5-second pong deadline enforcement on the server
  side (`internal/bridge/server.go`) is not yet enforced (server sends pings but
  does not time out on missing pong).

### OS keychain integration (Slice 5)

- WHEN `mctl-telegram-local init` completes, THE SYSTEM SHALL store the
  passphrase-derived key material in the OS keychain (macOS Keychain Services,
  Linux libsecret/GNOME Keyring with encrypted-file fallback for headless,
  Windows Credential Manager) via the `99designs/keyring` library.
- WHEN `mctl-telegram-local connect` completes, THE SYSTEM SHALL store the
  bridge token in the OS keychain rather than as a plain JSON file under
  `~/.config/mctl-telegram-local/`.
- IF an existing installation has secret material stored as plain files, THEN
  THE SYSTEM SHALL migrate those files into the keychain on first run after
  upgrade and delete the plain files.

### Cross-platform distribution (Slice 4)

- WHEN a release tag is pushed, THE SYSTEM SHALL produce signed binaries for
  macOS (Intel + ARM64), Linux (x86_64 + arm64), and Windows (x86_64) via
  GoReleaser.
- WHEN a macOS user runs `brew install mctlhq/tap/mctl-telegram-local`, THE
  SYSTEM SHALL install a working binary.
- WHEN `mctl-telegram-local` starts, IF a newer release is available, THE
  SYSTEM SHALL print a one-line hint to stderr; it SHALL NOT auto-download
  without explicit user action.

### Cross-repo OAuth scope (Slice 3)

- WHEN a user runs `mctl-telegram-local connect`, THE SYSTEM SHALL initiate an
  OAuth2 PKCE flow against the `local-bridge` scope on `mctl-api`, resulting in
  a JWT with `aud="bridge"` and TTL 1h, without requiring the user to manually
  copy an MCP token.

### User-facing documentation (Slice 6)

- WHEN a new user follows `docs/local-bridge.md`, THE SYSTEM SHALL describe the
  full setup path (install, init, login, connect) for macOS, Linux, and Windows.
- WHEN a user reads the troubleshooting section, THE SYSTEM SHALL provide
  resolution steps for: daemon won't start, websocket connection refused,
  session re-auth required.

### End-to-end acceptance

- WHEN a new user completes the install-init-login-connect sequence via
  `brew install` (or platform equivalent), THE SYSTEM SHALL allow that user to
  invoke Telegram MCP tools through Claude.ai without any CLI or Kubernetes
  access to the server.
- WHEN the user's network is interrupted for up to 5 minutes and restored, THE
  SYSTEM SHALL reconnect the daemon automatically without manual intervention.

## Out of scope

- End-to-end encryption of MCP payloads between the daemon and Claude.ai
  (requires client-side support that does not exist).
- mctl-portal "Connected daemons" UI view.
- Multi-daemon per user (laptop + desktop sharing one session); the current
  design enforces a singleton per user_id.
- Mobile daemon (iOS/Android).
- Flipping an existing `mode='hosted'` account to `mode='local'` via a
  self-service UI (operators do this out-of-band for now).

## Open questions

1. **Pong deadline on the server side.** The server sends pings every 25s but
   currently has no timeout on receiving a pong. The issue says "failure → drop
   connection and reconnect" within 5s. The most natural fix is a short
   `context.WithTimeout` around `wsjson.Read` in the server's reader goroutine,
   but `coder/websocket` ties read cancellation to context cancellation, which
   also closes the underlying connection — that is the desired behaviour here.
   Confirm the intended pong deadline is 5s (as stated) or 30s (as defined by
   `DeadlinePingPong` in `protocol.go`).

2. **Audit `call_path` column vs. tool_name suffix.** The issue says "column or
   suffix". This proposal recommends a new `call_path TEXT DEFAULT 'hosted'`
   column on `audit_logs` for clean queryability. If schema-change risk is a
   concern, appending `/local` to `tool_name` (e.g., `list_dialogs/local`) is
   a zero-migration alternative but breaks exact-match filtering on tool names.
   Team should confirm the preference before the implementer starts.

3. **Backpressure counter scope.** The issue says "cap 100 pending calls per
   daemon". The Hub's `pending` map already uses `sync.Map` with no bound.
   Implementing a hard cap requires an atomic counter per `daemonConn`. Confirm
   whether the 100-call cap applies to total in-flight `Hub.Call` goroutines or
   to the outbound send-channel depth (currently capped at 16 by `Register`).

4. **OAuth scope cross-repo timeline.** Slice 3 requires changes in `mctl-api`
   and `mctl-web` before the daemon's `connect` subcommand can use the new OAuth
   PKCE flow. The existing `connect --token` path remains functional until then.
   Confirm whether community release can ship with the manual-token path and
   migrate to OAuth in a follow-on, or whether Slice 3 is a hard gate.
