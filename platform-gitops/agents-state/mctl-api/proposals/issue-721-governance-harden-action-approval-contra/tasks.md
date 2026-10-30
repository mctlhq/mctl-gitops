# Tasks: issue-721-governance-harden-action-approval-contra

- [ ] 1. Freeze the current contract with regression tests before any behaviour change. Add a table-driven precedence test and an idempotency concurrency test in `internal/api/handlers_approval_governance_test.go` (T1, T2, T3). Cases that encode the new behaviour are marked as expected-to-change in task 2. — DoD: existing `TestF3_*`/`TestF6_*` and `handlers_action_approvals_test.go` tests pass, and the new tests compile and document the current ordering.
- [ ] 2. Enforce deterministic precedence (depends on 1). Export `ActionApprovalInput.ValidateStructure()` and `ValidateDecisionInput()` from `internal/workitems/action_approvals.go`, keeping the store's internal call as a backstop. In `CreateActionApproval` (`internal/api/handlers_action_approvals.go`), call it before `FillCreateContext`/`Missing()`. In `DecideActionApproval`, validate decision/reason before `guardDecision`. — DoD: T1 passes. Secret plus incomplete context is 400. Incomplete alone is 422.
- [ ] 3. Add spend-time completeness (depends on 1). Add step 0 to `governance.Revalidate`, which refuses `!DecisionContextOf(...).ContextComplete` with a new `ErrSpendContextIncomplete` that carries the missing fields. Map it in `actionApprovalRefusals` ahead of `ErrContextIncomplete` to 409 `approval_context_incomplete`, `reapproval_required=true`, `missing_fields`. — DoD: T5 incomplete cases are refused and stay `approved`, unspent.
- [ ] 4. Add strict-policy mechanism, default off (depends on 1).
  - In `internal/governance/governance.go`: add `ErrPolicyUnregistered`, `ErrPolicyUnavailable`, status `drift`, and `PolicySet.Admit(rule, version, strict)`, and use it in `Revalidate`.
  - In the handlers: call `Admit` in `CreateActionApproval` and in `guardDecision` (approve only).
  - Add refusal-table rows: `approval_policy_unregistered` (422 at create via a create-side sentinel, 409 plus reapproval at decide/spend) and `approval_policy_unavailable` (503).
  - Remove the silent fallback to `governance.Policies` when strict and the set is empty.

  DoD: T4 passes, and with strict off all existing tests pass unchanged.
- [ ] 5. Add minimal rollout observability (depends on 4). Add a `policy_status` param on create, decision, consume and refusal audit entries via `auditActionApproval`'s `extra` and `auditActionApprovalRefusal`. Log the strict mode and registered rule ids/versions at boot in `cmd/api/main.go`. — DoD: a test asserts `policy_status` on each audit op, and the boot log line is present.
- [ ] 6. Bound the legacy migration (depends on 3).
  - Narrow the backfill `UPDATE` in `actionApprovalSchema` to `state IN ('pending','approved')`, and never write `risk_level`.
  - Add the admin-only `GET /api/v1/action-approvals/legacy-inventory`, which returns counts by kind/rule/version/policy_status/context_complete, computed via `DecisionContextOf` and `PolicySet.Check`.
  - Register the route in `internal/api/router.go` and update the MCP tool count only if an MCP tool is added (none planned).

  DoD: T5 and T7 pass, and running the schema twice changes no rows.
- [ ] 7. Wire a single clock (depends on 2-4). Add a `workitems.WithClock` option to `NewStore`. In `cmd/api/main.go`, pass one clock to both the store and `api.Options.Clock`. Make sure no approval-lifecycle code path calls `time.Now` directly. — DoD: T6 passes against Postgres, and the guard test T8 passes.
- [ ] 8. Synchronize the contract docs (depends on 2-6). Update `docs/decision-context-contract.md` with the precedence, replay, spend-time completeness and strict-policy sections, and the refusal table. Update `internal/openapi/openapi.yaml` (the error code enum near line 1040, and the create/decision/consume responses). Add the runbook: inventory query, observation window of at least one `ACTION_APPROVAL_MAX_DECISION_AGE`, flip and rollback. — DoD: every code and status in the doc table matches `actionApprovalRefusals`, which T9 checks.
- [ ] 9. Run lint and the full suite (depends on all). Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD: green, and no strict-mode claim appears in the PR.
- [ ] 10. Post-deploy, as a separate GitOps step that is not part of the implementation PR:
  - observe for at least one max-decision-age window;
  - confirm via audit and legacy-inventory that every producer's rule is registered and no live incomplete row exists;
  - set `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY=true` in mctl-api's deployed values;
  - record the evidence on #721.

  DoD: the evidence is posted, and the rollback was rehearsed or documented.

