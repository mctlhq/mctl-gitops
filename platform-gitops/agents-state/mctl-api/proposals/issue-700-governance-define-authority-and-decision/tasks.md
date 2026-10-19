# Tasks: issue-700-governance-define-authority-and-decision

- [ ] 1. Add the `internal/governance` package. It contains:
  - `Policy`/`PolicySet`, with `Policies` seeded with `dev-loop.human-approval` (v1, `require_approval`, reasons `["dev-loop.proposal-acceptance"]`, side effect `write`) and `Check(ruleID, version)`;
  - the typed sentinels `ErrContextIncomplete`, `ErrContextChanged`, `ErrApprovalStale`, `ErrAuthorityRevoked`, `ErrDeciderDisabled`, `ErrAuthorityUnavailable` and `ErrPolicyDrift`;
  - `DecisionContext` and `DecisionContextOf(a, live)`, with `context_complete`/`missing_fields`;
  - `ContextDigest` (`mctl-decision-context/v1`, length-prefixed, fixed field order);
  - `LiveAuthority` and `Revalidate`.

  DoD: the package compiles with no import cycle (it imports `workitems`, `auth`, `operations`), and `go vet` and `golangci-lint` are clean.
- [ ] 2. Extend `actionApprovalSchema` in `internal/workitems/action_approvals.go` with nine columns: `risk_level`, `side_effect`, `intent_source`, `policy_decision`, `policy_reasons TEXT[]`, `decided_context_digest`, `authority_basis`, `authz_mode` and `fresh_until TIMESTAMPTZ`.
  - Add them to `ActionApprovalRequest`, `actionApprovalColumns` and `scanActionApproval`, and add the context fields to `ActionApprovalInput.validate()` with bounds and `scanSecrets`.
  - `ActionDecisionInput` gains `ContextDigest`, `AuthorityBasis`, `AuthzMode` and `FreshFor`. `DecideActionApproval` writes them, with `fresh_until = LEAST(expires_at, now+FreshFor)`.
  - Add `ErrApprovalStale` and the `fresh_until` guard to the `ConsumeActionApproval` CAS and its read-back.

  DoD: existing store tests pass unchanged; the new columns round-trip; legacy rows scan with empty values and `fresh_until=nil`.
- [ ] 3. (depends on 1, 2) Create path in `internal/api/handlers_action_approvals.go`:
  - `actionApprovalBody` accepts `risk_level`, `side_effect`, `intent_source`, `policy_decision` and `policy_reasons`;
  - `risk_level` is derived from `h.opts.Registry` for a registered `action_kind`, and a contradicting client value is refused with 400 `approval_context_invalid`;
  - omitted fields are filled from `governance.Policies` and the `intent_source` fallback.

  DoD: a DevLoop `mctl-agents-approve` request created with today's body produces a complete context.
- [ ] 4. (depends on 1, 3) Read path: `writeActionApproval`, `ListActionApprovals` and the DevLoop paths emit `decision_context` with every mandatory field, `context_digest`, `context_complete` and `missing_fields`. DoD: the context contains no `reason` text and no args.
- [ ] 5. (depends on 1, 2) Decide path, in `handlers_action_approvals.DecideActionApproval` and `handlers_dev_loop.go` (~line 648):
  - an `approve` with incomplete context gets 422 `approval_context_incomplete` (with `details.missing_fields`) and the request stays pending;
  - an optional `context_digest` in `actionDecisionBody` that mismatches gets 409 `approval_context_changed`;
  - on success, pass `ContextDigest`, `AuthorityBasis="platform_admin"`, `AuthzMode=h.opts.TenantAuthzMode` and `FreshFor` from the new `ACTION_APPROVAL_MAX_DECISION_AGE` (default 24h, parsed in `cmd/api/main.go`, exposed on `api.Options`, and added to `helm/values.yaml`).

  DoD: a decided row carries all four facts; an invalid env value fails boot with a clear error.
- [ ] 6. (depends on 1, 2) Consume paths: wire `governance.Revalidate` into `handlers_action_approvals.ConsumeActionApproval` and `handlers_approval_grant.spendApprovalGrant`, before `WorkItems.ConsumeActionApproval`. Reuse the `checkHumanPrincipal` pattern from `handlers_surface_identity.go`.
  - Add the new codes to `actionApprovalRefusals`, with a `reapproval` flag that writes `details.reapproval_required=true` for `approval_context_changed`, `approval_stale`, `approval_expired`, `approval_authority_revoked`, `approval_decider_disabled` and `approval_policy_drift`. Use 503 without the flag for `approval_authority_unavailable`.
  - Audit refusals through `auditActionApprovalRefusal`.
  - Extend the success audit params, and use the stored `risk_level` in `auditActionApproval`.

  DoD: no refused consume spends the approval or reaches `Executor.Submit`.
