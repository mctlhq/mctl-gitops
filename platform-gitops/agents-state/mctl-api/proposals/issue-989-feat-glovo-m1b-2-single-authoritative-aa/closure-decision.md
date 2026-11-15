# Closure decision record: issue-989 implementation slice

Status of this document: **AMENDED 2026-11-10 after the owner's decisions (section 6).
The closure itself is NOT yet done.** The owner decided to close the implementation slice
as DELIVERED-BY-DIRECT-PRS only AFTER the follow-ups exist and are linked and this
pull request is updated. The follow-ups now exist (section 5) and this is that update;
the closure remains pending (section 7, unfinished obligations). Nothing in this file,
and nothing in the pull request that carries it, marks #989 accepted, closed or
completed. It does not edit `.status.yaml`, `requirements.md`, `design.md` or
`tasks.md`.

Refs mctl-api#989.

- Verified against: mctl-api `origin/main` at `675dff75dad506e957dfbaf23f34b7fa70aadd47`
  (merge of #1001), read-only detached worktree, `GOTOOLCHAIN=go1.26.10`, on 2026-11-10.
- Test run: `go test -count=1 ./internal/workitems/ ./internal/glovo/... ./internal/bridge/...
  ./internal/api/ ./cmd/api/ ./internal/governance/` against a scratch PostgreSQL 16 with
  `TEST_DATABASE_URL` set (so the split-role database tests ran, none skipped). All packages
  passed. One run of `TestInterleavingsKeepTheInvariants` (round 2) failed with
  `remaining connection slots are reserved` because the scratch server's connection limit was
  exhausted by packages running in parallel; it passed in three isolated reruns. That is a
  property of the scratch server, not of the code. No test and no code was modified.
- Mutation checks (revert the fix, watch the test go red) were NOT re-run for this record.
  Where a task requires a proven-red test, the matrix says "present" for the test and does
  not claim the mutation was re-proven here.

## 1. The DevLoop failure record (kept verbatim, NOT converted)

The system's record of the DevLoop for this slice is a failure and stays one:

| Field | Value |
|---|---|
| DevLoop id | `dev-loop-mctlhq-mctl-api-989` |
| Workflow | `mctl-agents-implement-9fc5a135` |
| Outcome | `Failed` |
| Ended | `2026-11-10T08:01Z` (`blocked.since: 2026-11-10T08:01:35Z`) |
| Blocked code | `execution-unauthorized` |
| Blocked message | `execution not authorized: approved with no verifiable approval grant` |
| Remedy recorded by the system | Approve the proposal through its DevLoop (mctl-api `POST /api/v1/agents/dev-loop/<workflow>/approve`), which records a human decision bound to this proposal's current content. |
| Approval grant | none recorded; no `approval_ref` exists for this digest |

This record is NOT converted into `Completed`, `Succeeded` or any other success state by
this document, by the direct pull requests below, or by the proposed decision. A merged
direct pull request is a different fact from a successful DevLoop run, and both facts stay
on the record. The `blocked:` block and the `reconciliation:` block in `.status.yaml`
(added by mctl-gitops#2561) are left exactly as they are.

Two further facts the owner should have in front of them when deciding:

1. `status: accepted` in `.status.yaml` rests on an approval of digest
   `sha256:ed0a3408b42fb2b4960a4ed3c6521efef834aa27aa439eab8aac484f66d5bc92`. The
   proposal text on mctl-gitops `main` now hashes to
   `sha256:9bd4b0c27ffb35b70472dae1898c25e1347d1bc9ff63e7b305e1c9f5a60740fd`
   (`scripts/proposal-content-digest.py`), because commit `3d33c949d` (mctl-gitops#2562) amended `design.md`
   after the approval and after the merge (it describes the `Membership.IsMember(ctx, ...)`
   change that mctl-api #1001 made). The approval therefore no longer binds the bytes on
   `main`. The amendment is a documentation catch-up, not a scope change, but the binding is
   a fact and this record does not repair it.
2. The implementation did not go through the DevLoop. It went through direct agent pull
   requests under the owner-delegated review gate (section 2).

## 2. What delivered the slice

| PR | Merge commit | Merged (UTC) | Role |
|---|---|---|---|
| mctl-api#997 | `0aac452e` | 2026-11-10T09:10Z | bridge basket server faults reported as `internal` (prerequisite fix) |
| mctl-api#998 | `0e8d46d0` | 2026-11-10T10:18Z | the #989 implementation: tasks 0-9 (ledger, enforcement, fence, readiness) |
| mctl-api#1000 | `abe6c73c` | 2026-11-10T11:05Z | bridge store no longer falls back to `AUDIT_DB_URL` (supports the one-database proof) |
| mctl-api#999 | `dc55930c` | 2026-11-10T11:09Z | join schema and `ControlStartTx` (#957 A14), consumes the execution binding |
| mctl-api#1001 | `675dff75` | 2026-11-10T16:29Z | #985 control and worker dispatch, dark; consumes the fence and the sweeper and wires `installWriteFence` |

All five are merged. mctl-api#989 itself is still `OPEN`.

## 3. Acceptance matrix

Legend: DONE = implemented on `main` and a test that exercises it is present and passed
in the run above. PARTIAL = implemented or partly tested, a named gap remains. NOT DONE =
absent. OWNER-DECISION = implemented per a recommendation, or left open, and the item is
the owner's call rather than a defect. Paths are relative to the mctl-api repository root.

### 3.1 Tasks 0-9 (tasks.md)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 0 | `CreateGlovoExecutionTx`, `ExecutionBindingTx`: ids, one work item, event, execution, caller's tx, no advisory lock | DONE | `internal/workitems/glovo_execution.go:84`, `:116`; `TestGlovoExecutionTx` (`glovo_approvals_test.go:27`: generic ids are `not_found`, rollback leaves no row) |
| 1 | `ApplyGlovoApprovalSchema`: version row, widened and exact-kind CHECKs, bindings table, guards, grants, ownership check, downgrade refusal | DONE | `internal/workitems/apply_glovo.go:300`; `TestApplyGlovoApprovalSchemaTwiceAndForeignOwner`, `TestGlovoApprovalChecksAreValidated`, `TestGlovoApprovalObjectListsCoverTheDDL` |
| 2 | Kinds, states, intent, `GlovoReceiptState` expiry precedence, golden hash | DONE | `internal/workitems/glovo_kinds.go:72,88,135,163`; `TestGlovoIntentGoldenAndEveryFieldCounts`, `TestIsGlovoKindIsThePrefixPredicate`, `TestGlovoReceiptStateExpiryPrecedence` |
| 2b | `workitems.ApplySchema` moves the generic DDL under the migrator; `NewStore` sends no DDL when it does not own the tables | DONE (its DoD item T15e is PARTIAL, see 3.2) | `internal/workitems/apply_schema.go:108`; `TestApplySchemaOnEmptyDatabaseAndTwice`, `TestApplySchemaRefusesAForeignOwner`, `TestApplySchemaRefusesAHigherVersion`, `TestNewStoreSendsNoDDLWhenItDoesNotOwnTheTables`, `TestGenericGrantsAreExact` |
| 3 | Tx-aware store methods (create, lock, reserve, consume, revoke, mark-unknown, decide, status, for-decision); none begins or commits; nil collaborators give `not_ready` | DONE | `internal/workitems/glovo_approvals.go:177,186,268,337,367,400,424,478,506`; `TestGlovoApprovalLifecycle`, `TestGlovoNilCollaboratorIsNotReady`, `TestGlovoDecisionsTypedNilDependenciesAreNotReady` |
| 4 | Generic paths refuse `glovo.` kinds; generic CAS statements map a Glovo row to `approval_kind_not_spendable_here` | DONE | `internal/workitems/action_approvals.go:803,889,944,1037,1097`; `internal/api/handlers_action_approvals.go:241`; `TestGenericPathsRefuseGlovoKinds`; the pre-existing work-items and receipt-gate suites pass unchanged (HTTP-level test gap is under T9) |
| 5 | `AuthorityBasisResourceOwner`; `glovo.order.owner-approval` v1 registered; `decisionCapture` records `resource_owner` | DONE | `internal/governance/governance.go:60,91`; `internal/api/handlers_approval_governance.go:123-131`; `TestGlovoOwnerApprovalPolicyRegistered`, `TestDecisionCaptureForGlovoKind` |
| 6 | Owner decision: uniform 403, membership through `decideWrittenRole` without `roleGate`, `isGlovoOwnerCandidate` (`handlers_action_approvals.go:687`) and `isGlovoOwnerDecider` (`:700`), bridge-pool-free decide tx, owner read rule, audit without `args_digest` | DONE | `internal/api/handlers_action_approvals.go:687,700,717`; `internal/workitems/glovo_decisions.go:49`; `TestGlovoOwnerDecision`, `TestGlovoOwnerSeesTheApproval`, `TestGlovoOwnerDecisionBarsGlovoTokens`; existing decide tests pass unchanged |
| 7 | `receipt.Fence` with `PreLock` and `Check`; `WriteFence.PreLock` hook, no-op on `refusingFence`; `receipt.Membership`; `Audit`; `Sweeper` | DONE | `internal/glovo/receipt/fence.go:93,177`; `internal/bridge/permit.go:51-107`; `internal/glovo/receipt/audit.go`, `sweeper.go:35`; `TestFence*` (receipt), bridge suite unchanged (default fence byte for byte) |
| 8 | `receipt.Ready` with every design section 8 condition; startup unchanged with the closed gate and the fence stays `refusingFence` | DONE | `internal/glovo/receipt/ready.go:63`; `TestReady` (12 subtests), `cmd/api/glovo_bridge_test.go:132` `TestInstallWriteFenceNeedsAllSixPreconditions` |
| 9 | Cross-slice package comments; fmt, vet, lint, tests | DONE | `internal/glovo/receipt/doc.go`; `gofmt -l` and `go vet` clean on the touched packages in this run; `golangci-lint` was not re-run here (CI of #998 is the record for lint) |

### 3.2 Tests T1-T22 (tasks.md "Tests")

| ID | Requirement (short) | Status | Evidence and gap |
|---|---|---|---|
| T1 | A `hir_` answer alone changes no `aar_`, order or bridge row; `IssueWritePermit` refused | PARTIAL | No test names `hir_`; the string does not occur in mctl-api `main`. The property holds structurally (only the owner decision moves `pending`, `TestGlovoOwnerDecision`; a permit needs a `reserved` `aar_`, `TestFenceReplayAndForeignCommand`), but no test drives a clarification answer. |
| T2 | Wrong decider refused: other member, non-owner admin, Glovo-audience token, agent, service, CI, relayed, surface | PARTIAL | non-owner, non-owner admin, service, agent, nobody, audience and worker tokens are tested (`TestGlovoOwnerDecision`, `TestGlovoOwnerDecisionBarsGlovoTokens`). CI, relayed and surface callers are excluded by `isGlovoOwnerCandidate` (`handlers_action_approvals.go:687`) but have no test case. |
| T3 | Owner cannot decide a non-Glovo `aar_`; `mctl-agents-approve` stays admin-only | DONE | `TestGlovoOwnerDecision` (generic row by the owner: 403; by an admin: 200); the admin-only operation is covered by the existing suites, unchanged. |
| T4 | Byte-identical 403 for unknown, non-Glovo and someone else's id | DONE | `TestGlovoOwnerDecision` compares `res.raw` for all three. |
| T5 | 20 concurrent approve/refuse pairs, one winner | DONE | `TestGlovoConcurrentDecisions` (`glovo_approvals_test.go:600`). |
| T6 | Binding mismatch per field at the fence; Reserve per field changed and empty | PARTIAL | Reserve: 9 fields x changed/empty, present (`TestGlovoReserveBindingMismatch`). Fence: presented `we_`, `wi_`, tenant, owner, connection, revision, approval, intent hash; command provider, order, connection, revision; stored binding connection, execution, intent hash are present (`TestFenceBindingAndIdentityChecks`), `aar_` stays `reserved`. No subtest for a tampered stored-binding tenant, owner, install revision, `install_id` or `order_ref`; `fence.go:238-258` compares them, only the intent-hash recompute covers `install_id`. |
| T7 | Expiry at decide, reserve and fence; reserved past expiry only becomes `unknown`; final states never read `expired` | DONE | `TestGlovoExpiryAndInputBounds`, `TestFenceRefusals/approval_expired`, `TestGlovoReceiptStateExpiryPrecedence`, `TestSweeper`. |
| T7b | `ExpiresIn` bounds, `clock_timestamp()` expiry, `ReservePermitMargin` at Reserve, statement-time consume | DONE | `TestGlovoExpiryAndInputBounds`, `TestConsumeUsesStatementTimeNotTransactionStart` (`glovo_clock_test.go:15`), `TestGuardRefusesConsumeAfterExpiry`, `TestDispatchFreshnessWindow` (control). |
| T8 | Replay: second permit, same `cmd_` replay, other `cmd_`, `UNIQUE (order_ref)` | DONE | `TestGlovoApprovalLifecycle` (T8 block), `TestFenceReplayAndForeignCommand`. |
| T9 | Final states; generic routes answer `approval_kind_not_spendable_here`; generic create refuses Glovo kinds | PARTIAL (P3) | Store level proven for every Glovo state (`TestGenericPathsRefuseGlovoKinds`, `glovo_generic_refusal_test.go:34`). No HTTP-level handler test asserts the 409 `approval_kind_not_spendable_here` body from `actionApprovalRefusals` (`handlers_action_approvals.go:241`). |
| T10 | Written content differs: price, `item_code`, intent hash, extra field, wrapper, missing `lines`; matching payload passes | DONE | `TestFenceRecomputesFromWrittenContent` (7 mismatch subtests + matching payload with other key order), `TestFenceRefusesIntentHashMismatch`. |
| T11 | Reconnect after approval: `connection_revoked` / `stale_install`; nothing moves the `aar_` back | DONE | `TestFenceRefusals/connection_replaced`, `/install_moved`; `TestFenceEndToEndRevocation/revoke`, `/reconnect_supersedes` (control). |
| T12 | Owner removed from the tenant: `no_tenant` | DONE | `TestFenceRefusals/membership_gone`, `/membership_unreadable`, `TestFenceHungMembershipIsBoundedAndUnavailable`. |
| T13 | Ending without a permit: cancel to `unknown`, sweeper, provider `unknown` pair | DONE | `TestSweeper`, `TestSweeperIsNotStarvedByLiveBacklog` (`joint_test.go:106,142`), `TestClassifyTable`, `TestAuditOverRealRows`; cancel and `reconcileOrder` in `internal/glovo/control` (`TestCancelDispatched`, `TestReconcileOrderTable`). The mutation proof of the `completed`/`none` row was not re-run here. |
| T14 | Atomicity: failure after consume leaves `reserved`, no permit, `effect_state` `none` | DONE | `TestFenceRollbackLeavesApprovalReserved`, `TestFenceHappyPathConsumesAndKeepsLockOrder`. |
| T15 | Database enforcement under the runtime role, raw SQL | DONE | `TestGlovoDatabaseEnforcement` (about 55 subtests: every insert state and `decided_*` field, `glovo.other`, `glovo.cancel_order_fake`, every immutable column, forbidden transitions, `DELETE`, `ALTER TABLE ... DISABLE TRIGGER`, binding updates), `TestGlovoGuardRefusesTheOwnerRoleToo`. |
| T15b | Foreign roles and exact grants; `ProveOneDatabase` oracle | DONE | `TestGlovoForeignRolesAndExactGrants`, `TestAppliedGrantsAreExactlyTheDocumentedOnes`, `TestVerifyGlovoApprovalSchema` (11 subtests), `TestProveOneDatabase`, `TestProveRoleAndTriggers` (control). |
| T15c | Foreign permit scope takes no L1-L4 lock | DONE | `TestPreLockScopeTakesNoLock` (`fence_test.go:207`), `TestFenceEndToEndRevocation/a_foreign_or_absent_command_is_not_found_before_any_lock`, `TestFenceUnfencedCommandsAreRefusedPermanently`. |
| T15d | Decision pre-read with the role split: owner succeeds on the Glovo pool, non-owner gets the uniform 403, no `glovo.*` read on the work-items pool | PARTIAL | The two halves are tested separately: the handler with a fake ledger (`TestGlovoOwnerDecision`) and the store with the real split roles (`TestGlovoRevokeUnknownAndStatus` asserts `permission denied for schema glovo` on the work-items pool). No test composes the real route with the real `workitems.GlovoDecisions` on the real pools. |
| T15e | Other consumers after the ownership move; mutation per removed grant | PARTIAL | Exact grants are pinned (`TestAppliedGrantsAreExactlyTheDocumentedOnes`, `TestGenericGrantsAreExact`) and two revocations turn the start-up proof red (`TestVerifyGlovoApprovalSchema/SELECT_revoked`, `/work_item_write_revoked`). Not found: the per-consumer happy paths of `internal/api` routes, `mctl_get_ready_work_items`, the `delegation` projections and the #988 readiness probe under the moved ownership, nor the "one grant removed at a time" mutation sweep across the four tables and `work_item_execution_requests`. |
| T16 | Joint-state invariant table; `consumed` iff a permit exists | DONE | `TestClassifyTable`, `TestAuditOverRealRows`, `TestInterleavingsKeepTheInvariants` (control, 8 seeded rounds). |
| T17 | Secrecy: no basket, `args_digest`, lease token or credential in logs or audit across T1-T16 | PARTIAL | Point checks present: `TestRefusalIsSecretFree`, the owner-decision audit assertion that `args_digest` is absent (`TestGlovoOwnerDecision`), `GlovoApprovalStatus` returns ids and enums only. No test captures the logs and audit rows across the whole T1-T16 run. |
| T18 | Readiness: each missing URL, failed proof, disabled trigger, runtime-owned table, unregistered policy, nil collaborator; `SetFence` not called | DONE | `TestReady` (`/glovo_url`, `/work_items_url`, `/one_database`, `/policy`, `/approval_schema`, `/audit_violation`, `/no_orders`, `/no_members`, `/typed_nil_store`), `TestVerifyGlovoApprovalSchema/runtime_role_is_a_member_of_the_owner`, `TestInstallWriteFenceNeedsAllSixPreconditions`, `TestMainInstallsTheFenceOnlyThroughTheInstaller`. |
| T19 | Strict-mode governance: owner approve passes `guardDecision`; `artifact_hash` under `MCTL_APPROVAL_BINDING=enforce`; stale `content_digest` is `context_changed`; backfill leaves Glovo rows alone | PARTIAL | Basis, policy registration and `aar_guard` refusal of an empty `artifact_hash` are tested (`TestDecisionCaptureForGlovoKind`, `TestGlovoOwnerApprovalPolicyRegistered`, `TestGlovoDatabaseEnforcement/insert/empty_artifact_hash`). Not found: a test that runs an owner approve through `guardDecision` in strict mode with a binding copied from the `GET`, the `context_changed` case, or the start-up backfill leaving Glovo rows unchanged. |
| T20 | Control worker reads on the Glovo pool; revoke and mark-unknown idempotency | DONE | `TestGlovoRevokeUnknownAndStatus`, `TestAuditAndSweeperRunOnTheSharedRuntimeRole` (control). |
| T21 | Deadlocks, deterministic, five pairs: permit vs cancel, permit vs decide, dispatch vs decide, permit vs revoke, sweeper vs permit | PARTIAL | Forced interleavings present for permit vs revoker (`TestPermitWaitsForARevokerHoldingL2`, `TestPermitRevokerDispatchLockOrder`, `TestWaitingForL2HoldsNoLaterLock`, `TestRevocationRaceRevokerFirst`, `TestRevocationRaceDispatchFirst`), permit vs permit (`TestConcurrentFencesSerialize`) and a seeded random mix including cancel, revoke and permit (`TestInterleavingsKeepTheInvariants`, no `40P01`). No forced barrier test for permit vs decide, dispatch vs decide or sweeper vs permit as written. The sweeper takes `FOR UPDATE ... SKIP LOCKED` on the `aar_` only (`sweeper.go:35`), so a deadlock is not expected, but it is argued, not proven. |
| T22 | Refusal map: every design section 10 row gives its reason and wire code | PARTIAL | Fence-side codes are exercised (`TestRefusalOf`, `TestFenceRefusals`, `TestFenceBindingAndIdentityChecks`); the sweep over the whole table, including the generic-route 409, is not in one test (same gap as T9). |

### 3.3 Open questions (requirements.md)

| ID | Question | Status | Evidence |
|---|---|---|---|
| OPEN-989-1 | Ownership of the four tables moves to `glovo_migrator` | DONE | Decided 2026-11-10; implemented as task 2b. |
| OPEN-989-2 | Provisioning of `glovo_runtime` and `glovo_migrator` | NOT DONE | Staged only, in the draft mctl-gitops#2563 (`deploy/staged/glovo-m1/db/`, `suspend: true`, inert). No role, secret or env var exists live. Owner GO 2026-11-10 to PREPARE the two roles; applying is a separate step and nothing is applied. |
| OPEN-989-3 | Minimum live tenant role for the owner-decider | OWNER-DECISION | Implemented as the proposal said: `glovoMinDeciderRole = operations.RoleDeveloper` (`handlers_action_approvals.go`, constant above `isGlovoOwnerCandidate`). Decided by the owner 2026-11-10: `developer`, and only the order owner with current membership. |
| OPEN-989-4 | Who writes the basket payload into `bridge_commands.payload` | PARTIAL | In mctl-api the #985 dispatcher writes the order's final snapshot canonical bytes as the payload and refuses a fingerprint mismatch (`internal/glovo/control/dispatcher.go:353-394`), and the fence recomputes from the stored payload (`fence.go:226-243`). The client-side half (write exactly the payload's lines, vendor #1059) was tracked in mctl-telegram#1262, which is CLOSED (completed 2026-11-10T01:55Z) and whose body does not carry the obligation; it was not verified here and is not shown to be met, so the row stays PARTIAL and the obligation now lives in mctl-api#1004 (F2), added 2026-11-10. |
| OPEN-989-5 | Fingerprint of a low-entropy fake basket travels through Temporal history | OWNER-DECISION | Implemented as the merged #957/#1044 contracts say (`GlovoControlInput` carries `approval_ref` and the fingerprint). Decided by the owner 2026-11-10: allowed ONLY for the synthetic fake-only M1; a keyed digest is required before any real data. |
| OPEN-989-6 | Payload shape | DONE | Closed 2026-11-10 in the proposal; the vendored schema and `TestApprovalBasketRefResolves` (basket package) were not re-run individually but `internal/glovo/basket` passed. |
| OPEN-989-7 | `ReservePermitMargin` | OWNER-DECISION | Implemented at the recommended 120 s (`internal/workitems/glovo_kinds.go:72`), enforced in Reserve (`glovo_approvals.go:305`) and in dispatch (`control/dispatcher.go:315-318`). Decided by the owner 2026-11-10: 120 s. |
| OPEN-989-8 | Sweeper hook and its owner | NOT DONE | `Sweeper.Sweep` and `Sweeper.Run` exist (`sweeper.go:35,82`) and `Sweep` is tested; nothing in `cmd/api` or `internal` starts a `receipt.Sweeper` (no caller outside tests). `Run` itself has no test. The location of the hook (a second collaborator started from `main.go`, as the recommendation says, or a change to `bridge.Expirer`) was decided by the owner 2026-11-10: a separate `receipt.Sweeper` started from `cmd/api/main.go`; not built yet (F2). |
| OPEN-989-9 | Name of the work-items role passed to `WithWorkItemsRole` | OWNER-DECISION | The option exists (`apply_schema.go:82-86`) with the question in its comment; decided 2026-11-10: use the existing work-items runtime role. From GitOps that is the `mctl-api` role (shared CNPG cluster, database `mctl-api`; `WORK_ITEMS_DB_URL` is unset in `bootstrap/templates/mctl-platform/mctl-api.yaml`, so the store uses the `AUDIT_DB_URL` fallback with `DB_USER`). To be confirmed against the live state before the migration runs (F2). |

### 3.4 Totals

47 rows: 30 DONE, 11 PARTIAL, 2 NOT DONE, 4 OWNER-DECISION.

- Tasks: 11 of 11 DONE.
- Tests: 17 DONE, 10 PARTIAL (T1, T2, T6, T9, T15d, T15e, T17, T19, T21, T22).
- Open questions: 2 DONE (-1, -6), 1 PARTIAL (-4), 2 NOT DONE (-2, -8), 4 OWNER-DECISION (-3, -5, -7, -9).
- Carried items (PARTIAL plus NOT DONE): **13**.

Requirements-level reading (each EARS group of requirements.md maps to rows above):
execution binding = task 0; binding and creation = tasks 1, 3, 4 and T8, T9, T15;
decision = tasks 5, 6 and T2-T5, T19; lifecycle in the database = tasks 1, 2 and T7, T15, T16;
reserve, revoke, status = tasks 3, 4 and T6, T13, T20; fence = task 7 and T10-T14, T21, T22;
outcome = T13, T16; readiness = tasks 1, 2b, 8 and T15b, T15e, T18; secrecy = T17.

## 4. Remaining items

### 4.1 Carried from the matrix (13 rows)

| # | Item | Kind | Home (created 2026-11-10) |
|---|---|---|---|
| C1 | T1 `hir_` clarification-answer test | test | F1 mctl-api#1003 |
| C2 | T2 CI, relayed and surface decider cases | test | F1 mctl-api#1003 |
| C3 | T6 fence per-field subtests for stored-binding tenant, owner, install revision, `install_id`, `order_ref` | test | F1 mctl-api#1003 |
| C4 | T9 + T22 HTTP-level 409 `approval_kind_not_spendable_here` and a one-test sweep of the section 10 table (P3) | test | F1 mctl-api#1003 |
| C5 | T15d composed route + `GlovoDecisions` on the real split pools | test | F1 mctl-api#1003 |
| C6 | T15e per-consumer happy paths and one-grant-at-a-time mutation sweep | test | F1 mctl-api#1003 |
| C7 | T17 log and audit capture across the lifecycle | test | F1 mctl-api#1003 |
| C8 | T19 strict-mode `guardDecision`, `MCTL_APPROVAL_BINDING=enforce`, backfill unchanged | test | F1 mctl-api#1003 |
| C9 | T21 forced barriers for permit vs decide, dispatch vs decide, sweeper vs permit; `Sweeper.Run` test (P3) | test | F1 mctl-api#1003 |
| C10 | OPEN-989-8 Sweeper hook location and owner; start the sweeper | design + code | F2 mctl-api#1004 (decided: separate sweeper started from `main.go`) |
| C11 | OPEN-989-2 role and secret provisioning | deployment | F2 mctl-api#1004 + mctl-gitops#2563 (draft) |
| C12 | OPEN-989-4 whoever enqueues the command writes exactly the approved payload lines (client half was mctl-telegram#1262, closed, obligation not in its body) | cross-repo | F2 mctl-api#1004 (explicit item, added 2026-11-10) |
| C13 | `glovo.cancel_order_fake` refusal: the fence refuses it permanently with `approval_invalid` and takes no lock (`TestFenceUnfencedCommandsAreRefusedPermanently/cancel_order_fake`); M1 has no cancel approval, so a cancel has no write path. Decide whether M1 surfaces a clearer refusal or defers to an M2 cancel-approval design (P3) | design | F3 mctl-api#1005 |

The 13 PARTIAL or NOT DONE matrix rows map to entries C1-C12 (C4 covers two rows, T9 and
T22): C1 = T1, C2 = T2, C3 = T6, C4 = T9 + T22, C5 = T15d, C6 = T15e, C7 = T17, C8 = T19,
C9 = T21, C10 = OPEN-989-8, C11 = OPEN-989-2, C12 = OPEN-989-4. C13 is an extra P3 design
note from the lead's list; it has no matrix row of its own (the refusal itself is DONE and
tested), so "13 carried items" counts the 13 matrix rows, not the 13 list entries.

### 4.2 Blocks activation of the write fence (not part of #989's acceptance)

The slice lands dark by design ("Ready fails in an environment until
`ApplyGlovoApprovalSchema` and the ownership transfer have run there"). Verified on
`main`: the fence cannot be installed from this build, and each item below is an
independent reason.

| # | Blocker | Evidence on `main` | Owner of the follow-up |
|---|---|---|---|
| A1 | The hold flag is a constant false | `cmd/api/glovo_bridge.go:113` `const glovoWriteFenceHoldLifted = false` | owner decision (mctl-gitops#2457) |
| A2 | The receipt fence is not constructed; the installer's `Build` returns an error | `cmd/api/main.go:1166` ("the receipt fence collaborators are not constructed in this build") | mctl-api#985 task 9 |
| A3 | No production caller of `ApplyGlovoApprovalSchema` / `workitems.ApplySchema`, no migration entry point, no `workitems.GlovoDecisions` wired into `api.Options.GlovoApprovals`, no `WithGlovoOrders` | grep of `cmd/` and non-test `internal/` finds none; `internal/api/router.go:272` has the option, nothing sets it | mctl-api#985 task 4/9; migration job in mctl-gitops#2563 |
| A4 | Membership revocation detector is not wired: `MembershipRevocationWired()` is false until a probe is installed | `internal/glovo/store.go:282`; `cmd/api/glovo_control.go:56`; no `WithMembershipRevocationProbe` caller in `cmd/` | membership detector slice (OPEN-985-2) |
| A5 | Real revocation hook: the code is in place (the hook is `bridge.CancelOpenForConnections` when control is enabled, `cmd/api/glovo_team_grant.go:147-172`, `fenceHookReady` at `glovo_control.go:51`) and proven in tests over the real connection store and the real fence (`TestFenceEndToEndRevocation`). What is NOT proven is the same under the real production role split, because the roles do not exist yet | OPEN-989-2 | mctl-gitops#2563, then an activation-time proof |
| A6 | GitOps roles, database URLs and the table-ownership transfer | mctl-gitops#2563 is a draft, inert, `suspend: true` job with `/bin/false` command; its own open items 1-7 are unanswered | owner + operator |

## 5. Decision and follow-ups

> **Proposed; the owner agreed to it on 2026-11-10 on the ordering condition below:**
> the #989 implementation slice is closed as **DELIVERED-BY-DIRECT-PRS**, with **13
> partial or not-done matrix rows carried to named follow-ups**, **only after** the
> follow-ups exist and are linked and this pull request is updated. The DevLoop run
> `mctl-agents-implement-9fc5a135` stays `Failed` with `execution-unauthorized`. The
> proposal's `status: accepted` is not changed by this record.

The follow-ups were created on 2026-11-10, all in mctlhq/mctl-api, each carrying only
`Refs #989` (no closing keyword):

| Follow-up | Issue | Scope | Carries |
|---|---|---|---|
| F1 | mctl-api#1003 | tests only: authorization, isolation, secrecy, races | T1, T2, T6, T9, T22, T15d, T15e, T17, T19, T21 (10 PARTIAL rows), plus the `Sweeper.Run` test |
| F2 | mctl-api#1004 | P1 wiring, migrations, sweeper started from `main.go`, readiness, membership detector slice, activation-time hook proof, gitops roles; the hold flag stays `false` | OPEN-989-8 and OPEN-989-2 (the 2 NOT DONE rows), OPEN-989-4 (PARTIAL, payload ownership item), activation blockers A2-A6 (section 4.2) |
| F3 | mctl-api#1005 | docs only, non-blocking for M1: the `cancel_order_fake` refusal decision | item C13 |
| existing | mctl-gitops#2563 | staged roles, secrets, migration job (draft, inert) | OPEN-989-2 deployment half, A6 |

All 13 PARTIAL or NOT DONE matrix rows are bound: 10 to F1 and 3 to F2 (OPEN-989-2,
-4 and -8). mctl-telegram#1262, which the earlier text named for OPEN-989-4, is closed
(completed 2026-11-10T01:55Z) and its body does not carry the obligation, so it is not a
home; the obligation is an explicit item of mctl-api#1004. The carried count stays 13 rows,
now 10 in F1 and 3 in F2 with nothing left outside mctl-api (plus the staged gitops
work in mctl-gitops#2563 for OPEN-989-2). A4 (membership detector) is a separate slice inside F2, with a
heartbeat of at most 5 minutes that fails closed. A1 (the hold flag) is carried nowhere: it
stays an owner decision for the activation PR.

What "closed" would and would not mean once the owner performs it:

- It means: tasks 0-9 are on `main` through #998 (with #997, #999, #1000, #1001 around it)
  and the matrix is the audit of what is and is not proven. 30 of 47 rows are DONE and
  all 11 tasks are DONE.
- It does NOT mean: the DevLoop succeeded; an approval grant exists for the digest; the
  write fence may be installed; the feature may be activated; the 13 carried rows are done.
- It does not rewrite history: no merge, tag, release, deployment or status field changes.

## 6. Owner decisions (typed in chat, 2026-11-10)

Recorded as the owner's decisions, dated. This record applies none of them to any system.

1. **Closure.** AMEND this record, then close the slice as DELIVERED-BY-DIRECT-PRS only
   AFTER the follow-ups are created and linked (done, section 5) and this pull request is
   updated (this amendment). The owner's closure GO is conditional on those two steps;
   the closing act itself has not been performed (section 7).
2. **Digest mismatch.** Approval `sha256:ed0a3408b42fb2b4960a4ed3c6521efef834aa27aa439eab8aac484f66d5bc92`
   versus proposal on `main` `sha256:9bd4b0c27ffb35b70472dae1898c25e1347d1bc9ff63e7b305e1c9f5a60740fd`:
   keep BOTH digests and the whole history. Do not fake the approval and do not restart
   the Failed DevLoop.
3. **OPEN-989-3.** The `developer` role is the minimum, and only the order owner with
   current tenant membership may decide.
4. **OPEN-989-5.** The basket fingerprint in Temporal history is allowed ONLY for the
   synthetic fake-only M1.
5. **OPEN-989-7.** `ReservePermitMargin` is 120 s.
6. **OPEN-989-2.** GO to PREPARE `glovo_runtime` and `glovo_migrator`. Applying is a
   separate decision; nothing is applied.
7. **OPEN-989-9.** Use the existing WorkItems runtime role. The name was looked up in
   GitOps, not guessed: the work-items store runs as the `mctl-api` role of the shared
   CNPG cluster (`infra-components/data/cnpg/shared/cluster.yaml`, database `mctl-api`),
   because `WORK_ITEMS_DB_URL` is unset and the store falls back to `AUDIT_DB_URL` with
   `DB_USER` (`bootstrap/templates/mctl-platform/mctl-api.yaml`). The migrator must take
   over table ownership from that role. The name is to be confirmed against the live state
   in F2 before the migration runs.
8. **OPEN-989-8.** A separate `receipt.Sweeper`, started from `cmd/api/main.go` (F2).

Not decided here and still the owner's, for the activation PR: A1 (the hold flag
`glovoWriteFenceHoldLifted`, stays `false`), A4 (membership detector) and the
activation-time proof of A5.

## 7. Unfinished obligations (explicit)

The slice is NOT closed. Still open:

1. The closing act: closing mctl-api#989 with a comment linking this file. Not performed;
   it needs the owner's go after this pull request is reviewed. This pull request stays a
   draft and is not merged.
2. F1 (mctl-api#1003), F2 (mctl-api#1004) and F3 (mctl-api#1005) are created, not done.
   Of the 13 carried matrix rows, none is closed by this record.
3. The proposal's `blocked:` and `reconciliation:` blocks and the Failed DevLoop record
   are unchanged; no approval grant exists for the current digest.
4. The role name for OPEN-989-9 is derived from GitOps text, not verified live.
5. Nothing of the write path is active: the fence is not constructed, no migration has
   run, no role is provisioned, no sweeper runs, the membership detector is absent, and
   the hold flag is `false`.
6. Mutation (red-when-reverted) proofs were not re-run for this record.

## 8. How this record was stored

The proposal directory is read by `scripts/proposal-content-digest.py`, which hashes only
`requirements.md`, `design.md`, `tasks.md` and `proposed-content.md`. This file is none of
those, so adding it does not change the content digest of the proposal
(`sha256:9bd4b0c27ffb35b70472dae1898c25e1347d1bc9ff63e7b305e1c9f5a60740fd` before and
after), and it therefore does not alter what any approval binds. It lives beside the
proposal it records rather than in `_mentor/` (which holds weekly digests) because it is
about this proposal only.

Validators run on this branch (2026-11-10), from the repository root:

- `scripts/proposal-content-digest.py <proposal-dir>`: prints
  `sha256:9bd4b0c27ffb35b70472dae1898c25e1347d1bc9ff63e7b305e1c9f5a60740fd`, unchanged.
- `scripts/proposal-content-digest.py --selftest`: pass.
- `scripts/validate-agents-state-approval.py`: 936 proposals checked, none unrunnable. Pass.
- `scripts/validate-agents-state-approval.py --selftest`: pass.
- `scripts/validate-glovo-m1-staging.py`: FAILS locally, only because kubeconform has no
  schema for the `ExternalSecret` CRD in this environment ("could not find schema for
  ExternalSecret"). That is environmental, and the script excludes `agents-state/` from its
  leak guard and reads nothing this change touches. Not run to a pass here; CI's CRD
  catalog is the check for it.
