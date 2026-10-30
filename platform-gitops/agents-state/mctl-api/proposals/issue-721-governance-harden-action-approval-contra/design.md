# Design: issue-721-governance-harden-action-approval-contra

## Current state

The action-approval lifecycle (mctl-api#366, hardened by #700/#717):

- **Rules.** `internal/governance/governance.go`:
  - `PolicySet` / `Policies`: one registered rule, `dev-loop.human-approval` v1.
  - `PolicySet.Check` returns `PolicyUnregistered` (not an error) for an unknown rule.
  - `DecisionContextOf` computes `MissingFields` / `ContextComplete`.
  - `RiskOf` takes the live registry risk for a registered `action_kind`, else the stored value.
  - `CreateContext.Missing`, `FillCreateContext`.
  - `Revalidate` runs the checks in this order: F6 digest (only when `DecidedContextDigest != ""`), F4 `FreshUntil` vs `live.Now`, F3 decider principal/admin, then F9 `Policies.Check`. `StrictPolicy` turns `PolicyUnregistered` into `ErrPolicyDrift`.
- **HTTP.** `internal/api/handlers_action_approvals.go`:
  - `actionApprovalRefusals` maps sentinel errors to status, code and `reapproval_required`.
  - `CreateActionApproval` runs: decode, header/body key check, `requireOpenExecution` (DevLoop kind only), `FillCreateContext`, `Missing()` (422), then `WorkItems.CreateActionApproval`. Structural and secret validation (`ActionApprovalInput.validate`, `internal/workitems/action_approvals.go:396`) runs inside the store, after the 422 gate. A secret-bearing, context-incomplete request is therefore answered 422, not 400.
  - `DecideActionApproval` pre-reads the row and calls `guardDecision` (completeness/digest, `handlers_approval_governance.go:83`) before the store validates the `reason` text for secrets. Same masking.
  - `ConsumeActionApproval` runs `ConsumeStateRefusal`, then `revalidateApproval`, then the store CAS. State-before-revalidation precedence exists and is tested (`TestF3_ConsumeStateRefusalPrecedesRevalidation`).
- **Grant spend.** `handlers_approval_grant.go:201-210` follows the same order. The DevLoop decide path is `handlers_dev_loop.go:644-663` (`guardDecision` + `decisionCapture`).
- **Store.** `internal/workitems/action_approvals.go`:
  - `CreateActionApproval` takes an advisory lock per (requester, key), looks up the key, compares `IntentHash` (`ErrApprovalIdempotencyConflict`), then inserts. `UNIQUE` is the backstop.
  - `DecideActionApproval` sets `fresh_until = LEAST(expires_at, now+FreshFor)`.
  - `ConsumeActionApproval` is a CAS on `state='approved' AND intent_hash AND expires_at > $3 AND (fresh_until IS NULL OR fresh_until > $3)`.
  - Lazy expiry happens in `scanActionApproval(..., now)`.
  - Every time comes from `Store.now`, set in `store.go:199` to `time.Now().UTC()`, with no injection point outside package tests.
- **Clock split.** The handler uses `Options.Clock` (`router.go`) through `approvalNow()` only for `Revalidate.Now`. `cmd/api/main.go` (~line 978) never sets `Clock`. In production that is two independent `time.Now` reads, one in the handler and one in the store.
- **Legacy backfill.** The `actionApprovalSchema` boot SQL (`action_approvals.go` ~line 165) runs on every boot. It updates every row `WHERE intent_source = '' AND decided_context_digest = ''`, including terminal ones. It fills `side_effect='write'`, `policy_decision`, `policy_reasons=['legacy.pre-governance']` and `intent_source`, but never `risk_level`. It has no dry-run or count.
- **Spend-time completeness gap.** A legacy row approved before #700 has no `decided_context_digest`, so `Revalidate` skips F6, and nothing checks `ContextComplete` at spend. An approved legacy row for an unregistered `action_kind` with empty `risk_level` can be consumed today.
- **Strict policy.** `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` is parsed by `killSwitchOn` in `cmd/api/main.go:2207` and is enforced only in `Revalidate`. Create and decide do not consult it. A nil `Options.Policies` falls back to `governance.Policies`, so there is no unavailable state today. The consume audit records `revalidation` but not `PolicyStatus`.
- **Docs.** `docs/decision-context-contract.md` documents create/approve completeness, the revalidation order and the refusal table. It is silent on spend-time completeness, replay semantics, strict-mode at create/decide, and 400-vs-422 ordering. `internal/openapi/openapi.yaml` lines 4391-4650 mirror it.
- **Tests.**
  - `internal/api/handlers_approval_governance_test.go`: `TestF6_*`, `TestF3_*`.
  - `internal/api/handlers_action_approvals_test.go`: idempotency, secrets, lazy expiry. It uses a real Postgres via `workItemsEnv` and moves time by `UPDATE ... expires_at = now() - 1s`, not by a clock.
  - `internal/governance/governance_test.go`.

Deployed state checked:
- `mctl_list_services team=admins`: lists mctl-agents-worker{,-exec,-implement}, mctl-design, mctl-docs, mctl-web and umami. **mctl-api is not a catalogue service there.**
- `mctl_get_service_config admins/mctl-api`: error "service not found: admins/mctl-api".
- `$MCTL_GITOPS_ROOT` checkout (`/workdir/mctl-gitops/platform-gitops/services/{admins,karabu,labs}`): no mctl-api values file. `grep ACTION_APPROVAL` over services/ and tenants/ found nothing.
- `helm/values.yaml` in the clone: `ACTION_APPROVAL_MAX_DECISION_AGE: ""` (24h) and `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: ""` (off). These are chart defaults only. The production override could not be observed (see Open questions in requirements.md).

## Proposed solution

Six changes, each inside the existing packages. No new tables, no new service, no new policy engine.

### 1. Deterministic precedence (create, decide, spend)

- Export a structural validator from `workitems`: `func (in ActionApprovalInput) ValidateStructure() error`. It holds the current `validate()` minus nothing, and the store keeps calling it as a backstop. `CreateActionApproval` (handler) builds `in` first, calls `ValidateStructure()` (400 class: invalid, secret, `intent_hash_mismatch`), then `FillCreateContext` (400 `approval_context_invalid`), then `Missing()` (422), then the strict-policy create gate, then live admission (`requireOpenExecution`), then the store.
- `DecideActionApproval`: call a new `workitems.ValidateDecisionInput(in ActionDecisionInput)` (decision enum, reason length/secret) before `guardDecision`.
- The documented order is:

  1. authn/role (403);
  2. decode/structural/secret (400);
  3. context invalid (400);
  4. context incomplete (422);
  5. state refusal for decide/spend (409, existing `ConsumeStateRefusal`, plus already-decided/self-decision for decide);
  6. strict policy;
  7. live admission/revalidation;
  8. store CAS.

  For create, the idempotency key lookup happens in the store after steps 1-4 and 6-7.
- **Replay.** A matched replay is answered only after steps 1-4 (and 6-7 for create admission). It returns the stored row unchanged with 200. The handler never calls decide/consume on a replay, so it cannot renew `fresh_until`, `decided_at` or state. This is documented as "replay is a non-authorizing read of the stored request".

### 2. Spend-time completeness for legacy rows

In `governance.Revalidate`, add step 0 before the F6 digest check: `c := DecisionContextOf(a, Live{Registry})`. If `!c.ContextComplete`, return `ErrSpendContextIncomplete`, a new sentinel that wraps `ErrContextIncomplete` and carries `MissingFields` through a typed error. In `actionApprovalRefusals`, map it ahead of `ErrContextIncomplete` to 409 `approval_context_incomplete` with `reapproval_required=true` and `missing_fields`. This uses the same canonical `DecisionContextOf` as create and decide, so registry-derived `risk_level` is honoured.

### 3. Strict registered policy

- In `governance`:
  - Add `ErrPolicyUnregistered` and `ErrPolicyUnavailable`.
  - Add `PolicyDrift = "drift"` as a status.
  - Add `func (ps PolicySet) Admit(ruleID, version string, strict bool) (status string, err error)`, used by create, decide and spend. It returns `ErrPolicyUnavailable` when strict and `len(ps)==0`, and `ErrPolicyUnregistered` when strict and the rule is unknown. A version mismatch is always `ErrPolicyDrift`.
  - `Revalidate` step F9 calls `Admit`.
- In the handler, call `Admit` in `CreateActionApproval` and in `guardDecision` (approve only).
  - At create, an unregistered rule under strict mode is 422 `approval_policy_unregistered` and nothing is stored.
  - At create, a version that differs from the registered one is 409 `approval_policy_drift` without `reapproval_required`, because nothing exists yet. This applies in both strict and non-strict mode, so a producer can never create against a stale version of a registered rule.
- Refusal table:
  - `approval_policy_unregistered`: 409 at spend with `reapproval_required=true`; 422 at create.
  - `approval_policy_unavailable`: 503, no reapproval.
- **Observability.** Add a `policy_status` parameter to `auditActionApproval` and `auditActionApprovalRefusal` through the existing `extra` map, so every create, decision and consume entry carries it. At boot, `cmd/api/main.go` logs `slog.Info("action approval policy", "strict", ..., "rules", ...)`. The producer inventory uses the existing `GET /api/v1/audit` (`h.ListAudit`) filtered on `action_approval.create`, grouped by `action_kind` / `policy_rule_id` / `policy_status`. No new store.
- **Default and rollback.** The default stays off. Rollback is setting the env var back to empty in mctl-api's helm values and redeploying. That is bounded and needs no data change.

### 4. Bounded legacy migration

- Narrow the boot backfill to `WHERE intent_source = '' AND decided_context_digest = '' AND state IN ('pending','approved')`. Terminal rows are no longer rewritten. Rows already backfilled are unaffected, because the predicate is idempotent.
- Do not write `risk_level`. It stays registry-derived through `RiskOf`. A legacy row for an unregistered `action_kind` keeps an empty `risk_level`, is incomplete, and step 2 refuses it at spend and `guardDecision` at approve.
- Add a read-only admin endpoint `GET /api/v1/action-approvals/legacy-inventory`, human admin only, routed beside the existing action-approval routes in `internal/api/router.go`. It pages the live rows through `WorkItems.ActionApprovals` with a state filter. For each row it computes `DecisionContextOf` and `PolicySet.Check`, and returns counts by (`action_kind`, `policy_rule_id`, `policy_version`, `policy_status`, `context_complete`, `missing_fields`). This is the dry-run pre-state, and its postcondition is "no live row with `context_complete=false` or, in strict mode, `policy_status != ok`". It is computed through the same functions the spend path uses, not through SQL column counts. It is a query, not a persistent inventory.

### 5. One clock

- Add `workitems.WithClock(now func() time.Time) StoreOption`, accepted as a variadic argument to `workitems.NewStore`. `Store.now` defaults to `time.Now().UTC()`.
- In `cmd/api/main.go`, create one `clock := func() time.Time { return time.Now().UTC() }` and pass it to both `workitems.NewStore(ctx, url, workitems.WithClock(clock))` and `api.Options{Clock: clock}`.
- `approvalNow()` is the only handler time source in the approval lifecycle. The store's CAS keeps taking `now` as a SQL parameter, never SQL `now()`. A small guard test greps `internal/workitems/action_approvals.go` and the approval handler files for `time.Now(`. It supplements the behavioural proof and is not the acceptance evidence for it.
- Integration test: build a `workItemsEnv` with a controllable clock shared by store and handler. Decide at t0 and assert `decided_at == t0` and `fresh_until == t0+age`. Advance to `fresh_until+1s`: consume returns `approval_stale` from Revalidate. Bypass Revalidate by calling the store directly and the CAS also refuses stale. Advance past `expires_at`: GET returns `expired` via lazy expiry.

### 6. Contract documents

Update `docs/decision-context-contract.md`:
- new sections "Refusal precedence", "Idempotent replay", "Spend-time completeness" and "Registered policy and strict mode (rollout)";
- add `approval_policy_unregistered` and `approval_policy_unavailable` to the refusal table;
- add the rollback procedure.

Update `internal/openapi/openapi.yaml`: the error enum (line ~1040), and the create/decision/consume responses (4391-4650). Add a runbook section to the same doc, or `docs/runbooks/action-approval-strict-policy.md`, covering inventory, observation window and flip/rollback.

## Alternatives

1. **Only flip the strict default to on.** This is the issue's explicit non-goal. Without an inventory, an unknown producer (the test suite itself uses the unregistered `merge-needs-human`) would break in production with no evidence trail.
2. **Persist a migration ledger or policy inventory table.** This duplicates audit data and overlaps #701's durable-evidence scope. A computed admin query over existing rows plus audit entries is sufficient for rollout proof.
3. **Backfill `risk_level` in SQL (e.g. default `medium`).** This invents governance facts for unregistered kinds and makes SQL column counts look complete while the context is not. It was rejected in favour of read-time registry derivation and refusal.
4. **Make replay an unconditional historical read (skip live admission).** This is viable and simpler for callers, but it diverges from today's ordering and would let a replay answer 200 for a closed execution. Kept as an open question.

## Platform impact

- **Migrations.** One edit to the idempotent boot SQL: the backfill predicate gains `AND state IN ('pending','approved')`. No new columns or tables. Re-running is a no-op.
- **Backward compatibility.**
  - New codes `approval_policy_unregistered` and `approval_policy_unavailable` appear only under strict mode.
  - The spend-time `approval_context_incomplete` 409 affects only incomplete legacy approved rows. Those were spendable before, and blocking them is the intended hardening. The pre-deploy inventory must show how many exist.
  - Clients keyed on `reapproval_required` keep working.
  - The 400-before-422 reordering changes the code only for requests that were doubly wrong.
- **Resources.** Negligible. The inventory endpoint is bounded by `MaxApprovalList` paging and is admin-only.
- **Risks and mitigations.**
  - Strict mode refuses a legitimate producer. Mitigation: ship strict-off, inventory via audit `policy_status` for at least one `ACTION_APPROVAL_MAX_DECISION_AGE` window, register the rule in `governance.Policies` before the flip, and use env-var rollback.
  - The legacy spend refusal blocks an in-flight DevLoop. Mitigation: the inventory before deploy; affected rows can be re-requested (`reapproval_required=true`).
  - A clock refactor regression. Mitigation: the default stays `time.Now().UTC()`; the existing tests run unchanged.
- **#701 boundary.** Only audit parameters (`policy_status`) and a computed read endpoint are added. There is no decision/attempt schema.
