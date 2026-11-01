# Design: issue-869-feat-governance-bind-direct-human-decisi

## Current state

Direct human decisions

- `internal/api/handlers_action_approvals.go` contains three pieces:
  - `isHumanAdmin(u)` is `IsAdmin && !IsService && !relayed && !surface`.
  - `DecideActionApproval` refuses any other caller with 403 `approval_decider_forbidden`. It then validates the input (`workitems.ValidateDecisionInput` accepts only `approve`/`deny`), pre-reads the grant and calls `guardDecision`.
  - `actionDecisionBody.ContextDigest` is `omitempty`.
- `internal/api/handlers_approval_governance.go` `guardDecision`:
  - admits the policy (`approvalPolicies().Admit`) and requires `DecisionContext.ContextComplete`;
  - compares the digest only `if sentDigest != ""`, so an empty digest is accepted. The live digest is then recorded (`decisionCapture` sets `ContextDigest`, `AuthorityBasis=governance.AuthorityBasisPlatformAdmin`, `FreshFor`).
- `internal/api/handlers_dev_loop.go` `ApproveDevLoopWorkflow`:
  - goes through `requireTemporalAdmin` (`IsAdmin` only) and then `isHumanAdmin`;
  - `refuseIdentityFields`, then decodes `approveDevLoopRequest{Approver, Reason}` (unknown fields tolerated).
  - `decideDevLoopApproval` resolves the single open `we_` execution via `OpenExecutionsOfEngineRun`. It lists `ActionApprovals{ExecutionID, ActionKind: "mctl-agents-approve", Limit: 1}` and acts on `list[0]` ("newest grant decides"). A pending grant is approved with `guardDecision(..., "")`, which means no digest binding at all. An approved grant is re-sent. Other states return `closedApprovalCodes`.
  - With no grant and `LegacyApproverDisabled=false` (`MCTL_AGENTS_APPROVE_LEGACY_APPROVER`, `cmd/api/main.go` `parseLegacyApprover`), the legacy `approver` payload is signalled.
  - After a decide, `TemporalClient.SignalApprove` runs with no re-read of the grant.
- `internal/api/handlers_approval_grant.go`: the grant's `artifact_hash` is the proposal content digest (mctl-agents#681), passed through as `expected_content_digest`. `approval_content_unbound` already refuses a DevLoop grant with no content binding at spend time.
- The governance codes already exist and are mapped in `actionApprovalRefusals`: `approval_context_changed` (409, reapproval), `approval_context_incomplete`, `approval_stale`, `approval_authority_revoked`, `approval_authority_unavailable`, `approval_policy_drift`, `approval_policy_unavailable`. `governance.Revalidate` rechecks authority and policy before a spend.

Abandon

- `AbandonDevLoopWorkflow` (`handlers_dev_loop.go`) goes through `requireTemporalAdmin` (any admin, including the service principal; there is no relay check). It describes the execution, then signals the run it observed, and answers `signalled` or `already_finished`. It reports nothing about effects.

Decisions and delegation

