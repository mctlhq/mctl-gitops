# Design: issue-971-hardening-bridge-lease-token-redaction-e

## Current state

All bridge logic lives in `internal/bridge/`. It is dark by default:
`cmd/api/main.go` builds `bridge.NewStore` only when
`MCTL_BRIDGE_ENABLED=true`, and starts `bridge.Dispatcher` only when
`TEMPORAL_ADDRESS` is also set.

**Result persistence (finding 1).** `store.go::submitTx`:
- Validates `res` (`schema.go::Result`, which has a required
  `LeaseToken string json:"lease_token"`).
- Compares `tokenEqual(row.LeaseToken, res.LeaseToken)`.
- Stores `stored, _ := json.Marshal(res)` into `bridge_commands.result`. The
  token is therefore persisted in JSONB.

`result_digest` comes from `Result.Digest()`: sha256 over
`json.Marshal(r)`, which includes the token. That digest is also written to
`bridge_signal_outbox.result_digest` and sent by `Dispatcher.RunOnce` via
`SignalBridgeResult(workflowID, runID, commandID, resultDigest)`.

`store.go::ReadOutcome` selects `result` and returns it verbatim as
`Outcome.Result json.RawMessage`, token included. It is not exposed over
HTTP: `internal/api/handlers_bridge.go::BridgeService` lists only `Claim`,
`SubmitResult` and `IssueWritePermit`, and no other caller exists in the
repo. Replay (`row.Status == StatusCompleted && row.ResultDigest == digest`)
runs only after the token check against the `bridge_commands.lease_token`
column, so it never reads the stored result JSON.

`handlers_bridge.go::auditBridge` already logs ids, digests and codes only.
The dispatcher logs `command_id` only.

**Expiry (finding 2).** The only expiry path is the first statement of
`store.go::claimTx`:
`UPDATE bridge_commands SET status='expired' ... WHERE provider_ref=$1 AND tenant = ANY($2) AND status IN ('pending','leased') AND expires_at <= now()`.
It is scoped to the polling provider and its tenant bound, so commands of a
provider that never polls never expire. `leaseLive` refuses a past-`expires_at`
row with `lease_stale`, so no wrong result is accepted, but the row and the
waiting workflow never reach a terminal state.

**Transitions (finding 3).** `addTransition` is called with literal
`from_status` values in two places:
- `claimTx` expiry: `addTransition(..., "open", StatusExpired, ...)`. The
  actual prior status is `pending` or `leased`.
- `claimTx` lease: `addTransition(..., StatusPending, StatusLeased, ...)`, even
  when the selector picked `status='leased' AND lease_expires_at <= now()` (a
  reclaim).

`Cancel` and `submitTx` already record the locked `row.Status` /
`StatusLeased` correctly.

