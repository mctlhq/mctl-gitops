# Tasks: issue-721-governance-harden-action-approval-contra

- [ ] 1. Export structural validation: add `workitems.ValidateActionApprovalInput` wrapping `ActionApprovalInput.validate` in `internal/workitems/action_approvals.go`. — DoD: the store still calls it; it is unit-tested for length, enum, prefix, secret and intent_hash cases.
- [ ] 2. Add `FindActionApprovalByKey(ctx, requestedBy, key)` to `workitems.Store` and the `WorkItems` interface in `internal/api/interfaces.go`, and update the fakes. (depends on 1) — DoD: it returns `ErrApprovalNotFound` when absent; existing tests compile.
- [ ] 3. Reorder `CreateActionApproval` (`internal/api/handlers_action_approvals.go`) to: gate, decode, structural validation (400), replay/conflict (200/409), open execution, `FillCreateContext`, strict policy, `Missing()`, store create. (depends on 1, 2) — DoD: the precedence table in T1 passes; the store's transactional lookup is unchanged.
- [ ] 4. Spend-time completeness: add step 0 to `governance.Revalidate`, the sentinel `ErrContextIncompleteAtSpend` wrapping `ErrContextIncomplete`, and a refusal-table entry `409 approval_context_incomplete, reapproval=true` ahead of the 422 entry. — DoD: an approved row with empty `risk_level` cannot be consumed or grant-spent, and stays `approved`.
- [ ] 5. Policy observability: add `PolicySet.Status`; record `policy_status` on create, decide and consume audit entries; `slog.Warn` for unregistered; log strict mode and the registered rule:version list at startup in `cmd/api/main.go`. Add the store method `ActionApprovalPolicyInventory` and a boot log line. — DoD: tests assert the audit parameter with strict off.
- [ ] 6. Strict enforcement at create and approve: new code `aarCodePolicyUnregistered = "approval_policy_unregistered"` (422) with sentinel `governance.ErrPolicyUnregistered`; version mismatch gives `ErrPolicyDrift` (409). Wire it into `CreateActionApproval` step 7 and `guardDecision`, only when `RequireRegisteredPolicy`. (depends on 3, 5) — DoD: T3 passes; with strict off, behaviour is unchanged apart from the audit.
- [ ] 7. Bounded legacy migration: remove the trailing `UPDATE` from `actionApprovalSchema`; add `(*Store).migrateLegacyGovernance` (count per state, then mutate only live rows `state IN ('pending','approved') AND expires_at > now`, no `risk_level`), plus `LiveIncompleteGovernanceCount`. Add the env `ACTION_APPROVAL_LEGACY_BACKFILL` (`apply` default, `count` = observe only), parsed in `cmd/api/main.go` and documented in `helm/values.yaml`. — DoD: T5 passes; terminal rows are untouched; a second run changes 0 rows.
- [ ] 8. One clock: `workitems.NewStore(ctx, conn, opts ...StoreOption)` with `WithClock`; in `cmd/api/main.go` build one `approvalClock` and pass it to both the store and `api.Options.Clock`; comment the `approvalNow` nil fallback as test-only. Add a shared controllable clock to the `workItemsEnv` test harness. — DoD: T6 and T7 pass; production time source still `time.Now().UTC()`.
- [ ] 9. Docs and OpenAPI: add Precedence, Registered policy (with rollout runbook and rollback) and Legacy rows sections to `docs/decision-context-contract.md`, plus the new code rows; update `internal/openapi/openapi.yaml` (error-code enum, create/decide/consume responses, replay rule, `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` description). (depends on 3, 4, 6, 7) — DoD: every code in `actionApprovalRefusals` appears in both; T8 passes.
- [ ] 10. Production rollout: ship tasks 1-9 with strict off, collect the inventory and `policy_status=unregistered` audits over at least one `ACTION_APPROVAL_MAX_DECISION_AGE` window, register or retire every unregistered producer, then set `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"` in `helm/values.yaml` and the mctl-api deployment values. (depends on 5, 6) — DoD: the inventory evidence is linked in the PR; zero unregistered live producers; the post-flip boot log shows `strict_policy=true`.

## Tests

- [ ] T1. `internal/api/handlers_approval_precedence_test.go`, table-driven create cases:
  - malformed JSON gives 400;
  - an overlong `target` with missing `side_effect` gives 400 (not 422);
  - a secret in `target` with missing context gives 400;
  - a bad `risk_level` enum gives 400;
  - a contradicting `risk_level` for a registered kind gives 400 `approval_context_invalid`;
  - a valid but incomplete request gives 422 `approval_context_incomplete` with `missing_fields`;
  - same key and same intent gives 200 with the same id, including when the retried body omits context and when the DevLoop execution has since finished;
  - same key with a different intent gives 409 `approval_idempotency_conflict`;
  - first create gives 201.
- [ ] T2. Spend precedence table, for each state (pending, denied, expired, consumed, executed) combined with each revalidation failure (revoked authority, disabled decider, policy drift, stale, context changed, context incomplete): the state code wins. Also assert that the stored row (`state`, `consumed_at`, `fresh_until`, `decided_at`) is unchanged after every refusal on consume, grant spend and decide.
- [ ] T3. Strict policy on:
  - unregistered rule at create gives 422 `approval_policy_unregistered`, nothing stored;
  - registered rule at the wrong version at create gives 409 `approval_policy_drift`;
  - a pre-existing pending unregistered row: approve is refused and the row stays pending;
  - a pre-existing approved unregistered row: consume gives 409 `approval_policy_drift`, `reapproval_required=true`, not spent;
  - `dev-loop.human-approval` v1 is created, approved and consumed normally.
- [ ] T4. A registered policy version change after a decision (swap `Options.Policies`) gives 409 `approval_policy_drift` in both strict and non-strict mode.
- [ ] T5. Migration (Postgres, `internal/workitems`): seed legacy rows in each state, live and expired; `count` mode mutates nothing and logs the counts; `apply` fills live pending/approved rows only; terminal and expired rows stay as they are; `risk_level` stays empty; a second run updates 0 rows; `LiveIncompleteGovernanceCount` returns 0 for registered-kind rows. An unregistered-kind live row is still refused at approve and spend.
- [ ] T6. F4 with one clock: decide at t0 with `ACTION_APPROVAL_MAX_DECISION_AGE=1h`, advance the shared clock 2h: consume gives 409 `approval_stale`. With the same clock, `Store.ConsumeActionApproval` called directly also refuses (CAS path). Advance past `expires_at`: GET reads `expired` and consume gives 409 `approval_expired`.
- [ ] T7. `cmd/api` wiring test: the built `api.Options.Clock` is non-nil and is the clock given to the store. A grep test finds no `time.Now(` in `internal/governance` or `handlers_approval_governance.go` beyond the documented fallback.
- [ ] T8. Doc/OpenAPI consistency test: every code in `actionApprovalRefusals` appears in the `ActionApprovalError.code` enum and in `docs/decision-context-contract.md`.
- [ ] T9. The existing `TestF3_*` and `TestF6_*` tests, the action-approval suites and the grant tests stay green (`go test ./...`, `golangci-lint`).

## Rollback

- Strict policy: set `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` back to `""`/`"false"` and redeploy. No data changes. Approvals refused under strict were never spent, so producers can re-request.
- Migration: set `ACTION_APPROVAL_LEGACY_BACKFILL=count` to stop further mutation. The migration only fills empty columns on live rows (the same values #700 already wrote), so no reverse migration is needed.
- Code: revert the PR. The precedence and clock changes carry no schema change; reverting restores the #717 behaviour exactly, including the old unconditional backfill on the next boot.
