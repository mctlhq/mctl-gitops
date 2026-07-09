# Design: issue-34-gateway-process-periodically-blocks-even

## Current state

### Timer topology

`startGatewayMaintenanceTimers` (`src/gateway/server-maintenance.ts:17-196`) starts
four timers on gateway startup:

| Timer | Interval | Work done |
|---|---|---|
| `tickInterval` | 30 s | Broadcasts `{ts}` keepalive — negligible |
| `healthInterval` | 60 s | Calls `refreshGatewayHealthSnapshot({ probe: true })` |
| `dedupeCleanup` | 60 s | Map iteration + conditional `toSorted` + abort-controller sweep |
| `mediaCleanup` | 60 min | `cleanOldMedia` — fully async, has in-flight guard |

A fifth timer is started separately by `startChannelHealthMonitor`
(`src/gateway/channel-health-monitor.ts:76-203`) at `DEFAULT_CHECK_INTERVAL_MS
= 5 * 60_000` (5 minutes). It iterates channel runtime snapshots and may call
`stopChannel` / `startChannel` on unhealthy accounts. This loop is async and
does not call `loadSessionStore`.

### The health-probe call chain

Every 60 seconds, `healthInterval` calls:

```
refreshGatewayHealthSnapshot({ probe: true })   // server/health-state.ts:75
  └─ getHealthSnapshot({ probe: true })          // commands/health.ts:305
       ├─ for each agent:
       │    buildSessionSummary(storePath)        // commands/health.ts:130
       │      └─ loadSessionStore(storePath)      // config/sessions/store-load.ts:100
       │           ├─ getFileStatSnapshot()        //   → fs.statSync (sync)
       │           ├─ fs.readFileSync(storePath)   //   → sync, blocks event loop
       │           └─ JSON.parse(raw)              //   → sync, blocks event loop
       │
       └─ for each channel plugin:
            for each accountId in accountIdsToProbe:  // sequential await
              await plugin.status.probeAccount(...)    // commands/health.ts:397
```

`refreshGatewayHealthSnapshot` deduplicates concurrent calls via a module-level
`healthRefresh` promise (`server/health-state.ts:81-115`): if a refresh is
already in-flight, subsequent callers join the same promise. This prevents
stacking multiple probes but does not prevent the single in-flight probe from
blocking the event loop.

### Why the event loop blocks

`getFileStatSnapshot` (`src/config/cache-utils.ts:151`) calls `fs.statSync`.
`loadSessionStore` then calls `fs.readFileSync(storePath, "utf-8")` and
`JSON.parse(raw)` unconditionally when the mtime-based cache misses
(`src/config/sessions/store-load.ts:127,132`). In a live environment,
`sessions.json` is updated on every session write, so the mtime cache misses on
almost every health-probe tick. All three calls — `statSync`, `readFileSync`,
`JSON.parse` — are synchronous and run on the main thread. A `sessions.json`
that has grown to tens of megabytes (many active sessions, each entry carrying
metadata from normalized fields) can block the main thread for 10-40 seconds
per parse, directly stalling every pending timer and queued Promise callback,
including the `setTimeout(..., 10000)` abort timer inside `fetchWithTimeout`
(`src/utils/fetch-timeout.ts:100-107`). The timer fires ~30 seconds late, which
is the canary log line reported in the issue.

### Why sequential probing compounds the problem

Inside `getHealthSnapshot`, probes for every account of every configured channel
plugin are issued in a nested `for...of` loop with `await` at each iteration
(`src/commands/health.ts:382-406`). The probe timeout is `DEFAULT_TIMEOUT_MS =
10_000` ms (`src/commands/health.ts:48`). If the tenant has N accounts across M
plugins, the maximum sequential-probe duration is N * 10 s. Even when individual
probes resolve quickly, each `await` yields to the microtask queue but never to
the macro-task queue (timers, I/O events), so incoming RPC frames accumulate in
the uv I/O queue while the health-probe Promise chain consumes the async frame.

### Event-loop health monitor

