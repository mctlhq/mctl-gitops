# Tasks: issue-869-feat-governance-bind-direct-human-decisi

- [ ] 1. Add `cardBinding` type, `checkCardBinding`, and `Options.ApprovalCardBinding`. The option is parsed from `MCTL_APPROVAL_CARD_BINDING` (`legacy`|`require`, default `legacy`, invalid value fails startup) in `cmd/api/main.go`. — DoD:
  - `guardDecision` in `internal/api/handlers_approval_governance.go` uses the binding.
  - Empty fields refuse 422 `approval_context_incomplete`.
  - An id, context or content mismatch refuses 409 `approval_context_changed`.
  - Legacy mode keeps today's behaviour and audits `binding=legacy`.
- [ ] 2. Wire `card_binding` into `DecideActionApproval` (`actionDecisionBody`). Add the replay rule: an identical decider and binding on an approved grant answers 200 `replayed:true`. (depends on 1) — DoD: path id mismatch gives 409, and the store still records exactly one decision.
- [ ] 3. Wire `card_binding` into `ApproveDevLoopWorkflow` / `decideDevLoopApproval` (`approveDevLoopRequest`). (depends on 1) — DoD:
  - The binding's `approval_id` is compared with the newest grant, and the newest grant is never substituted.
  - `require` mode refuses the legacy no-grant payload.
  - A pre-signal re-read plus `revalidateApproval` runs before `SignalApprove`.
  - The response carries `approval_id` and `decision_outcome`, including `decided_not_signalled` on signal failure.
- [ ] 4. Abandon: refuse relayed/surface callers with 403. Add the `effects` block (`pending`/`in_flight`/`applied`, plus status `cancellation_pending` or `cancellation_effects_unknown`) in `AbandonDevLoopWorkflow`. — DoD: abandon never mutates any `aar_`, and a store read failure still returns the signal outcome, with `cancellation_effects_unknown`.
- [ ] 5. Create `internal/autonomy` with the store (`autonomy_enrollments`, append-only versions) and the `Evaluator`, which returns the outcome codes `allowed`, `delegation_missing`, `delegation_expired`, `delegation_revoked`, `delegation_scope_mismatch` and `policy_checkpoint_unavailable`. — DoD:
  - Unit tests cover each outcome.
  - A store error never yields `missing` or `allowed`.
  - Mode `off`/`advisory`/`enforce` comes from `MCTL_AUTONOMY_POLICY_MODE` (default `advisory`).
  - `enforce` requires `MCTL_POLICY_CHECKPOINT_ATTESTED`.
- [ ] 6. Add the autonomy REST handlers and routes in `internal/api/router.go`: create, revoke and downgrade (all `isHumanAdmin`; the policy actor must be non-human via `CheckHumanPrincipal`; `expires_at` is mandatory and capped by `MCTL_AUTONOMY_MAX_TTL`), list (admin), and evaluate (direct service/policy principal). (depends on 5) — DoD: handlers have audit entries and OpenAPI entries (`internal/openapi`).
- [ ] 7. Add `governance.AuthorityBasisAutonomyPolicy`. Extend `decisions.DecisionInput.validate` and `RecordDecision` so that the basis requires an empty `approval_id`, a non-human actor equal to the enrollment's policy actor, and a live `enrollment:` reason. (depends on 5) — DoD: an invalid combination gives 422 `decision_invalid`.
- [ ] 8. Add the separation guards: `DecideActionApproval`, `ConsumeActionApproval` and `MarkActionApprovalExecuted` refuse an active policy actor principal. (depends on 5) — DoD: 403 `approval_decider_forbidden`.
- [ ] 9. Add the optional `approval_id`/`context_digest`/`content_digest` args to MCP `mctl_approve_dev_loop` (`internal/mcp/server.go`) and update its description. (depends on 3) — DoD: the tool count in `server_test.go` is unchanged.
- [ ] 10. Docs: describe the migration mode, codes and the advisory default in the README/OpenAPI. State that no enrollment or enforce flag is activated. — DoD: `go fmt`, `go vet` and `golangci-lint` are clean.

## Tests

- [ ] T1. Decision route: a relay, surface, service and policy principal each get 403 `approval_decider_forbidden`, and the grant stays pending.
- [ ] T2. Card binding missing a field: 422 `approval_context_incomplete` with `missing_fields`. Run in both modes, so that an empty value is never a bypass.
- [ ] T3. `require` mode with no `card_binding`: 422 on both routes. `legacy` mode with no binding: today's behaviour, and the audit carries `binding=legacy`.
- [ ] T4. Stale card after supersession: grant A is shown, grant B is created, and an approve with `approval_id=A` gives 409 `approval_context_changed`. B stays pending and nothing is signalled.
- [ ] T5. Context digest changed (for example a policy version change) gives 409. A changed `artifact_hash` gives 409. An empty `artifact_hash` gives `approval_content_unbound`.
- [ ] T6. Pre-signal recheck: a fake store that changes the grant between the decide and the signal leads to no `SignalApprove` call and a 409.
- [ ] T7. Signal failure after the decide answers `decision_outcome=decided_not_signalled` with `approval_id`. A retry with the same binding re-signals and decides nothing new.
- [ ] T8. Duplicate identical decision: one stored decision, and the second call answers 200 `replayed:true`.
- [ ] T9. `request_changes`, `defer` and `cancel` as decisions are refused, and the `aar_` stays pending. A human-input response leaves the `aar_` pending.
- [ ] T10. Abandon: a relayed caller gets 403. A direct admin gets `effects` grouped correctly. A store failure gives `cancellation_effects_unknown`, and no `aar_` state changes.
- [ ] T11. Evaluator table tests: missing, expired, revoked, scope mismatch (action class, work scope, risk, cross-tenant), checkpoint not attested, store error (gives `policy_checkpoint_unavailable`), and allowed. In advisory mode, `permitted` is always false.
- [ ] T12. Downgrade or revoke after an allowed evaluation: the next evaluation, and the pre-effect recheck, refuse.
- [ ] T13. Enrollment create with a human `policy_actor_principal_id` is refused. Create by a non-`isHumanAdmin` caller is refused.
- [ ] T14. A `dec_` with `authority_basis=autonomy-policy` and a non-empty `approval_id`, a human actor, or a dead enrollment gives 422.
- [ ] T15. A policy actor calling decide, consume or execute gets 403.
- [ ] T16. Mutation tests (a build-tag or table-driven guard toggle): disabling each guard in turn (isHumanAdmin, binding presence, id equality, context digest, content digest, pre-signal recheck, non-human actor, empty approval_id, policy-actor refusal) makes at least one of T1-T15 fail.

## Rollback

Every behaviour change is gated or additive:

- Set `MCTL_APPROVAL_CARD_BINDING=legacy` to restore today's approve behaviour.
- Set `MCTL_AUTONOMY_POLICY_MODE=off` to disable evaluation entirely.
- The `autonomy_enrollments` table is unused when the mode is off and can stay in place.
- For a full rollback, revert the release image through the normal gitops image-tag rollback. The new table is additive and needs no down-migration.
- If the abandon relay refusal breaks a caller, revert that one commit (task 4) independently.
