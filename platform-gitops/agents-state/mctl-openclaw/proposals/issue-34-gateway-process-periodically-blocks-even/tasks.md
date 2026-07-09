# Tasks: issue-34-gateway-process-periodically-blocks-even

- [ ] 1. Add `getFileStatSnapshotAsync` to `src/config/cache-utils.ts` — DoD:
  new async export calls `fs.promises.stat`, returns the same `FileStat` shape
  as `getFileStatSnapshot`, returns `undefined` on ENOENT without throwing; unit
  test verifies async stat is called and cache-miss path works.

- [ ] 2. Add `loadSessionStoreAsync` to `src/config/sessions/store-load.ts`
  (depends on 1) — DoD: new async export mirrors the mtime-based cache check
  using `getFileStatSnapshotAsync` + existing `readSessionStoreCache`; on cache
  miss calls `fs.promises.readFile` then `JSON.parse`; runs
  `applySessionStoreMigrations` + `normalizeSessionStore` on the parsed result;
  returns `{}` on ENOENT; updates the session-store cache after a successful
  read; passes the full existing `loadSessionStore` test suite when the async
  variant is substituted.

- [ ] 3. Update `buildSessionSummary` in `src/commands/health.ts` to call
  `loadSessionStoreAsync` (depends on 2) — DoD: the `await import(...)` in
  `buildSessionSummary` (line 131) resolves `loadSessionStoreAsync` from
  `store.js`; the function signature and return type are unchanged; no
  synchronous `fs.*Sync` call remains in the `buildSessionSummary` call chain;
  the `src/commands/health.ts` export barrel re-exports `loadSessionStoreAsync`
  for callers outside the module if needed.

- [ ] 4. Parallelize `probeAccount` calls in `getHealthSnapshot`
  (`src/commands/health.ts:382-466`) — DoD: the inner `for (const accountId of
  accountIdsToProbe)` loop is replaced with `Promise.allSettled`; each settled
  result is collected into `accountSummaries` in the same order as
  `accountIdsToProbe`; a rejection from one account's probe does not abort other
  accounts' probes; the outer per-plugin loop remains sequential (plugins are
  probed one at a time).

- [ ] 5. Wire proactive event-loop degradation logging into
  `startGatewayMaintenanceTimers` (`src/gateway/server-maintenance.ts`)
  (depends on no prior task, can be done independently) — DoD: the params type
  gains an optional `getEventLoopHealth?: () => GatewayEventLoopHealthMonitor['snapshot'] | undefined`
  field; inside the 30-second `tickInterval` callback, if `getEventLoopHealth`
  is provided and `snapshot().degraded === true`, a `warn`-level structured log
  is emitted with `{ reasons, delayMaxMs, delayP99Ms, utilization, cpuCoreRatio,
  uptimeMs }`; the log line is emitted at most once per `tickInterval` fire (no
  additional debounce needed); `server.impl.ts` passes `readinessEventLoopHealth.snapshot`
  bound as `getEventLoopHealth`.

- [ ] 6. Add a large-file size guard to `loadSessionStoreAsync` (depends on 2)
  — DoD: if `stat.sizeBytes` exceeds a configurable threshold (default 10 MB,
  overridable via `OPENCLAW_SESSION_STORE_MAX_PARSE_BYTES` env var), the
  function emits a single `warn` log and returns `{}` rather than attempting to
  parse; a unit test verifies the guard triggers and logs correctly.

## Tests

- [ ] T1. Unit test `loadSessionStoreAsync` in
  `src/config/sessions/store-load.test.ts` (or a sibling file): mock
  `fs.promises.stat` and `fs.promises.readFile`; verify cache-hit path skips
  file read; verify cache-miss path reads the file and calls `JSON.parse`;
  verify ENOENT returns `{}` without throwing; verify large-file guard skips
  parse and emits a warning.

- [ ] T2. Unit test parallel probing in `src/commands/health.test.ts` (or
  existing health test): mock `plugin.status.probeAccount` to resolve after
  different delays for two accounts; verify both probes are started before
  either resolves (i.e., they run concurrently, not sequentially); verify a
  rejection from one account does not prevent the other account's result from
  appearing in the returned snapshot.

- [ ] T3. Unit test for `startGatewayMaintenanceTimers` degradation log
  (`src/gateway/server-maintenance.test.ts`): provide a `getEventLoopHealth`
  stub that returns `{ degraded: true, reasons: ['event_loop_delay'], ... }`;
  advance the 30-second tick timer by one interval; assert `logHealth.warn` was
  called with the expected fields; advance again with `degraded: false`; assert
  `logHealth.warn` was not called.

- [ ] T4. Regression test: call `getHealthSnapshot({ probe: true })` with a
  mocked `loadSessionStoreAsync` that resolves asynchronously; assert no
  synchronous `fs.readFileSync` or `fs.statSync` is called during the health
  snapshot. (Spy on `node:fs` module before the call.)

- [ ] T5. Integration: run `pnpm test src/commands/health.test.ts
  src/config/sessions/store-load.test.ts src/gateway/server-maintenance.test.ts`
  in a Testbox (`pnpm test:changed`) after all code changes land to confirm no
  regressions in the health-snapshot or session-store pipelines.

## Rollback

1. Revert the three changed files (`src/config/cache-utils.ts`,
   `src/config/sessions/store-load.ts`, `src/commands/health.ts`,
   `src/gateway/server-maintenance.ts`) to the commit before this change using
   `git revert <merge-sha>` or by reverting the individual files. No schema
   changes, no migrations, and no persistent state is altered by this change.
2. The session store on disk is not touched by these changes (read-only path);
   rollback leaves all session data intact.
3. The event-loop health monitor (`src/gateway/server/event-loop-health.ts`) is
   not modified; removing the logging wire-up in task 5 is a one-line revert in
   `server.impl.ts` with no other side effects.
4. After rollback, redeploy the gateway pod. The synchronous behavior resumes
   immediately on restart; no cache flush or state migration is needed.