**Tests.** `store_pg_test.go` (skipped without `TEST_DATABASE_URL`) covers
replay/tenancy, reclaim fencing, permits and reclaim-after-permit. Nothing
inspects `bridge_command_transitions` or the stored `result` JSON.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` = `/workdir/mctl-gitops/platform-gitops`.
  `grep -rn BRIDGE` over it, excluding agents-state, found no `MCTL_BRIDGE_*`
  setting for mctl-api. The only hits are mctl-telegram's unrelated
  `BOT_START_BRIDGE_TOKEN`. mctl-api is deployed from
  `bootstrap/templates/mctl-platform/mctl-api.yaml`, which sets no bridge env.
  So the bridge is not enabled in the deployed configuration, and no
  production rows are expected in `bridge_commands`.
- `services/` has no `mctl-api` service directory (tenants: admins, karabu,
  labs, namax66). mctl-api is a platform component, not a tenant service.
- The mctl MCP tools were not called. Reading the cluster DB row count is not
  possible through them, so whether any historical bridge rows exist is
  unobserved. The historical scrub below is written to be correct either way.

## Proposed solution

### 1. Redact the token from stored and read-back results (no contract change)

- Add an unexported `storedResult` type in `schema.go`, or a method
  `(*Result) redacted() ([]byte, error)`. It marshals every `Result` field
  except `lease_token`, in the same field order. `submitTx` stores
  `res.redacted()` instead of `json.Marshal(res)`.
- **The digest is unchanged.** `Result.Digest()` keeps hashing the full parsed
  projection including the token. This keeps:
  - historical `result_digest` and outbox values valid;
  - replay (same body and token, so the same digest) and `result_conflict`
    semantics byte-identical;
  - the signal payload unchanged.

  The digest is a one-way sha256 over a document that carries 192 bits of
  token entropy (`randURL(24)`), so it reveals nothing usable. No schema,
  PROVENANCE or digest AMEND is needed. If review decides the digest must
  exclude the token, that is a contract change, and the implementer must stop
  and request the AMEND, as the issue requires.
- `ReadOutcome` defensively scrubs on read: `SELECT ... result - 'lease_token'`
  in SQL. Old and new rows read back identically.
- Historical rows: do **not** append a bulk UPDATE to `bridgeSchema` or run a scrub from `NewStore`.
  Introduce a bounded `Store.ScrubLegacyResultBatch(ctx, limit)` maintenance operation, invoked only by
  a separately authorized operator before activation. Per-batch: select at most `limit` rows with
  `result ? 'lease_token'` under `FOR UPDATE SKIP LOCKED`, update using `result - 'lease_token'` in short
  transactions, apply bounded statement/lock timeouts, and report processed/remaining/errors.
  Retries are idempotent and resumable, with independently verified zero remaining before provider activation;
  read-time `ReadOutcome` redaction works *even before* the scrub. New stored results are always redacted.
  This avoids unbounded startup locks, WAL bursts and stalled rolling deployments. Explicitly consider any
  token copies already present in backups/retention.
- Document the private stored-result shape in `docs/bridge.md`: the stored
  result is the v1alpha1 result minus `lease_token`, and the digest is over the
  submitted projection.

### 2. Bounded asynchronous expiry sweep

- Factor the expiry step out of `claimTx` into
  `expireTx(ctx, tx, scope expiryScope, limit int, actor string) (int, error)`.
  - `scope` is either `{provider, tenants}` (the lazy path) or unscoped (the
    sweep).
  - SQL:
    ```sql
    WITH due AS (
      SELECT command_id, status AS old_status FROM bridge_commands
      WHERE status IN ('pending','leased') AND expires_at <= now()
        [AND provider_ref=$p AND tenant = ANY($t)]
      ORDER BY expires_at LIMIT $n FOR UPDATE SKIP LOCKED)
    UPDATE bridge_commands c SET status='expired', updated_at=now(),
      effect_state = CASE WHEN c.effect_state='permitted' THEN 'unknown' ELSE c.effect_state END
    FROM due WHERE c.command_id = due.command_id
    RETURNING c.command_id, c.workflow_id, c.run_id, c.lease_epoch, due.old_status
    ```
  - It inserts the transition (`from_status = old_status`) and the `expired`
    outbox row (`ON CONFLICT DO NOTHING`) exactly as today.
- Add `Store.ExpireDue(ctx, limit) (int, error)`, one transaction per batch,
  actor `system:expiry-sweep`. Add an `Expirer` struct (`expiry.go`) with
  `RunOnce` and `Run(ctx)`: a ticker (default 30s), batch of 100 and explicit finite batch cap/tick.
  Full batches continue up to the cap and residual backlog resumes next tick. Prefer oldest unlocked due
  commands with `ORDER BY expires_at`; SKIP LOCKED rows remain eligible later. Do **not** promise one-interval
  completion when capacity or locks prevent it. Expose redacted metrics for processed count, due backlog,
  oldest overdue age, failures and last successful sweep; alert on sustained age/backlog/error thresholds.
  Tests exercise more than one batch, locked rows, delayed progress and multiple replicas; logs contain only
  counts/errors without token or row content.
- `cmd/api/main.go`: when `bridgeStore` is non-nil, `go (&bridge.Expirer{...}).Run(rootCtx)`.
  This does not depend on Temporal. Read `MCTL_BRIDGE_EXPIRY_SWEEP_INTERVAL`
  (Go duration) as an optional override. Nothing starts when the bridge is off.
- Race safety:
  - `SKIP LOCKED` means the sweep never blocks on, or steals from, a
    transaction holding the row (`submitTx`/`permitTx`/`Cancel` take
    `FOR UPDATE`; `claimTx` locks selected rows).
  - The `status IN ('pending','leased')` re-check under the lock makes a
    committed `completed`/`cancelled` row ineligible.
  - Commit order decides the winner. If the sweep commits first, `submitTx`
    sees `expired` through `leaseLive`. If submit commits first, the sweep
    skips the row.
  - Effects are only escalated `permitted -> unknown`, never downgraded, so an
    ambiguous prior write is never overridden.

### 3. Record the real prior status

- Lazy expiry uses `expireTx`, so it gets the locked `old_status` for free.
- Lease: change the `claimTx` selector to
  `SELECT c.command_id, c.status ... FOR UPDATE OF c SKIP LOCKED`. The row is
  locked from that point, so the selected status is the locked status. Pass it
  to `addTransition(ctx, tx, id, oldStatus, StatusLeased, row.LeaseEpoch, ...)`.
- `Cancel` and `submitTx` are already correct and are left untouched.

## Alternatives

1. **Exclude the token from the digest** (hash the redacted projection).
   Cleaner in isolation. But it changes every digest value, invalidates the
   stored `result_digest` of historical rows (replay of an old completed
   command would become `result_conflict`), and changes the signal payload
   semantics. That is a contract AMEND. Dropped. It stays available as an
   owner decision.
2. **Replace the token with `"redacted"` instead of dropping the key.** The
   stored document would look schema-shaped but would fail the `lt_` pattern
   and could be mistaken for a real token by downstream code. Dropping the key
   is unambiguous. Dropped.
3. **Expire on read, or in a Postgres trigger/`pg_cron`, instead of a Go
   sweep.** On-read expiry still needs a reader; nothing reads abandoned
   commands. `pg_cron` is not part of the shared CNPG setup and could not emit
   outbox rows under the same Go-owned semantics. A Go ticker matches the
   existing `Dispatcher` pattern. Dropped.
4. **Fold lease-token column hashing into this change.** That changes the
   claim/permit/replay token comparison path and the at-rest format, which
   does not fit a "separate, small" proposal. Recorded as a DEFERRED item with
   an activation gate.

## Platform impact

- **Migrations:** no unbounded historical UPDATE in `bridgeSchema` or application startup. A separately
  authorized bounded/restartable maintenance scrub removes legacy JSONB token fields and reports verified
  completion before activation. Failure does not block dark-code startup (redaction on read is immediate),
  but nonzero remaining tokens block activation. Optional expiry index is additive DDL only.
- **Backward compatibility:**
  - Wire schemas, `PROVENANCE`, HTTP routes, error codes, the digest and the
    signal payload are all unchanged.
  - `Outcome.Result` loses the `lease_token` key. That is the intended
    security fix, and no in-repo caller depends on it.
  - Transition rows now say `leased`/`pending` where they said `pending`/
    `open`. Historical rows are not rewritten, because audit history is
    append-only.
- **Resources:** one extra goroutine plus bounded, measured expiry queries every 30s when the bridge
  is enabled; backlog/lock/error metrics are required to assess actual latency. The query filters `status` and `expires_at`. An
  optional partial index
  `CREATE INDEX IF NOT EXISTS bridge_commands_expiry ON bridge_commands (expires_at) WHERE status IN ('pending','leased')`
  keeps it cheap and is added the same additive way. Zero cost when the bridge
  is disabled (the default, and the deployed state).
- **Risks and mitigations:**
  - Risk: the sweep races a result. Mitigated by `SKIP LOCKED`, the status
    re-check and the CAS in `submitTx`. Covered by a PG race test.
  - Risk: the sweep wrongly marks an effect. Effects are only escalated
    `permitted -> unknown`. Covered by a test.
  - Risk: multiple replicas run the sweep at once. `SKIP LOCKED`, the
    status-guarded update and the outbox `ON CONFLICT DO NOTHING` keep it
    idempotent.
  - Risk: token leakage through logs. A test captures slog output from the
    `Expirer`/`Dispatcher` and the store paths and asserts no `lt_` substring.
- **Finding dispositions** (to be copied into the PR):
  1. Redaction: FIXED by this proposal.
  2. Expiry sweep: FIXED.
  3. Transition audit: FIXED.
  4. Plaintext token column at rest and backups: SECURITY DECISION REQUIRED (owner: mctl-api security
     maintainers; dependency: mctl-gitops#2457; criterion: separately reviewed hashing/encryption/expiry
     treatment or explicit scoped risk acceptance **before first provider credential issuance**).

## AMEND 2026-11-08 — bounded migration and realistic expiry contract

Read/write paths redact `Result.lease_token` immediately. Historical cleanup is a separately operated bounded migration, never a full-table update in `NewStore`, with progress, timeout and verified zero remaining before activation. Expiry sweep backlog/lock contention can push latency beyond one tick, so metrics, alerts and >batch/lock/restart tests are required. Plaintext lease-token column and backups remain an independent security-owner credential-issuance gate; JSONB redaction does not make them safe by itself.
