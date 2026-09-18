# Guarded operator recovery for lifecycle ownership

## Context

`internal/lifecycle` already holds the durable answer to "who is responsible for
advancing this entity through this phase", and `internal/api/handlers_lifecycle.go`
already exposes it: four reads and seven writes. Every one of those writes is an
ACTOR surface — the caller must be the current owner and must name the fencing
epoch it holds (`Store.RecordProgress`, `HandoffStart`, `HandoffComplete`,
`Release`, `Terminal`), with the single exception of `Store.Recover`, which takes
a row from a server-verified DEAD owner and installs a named successor. There is
no operator surface at all: when reconciliation correctly refuses to act — a
stuck-but-alive owner, a handoff whose target never arrived, a dead claim nobody
wants to inherit — a human has no narrowly-scoped operation to break the tie.
The only mutations available are the actor writes (which require being the actor)
and `Recover` (which requires a successor and a dead owner).

This proposal adds the human path: four named recovery transitions plus one
conflict-evidence read, each taking optimistic preconditions that fail closed,
each audited with the acting principal, and none of them capable of installing an
owner of the operator's choosing or of touching GitHub at all. It deliberately
does NOT add a generic override: the store's central property is that the actor
who wants to act is not the actor who decides whether it may (see the three
properties documented on `Store.Recover`, `internal/lifecycle/store.go:1224-1239`),
and a `force_owner` parameter would hand that decision straight back. Automatic
recovery is `mctlhq/mctl-agents#353` and is explicitly out of scope here.

## User stories

- AS a platform operator I WANT to inspect the full conflict evidence for one
  entity phase — the stored row, the derived status and bounds, the legacy
  DevLoopWorkflow answer, the divergence class and the recent transitions — SO
  THAT I decide whether to intervene from what the platform measured rather than
  from grepped logs.
- AS a platform operator I WANT to release a claim whose owner is provably dead,
  without appointing a successor, SO THAT the normal `Acquire` race can hand the
  entity to whichever actor is actually running.
- AS a platform operator I WANT to route a handoff off an owner that is alive but
  has effected nothing past its progress bound SO THAT the escalation ADR-010
  prescribes for a stuck owner has an operation behind it instead of only a
  status string.
- AS a platform operator I WANT to retry a handoff whose named target never
  arrived SO THAT a stalled handoff can be re-armed for the same target without
  moving ownership.
- AS a platform operator I WANT to record a request for ownership reconciliation
  of one entity SO THAT the reconciler (`mctlhq/mctl-agents#353`) and the next
  human both see that a review was asked for, and why.
- AS a reviewer or auditor I WANT every recovery to appear in the mctl audit
  trail with the acting principal, the preconditions, the before/after epoch and
  claim state, and the outcome SO THAT a takeover is explicable after the fact.
- AS a service owner I WANT a guarantee that no recovery operation can merge,
  approve or push to a repository SO THAT ownership bookkeeping never becomes a
  way around CODEOWNERS, branch protection or repository merge policy.

## Acceptance criteria (EARS)

Preconditions and fail-closed behaviour

- WHEN a recovery request omits `expected_epoch`, `expected_owner_type`,
  `expected_owner_id`, `expected_version` or `reason` THE SYSTEM SHALL answer
  400 naming the missing field and SHALL NOT read or mutate the ownership row.
- WHEN a recovery request carries an `expected_epoch` that is not the row's
  current epoch THE SYSTEM SHALL answer 412, SHALL leave the row unchanged, and
  SHALL return the current record so the caller can re-read.
- WHEN a recovery request names an expected owner that is not the row's current
  owner THE SYSTEM SHALL answer 412 and SHALL leave the row unchanged, even when
  the epoch matches.
- WHEN a recovery request carries an `expected_version` that is not the row's
  current `entity_version` THE SYSTEM SHALL answer 412 and SHALL leave the row
  unchanged, even when owner and epoch both match.
- WHILE a recovery statement is executing THE SYSTEM SHALL carry every
  precondition it evaluated — epoch, owner, entity version, and the liveness
  evidence (`last_seen_at` or `handoff_started_at`) the decision was derived
  from — in the `WHERE` clause of the `UPDATE`, so that a row changing between
  the read and the write refuses the write rather than absorbing it.
- IF a row changes between a recovery's read and its write THEN THE SYSTEM SHALL
  re-read the row and answer the sentinel that describes what actually happened
  (epoch moved, owner moved, version moved, state became absorbing) rather than a
  generic failure.
- WHEN a request body carries an unrecognised field THE SYSTEM SHALL answer 400,
  so that a misspelled or invented precondition is never silently dropped.

Named transitions, and only those

- WHEN an operator fences a claim THE SYSTEM SHALL require the row to be
  server-derived dead (`Ownership.IsDead`, re-evaluated inside the transaction
  against the database clock) and SHALL answer 409 otherwise.
- WHEN a fence succeeds THE SYSTEM SHALL move the row to `released`, increment
  the epoch in the database, record the fenced owner and reason on the row, and
  SHALL NOT install a new owner.
- WHEN an operator requests a handoff THE SYSTEM SHALL require the row to be
  `active` and server-derived stuck (`Ownership.IsStuck`) and SHALL answer 409
  when the owner is healthy, dead, or already handing off.
- WHEN an operator-requested handoff succeeds THE SYSTEM SHALL move the row to
  `handing-off` with the named target, SHALL NOT increment the epoch, and SHALL
  leave completion to the named target's own `HandoffComplete` call.
- WHEN an operator retries a handoff THE SYSTEM SHALL require the row to be
  `handing-off` and server-derived stalled (`Ownership.HandoffStalled`) and SHALL
  answer 409 otherwise.
