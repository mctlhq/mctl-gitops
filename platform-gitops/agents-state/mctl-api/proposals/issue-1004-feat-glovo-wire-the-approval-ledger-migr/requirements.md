# Wire the Glovo approval ledger, migrations, receipt sweeper and fence readiness behind the closed gate (#989 F2)

## Context

mctl-api#989 (single authoritative approval ledger) and #985 (control and worker
dispatch) are merged on `main` but land dark. The write fence for `place_order_fake`
commands can only be installed by `installWriteFence` (`cmd/api/glovo_bridge.go`) when
all six #985 section 7.3 preconditions hold. Today several of those are structurally
false, independently of the closed gate: the receipt fence is never built
(`cmd/api/main.go` returns "the receipt fence collaborators are not constructed in this
build"), the one-database proof is called with a nil work-items pool, nothing runs
`workitems.ApplySchema` / `workitems.ApplyGlovoApprovalSchema` in production,
`api.Options.GlovoApprovals` and `workitems.WithGlovoOrders` are never wired, no
`receipt.Sweeper` is started, and no membership-revocation detector exists, so
`glovo.Store.MembershipRevocationWired()` is always false.

This proposal wires every one of those collaborators so that the remaining blockers are
only the deliberate ones: `glovoWriteFenceHoldLifted` (const `false`) and the build gate
`glovo.ControlDefault.Open` (const `false`). Nothing here opens either; nothing is
applied to a live database by this change. It also closes the payload-ownership
obligation OPEN-989-4 with a test that pins the single writer of
`bridge_commands.payload` for `place_order_fake`.

## User stories

- AS the platform operator I WANT a one-shot migration entry point that applies the
  work-items and Glovo approval schemas as `glovo_migrator` SO THAT the runtime roles
  never own DDL and the ledger exists before any fence is considered.
- AS the Glovo order owner I WANT my approval decision to go through the Glovo ledger
  (`workitems.GlovoDecisions`) SO THAT a decision binds to the exact approved basket.
- AS a reviewer of the fence activation I WANT every precondition to be observed, logged
  and false whenever it cannot be observed SO THAT activation is never assumed.
- AS a security reviewer I WANT proof that only the control dispatcher writes a
  `place_order_fake` payload SO THAT no re-read basket can reach the bridge.

## Acceptance criteria (EARS)

Migrations
- WHEN the migration entry point (`cmd/glovo-migrate`) runs with `-confirm=apply-glovo-approval-schema`,
  a migration DSN, the Glovo runtime role and the work-items role THE SYSTEM SHALL call
  `workitems.ApplyGlovoApprovalSchema(ctx, migrationDSN, glovoRuntimeRole, workitems.WithWorkItemsRole(workItemsRole))`
  (which runs `workitems.ApplySchema` first) and exit 0 only on success.
- IF the `-confirm` flag is absent or wrong, or any role name is empty or rejected by the
  role-name rule, THEN THE SYSTEM SHALL exit non-zero without connecting to the database.
- IF the migration reports that a relation of the block is owned by another role THEN THE
  SYSTEM SHALL exit non-zero and print the operator ownership-transfer step, and SHALL NOT
  attempt the transfer itself.
- WHILE the API server runs THE SYSTEM SHALL NOT execute either schema function
  (`cmd/api` never calls them).

Wiring (all inside the existing `MCTL_BRIDGE_ENABLED` / `GLOVO_ENABLED` /
`MCTL_GLOVO_CONTROL_ENABLED` dark paths)
- WHEN `cmd/api` has a Glovo store, a bridge store on the same pool and a work-items store
  THE SYSTEM SHALL construct the #988 orders store on the Glovo pool, the work-items store
  with `workitems.WithGlovoOrders`, a `workitems.GlovoDecisions` and pass it as
  `api.Options.GlovoApprovals`.
- WHEN `installWriteFence` evaluates its `Build` THE SYSTEM SHALL call `receipt.Ready` with
  observed `Deps` first and return `receipt.NewFence(...)` only when `Ready` returns nil.
- IF any collaborator of `receipt.Deps` is missing THEN THE SYSTEM SHALL leave it nil so
  that `receipt.Ready` reports `collaborator_missing`, never substitute a default.
- WHEN `controlProof` runs THE SYSTEM SHALL pass the real work-items pool instead of `nil`.
- WHILE `glovoWriteFenceHoldLifted` is `false` or `glovo.ControlDefault.Open` is `false`
  THE SYSTEM SHALL NOT call `bridge.Store.SetFence` (unchanged behaviour, now covered by a
  test with every other precondition true).
- WHEN the fence decision is made THE SYSTEM SHALL log each of the six preconditions and
  the `receipt.Ready` reason code.

Sweeper
- WHEN the bridge store and the Glovo approval ledger are both wired THE SYSTEM SHALL start
  exactly one `receipt.Sweeper` goroutine from `cmd/api/main.go`, separate from
  `bridge.Expirer`, stopped by the root context.
- IF a sweep tick fails THEN THE SYSTEM SHALL log it and count it in a Prometheus counter
  without stopping the loop.
- IF any sweeper collaborator is missing THEN THE SYSTEM SHALL NOT start the goroutine and
  SHALL log why.

Membership detector
- WHILE the membership detector is running THE SYSTEM SHALL record a heartbeat after every
  completed scan and SHALL revoke connections whose owner is no longer a tenant member via
  `glovo.Store.RevokeForMembership`.
- IF the last heartbeat is missing or older than 5 minutes THEN the probe installed with
  `glovo.WithMembershipRevocationProbe` SHALL return false.
- IF a membership read fails THEN THE SYSTEM SHALL NOT advance the heartbeat.

Payload ownership (OPEN-989-4)
- THE SYSTEM SHALL have exactly one production call site of `bridge.Store.Enqueue` with
  `Kind == place_order_fake`, namely `control.Dispatcher`, which writes the final snapshot
  bytes and refuses a fingerprint mismatch; a test SHALL fail if another call site appears.
- THE SYSTEM SHALL keep the vendored #1059 basket contract pinned by
  `internal/glovo/basket/contract/PROVENANCE` and its existing provenance test.

Readiness proof
- WHEN the activation proof test runs against a database with real `glovo_runtime`,
  `glovo_migrator` and work-items roles THE SYSTEM SHALL show that the installed revocation
  hook is `bridge.CancelOpenForConnections` and that it cancels open commands under the
  runtime role.

## Out of scope

- Lifting `glovoWriteFenceHoldLifted`, opening `glovo.Default` or `glovo.ControlDefault`.
- Any real Glovo provider.
- Applying the migration or the role changes to a live database; changing mctl-gitops
  (mctl-gitops#2563 stays a separate step).
- The tests listed in follow-up F1 of the #989 closure.
- Reopening decisions already taken: decider is the order owner with current membership
  and at least `developer`; `ReservePermitMargin` is 120 s; fingerprint in Temporal history
  only for the fake-only M1.

## Open questions

- Work-items role name. GitOps gives the work-items store the `mctl-api` role (database
  `mctl-api` on `shared-pg`, via the `AUDIT_DB_URL` fallback). Every `roleNameRE` in the
  repo (`^[a-z_][a-z0-9_]{0,62}$`) refuses `mctl-api` because of the hyphen, so
  `WithWorkItemsRole("mctl-api")` cannot succeed. This proposal assumes a dedicated
  underscore role (proposed `mctl_api_workitems`) with an explicit `WORK_ITEMS_DB_URL`
  (which `receipt.Ready` requires anyway, `WorkItemsURLExplicit`). The alternative is to
  quote identifiers and admit hyphens. A clarification question was filed.
- One database. `control.ProveOneDatabase` requires the Glovo, bridge and work-items stores
  on the same database. Work items live in database `mctl-api`, so `GLOVO_DB_URL` must also
  point at `mctl-api` (not a separate Glovo database). mctl-gitops#2563 was not readable
  from this run; confirm it targets that database.
- Whether the migration entry point should also run `glovo.ApplySchema`,
  `orders.ApplySchema`, `glovojoin.ApplySchema` and `bridge.ApplySchema` (none has a
  production caller either). This proposal adds them as optional, ordered steps behind
  separate flags but only the two work-items functions are mandatory here.
- Membership detector source of truth: membership is a GitOps read (`gitReader`), so the
  detector polls owners of live connections; the scan interval (proposed 60 s, bounded well
  below the 5 minute heartbeat) is a recommendation.
