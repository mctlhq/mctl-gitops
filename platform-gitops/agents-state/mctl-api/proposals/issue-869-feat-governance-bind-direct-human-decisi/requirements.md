# Governance, Slice 1: bind direct human decisions to the exact grant and context shown

## Scope decision

mctl-api#869 holds three pieces of work with different dependencies. The lesson of #895 (a full-scope proposal failed with `no-commits`, the narrowed one shipped) applies, so the issue is split and **this proposal authorizes Slice 1 only**:

- **Slice 1 (this issue, mctl-api#869):** stale-card protection. A direct human decision from a card must carry the exact `aar_` id and `context_digest` the human was shown, plus the proposal content binding. Both decision routes. Observe/enforce rollout for legacy callers.
- **Slice 2 (new issue):** action semantics. Cancel maps to the authorized abandon handler with recorded effects; request-changes and defer are workflow requests, never `aar_` decisions.
- **Slice 3 (new issue, blocked on mctl-gitops#1980):** delegation enrollment store and policy evaluator for the `autonomy-policy` arm, observe mode only until the checkpoint is verified live.

Slices 2 and 3 are out of scope and must not be implemented in this run.

## Context

`POST /api/v1/action-approvals/{id}/decision` takes an optional `context_digest`; empty means no check (`guardDecision`: `sentDigest != "" && sentDigest != c.ContextDigest`). `POST /api/v1/agents/dev-loop/{workflow_id}/approve` takes no binding at all: `decideDevLoopApproval` decides the execution's newest grant and passes `""` as the digest. A card rendered for grant A, shown to a person, and sent after the proposal was amended and grant B superseded A, therefore approves B. The person never saw B.

## Acceptance criteria (EARS)

Binding object

- THE SYSTEM SHALL accept an optional `binding` object on both routes: `{approval_ref, context_digest, content_digest}`. `approval_ref` is an `aar_` id, `context_digest` is the value of `decision_context.context_digest` at render time, `content_digest` is the `artifact_hash` (the proposal content digest) at render time.
- WHEN `binding` is present THE SYSTEM SHALL require all three fields; a missing or malformed field is refused with 422 `approval_binding_missing` (`details.missing_fields`) and nothing is decided.
- WHEN `binding` is present on the DevLoop approve route THE SYSTEM SHALL decide only the grant named by `approval_ref`. IF the execution's newest grant has another id THEN 409 `approval_context_changed` with `details.current_approval_ref` and `details.reapproval_required=true`. It SHALL NEVER substitute the newest grant.
- WHEN `binding` is present THE SYSTEM SHALL compare `context_digest` with the grant's current decision context and `content_digest` with its `artifact_hash`; any difference is 409 `approval_context_changed`, and the grant stays pending.
- IF the named grant is already approved by the same binding THEN THE SYSTEM SHALL return the existing decision and create no second one. A duplicate request produces exactly one decision.
- IF the named grant is denied, consumed, executed, in flight or expired THEN THE SYSTEM SHALL refuse with that state's existing code, as today.

Legacy callers and rollout

- THE SYSTEM SHALL add `MCTL_APPROVAL_BINDING` with values `off`, `observe` (default) and `enforce`, following `MCTL_AGENT_RECEIPT_GATE`. An unknown value fails startup.
- WHILE the mode is `observe` THE SYSTEM SHALL accept a decision without `binding`, and record an audit entry `approval.binding_absent` and a counter per route.
- WHILE the mode is `enforce` THE SYSTEM SHALL refuse a decision without `binding` with 422 `approval_binding_missing`. There is no optional-empty path in `enforce`.
- THE SYSTEM SHALL NOT switch the mode to `enforce` in this run. The flip is a separate gitops change with owner approval.
- The top-level `context_digest` field of the action-approval route keeps working as a legacy alias in `off` and `observe`; in `enforce` it no longer substitutes for `binding`.

Authority, unchanged

- THE SYSTEM SHALL keep `isHumanAdmin` as the only gate on both routes. A relay, service or policy principal still gets 403 `approval_decider_forbidden`, with or without `binding`. No code path in this slice widens `isHumanAdmin`, `CheckHumanPrincipal` or the relay checks.
- A body that names who acted is still refused (`refuseIdentityFields`).

Audit and privacy

- Every refusal is audited with its code. Audit entries and responses carry ids, digests and codes only: no args, no free-text reason, no proposal text.

Docs and schema

- THE SYSTEM SHALL update `internal/openapi/openapi.yaml`, `docs/decision-context-contract.md` (new codes, migration, precedence) and the MCP tool schemas that wrap the two routes, adding `binding` as optional.

Tests (mutation-verified)

- Each guard above SHALL have a test that fails when the guard is removed. Each mutation and its result is recorded in the PR description.

## Out of scope

Cancel/abandon semantics, request-changes, defer, enrollment, policy evaluation, the `delegation_*`, `policy_checkpoint_unavailable`, `cancellation_*` codes, the Telegram/agents card, any change to mctl-agents, any gitops change, and the `enforce` flip.
