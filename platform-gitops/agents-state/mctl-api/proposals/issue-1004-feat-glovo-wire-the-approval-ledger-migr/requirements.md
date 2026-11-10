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

## Amendment 2026-11-10: owner decisions D1 and D2

Result of the independent review: AMEND REQUIRED, NO IMPLEMENTATION GO. This amendment
records two owner decisions and does not approve implementation. Implementation approval
is a separate, later request; `.status.yaml` stays `proposed`. Anything below that could
not be verified against code or GitOps is marked UNVERIFIED and is not an assertion.

D1 (work-items role, variant A). The work-items store gets a new login role
`mctl_api_workitems` and an explicit `WORK_ITEMS_DB_URL`.
- Least privilege: only the DML that `workitems` already uses (the `genericGrants` table in
  `internal/workitems/apply_schema.go` plus USAGE on `work_item_intents_id_seq`, and SELECT on
  `bridge_colocation_probe` through `bridge.WithWorkItemsRole`); no DDL, no ownership, not
  superuser, no CREATEROLE, CREATEDB, BYPASSRLS or replication.
- The physical database is the existing `mctl-api` database on `shared-pg`. The Glovo
  store, the bridge store, the orders store and the work-items store SHALL all use that one
  physical database (the `control.ProveOneDatabase` precondition); no separate Glovo database.
- The working production DSN is not changed by this proposal or by its implementation. The
  current production path (`AUDIT_DB_URL` fallback as role `mctl-api`) keeps working until a
  separate deployment approval (D2 step 2) says otherwise.
- The role-name rules are not widened: every `roleNameRE` stays `^[a-z_][a-z0-9_]{0,62}$`,
  so the hyphenated `mctl-api` is never passed to `WithWorkItemsRole` and no identifier
  quoting is introduced. Quoting is kept only as a rejected alternative (design).
- This proposal includes grants verification, compatibility with the existing WorkItems and
  DevLoop, and rollback (design sections 7 to 9, tasks 11 to 14).

D2 (order). Four steps, each its own gate; no step is implied by the previous one:
1. A15 mctl-gitops#2563 (draft, staged and inert): stages the roles `glovo_runtime`,
   `glovo_migrator`, `mctl_api_workitems`, the grants and ownership plan, the
   ExternalSecrets and the DSNs. Nothing in it is reconciled.
2. A separate deployment gate, performed by an operator after its own approval: actual role
   creation, grants and any necessary ownership transfer. There is NO automatic ownership
   change of existing production tables, by this code or by any job. Ownership is
   transferred only for the tables the migration strictly requires, and existing WorkItems
   and DevLoop must not be harmed (design section 7).
3. `cmd/glovo-migrate` applies the schemas as `glovo_migrator`, after a read-only ownership
   pre-check and only with an explicit `-confirm`.
4. Wiring is enabled only after the migrations, roles and readiness are confirmed, with the
   feature flags closed and the write fence on (the bridge keeps its default refusing fence;
   `bridge.Store.SetFence` is never called; `glovoWriteFenceHoldLifted` stays `false`).
   Merging dark wiring code earlier is allowed only because every path is behind closed flags.

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
- IF the `-confirm` flag is absent or wrong, or any role name is empty, equal to another
  role of the call, or rejected by the role-name rule, THEN THE SYSTEM SHALL exit non-zero
  without connecting to the database. There is no default for `-confirm` and no environment
  variable that supplies it.
- WHEN `-confirm` is correct THE SYSTEM SHALL, before any DDL, run a read-only ownership
  pre-check as the migration role (`SET TRANSACTION READ ONLY`) over every relation,
  sequence, function and schema the selected steps would touch, and SHALL list each one
  whose owner is not the connecting role together with the operator transfer step.
- IF the pre-check finds any foreign-owned object, or cannot complete (connection, catalog
  read or malformed result), or the connecting role is not the expected migration role, or a
  named role (`glovo_runtime`, `mctl_api_workitems`) does not exist, THEN THE SYSTEM SHALL
  exit non-zero (2 for a foreign-owned object, 1 for a read failure) before issuing any DDL.
  A failed read is never treated as "nothing foreign-owned".
- IF the migration reports that a relation of the block is owned by another role THEN THE
  SYSTEM SHALL exit non-zero and print the operator ownership-transfer step, and SHALL NOT
  attempt the transfer itself, now or in any later change: no code path of this proposal
  issues `ALTER ... OWNER TO`, and no job changes ownership of an existing production table.
