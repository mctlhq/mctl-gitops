# Harden the action-approval governance contract after #700

## Context

mctl-api#700 (PR #717) added the authority and decision-context contract for action approvals (`aar_`): mandatory decision context (`internal/governance.DecisionContextOf`), a context digest bound at decision time, `fresh_until`, and execution-time revalidation (`governance.Revalidate`) before the store's consume compare-and-set. The post-merge review found gaps where the normative document, production policy configuration and edge-case semantics can drift from the intended governance boundary. Four were confirmed in the code:

- A legacy approved row with no `decided_context_digest` is spent without any completeness check. `Revalidate` skips the F6 step, and nothing else checks `ContextComplete` at spend.
- `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` is enforced only at spend. Create and decide accept unregistered rules, and the consume audit entry does not record `policy_status`.
- Governance completeness (422) is evaluated before structural/secret validation (400) in both create and decide, so a malformed request can get the wrong class of refusal.
- The handler clock (`Options.Clock`, nil in production) and the store clock (`workitems.Store.now`, hard-wired to `time.Now`) are separate sources for one authorization lifecycle.

This proposal hardens the existing contract. It adds no second policy or approval framework. Durable decision/execution-attempt history stays with #701.

## User stories

- AS a platform admin I WANT an approval to be executable only when its policy identity/version is registered and revalidatable SO THAT an unknown policy can never authorize a side effect in production.
- AS an approval consumer (mctl-agents worker) I WANT deterministic, documented refusal precedence SO THAT I can branch on one typed code and never discard a live approval because of a masked refusal.
- AS an operator I WANT a dry-run count of legacy approval rows and of policy usage per producer SO THAT I can enable strict mode with evidence, and roll it back within a bounded window.
- AS a reviewer of governance changes I WANT `docs/decision-context-contract.md`, `internal/openapi/openapi.yaml` and runtime behaviour to agree SO THAT the normative contract is the actual contract.
- AS a test author I WANT one injectable clock behind decision time, freshness, lazy expiry, revalidation and consume CAS SO THAT freshness boundaries can be proven, not assumed.

## Acceptance criteria (EARS)

### Precedence and validation
- WHEN a create or decision request is structurally malformed or carries forbidden secret material THE SYSTEM SHALL refuse it with the specific 400-class code (`work_item_invalid`, the secret code, `intent_hash_mismatch` or `approval_context_invalid`) before any governance completeness check runs.
- WHEN a structurally valid create request lacks mandatory decision context after registry/policy defaults THE SYSTEM SHALL refuse it with 422 `approval_context_incomplete` and `details.missing_fields`, and store nothing.
- WHEN a create reuses an idempotency key with the same canonical intent THE SYSTEM SHALL return the existing `aar_` with 200 and SHALL NOT create a second row.
- WHEN a create reuses an idempotency key with a different canonical intent THE SYSTEM SHALL refuse it with 409 `approval_idempotency_conflict`.
- WHEN concurrent creates race on the same requester and key with the same intent THE SYSTEM SHALL produce exactly one durable `aar_` identity. When they race with different intents, exactly one SHALL win and every loser SHALL receive 409 `approval_idempotency_conflict`.
- WHEN a matched idempotent replay is answered THE SYSTEM SHALL first establish structural validity and canonical intent identity, and SHALL still apply the live create-admission checks (open execution for `mctl-agents-approve`, and strict registered policy when enabled). The replay is returned as a historical, non-authorizing resource: it SHALL NOT change state, `decided_at`, `fresh_until`, `expires_at` or authority.
- WHEN consume or the grant-authorized `mctl-agents-approve` spend is called on an approval that is not `approved` THE SYSTEM SHALL answer with the state refusal (`approval_not_approved`, `approval_denied`, `approval_expired`, `approval_consumed`), even when authority, policy, context or freshness revalidation would also fail.
- IF validation or revalidation refuses a consume or grant spend THEN THE SYSTEM SHALL leave the approval in its prior state, unspent.

### Spend-time completeness (legacy rows)
- WHEN an approved row is spent THE SYSTEM SHALL recompute `DecisionContextOf` with the live registry. IF `ContextComplete` is false THEN THE SYSTEM SHALL refuse with 409 `approval_context_incomplete`, `details.missing_fields` and `details.reapproval_required=true`, whether or not the row has a `decided_context_digest`.

