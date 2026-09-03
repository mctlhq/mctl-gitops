# fix(alerts): MctlBridgeDaemonsFlapping resolves itself while a daemon is still flapping

## Context

`MctlBridgeDaemonsFlapping` (`deploy/alerts/mctl-telegram.rules.yaml`) is meant to catch
a Local Bridge daemon stuck in a reconnect loop. Its expression,
`changes(mctl_bridge_active_daemons[10m]) > 20`, was sized for a fleet where many
daemons each contribute their own connect/disconnect pair to the shared gauge. With the
current pilot running a small number of daemons, the threshold is effectively
unreachable in steady state for a single flapping daemon.

The daemon's reconnect loop (`cmd/local/daemon.go`, `runDaemon`/`daemonSession`) backs
off from `reconnectBase` (2s) up to `reconnectMax` (60s), doubling each failed attempt,
and only resets to base if a session ran for at least `reconnectMax` (`if
time.Since(sessionStart) >= reconnectMax { backoff = reconnectBase }`). A daemon that
never holds a session that long never resets: its backoff settles at the 60s cap. Each
reconnect cycle moves `mctl_bridge_active_daemons` twice (1->0 on disconnect via
`Hub.Unregister`/`UnregisterSend`, 0->1 on the next `Hub.Register`), so a settled flap
produces about 600s / 60s = 10 cycles per 10-minute window = 20 gauge changes — at, but
not above, the current `> 20` threshold. The alert fires during the first ~2 minutes
while backoff is still ramping (2s, 4s, 8s, 16s, 32s produce dense cycles), then goes
quiet once the ladder settles, exactly when the flap has become a permanent condition
instead of a transient one. An on-call engineer sees a warning clear itself and reads
that as recovery.

This matters because Local Bridge is the credential path for `local`-mode Telegram
accounts (`internal/bridge/hub.go`, `internal/bridge/server.go`); a daemon stuck
flapping means that user's bridge calls are failing (`ErrNoDaemonConnected`) for the
whole episode, silently, once the alert has resolved.

## User stories

- AS an on-call engineer I WANT `MctlBridgeDaemonsFlapping` to keep firing for as long
  as a daemon is actually cycling SO THAT I do not mistake a settled flap for a
  recovered one.
- AS an on-call engineer I WANT the runbook's stated threshold and the alert's actual
  expression to match SO THAT I can trust the diagnostic guidance while triaging.
- AS a future maintainer I WANT a test that fails if the alert stops catching a
  60-second-cycle flap SO THAT a future edit to the expression or the daemon's backoff
  constants cannot silently reopen this gap.

## Acceptance criteria (EARS)

- WHEN a single Local Bridge daemon flaps continuously with its backoff settled at the
  `reconnectMax` (60s) cap for at least 10 minutes THE SYSTEM SHALL keep
  `MctlBridgeDaemonsFlapping` firing (not resolved) for that daemon.
- WHEN a normal rollout disconnects and reconnects exactly one daemon (one 1->0 then
  0->1 transition pair, i.e. 2 gauge changes in the 10-minute window) THE SYSTEM SHALL
  NOT fire `MctlBridgeDaemonsFlapping`.
- WHILE the alert rule expression in `deploy/alerts/mctl-telegram.rules.yaml` encodes a
  numeric threshold for `changes(mctl_bridge_active_daemons[10m])` THE SYSTEM SHALL keep
  the `runbook_url` target section (`docs/runbook.md`, anchor
  `#mctlbridgedaemonsflapping`) describing the same threshold and the same
  connect/disconnect-counts-as-two-changes mechanics.
- IF the alert's rule file or the daemon's `reconnectBase`/`reconnectMax` constants
  change such that a steady 60s-cycle flap would no longer cross the threshold THEN THE
  SYSTEM SHALL fail the corresponding promtool rule unit test in CI.
- WHERE the fix changes only the alert threshold (interim, single-daemon-scoped fix)
  THE SYSTEM SHALL record in the rule's comments and in the runbook that the new
  threshold is coupled to the current daemon count and will need re-tuning as the pilot
  fleet grows, pointing at the counter-based alternative described in the issue.

## Out of scope

- Introducing a new `mctl_bridge_connections_total` monotonic counter and switching the
  alert to `increase(...) > N` (the issue's "option 2"). This is the structurally better
  fix — per-daemon via labels, independent of fleet size — but requires new
  instrumentation in `internal/bridge/hub.go`, a metrics registration change in
  `internal/metrics/metrics.go`, and its own test coverage. It is recorded here as
  planned follow-up, not part of this proposal.
- Any change to the daemon's backoff/reconnect algorithm itself
  (`cmd/local/daemon.go`). The issue's problem is detection, not the backoff design.
- Alerting on bridge call failure rate (`mctl_bridge_calls_total`) as a corroborating
  signal. Useful context for the runbook's existing diagnostic queries, not part of this
  fix.
- Re-tuning any other alert in `deploy/alerts/mctl-telegram.rules.yaml`.

## Open questions

- The issue explicitly offers two options and says "pick one deliberately." This
  proposal picks option 1 (lower the threshold) as the immediate fix, per the issue's
  own framing of it as "defensible as an interim fix if it is recorded as such" — it is
  a small, low-risk change that closes the detection gap now. Option 2 (connection
  counter) is left as an explicit, recorded follow-up rather than bundled in, since it
  touches instrumentation code and its own test surface. If a reviewer wants option 2
  done immediately instead, that changes the design and task list substantially.
- The issue proposes `> 4` as the interim number ("more than two reconnects in ten
  minutes"). This proposal adopts that exact value: it is derived independently in this
  document (10 steady-state cycles/10min = 20 changes for a settled flap; a rollout
  produces exactly 2) and both derivations agree it comfortably separates the two cases.
  No open question remains on the number itself.