- THE SYSTEM SHALL name the work-items role only as `mctl_api_workitems` in every deployed
  configuration; the hyphenated `mctl-api` is rejected by the role-name rule and is never
  passed to `WithWorkItemsRole`.
- WHILE the API server runs THE SYSTEM SHALL NOT execute either schema function
  (`cmd/api` never calls them).

Wiring (all inside the existing `MCTL_BRIDGE_ENABLED` / `GLOVO_ENABLED` /
`MCTL_GLOVO_CONTROL_ENABLED` dark paths). Every wiring task is gated behind those closed
flags: with them unset (current production) none of the criteria below changes behaviour,
and this change sets no flag, no env var and no DSN anywhere (D2 step 4 is a later,
separately approved operator action that needs the roles, migrations and readiness
confirmed first).
- IF `WORK_ITEMS_DB_URL` is unset or the work-items database differs from the Glovo database
  THEN THE SYSTEM SHALL leave the ledger unwired and report `one_database_not_proven`; it
  SHALL NOT fall back to `AUDIT_DB_URL` for the ledger.
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

Roles, grants and compatibility (D1)
- WHEN the grants verification runs against a database THE SYSTEM SHALL compare, read-only,
  the live privileges of `mctl_api_workitems`, `glovo_runtime` and `glovo_migrator` with the
  in-code grant tables and report any extra or missing privilege, any DDL or ownership held
  by a runtime role, and any superuser/CREATEROLE/CREATEDB/BYPASSRLS/replication attribute.
  A role or object that cannot be read is reported unknown, never absent or clean.
- THE SYSTEM SHALL keep every existing WorkItems and DevLoop path working through each step
  of D2: before any ownership transfer the legacy role `mctl-api` holds the same DML on the
  affected tables as a transitional grant (design section 7), so a pod still running on
  `AUDIT_DB_URL` neither loses access nor attempts DDL.
- THE SYSTEM SHALL provide a rollback for each D2 step (design section 9).

## Out of scope

- Lifting `glovoWriteFenceHoldLifted`, opening `glovo.Default` or `glovo.ControlDefault`.
- Any real Glovo provider.
- Applying the migration or the role changes to a live database; changing mctl-gitops
  (mctl-gitops#2563 stays a separate step); creating roles, grants or ownership changes
  (D2 step 2 is an operator action behind its own approval); changing the working
  production DSN; any implementation approval (this amendment grants none).
- Widening any `roleNameRE` or quoting identifiers to admit `mctl-api`.
- The tests listed in follow-up F1 of the #989 closure.
- Reopening decisions already taken: decider is the order owner with current membership
  and at least `developer`; `ReservePermitMargin` is 120 s; fingerprint in Temporal history
  only for the fake-only M1.

## Decided and open questions

Decided (2026-11-10, owner):
- Work-items role: `mctl_api_workitems`, explicit `WORK_ITEMS_DB_URL` (D1). The earlier
  open question and its "quote identifiers" alternative are closed; quoting is rejected.
- One database: the existing `mctl-api` database on `shared-pg` for Glovo, bridge, orders
  and work-items (D1). `GLOVO_DB_URL` points at it, not at a new database.
- Order: A15 staging, separate deployment gate, migration, then wiring (D2).

Still open (not decided here):
- Whether the migration entry point should also run `glovo.ApplySchema`,
  `orders.ApplySchema`, `glovojoin.ApplySchema` and `bridge.ApplySchema` (none has a
  production caller either). This proposal adds them as optional, ordered steps behind
  separate flags but only the two work-items functions are mandatory here.
- Membership detector source of truth: membership is a GitOps read (`gitReader`), so the
  detector polls owners of live connections; the scan interval (proposed 60 s, bounded well
  below the 5 minute heartbeat) is a recommendation.
- Role for `COMMERCE_DB_URL` (the bridge reads only that variable; the commerce store
  falls back to `AUDIT_DB_URL`). D1 fixes the database, not this role. UNVERIFIED: which
  role owns the bridge and commerce tables today, and whether the bridge tables exist at
  all in production (the bridge is off). The operator inventory of D2 step 2 answers it.
- Whether other consumers use the work-items tables under a role other than `mctl-api`.
  UNVERIFIED; the inventory in design section 7 must list them before any ownership change.
- Meaning of "write fence on" in D2 step 4 is read here as: the bridge keeps its default
  refusing fence (`bridge.Store.SetFence` is not called, `glovoWriteFenceHoldLifted` stays
  `false`). Confirm with the owner when implementation approval is requested.
