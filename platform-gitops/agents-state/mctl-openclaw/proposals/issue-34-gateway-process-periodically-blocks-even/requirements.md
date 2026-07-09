# Eliminate Gateway Event-Loop Blocks from Synchronous Session-Store Reads and Sequential Channel Probing

## Context

The `openclaw` gateway process periodically stalls its Node.js event loop for
30-45 seconds every 10-12 minutes on the `ovk-openclaw-base-service` preprod
deployment. During each stall window the gateway pegs approximately 85-90% of
one CPU core for 4-5 minutes and every WebSocket RPC response (regardless of
method) is delayed by 30-45 seconds simultaneously. The stall is confirmed as
an event-loop block — not a slow network path — because a `setTimeout(...,
10000)` timeout in `fetchWithTimeout`/`buildTimeoutAbortSignal` fires
approximately 40 seconds late, and a parallel `curl` to the same host responds
in under 120 ms.

The primary periodic trigger is the 60-second health-probe cycle started by
`startGatewayMaintenanceTimers` (`src/gateway/server-maintenance.ts:72-76`),
which calls `refreshGatewayHealthSnapshot({ probe: true })` and ultimately
executes `buildSessionSummary` (`src/commands/health.ts:130-147`). That
function invokes `loadSessionStore` (`src/config/sessions/store-load.ts`)
which calls `fs.statSync` and `fs.readFileSync` followed by `JSON.parse` — all
synchronous, all on the main thread. In a heavily-used tenant with a large
`sessions.json` on disk, a single synchronous parse can block the event loop
for tens of seconds. A secondary contributor is that `probeAccount` calls for
all configured channel accounts are issued sequentially with `await` inside a
`for` loop (`src/commands/health.ts:382-406`), creating an extended async
chain that holds up the Promise queue. Kubernetes liveness and readiness probes
fail during the stall windows, causing brief pod-NotReady periods and
intermittent user-visible errors.

## User stories

- AS a gateway operator I WANT the health-probe cycle to use only async I/O SO
  THAT it never blocks the main event loop regardless of session-store file size.
- AS a gateway operator I WANT channel account probes to run concurrently SO
  THAT a slow or timed-out probe for one account does not delay probes for other
  accounts or unrelated RPC handling.
- AS a site-reliability engineer I WANT the gateway to emit a structured log
  warning whenever measured event-loop delay exceeds a threshold SO THAT I can
  correlate spikes to specific periodic tasks without polling `/readyz`.
- AS a gateway end user I WANT WS RPC responses to remain below 1 second during
  all routine maintenance cycles SO THAT interactive actions (connecting OAuth,
  starting a session) succeed rather than timing out.
- AS a Kubernetes controller I WANT `/healthz` and `/readyz` to respond within
  their deadline during routine maintenance cycles SO THAT the pod is not
  incorrectly marked NotReady.

## Acceptance criteria (EARS)

- WHEN the 60-second health-probe timer fires THE SYSTEM SHALL read the
  session-store file using only async I/O (`fs.promises.stat` /
  `fs.promises.readFile`) so that no single synchronous FS call occupies the
  main thread for more than a negligible duration.
- WHEN `getHealthSnapshot` probes multiple channel accounts THE SYSTEM SHALL
  issue all `probeAccount` calls for the same plugin concurrently using
  `Promise.allSettled` rather than sequentially awaiting each.
- WHILE the event-loop delay monitor reports `delayMaxMs` above 500 ms THE
  SYSTEM SHALL emit a structured warning log line that includes the measured
  delay, the active periodic task label, and the gateway uptime at the time of
  the measurement.
- IF the event-loop delay monitor reports a degraded snapshot when a `/readyz`
  or `/healthz` request arrives THE SYSTEM SHALL include the `eventLoop` field
  in the response body as it does today, without any behavioral regression.
- WHEN `loadSessionStore` is called from the health-probe path and the session
  store file does not exist THE SYSTEM SHALL return an empty store without
  throwing, identical to the current synchronous behavior.
- WHILE an in-flight health-probe refresh is still running when the next
  60-second timer fires THE SYSTEM SHALL return the existing in-flight promise
  and not start a second concurrent read, preserving the existing deduplication
  in `refreshGatewayHealthSnapshot` (`src/gateway/server/health-state.ts:81-115`).
- WHEN the mtime-based session-store cache in `loadSessionStore` determines
  the on-disk file has not changed since the last load THE SYSTEM SHALL return
  the cached parsed store without performing any file I/O, async or otherwise.

## Out of scope

- Migrating all callers of `loadSessionStore` to async; only the
  health-probe-path callers (`buildSessionSummary`) must change in this
  proposal.
- Changing the health-probe interval or the set of accounts that are probed.
- Replacing the session-store format (e.g., switching from a flat JSON file to
  a database).
- Diagnosing or fixing the root cause of the ~10-12 minute cadence, which the
  existing black-box evidence does not yet explain (see Open questions).
- Addressing the media-cleanup timer (`60 * 60_000 ms`) in
  `src/gateway/server-maintenance.ts:189-191`; it already uses fully async
  `fs.promises.readdir` / `fs.promises.lstat` and has an in-flight guard.

## Open questions

1. The ~10-12 minute cadence does not align with any single known timer
   (health probe 60 s, channel health monitor 5 min, media cleanup 60 min).
   Could there be an external periodic actor — a Kubernetes controller,
   Traefik health-check loop, or node-level cron on the preprod host — that
   triggers additional gateway load at this interval? Runtime instrumentation
   is needed to confirm.

2. Is the `ovk` session-store file located on a network filesystem (NFS, EFS,
   or a Kubernetes `hostPath` backed by network storage)? Network-attached
   storage can make `readFileSync` on a file that appears small take orders of
   magnitude longer than local SSD, which would amplify the block duration.

3. The Telegram channel probe (`extensions/telegram/src/probe.ts`) can call
   `auditTelegramGroupMembership` in addition to `getMe` and `getWebhookInfo`.
   How many group memberships does the `ovk` tenant have configured? A large
   number of sequential group-membership HTTP calls during a single probe cycle
   could extend the overall probe window even after the session-store fix.

4. Does `buildSessionSummary` need to call `loadSessionStore` with full
   migration and maintenance passes (`runMaintenance`, `applySessionStoreMigrations`,
   `normalizeSessionStore`)? If those passes are only needed when saving the
   store, health-probe reads could use a lighter read-only async path that
   skips in-memory mutation of the store object, reducing CPU time further.