### Registered policy
- WHILE `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` is on THE SYSTEM SHALL refuse create, approve and spend of an approval whose `policy_rule_id` is not in the registered `PolicySet`, with `approval_policy_unregistered`. Spend refusals SHALL carry `reapproval_required=true`.
- WHEN the registered version of a rule differs from the approval's `policy_version` THE SYSTEM SHALL refuse spend with 409 `approval_policy_drift` and `reapproval_required=true`, whatever the strict-mode setting.
- WHEN a create names a registered rule with a `policy_version` that differs from the registered one THE SYSTEM SHALL refuse it with 409 `approval_policy_drift` and store nothing.
- IF the authoritative policy set cannot be established (nil or empty `PolicySet` at runtime) WHILE strict mode is on THEN THE SYSTEM SHALL fail closed with 503 `approval_policy_unavailable` and SHALL NOT spend.
- WHEN the server boots THE SYSTEM SHALL log the effective strict-policy mode and the registered rule ids and versions.
- WHEN an approval is created, decided, spent or refused THE SYSTEM SHALL record `policy_status` (`ok`, `unregistered`, `drift`) in the existing audit entry parameters, reusing `approval_id`, `action_kind`, `policy_rule_id` and `policy_version`.
- WHILE strict mode is off THE SYSTEM SHALL keep today's behaviour for unregistered rules (allowed, audited as `policy_status=unregistered`).

### Legacy migration
- WHEN an operator requests the legacy inventory (dry run) THE SYSTEM SHALL report counts of live (pending/approved, unexpired) rows by `action_kind`, `policy_rule_id`/`policy_version`, registration status and context completeness, as computed by `DecisionContextOf`, without mutating anything.
- WHEN the boot-time backfill runs THE SYSTEM SHALL mutate only rows in `pending` or `approved` state, SHALL NOT rewrite terminal rows, and SHALL be idempotent.
- THE SYSTEM SHALL derive `risk_level` for legacy rows from the operation registry at read time (`governance.RiskOf`) and SHALL NOT invent a value for an unregistered `action_kind`. Such a row stays incomplete and non-executable.

### Single clock
- THE SYSTEM SHALL use one injected clock (`func() time.Time`, wired once in `cmd/api/main.go`) for decision time, `fresh_until`, lazy expiry, `Revalidate`'s `Now`, and the consume/execute CAS parameters.
- WHEN that clock is advanced past `fresh_until` THE SYSTEM SHALL report the approval as stale in revalidation and in the store CAS consistently, and SHALL report a lazily expired state past `expires_at`, all from the same instant.

### Contract
- THE SYSTEM SHALL keep `docs/decision-context-contract.md` and `internal/openapi/openapi.yaml` consistent with runtime on completeness, policy, replay and refusal ordering.
- THE SYSTEM SHALL keep the existing #700 tests (`TestF3_*`, `TestF6_*`, `TestF4`/`TestF9` equivalents) green and unchanged in intent.

## Out of scope

- Durable decision/execution-attempt/outcome records or a canonical evidence schema (#701).
- A new policy engine, approval service or persistent policy-inventory subsystem.
- Reimplementing F3/F4/F6/F9 or replacing the #700 authority/policy model.
- Break-glass design; broad audit/evidence redesign.
- The production strict-mode flip itself. It is a separate governed GitOps rollout after at least one `ACTION_APPROVAL_MAX_DECISION_AGE` observation window. The implementation ships strict-off.

## Open questions

- Replay semantics: this proposal keeps live admission checks on a matched replay, which matches today's ordering in `CreateActionApproval` (`requireOpenExecution` runs before the store's key lookup). The alternative, returning the stored row unconditionally as history, is also allowed by the issue. A reviewer should confirm the choice.
- The new code `approval_policy_unregistered` versus reusing `approval_policy_drift`: today strict mode returns `approval_policy_drift`. This proposal adds a distinct code for observability and keeps `reapproval_required=true`. Clients keyed on `reapproval_required` are unaffected.
- Should the spend-time 422/409 for an incomplete legacy row be 409 (state of the stored approval) or 422? This proposal uses 409 with `reapproval_required=true`, because the client cannot cure it by resending.
- Where mctl-api is deployed and its live env values could not be observed: `mctl_get_service_config admins/mctl-api` returned "service not found", and no mctl-api values file exists in the gitops services checkout. The effective production values of `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` and `ACTION_APPROVAL_MAX_DECISION_AGE` are therefore unverified. Helm defaults are both empty.
- Whether any producer other than the DevLoop (`mctl-agents-approve` under `dev-loop.human-approval`) creates approvals in production is unknown. The audit inventory (task 5) must answer it before the flip.