`createGatewayEventLoopHealthMonitor` (`src/gateway/server/event-loop-health.ts`)
already measures `perf_hooks.monitorEventLoopDelay` (resolution 20 ms), event
loop utilization, and CPU core ratio. Its `snapshot()` output is wired into the
`/readyz` response via `readinessEventLoopHealth` in `server.impl.ts:740`.
However, the monitor only surfaces degradation reactively when `/readyz` is
polled; it does not proactively log when delay spikes, so the stall windows are
invisible in structured logs.

### What explains the ~10-12 minute cadence

The exact cadence is not explained by any single known timer interval. Possible
contributing factors:

- The 60 s health-probe block duration fluctuates with session-store file size
  and OS I/O scheduling. If the block is severe enough to delay the dedupe
  cleanup timer (also 60 s) into the same event-loop slot, the two compete and
  extend the overall stall window.
- The 5-minute channel health monitor and 60 s health probe share a harmonic at
  5 minutes; if both run while the session store is large, the combined async
  queue depth is higher.
- None of the known timers has a 10-minute period. The true cause of the cadence
  requires runtime instrumentation to confirm (see Open questions in requirements).

## Proposed solution

### Change 1: Async session-store reads in the health-probe path

Add an async variant of the session-store read to `src/config/sessions/store-load.ts`:

```typescript
// New export alongside the existing loadSessionStore
export async function loadSessionStoreAsync(
  storePath: string,
  opts: LoadSessionStoreOptions = {},
): Promise<Record<string, SessionEntry>> {
  if (!opts.skipCache && isSessionStoreCacheEnabled()) {
    const currentFileStat = await getFileStatSnapshotAsync(storePath); // fs.promises.stat
    const cached = readSessionStoreCache({ storePath, mtimeMs: currentFileStat?.mtimeMs, ... });
    if (cached) return cached;
  }
  let raw: string;
  try {
    raw = await fs.promises.readFile(storePath, "utf-8");
  } catch {
    return {};
  }
  const parsed = JSON.parse(raw);  // still sync, but file read is off the hot path
  // ... existing normalization, migration, caching logic
}
```

Update `buildSessionSummary` (`src/commands/health.ts:130-147`) to call
`loadSessionStoreAsync` instead of `loadSessionStore`. The function is already
`async`, so the call site change is a one-line substitution.

`JSON.parse` on the already-read string is still synchronous. For files smaller
than a configurable threshold (e.g., 5 MB) this is acceptable; if needed, a
follow-up can chunk parsing via `setImmediate` or move it to a worker thread.
The primary win is moving the blocking disk read off the main thread.

### Change 2: Parallel channel account probing

In `getHealthSnapshot` (`src/commands/health.ts:380-466`), replace the inner
sequential loop:

```typescript
// Before
for (const accountId of accountIdsToProbe) {
  // ... resolve context ...
  probe = await plugin.status.probeAccount({ ... });
  // ... build snapshot ...
}
```

with a concurrent fan-out using `Promise.allSettled`:

```typescript
// After
const accountResults = await Promise.allSettled(
  accountIdsToProbe.map(async (accountId) => {
    // ... resolve context ...
    const probe = plugin.status?.probeAccount
      ? await plugin.status.probeAccount({ ... }).catch((err) => ({ ok: false, error: ... }))
      : undefined;
    return { accountId, probe, ... };
  }),
);
// collect settled results into accountSummaries
```

Each `probeAccount` call already has its own `timeoutMs` budget, so concurrent
calls are bounded. The result collection loop after `Promise.allSettled` is
synchronous and O(n) in the number of accounts, which is trivial.

### Change 3: Proactive event-loop degradation logging

Extend `startGatewayMaintenanceTimers` or the tick timer to sample the event
loop health monitor and emit a warning when degraded:

```typescript
// In server-maintenance.ts, within the tickInterval (30 s) callback:
const health = params.getEventLoopHealth?.();
if (health?.degraded) {
  params.logHealth.warn(
    `event loop degraded (reasons=${health.reasons.join(',')}, ` +
    `delayMaxMs=${health.delayMaxMs}, utilization=${health.utilization})`,
  );
}
```