- WHEN a handoff retry succeeds THE SYSTEM SHALL re-arm `handoff_started_at` for
  the SAME target, and SHALL NOT change owner, target, state or epoch.
- WHEN an operator requests reconciliation THE SYSTEM SHALL append a
  `reconcile-requested` event and SHALL NOT modify any column of the ownership
  row.
- WHILE this proposal is in effect THE SYSTEM SHALL expose no operation that
  accepts an arbitrary owner for a live row, and no parameter that disables a
  precondition check.

Evidence, authorization and audit

- WHEN an operator reads the conflict endpoint for one entity phase THE SYSTEM
  SHALL return the stored row, the derived view with its bounds, the legacy
  DevLoopWorkflow answer, the divergence class, recent transitions, and the exact
  precondition values a follow-up recovery must send.
- WHEN the conflict read cannot obtain the legacy answer THE SYSTEM SHALL report
  it as unavailable with a reason, and SHALL NOT report it as "no DevLoop".
- WHILE the caller is not an authenticated admin THE SYSTEM SHALL refuse every
  recovery operation with 401 or 403.
- IF the audit log is not configured THEN THE SYSTEM SHALL refuse every recovery
  operation with 503, because a recovery that cannot be audited must not happen.
- WHEN a recovery operation succeeds or is refused on a precondition THE SYSTEM
  SHALL write one audit entry recording the principal, operation, entity, phase,
  entity version, before and after owner epoch, before and after claim state, the
  licensing condition relied on (dead, stuck, handoff-stalled, or none), the
  operator's reason, and the outcome.
- WHEN a recovery mutates the store THE SYSTEM SHALL append a lifecycle event
  whose actor is the acting human principal, using the `human-codeowner` owner
  type.
- WHILE a recovery handler is executing THE SYSTEM SHALL use no client other than
  the lifecycle store and the audit log, so that no recovery path can merge,
  approve, comment on, or push to a repository.

MCP surface

- WHEN the MCP server registers the recovery tools THE SYSTEM SHALL give each one
  a name that states its single transition, a description that states it mutates
  state, the preconditions it requires, and that it confers no merge or approval
  authority.
- WHILE both surfaces exist THE SYSTEM SHALL keep the read tools annotated
  read-only and the recovery tools annotated non-read-only, with an idempotency
  hint on each mutating tool, so a client cannot confuse them.
- WHEN a destructive recovery tool is called without an explicit confirmation
  argument THE SYSTEM SHALL refuse and explain what would change.
- WHEN a tool is added THE SYSTEM SHALL record it in the annotation hint table,
  the tool-count expectation and the portal allowlist, with an explicit
  enabled/disabled decision.

## Out of scope

- Automatic recovery, sweeps, timers, queues or a `due_at` column. ADR-010 and
  the package doc (`internal/lifecycle/types.go:23-27`) forbid turning this store
  into a scheduler; automatic reconciliation is `mctlhq/mctl-agents#353`.
- `ExecutionClaim` (`mctlhq/mctl-agents#352`). Entity version becomes a
  precondition on RECOVERY here; it remains outside the ownership key
  (`internal/lifecycle/types.go:156-168`) and outside ordinary actor writes.
- A free-form admin endpoint for reassigning any lifecycle entity, and any
  `force_owner`-shaped parameter.
- Making mctl-api authoritative for Temporal/DevLoop lifecycle state. The legacy
  answer stays a read-only probe of the dev-loop describe route.
- Retrofitting audit entries onto the seven existing actor writes. Worth doing
  and trivially adjacent (each handler already discards the `*auth.User` that
  `requireLifecycleAdmin` returns), but it is a different change with a different
  blast radius.
- Backfilling `internal/openapi/openapi.yaml`, which today documents none of the
  eleven existing lifecycle routes; documenting the new ones is an optional task.
- Changing the existing `POST /api/v1/lifecycle/ownership/recover` contract, which
  stays the reconciler-facing appointing operation.

## Open questions

- Should an operator-requested handoff be licensed on `stuck` only, or also on a
  healthy owner? Taken here: `stuck` only. `IsStuck` is the one derived condition
  whose documented remedy is a human (`internal/lifecycle/types.go:246-251`), and
  permitting it on a healthy owner would let an operator push work off an actor
  that is doing exactly the right thing.
- Should `expected_version` be required on rows whose `entity_version` is empty?
  Taken here: the JSON key is required, the value may be the empty string, and it
  must match exactly. A pointer field distinguishes "absent" (400) from
  "explicitly empty" (matches an unset row).
- Who consumes `reconcile-requested` events? Taken here: nobody in mctl-api —
  there is deliberately no queue. `mctlhq/mctl-agents#353` can read them through
  `GET /api/v1/lifecycle/events`, and until it does the event is a durable record
  that a human asked.
- Should recovery also appear in the `internal/operations` registry so it shows up
  in `mctl_list_operations` with `RiskLevel`/`RequiresConfirm`? Taken here: no.
  That registry submits Argo workflows and the lifecycle endpoints bypass it
  entirely (`internal/api/router.go:105` wires the store directly); registering a
  non-workflow operation there would need registry changes beyond this scope. The
  audit entry still carries a `RiskLevel`.
- Should fencing be allowed on a `handoff-stalled` row? Taken here: yes — such a
  row is dead by `IsDead`, which covers handing-off rows
  (`internal/lifecycle/derive.go:50-56`), and the event records which condition
  licensed it.
- Should the four mutating tools be enabled on the shared Cloudflare MCP portal?
  Taken here: no — recorded in `docs/portal-allowlist.json` as an explicit
  `enabled: false` decision, which also avoids the `mutatingOnPortal` Go change.