- [ ] 7. (depends on 1) Replace `devLoopApprovalPolicyRule`/`devLoopApprovalPolicyVersion` in `handlers_approval_grant.go` with reads from `governance.Policies`. Add `api.Options.Policies` (a test seam) and `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` (default false). DoD: there is one source of truth for the DevLoop policy version, and the existing grant tests pass.
- [ ] 8. Write `docs/decision-context-contract.md` and link it from `docs/tenant-roles.md`. It contains:
  - the mandatory fields;
  - captured versus revalidated facts;
  - the refusal-code table with `reapproval_required`;
  - freshness semantics (`expires_at` versus `fresh_until`);
  - the privacy rule;
  - the #182 table exactly: F3 authority loss, F4 expiry/freshness, F6 reviewer context, F9 policy drift.

  Update `internal/openapi/openapi.yaml` for the body fields, `decision_context` and the error codes. DoD: the doc matches the implemented codes, and the `internal/openapi` tests pass.
- [ ] 9. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./...`. DoD: all green, and the MCP tool count in `server_test.go` is unchanged.

## Tests

Test names carry the #182 IDs.

- [ ] T1. `internal/governance` unit tests:
  - `ContextDigest` is stable, and changes when any single mandatory field changes;
  - `DecisionContextOf` reports the exact `missing_fields`;
  - table-driven `Revalidate` covers pass, plus each refusal in check order;
  - in legacy mode the admin-membership check is skipped but the principal status is still checked;
  - an unregistered rule passes as `unregistered`, and fails in strict mode.
- [ ] T2. `TestF3_ApprovalAuthorityRevoked` (`internal/api`): approve an `aar_` as admin A, then rebuild `Options.AdminPrincipals` without A. Both grant-authorized `mctl-agents-approve` and direct `/consume` return 409 `approval_authority_revoked` with `details.reapproval_required=true`. `Executor.Submit` is not called and the row is still `approved`. An approval with an empty `decided_by_principal_id` gets the same code.
- [ ] T3. `TestF3_ApprovalDeciderDisabled`: a fake `HumanPrincipalChecker` returns `auth.ErrPrincipalDisabled`, and separately `auth.ErrIdentityRefused` (merged or not human). Both produce 409 `approval_decider_disabled` with `reapproval_required`, and the approval is unspent.
- [ ] T4. `TestF3_ApprovalAuthorityUnavailable`: the checker returns `principals.ErrUnresolved`, and separately the resolver lacks `HumanPrincipalChecker`. Both produce 503 `approval_authority_unavailable`, the row stays `approved`, the refusal is audited as `action_approval.consume_refused`, and a retry after the checker recovers consumes successfully.
- [ ] T5. `TestF4_ApprovalStale` and `TestF4_ApprovalExpired`, using an injected clock:
  - decide at t0 with `FreshFor=1h` and consume at t0+2h: 409 `approval_stale` with `reapproval_required`;
  - the store-level CAS test proves the same refusal with handler revalidation bypassed;
  - consume past `expires_at`: 409 `approval_expired` with `reapproval_required`;
  - a legacy row with `fresh_until=NULL`: only `expires_at` applies.
- [ ] T6. `TestF6_DecisionViewHasMandatoryContext`: for a DevLoop request created with today's body, `GET /api/v1/action-approvals/{id}` returns `decision_context` with non-empty `target`, `args_digest`, `intent_hash`, `risk_level`, `side_effect`, `intent_source`, `policy.rule_id`, `policy.version`, `policy.decision` and `policy.reasons`, plus `context_digest` and `context_complete=true`. The same holds for the list view. Neither `reason` text nor args appear in the context or in any audit entry.
- [ ] T7. `TestF6_IncompleteContextCannotBeApproved`: create a request under an unregistered policy with `side_effect` omitted (and, in sub-cases, `intent_source` reduced to nothing derivable, or `policy_reasons` omitted). Decision `approve` returns 422 `approval_context_incomplete` with `details.missing_fields`, the row stays `pending`, and no grant can be consumed (consume returns `approval_not_approved`). Decision `deny` succeeds.
- [ ] T8. `TestF6_DecisionBoundToContextDigest`:
  - (a) a decision sent with a `context_digest` different from the current one returns 409 `approval_context_changed` and the row stays pending;
  - (b) a successful decision stores `decided_context_digest` equal to the digest shown in GET;
  - (c) after the decision, change a context input: either update the row's `side_effect` directly in the test DB, or swap the injected `operations.Registry` so the action kind's risk level changes. Consume then returns 409 `approval_context_changed` with `reapproval_required`, and the row stays `approved`.
- [ ] T9. `TestF9_ApprovalPolicyDrift`: approve under `dev-loop.human-approval@v1`, then switch `Options.Policies` to v2. Consume returns 409 `approval_policy_drift` with `reapproval_required`. A new request created and approved under v2 then consumes successfully.
- [ ] T10. Store migration test: `actionApprovalSchema` applies twice idempotently, and pre-existing rows get correct defaults.

## Rollback

All schema changes are additive columns with defaults, so redeploying the
previous image is safe. Old code ignores the new columns. Approvals decided
under the new code stay consumable by old code, which checks only state,
intent hash and `expires_at`.

For softer mitigation without a redeploy, set
`ACTION_APPROVAL_MAX_DECISION_AGE=168h`. This neutralises the freshness bound
(F4).

Authority, policy and context revalidation have no kill switch by design,
because they are the fix. If a targeted revert is needed, revert task 6 (the
consume wiring) or task 5's completeness gate alone. Tasks 2-4, 7 and 8 can
stay.

No data migration needs undoing, and leaving the columns in place is
harmless.