## Tests

- [ ] T1. Precedence matrix, table-driven, in `handlers_approval_governance_test.go`:
  - malformed body → 400;
  - secret in target plus incomplete context → 400 secret code;
  - contradicting `risk_level` → 400 `approval_context_invalid`;
  - incomplete context → 422 with `missing_fields`;
  - same key, different intent → 409 `approval_idempotency_conflict`;
  - for each of denied, consumed, executed and expired state combined with a revoked decider, drifted policy, changed context or stale freshness, the state code wins;
  - after every refusal, the row state is unchanged.
- [ ] T2. Concurrency: N goroutines create with the same key and intent → exactly one `aar_` id, with one 201 and the rest 200. N goroutines with the same key and differing intents → one 201, and every other response is 409.
- [ ] T3. Replay non-authority:
  - replaying a create for an approved, expired, consumed or closed-execution approval never changes `state`, `decided_at`, `fresh_until` or `expires_at`;
  - a replay of a closed-execution DevLoop create answers `approval_execution_not_open`;
  - a replay followed by consume of an expired row is still refused.
- [ ] T4. Strict policy:
  - strict on with an unregistered rule → create 422 `approval_policy_unregistered`, approve refused, and spend 409 with `reapproval_required`;
  - strict on with an empty `Policies` → spend 503 `approval_policy_unavailable`, unspent;
  - a registered version bump after the decision → 409 `approval_policy_drift` (strict on and off);
  - strict off with an unregistered rule → allowed, audited `policy_status=unregistered`.
- [ ] T5. Migration-to-execution matrix: {registered `mctl-agents-approve` / unregistered kind} × {complete / incomplete legacy approved row without `decided_context_digest`}, inserted via SQL, then consumed through the real handler/Revalidate/CAS path, under strict on and off. Only complete plus registered is executable under strict.
- [ ] T6. Single clock: inject a shared fake clock into the store and handler. Decide at t0 and assert `decided_at=t0` and `fresh_until=t0+age`. Advance to `fresh_until` → `approval_stale` from Revalidate, and the store CAS called directly also refuses. Advance past `expires_at` → GET reports `expired`.
- [ ] T7. Backfill idempotency and boundary: seed terminal and live legacy rows, run the schema twice → terminal rows are byte-identical and live rows are backfilled once. The inventory counts before and after match the expected values.
- [ ] T8. Static guard (supplementary): there is no `time.Now(` in `internal/workitems/action_approvals.go`, `handlers_action_approvals.go`, `handlers_approval_governance.go` or `handlers_approval_grant.go` outside the documented default.
- [ ] T9. Doc/runtime sync: parse the refusal table in `docs/decision-context-contract.md` and the OpenAPI error enum, and assert they cover every code in `actionApprovalRefusals`.
- [ ] T10. The existing #700 tests (`TestF3_*`, `TestF6_*`, freshness/policy-drift tests in `internal/governance/governance_test.go`) remain green and unmodified in intent.

## Rollback

- **Strict policy.** Set `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` back to empty in mctl-api's deployed values and redeploy. Enforcement stops at the next request, with no data change.
- **Code.** Revert the implementation PR. The only schema change is a narrower `WHERE` in an idempotent backfill, so reverting restores the old predicate with no destructive effect. Rows touched by the narrower backfill are a subset of what the old one would have touched.
- **Spend-time completeness refusals.** If they block an in-flight flow, the affected approval is re-requested (`reapproval_required=true`). Reverting the PR restores the previous lenient spend.