This reuses the existing `GatewayEventLoopHealthMonitor.snapshot()` API without
adding a new timer. The 30-second tick is low-overhead and appropriate for
detecting sustained degradation windows (the stall windows in the issue last
4-5 minutes). No new dependencies are introduced.

### Change 4: Add `getFileStatSnapshotAsync` to `src/config/cache-utils.ts`

The existing `getFileStatSnapshot` calls `fs.statSync`. Add a paired async
version:

```typescript
export async function getFileStatSnapshotAsync(
  filePath: string,
): Promise<FileStat | undefined> {
  try {
    const stats = await fs.promises.stat(filePath);
    return { mtimeMs: stats.mtimeMs, sizeBytes: stats.size };
  } catch {
    return undefined;
  }
}
```

Used only by `loadSessionStoreAsync`. The synchronous `getFileStatSnapshot`
remains for callers that require synchronous behavior.

## Alternatives

### A. Move JSON parsing to a `worker_threads` worker

A dedicated worker thread would fully decouple `JSON.parse` from the main
thread. This eliminates the remaining synchronous CPU work. It is the correct
long-term direction for large session stores but adds significant complexity:
a worker file, inter-thread message passing, serialization round-trips, and
error handling across the thread boundary. The async read in Change 1 already
removes the dominant block (disk I/O); `JSON.parse` on a warmed kernel page
cache is much faster than a cold `readFileSync`. This option should be revisited
if profiling after Change 1 shows `JSON.parse` itself still contributes
measurable delay.

### B. Reduce `HEALTH_REFRESH_INTERVAL_MS` from 60 s to 300 s

Cutting the probe frequency to 5 minutes would reduce the chance of a stall
overlapping with a user action. It does not eliminate the stall when it
does occur, and it degrades freshness of the health cache for clients that
poll the snapshot. Rejected in favor of fixing the root cause.

### C. Skip session summary in the periodic background probe

Remove the `buildSessionSummary` call from the background probe path and only
compute it when a client explicitly requests a health snapshot (e.g., the
`health` RPC method). This eliminates the synchronous read on the 60-second
timer but reduces the usefulness of the cached health snapshot that is broadcast
to all connected clients on change. The async read in Change 1 achieves the
same safety without sacrificing observability.

## Platform impact

### Migrations

None. `loadSessionStoreAsync` is a new export alongside the existing
`loadSessionStore`. No existing callers change; only `buildSessionSummary` is
updated to use the async variant.

### Backward compatibility

The async path performs identical normalization, migration, and caching logic as
the synchronous path. The health snapshot payload shape is unchanged. The
`/readyz` response shape is unchanged.

### Resource impact

- Disk I/O for `fs.promises.readFile` is handled by libuv's thread pool
  (default size 4), not the main thread. On pods with multiple concurrent
  readers this may increase thread pool utilization, but the session-store file
  is read at most once per 60-second window due to the `healthRefresh`
  deduplication guard.
- `Promise.allSettled` on N account probes uses N concurrent network
  connections. For the `ovk` tenant (3 skills listed, Telegram channel), the
  number of accounts is expected to be small (under 10), posing no resource risk.
  If a tenant has many accounts, the existing per-probe timeout (10 s) provides
  the bounding constraint.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `loadSessionStoreAsync` diverges from `loadSessionStore` migration logic over time | Both call a shared `applySessionStoreMigrations` / `normalizeSessionStore` helper; async variant wraps the same logic |
| Concurrent account probes cause rate-limiting at a channel API (e.g., Telegram) | Probe concurrency is bounded by `accountIdsToProbe` length per plugin; each plugin probes its own accounts concurrently, not across plugins |
| `JSON.parse` on a very large file (>50 MB) still blocks for seconds | A size guard can be added to `loadSessionStoreAsync`: skip the parse and return an empty summary if `sizeBytes` exceeds a configured limit, emitting a warning |
| Event-loop degradation log spam if the stall is sustained | The 30-second tick interval bounds log output to at most 2 lines per minute during a degradation window; no debounce needed at that rate |
