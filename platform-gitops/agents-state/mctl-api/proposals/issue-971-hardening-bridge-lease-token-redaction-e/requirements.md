# Bridge hardening after #968: result lease-token redaction, bounded expiry sweep, accurate transition audit

## Context

mctl-api#962 / PR #968 added the dark command bridge (`internal/bridge/`): a
Postgres command outbox, short provider leases and an exactly-once result
callback. The PR was merged with five P3 review findings left open. Issue
#971 tracks three of them. The other two, real-PostgreSQL signal outbox tests
and the `command_expired` vs `lease_stale` error code, belong to #970 and are
not part of this proposal.

The three findings:
1. `Store.submitTx` persists `json.Marshal(res)` into `bridge_commands.result`,
   so the provider's bearer `lease_token` sits in JSONB, and
   `Store.ReadOutcome` returns it to callers.
2. Commands expire only lazily, inside `claimTx`, and only for the claiming
   provider's tenants. A command whose provider never polls stays
   `pending`/`leased` forever.
3. `bridge_command_transitions.from_status` is hardcoded: `"open"` on expiry
   and `pending` on every lease, including the reclaim of a `leased` row. The
   audit trail is wrong.

All three must be fixed before any bridge or provider activation
(mctl-gitops#2457 stays held). The fix must not change the vendored v1alpha1
wire schemas or any unrelated API semantics.

## User stories

- AS a platform security owner I WANT the provider lease token never to be
  persisted in, or returned from, a stored result SO THAT a database read, a
  backup or an outcome read-back cannot replay or impersonate a lease.
- AS a control-plane workflow I WANT every command to reach a terminal state
  by its `expires_at`, plus a bounded delay, even when no provider polls SO
  THAT a waiting execution always gets a terminal signal.
- AS an auditor I WANT each transition row to record the status the command
  really had when it was locked SO THAT I can rebuild the true history of a
  command across reclaims and expiry.

## Acceptance criteria (EARS)

### Finding 1: lease-token redaction

- WHEN `SubmitResult` stores a first-time result THE SYSTEM SHALL write a
  `bridge_commands.result` document that has no `lease_token` key, with every
  other result field unchanged.
- WHEN `SubmitResult` computes `result_digest` THE SYSTEM SHALL keep using the
  existing `Result.Digest()` over the full parsed v1alpha1 projection. Stored
  digests, outbox digests and the `bridge-result` signal payload therefore stay
  byte-identical to today.
- WHEN the same result body is submitted again with the same lease token THE
  SYSTEM SHALL keep returning `replayed: true` with the stored outcome. WHEN a
  body with a different digest is submitted THE SYSTEM SHALL keep returning
  `result_conflict`.
- WHEN `ReadOutcome` returns a result THE SYSTEM SHALL return a document with
  no `lease_token` key. This includes rows written before this change.
- WHEN the bridge store starts (`NewStore` applies `bridgeSchema`) THE SYSTEM SHALL **not** run an unbounded
  historical result scrub. THE SYSTEM SHALL defensively redact `lease_token` from `ReadOutcome` immediately,
  irrespective of migration progress. A separately invoked, bounded, idempotent maintenance operation SHALL
  remove legacy token-bearing JSONB results in short locked batches without holding startup or critical-path
  transactions. THE SYSTEM SHALL report remaining unsafe rows and SHALL block provider activation until
  migration reaches verified zero remaining rows; failures remain visible and retryable.
- THE SYSTEM SHALL NOT write a raw `lease_token` to slog, to audit parameters
  (`auditBridge`), to error messages or to the signal outbox.
- IF the redaction would require changing the v1alpha1 result schema, the
  result digest definition or the subscriber outcome contract THEN
  implementation SHALL stop and request a contract AMEND from the owner. This
  design requires none of them.

### Finding 2: expiry liveness

- WHILE the bridge is enabled (`MCTL_BRIDGE_ENABLED=true` and a store is
  configured) THE SYSTEM SHALL run a background expiry sweep. The sweep is
  independent of any provider poll and of `TEMPORAL_ADDRESS`.
- WHEN a command has `status IN ('pending','leased')` and `expires_at <= now()` THE SYSTEM SHALL become
  eligible for a bounded unscoped sweep that moves it to `expired`, appends one terminal transition and
  inserts one `expired` signal-outbox row (`ON CONFLICT DO NOTHING`), across provider and tenant scopes.
  Under low backlog it SHOULD progress by the next tick; there is **no deterministic one-interval SLA** under
  large backlog, long row locks, replica contention or database failures. THE SYSTEM SHALL expose oldest-due age,
  remaining-due count, processed counts and errors, alert on sustained overdue age/backlog, and safely retry.
- WHEN the sweep expires a command whose `effect_state` is `permitted` THE
  SYSTEM SHALL set `effect_state='unknown'`.
- THE SYSTEM SHALL NOT overwrite an `effect_state` that is already `unknown`,
  `succeeded`, `failed` or `not_performed`.
- THE SYSTEM SHALL process at most a bounded batch per pass (default 100), impose a finite number of batches
  per tick and skip rows locked by a concurrent claim, result, permit or cancel (`FOR UPDATE SKIP LOCKED`).
  Backlog resumes on subsequent ticks without starving oldest unlocked rows, and persistent errors/lock skips
  remain observable. Each transition happens at most once.
- WHEN a result submission and the sweep race on the same command THE SYSTEM
  SHALL end in exactly one terminal state (`completed` or `expired`), with
  exactly one outbox row and one terminal transition.
- WHILE `MCTL_BRIDGE_ENABLED` is unset (the default) THE SYSTEM SHALL start no
  sweep and change no behaviour.

### Finding 3: transition audit correctness

- WHEN a command is leased THE SYSTEM SHALL record the status that was read
  under the row lock as `from_status`: `pending` for a first lease, `leased`
  for a reclaim. It SHALL record the new `lease_epoch`.
- WHEN a command is expired, lazily in `Claim` or by the sweep, THE SYSTEM
  SHALL record the locked prior status (`pending` or `leased`) as
  `from_status`, never `"open"`.
- THE SYSTEM SHALL record transitions in commit order per command (`id`
  ascending) and only for the command's own row. No cross-tenant row is ever
  touched by a provider-scoped call.

### Governance

- Each finding SHALL be marked FIXED (linked PR and test) in the implementing
  PR description, or DEFERRED with a reason, an owner, an activation
  dependency and an expiry criterion. Finding 1 SHALL NOT be deferred past
  activation. A verified complete historical scrub and an explicit security decision on the plaintext
  `bridge_commands.lease_token` column, backup retention and replay risk are required **before first
  provider credential issuance**; redacted JSONB alone is not complete credential-at-rest protection.
- Regression tests SHALL run against real PostgreSQL (`TEST_DATABASE_URL`)
  wherever row locking or SQL is involved.

## Out of scope

- Signal outbox PostgreSQL tests and the `command_expired` vs `lease_stale`
  code. Both belong to #970.
- Any change to `internal/bridge/schema/*.json` or `PROVENANCE`.
- Enabling the bridge, issuing provider credentials, Glovo integration,
  deployment or release (mctl-gitops#2457 stays held).
- Hashing or clearing the `bridge_commands.lease_token` column itself. It is
  needed for lease checks and replay; see Open questions.
- Reclaiming expired leases outside `Claim`. A leased row whose lease ran out
  but whose `expires_at` has not passed still waits for its provider's next
  claim, as today.

## Open questions

- The `bridge_commands.lease_token` column still holds the live plaintext token
  at rest, including after completion, because the replay check needs it.
  Storing only `sha256(token)` and comparing digests would eliminate this plaintext copy but changes
  column/replay semantics. This remains a **separate mandatory security decision** (owner: mctl-api security
  maintainers; blocked by mctl-gitops#2457): approve and verify hashing/encryption/expiry controls or
  explicitly sign narrowly scoped risk acceptance with sufficient compensating controls **before the first
  provider credential is issued**. Historical backups and retention must be included.
- The sweep runs whenever the bridge is enabled. A separate opt-out switch
  (for example `MCTL_BRIDGE_EXPIRY_SWEEP=false`) is not proposed. The default
  interval is 30s, overridable with `MCTL_BRIDGE_EXPIRY_SWEEP_INTERVAL`.
- No caller of `ReadOutcome` exists in this repo today. The "subscriber outcome
  contract" is taken to be the `Outcome` Go struct and the signal payload
  (`command_id`, `result_digest`), and neither changes.

## AMEND 2026-11-08 — independent review corrections

- Do not run bulk historical JSONB cleanup in `NewStore`, `bridgeSchema`, or pod boot. Use operator-owned bounded, restartable maintenance batches with timeouts, metrics, read-time redaction and zero-remaining verification before activation.
- A periodic sweep's expiry latency depends on capacity, lock contention and backlog: specify thresholds, alerts and tests for >batch workload, blocked rows and concurrent replicas; never claim a one-interval hard guarantee.
- JSONB redaction does not sanitize plaintext token columns or backups; provider credential issuance awaits an explicit security-owner decision and activation gate.
- This AMEND is docs-only; no implementation approval, code merge, deployment, or bridge activation.