- `internal/decisions` holds the immutable `dec_` record (mctl-api#701): verdict, code, policy_version, rule_id, actor, principal_id, tenant, approval_id, authority_basis and action digests. It also holds the append-only attempt events. `Record` checks the `aar_` binding (`checkApprovalBinding`) and is idempotent by `(recorded_by, idempotency_key)`. `POST /api/v1/decisions` (`handlers_decisions.go` `RecordDecision`) needs `PermissionEvidenceWrite`. Neither `authority_basis` nor the actor kind is validated against anything.
- The name `internal/delegation` is already taken: it resolves `X-MCTL-On-Behalf-Of` refs (`xr_`, `aar_`, `wi_`, `sil_`) to stored subjects. It is not an enrollment store. The new store therefore needs a different name so the two concepts cannot be confused.
- `auth.PrincipalChecker.CheckHumanPrincipal` (`internal/auth/principal.go`) is already used by `handlers_surface_identity.go`.
- Nothing in the repo mentions `execution_authorization` or `autonomy-policy`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/` was listed. The tenants present are `admins`, `karabu`, `labs` and `namax66`. `services/admins/` contains `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement`, but no `mctl-api` service directory. mctl-api's deployed values (current `MCTL_AGENTS_APPROVE_LEGACY_APPROVER`, `TenantAuthzMode`, `RequireRegisteredPolicy`, replicas) were therefore not observed. A recursive grep of `$MCTL_GITOPS_ROOT` for those env names found them only in earlier proposals under `agents-state/mctl-api/proposals/`, not in deployed config.
- `$MCTL_GITOPS_ROOT/governance/policy-checkpoint-coverage.yaml` was read. Its header shows schema `mctl-policy-coverage/v1`, `approvals_backend: mctl-api`, `min_approvals_version: 1.86.1`, and surfaces with `governed`/`rollout: staged` markers. This is the declared coverage, not proof that the checkpoint is enabled at runtime (the issue's gitops#1980 caveat).
- The mctl MCP tools were not called. The repo and gitops reads above were enough for the API contract, and the deployed mctl-api config gap is recorded under Open questions.

## Proposed solution

### 1. Card binding on direct decisions (both routes)

Add a shared type to `internal/api/handlers_approval_governance.go`:

```go
type cardBinding struct {
    ApprovalID    string `json:"approval_id"`
    ContextDigest string `json:"context_digest"`
    ContentDigest string `json:"content_digest"`
}
```

Add `CardBinding *cardBinding \`json:"card_binding,omitempty"\`` to both `actionDecisionBody` and `approveDevLoopRequest`. The existing top-level `context_digest` on the decision route keeps today's semantics for legacy callers only.

Add `checkCardBinding(w, r, user, a, b *cardBinding) (digest string, ok bool)`, called from `guardDecision` in place of the `sentDigest` comparison. It applies only to an approve, because deny stays ungated, which is today's behaviour. The checks run in this order:

1. `b == nil`:
   - in mode `require`, refuse 422 `approval_context_incomplete` with `missing_fields=[card_binding]`;
   - in mode `legacy`, fall back to the current `sentDigest` rule and mark the audit entry `binding=legacy`.
2. Any empty field: 422 `approval_context_incomplete` with the missing names. An empty field is never a bypass, in any mode.
3. `b.ApprovalID != a.ID`: 409 `approval_context_changed`.
4. `b.ContextDigest != DecisionContextOf(a).ContextDigest`: 409 `approval_context_changed`.
5. `b.ContentDigest != a.ArtifactHash`:
   - if `a.ArtifactHash == ""` on the DevLoop kind, refuse `approval_content_unbound`;
   - otherwise 409 `approval_context_changed`.

The new mode lives in `Options.ApprovalCardBinding`, read from `MCTL_APPROVAL_CARD_BINDING` (`legacy` | `require`, default `legacy`) in `cmd/api/main.go`. It follows the same parse-or-fail-at-startup pattern as `parseLegacyApprover`. This is the explicit legacy migration: `legacy` is today's behaviour plus an audit marker, and `require` removes all unbound approves. Neither mode admits a half-filled binding.

DevLoop route (`decideDevLoopApproval`):

- When a binding is present, the handler still reads the newest grant (`Limit: 1`), but compares `newest.ID` with `b.ApprovalID` first. A mismatch is 409 `approval_context_changed` with `details: {reapproval_required: true, current_approval_id: newest.ID}`. The newest grant is never substituted.
- An `approved` newest grant with a matching binding is a replay. The handler returns its id and re-signals, which keeps the lost-signal retry.
- In `require` mode the legacy no-grant `approver` payload is refused, because a bound approve must name a grant (`approval_grant_missing`).

Pre-effect recheck. Between the decide and `SignalApprove`, `ApproveDevLoopWorkflow` re-reads the grant (`WorkItems.ActionApproval`). It asserts `state==approved`, the same id, `DecidedContextDigest == b.ContextDigest` and `ArtifactHash == b.ContentDigest`. It also calls the existing `revalidateApproval`, which covers authority revoked, stale and policy drift. On failure nothing is signalled and the governance code is returned.

Definite outcome. The success body gains `approval_id` and `decision_outcome` (`decided_and_signalled` | `replayed_signalled`). A signal failure after the decide answers 502/503 with `decision_outcome: "decided_not_signalled"` and `approval_id`, so the caller (and mctl-agents#773) can retry with the same binding or query `GET /api/v1/action-approvals/{id}` instead of guessing.

Duplicate requests. Today, `DecideActionApproval` on an already approved grant whose decider, binding and `DecidedContextDigest` all match the request answers `approval_already_decided`. The change makes it return 200 with the existing approval and `replayed: true`. A different decider or binding still gets `approval_already_decided`. The store's single-transition decide continues to guarantee one decision.

Authority is unchanged. `isHumanAdmin` stays the first check on both routes, before the body is decoded. No relay or surface allowance is added.

### 2. Action semantics

- `ValidateDecisionInput` already restricts decisions to approve/deny. The change adds tests that pin this for `request_changes`, `defer` and `cancel`, plus a code comment saying these are information/workflow requests and not `aar_` decisions.
- Human input. A test asserts that `RespondHumanInput` leaves every `aar_` of the execution `pending`.
- Abandon. A new `isRelayedOrSurface(user)` check refuses relayed and surface callers with 403 `abandon_forbidden_relay`. This only narrows the route. A direct human admin and the direct service principal keep access, as today. The success body gains:

```json
"effects": {"status": "cancellation_pending|recorded|cancellation_effects_unknown",
            "pending": ["aar_..."], "in_flight": ["aar_..."], "applied": ["aar_..."]}
```

  The block is built from `OpenExecutionsOfEngineRun` + `ActionApprovals{ExecutionID}` grouped by state (`pending`; `in_flight`; `consumed`/`executed` as applied). `cancellation_pending` is used while outcome=`signalled`. `cancellation_effects_unknown` is used when the work-item store is nil or the read fails; that read never fails the abandon itself, because the signal already went out. Abandon never denies an `aar_`, rolls back an effect, or touches the GitHub issue.

### 3. Autonomy policy: enrollment store and evaluator (new, `internal/autonomy`)

The package is named `autonomy` so it does not collide with `internal/delegation`, which is on-behalf-of resolution. It is a Postgres store in the same style as `internal/decisions` (`NewStore(ctx, connStr)`, `CREATE TABLE IF NOT EXISTS`):

```
autonomy_enrollments(
  id text PK ('aen_'), version int, tenant text, action_class text,
  work_scope text, risk_ceiling text, policy_actor_principal_id text,
  enrolled_by_principal_id text, created_at, expires_at NOT NULL,
  revoked_at NULL, revoked_by_principal_id NULL, supersedes_version int NULL,
  idempotency_key text, UNIQUE(id, version))
```

Rows are append-only. A downgrade inserts version+1, and a revoke inserts a tombstone version. Evaluation reads only the highest version.

`Evaluator.Evaluate(ctx, Request{Tenant, ActionKind, Target, Risk, ActorPrincipalID}) (Outcome, error)` checks, in order:

1. checkpoint attested;
2. enrollment found;
3. not revoked;
4. not expired;
5. tenant equal;
6. action class equal;
7. target matches work scope;
8. risk at or below the ceiling;
9. actor equals the policy actor.

The outcomes are `allowed` (with `enrollment_id@version`), `delegation_missing`, `delegation_revoked`, `delegation_expired`, `delegation_scope_mismatch` and `policy_checkpoint_unavailable`. A store error is `policy_checkpoint_unavailable` (503) and never `missing`. `Outcome.Permitted` is true only when the mode is `enforce`, the outcome is `allowed`, and `MCTL_POLICY_CHECKPOINT_ATTESTED` is set. The default `advisory` mode answers `permitted:false` with the outcome it would have given.

REST endpoints, added in `router.go` in the write group:

- `POST /api/v1/autonomy/enrollments`, `POST /api/v1/autonomy/enrollments/{id}/revoke`, `POST /api/v1/autonomy/enrollments/{id}/downgrade`: `isHumanAdmin` only. Create also requires that `CheckHumanPrincipal(policy_actor_principal_id)` returns *not human*, and that `expires_at` is in the future and within `MCTL_AUTONOMY_MAX_TTL` (default 30d).
- `GET /api/v1/autonomy/enrollments`: admin read.
- `POST /api/v1/autonomy/evaluate`: direct service or policy principal. It is read-only apart from an audit entry, and it is idempotent.

`dec_` attribution. Add `AuthorityBasisAutonomyPolicy = "autonomy-policy"` to `internal/governance`. Extend `decisions.DecisionInput.validate` and `RecordDecision` so that `authority_basis=autonomy-policy` requires:

- `ApprovalID == ""` (never an `aar_`);
- `PrincipalID` equal to the enrollment's policy actor and not human (`CheckHumanPrincipal`);
- a `policy_reasons` entry `enrollment:aen_...@v` that the evaluator re-resolves as live at record time.

Separation guards:

- `DecideActionApproval`, `ConsumeActionApproval` and `MarkActionApprovalExecuted` refuse any caller whose principal is an active policy actor, with 403 `approval_decider_forbidden`. This covers the case where an operator mis-grants the policy actor a role.
- `internal/delegation`'s `StoreResolver` is not changed, so a policy actor has no path to an on-behalf-of subject.
- `requires_human_approval` is satisfied only by an `aar_` decided through `isHumanAdmin`, which is unchanged.

### 4. MCP

`mctl_approve_dev_loop` (`internal/mcp/server.go`) gains three optional string args, `approval_id`, `context_digest` and `content_digest`. When any of them is given, the tool sends all three as `card_binding`. The tool description documents the 409/422 codes. No MCP tools are added or removed, so the `server_test.go` count is unchanged.

## Alternatives

- **Always bind to the newest grant, but compare digests only.** Dropped. The issue explicitly forbids substituting the newest grant, and two grants can share a context digest while differing in content or id.
- **Make binding mandatory immediately (no `legacy` mode).** Dropped. It would break the current MCP, portal and Telegram callers that send no binding. The explicit two-value mode with a startup parse gives a visible migration, and it still never admits a half-filled binding.
- **Store autonomy enrollments as a special `aar_` kind or an auto-approved grant.** Dropped. It would let policy authority write `decided_by`/`approved_by` and satisfy `requires_human_approval`, which is exactly what the issue's authority invariants forbid. Reusing `dec_` for the effect record and keeping enrollment as a separate store keeps human and policy authority in disjoint structures.
- **Extend `internal/delegation` with enrollments.** Dropped. That package is on-behalf-of subject resolution. Mixing the two would let an enrollment look like a delegation of a human's identity.

## Platform impact

- **Migrations.** One new table, `autonomy_enrollments`, is created idempotently at startup. There are no changes to existing tables. New `dec_` validation applies only to `authority_basis=autonomy-policy`, which no current writer sends.
- **Backward compatibility.** The default `MCTL_APPROVAL_CARD_BINDING=legacy` keeps every current call working. Responses are additive (`approval_id`, `decision_outcome`, `effects`, `replayed`). Two behaviour changes are intentional: a relayed or surface caller on `/abandon` now gets 403, and a matching duplicate decision now answers 200 replayed instead of 409.
- **Resources.** There is one extra grant read before each DevLoop signal and one list query per abandon. Both are negligible.
- **Risks and mitigations.**
  - Card clients send a wrong digest, so every approve answers 409. The digest is exactly `decision_context.context_digest` from GET, and contract tests pin this.
  - The policy path becomes a silent bypass. Mitigations: default advisory, enforce gated on an explicit checkpoint attestation, guards against human actors and `aar_` use, and mutation tests.
  - The relay refusal on abandon breaks a caller. The deployed caller list was not observable; record the refusal in audit and confirm with the mctl-telegram owners before release.
- **Activation.** No enrollment is created and neither flag is flipped by this work. Activation is a separate human-approved gitops change after gitops#1980 is verified deployed.
