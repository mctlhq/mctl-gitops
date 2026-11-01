# Bind direct human decisions to the reviewed card and separate delegated policy authorization

## Context

Issue mctlhq/mctl-api#869 (parent epic mctlhq/.github#281) asks for two related changes in mctl-api.

First, direct human decisions must be bound to exactly what the human saw. Today `POST /api/v1/action-approvals/{id}/decision` accepts an optional `context_digest`, and an empty one is accepted (`guardDecision` in `internal/api/handlers_approval_governance.go` only compares when `sentDigest != ""`). `POST /api/v1/agents/dev-loop/{workflow_id}/approve` takes no binding at all: `decideDevLoopApproval` in `internal/api/handlers_dev_loop.go` picks the execution's newest `mctl-agents-approve` grant (`Limit: 1`) and approves it with an empty digest. A human looking at a stale card (for example a Telegram or portal card rendered before the grant was superseded) can therefore approve a newer grant whose context and proposal content they never reviewed.

Second, the issue asks for a separate, non-human authorization path, "autonomy policy". A human admin enrolls a named action class, work scope, risk ceiling and tenant scope with an expiry. A policy evaluator can then authorize a matching effect under the reserved `execution_authorization=autonomy-policy` arm. That path records a `dec_` decision (`internal/decisions`) attributed to a non-human policy actor. It never decides or spends an `aar_`, never writes `approval.approved_by`, never uses `wi_`/`xr_` on-behalf-of attribution, and never satisfies `requires_human_approval`. The path is advisory by default. Enforcement depends on deployed checkpoint coverage (mctl-gitops#1980) and is not activated by this proposal.

## User stories

- AS a human platform admin I WANT my approval to apply only to the exact grant, decision context and proposal content shown on my card SO THAT a stale card can never approve something I did not review.
- AS a human platform admin I WANT a superseded or changed grant to answer 409 `approval_context_changed` SO THAT I re-review instead of approving blind.
- AS a legacy API/MCP caller I WANT an explicit, time-boxed migration mode SO THAT existing direct approve calls keep working until enforcement is switched on.
- AS a human platform admin I WANT to enroll, expire and revoke a narrowly scoped autonomy policy SO THAT routine low-risk work can proceed without me, without impersonating me.
- AS an auditor I WANT every policy-authorized effect recorded as a `dec_` attributed to the policy actor and its enrollment SO THAT human and policy authority are never confused.
- AS an operator I WANT "cancel" to stop future DevLoop work and report pending, in-flight and applied effects SO THAT I know what already happened, with no rollback implied.

## Acceptance criteria (EARS)

Direct decision binding

- WHEN a direct decision request carries a `card_binding` object THE SYSTEM SHALL require all three of `approval_id`, `context_digest` and `content_digest`, and IF any is empty THEN THE SYSTEM SHALL refuse with 422 `approval_context_incomplete` (details.missing_fields naming the empty fields) and leave the `aar_` pending.
- WHEN `card_binding.approval_id` on `POST /api/v1/agents/dev-loop/{workflow_id}/approve` differs from the execution's newest `mctl-agents-approve` grant THE SYSTEM SHALL refuse with 409 `approval_context_changed` (details.reapproval_required=true) and SHALL NOT decide or signal any grant.
- WHEN `card_binding.approval_id` on `POST /api/v1/action-approvals/{id}/decision` differs from the path `{id}` THE SYSTEM SHALL refuse with 409 `approval_context_changed`.
- WHEN `card_binding.context_digest` differs from the live `governance.ContextDigest` of the grant, or `card_binding.content_digest` differs from the grant's `artifact_hash`, THE SYSTEM SHALL refuse with 409 `approval_context_changed` and leave the grant pending.
- IF the grant's `artifact_hash` is empty on a DevLoop approve THEN THE SYSTEM SHALL refuse with the existing `approval_content_unbound` code.
- WHILE `MCTL_APPROVAL_CARD_BINDING=require` THE SYSTEM SHALL refuse every direct approve that carries no `card_binding` with 422 `approval_context_incomplete`. No empty or legacy bypass exists in this mode.
- WHILE `MCTL_APPROVAL_CARD_BINDING=legacy` (the default during migration) THE SYSTEM SHALL accept an approve without `card_binding` exactly as today, and SHALL record `binding=legacy` in the audit entry.
- WHEN a bound approve succeeds THE SYSTEM SHALL re-read the grant immediately before the Temporal signal and confirm that its id, state (`approved`), decided context digest and `artifact_hash` still equal the binding. IF they differ THEN THE SYSTEM SHALL NOT signal, and SHALL answer 409 `approval_context_changed`.
- WHEN a DevLoop approve has decided the grant but the signal fails THE SYSTEM SHALL answer with a definite outcome (`decision_outcome: "decided_not_signalled"`, `approval_id`) so that a retry carrying the same binding re-sends the signal and never decides a second grant (coordinated with mctl-agents#773).
- WHEN the same human repeats an identical bound approve for an already approved grant THE SYSTEM SHALL return the existing decision (`replayed: true`) and SHALL NOT create a second decision.
- WHILE any binding mode is active THE SYSTEM SHALL keep the existing `isHumanAdmin` requirement on both routes. A relay, surface, service or policy principal SHALL get 403 `approval_decider_forbidden`, checked before the body is read.

Action semantics

- THE SYSTEM SHALL accept only `approve` and `deny` as `aar_` decisions. IF the decision is `request_changes`, `defer` or anything else THEN THE SYSTEM SHALL refuse with the existing validation error and leave the `aar_` pending.
- WHEN a human-input answer (`POST /api/v1/human-input/{request_id}/response`) is recorded THE SYSTEM SHALL NOT change the state of any `aar_`.
- WHEN `POST /api/v1/agents/dev-loop/{workflow_id}/abandon` is signalled THE SYSTEM SHALL report an `effects` block listing the execution's grants by state (pending, in_flight, applied). It SHALL report `cancellation_pending` while the workflow has not yet reached an observation point, and `cancellation_effects_unknown` when the work-item store cannot be read. Abandon SHALL NOT deny or decide any `aar_`, roll back an effect, or close the GitHub issue.
- WHEN `POST /abandon` is called by a relayed (surface) principal THE SYSTEM SHALL refuse with 403. A surface such as Telegram must deep-link the user to a direct session instead.

Autonomy policy (new, advisory by default)

- WHEN a human admin acting directly creates an enrollment THE SYSTEM SHALL store `action_class`, `work_scope`, `risk_ceiling`, `tenant`, `policy_actor_principal_id`, `enrolled_by_principal_id` and a mandatory `expires_at`. IF the caller is not `isHumanAdmin`, or `policy_actor_principal_id` passes `CheckHumanPrincipal`, THEN THE SYSTEM SHALL refuse.
- WHEN the evaluator is asked to authorize an action THE SYSTEM SHALL answer exactly one of: `allowed` (with enrollment id), `delegation_missing`, `delegation_expired`, `delegation_revoked`, `delegation_scope_mismatch` (action class, work scope, risk, or cross-tenant), or `policy_checkpoint_unavailable`.
- IF the enrollment store or the checkpoint attestation cannot be read THEN THE SYSTEM SHALL answer 503 `policy_checkpoint_unavailable`. A failed read SHALL never count as allowed.
- WHILE `MCTL_AUTONOMY_POLICY_MODE` is `off` or `advisory` (default `advisory`) THE SYSTEM SHALL record the evaluation outcome and SHALL answer `permitted: false` for every request.
- WHEN a policy-authorized decision is recorded on `POST /api/v1/decisions` with `authority_basis=autonomy-policy` THE SYSTEM SHALL require an empty `approval_id`, a non-human `actor` principal equal to the enrollment's policy actor, and a live enrollment reference. If any check fails it SHALL refuse with 422 `decision_invalid`.
- THE SYSTEM SHALL never let the autonomy-policy path decide, consume or execute an `aar_`, set `decided_by` / `approved_by`, or resolve a `wi_`/`xr_` on-behalf-of grant to the enrolling human.
- WHEN an enrollment is revoked or expires THE SYSTEM SHALL refuse every later evaluation that relies on it (`delegation_revoked` / `delegation_expired`), including a recheck immediately before the effect.
- WHEN an enrollment is downgraded (narrower scope or lower risk ceiling) THE SYSTEM SHALL record a new version and evaluate only against the newest version.

Hardening

- For each guard above (human-admin check, binding presence, approval-id equality, context-digest equality, content-digest equality, pre-signal recheck, non-human policy actor, empty approval_id on policy decisions), a mutation test SHALL remove the guard, and at least one test SHALL then fail.

## Out of scope

- Creating any enrollment, or switching `MCTL_AUTONOMY_POLICY_MODE=enforce` or `MCTL_APPROVAL_CARD_BINDING=require` in production. Activation is a separate, human-approved gitops change after mctl-gitops#1980 coverage is verified deployed.
- The Telegram/portal card rendering and deep-link UX (mctl-telegram, mctl-portal). This proposal only defines the API contract those cards must send.
- The mctl-agents-side checkpoint arm `execution_authorization=autonomy-policy` (mctl-agents#905) and the definite-outcome query on the worker (mctl-agents#773).
- Rollback of applied effects on cancel, and closing GitHub issues.
- New MCP tools for enrollment management. Enrollment is REST-only and admin-only in this slice.

## Open questions

- The reserved arm `execution_authorization=autonomy-policy` does not appear anywhere in this repo. The proposal assumes it is defined by mctl-agents#905 and that mctl-api only needs `authority_basis=autonomy-policy` on `dec_` records. Confirm the exact field name the checkpoint sends.
- How mctl-api learns that the gitops#1980 checkpoint is deployed and enabled is not specified. The proposal uses an explicit operator-set attestation (`MCTL_POLICY_CHECKPOINT_ATTESTED=<coverage file digest>`). Without it, `enforce` evaluates to `policy_checkpoint_unavailable`. A live read of `governance/policy-checkpoint-coverage.yaml` could replace this later.
- Missing binding uses 422 `approval_context_incomplete`, which reuses an observed code. The issue says only "missing binding refuses". Confirm that no new code is wanted here.
- The vocabulary for `action_class`, `work_scope` and `risk_ceiling` is not defined by the issue. The proposal uses operation-registry action kinds, `<repo>` or `<repo>#<issue>` globs, and `operations.RiskLevel` respectively.
- The date for flipping `MCTL_APPROVAL_CARD_BINDING` to `require`, and the date for removing the `legacy` mode, are left to the epic owner.
- The deployed mctl-api configuration (current values of `MCTL_AGENTS_APPROVE_LEGACY_APPROVER`, authz mode, replicas) could not be observed. See design.md.
