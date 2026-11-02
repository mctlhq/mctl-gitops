# Governance Slice 2: owner action semantics for request-changes, defer and request-cancel

## Context

mctlhq/mctl-api#869 (Slice 1) bound direct human approve/deny decisions to the
exact `aar_` grant and decision context the person was shown
(`internal/api/approval_binding.go`, `docs/decision-context-contract.md`).
Owner triage cards (rendered by mctlhq/mctl-agents#907) also offer three
controls that are not approval decisions: request changes, defer and request
cancel. Today mctl-api has no contract for them. The only nearby primitives
are the approve route (which decides an `aar_`), the abandon route
(`AbandonDevLoopWorkflow`, which ends a run but takes free-text `reason`, has
no idempotency key and admits any admin including the service principal) and
the human-input response route (information only). Without an explicit
contract a card control could be wired to the wrong primitive, for example a
"cancel" answer delivered as a human-input reply, or "request changes"
implemented as a denial.

This proposal adds one owner-action route per DevLoop with three action
kinds, each with defined authority, stale-card binding, idempotency and
privacy-safe outcomes. Approve and deny remain the only `aar_` decisions.
Request-cancel reuses the existing abandon signal path and reports whether
the cancellation is pending, whether the run is known stopped, or whether
already-started effects cannot be observed. Cancel means stop future work,
never rollback.

## User stories

- AS a human admin owning a DevLoop proposal I WANT to request changes
  without approving or denying the grant SO THAT the proposal can be reworked
  while the approval stays open.
- AS a human admin I WANT to defer my decision SO THAT the loop records that
  I saw the card and postponed action, without the grant being decided.
- AS a human admin I WANT to request cancellation of a DevLoop SO THAT no
  further work is started, and I am told honestly whether work already in
  flight has stopped or cannot yet be observed.
- AS the Telegram card renderer (mctl-agents#907) I WANT a stable action
  contract with typed outcome codes SO THAT I can render results without
  defining authorization myself.
- AS an auditor I WANT every owner action recorded with ids, codes and states
  only SO THAT I can reconstruct what happened without proposal text or
  owner free text in the log.

## Acceptance criteria (EARS)

Authority

- WHEN a caller posts to `POST /api/v1/agents/dev-loop/{workflow_id}/owner-actions`
  THE SYSTEM SHALL accept the request only if `isHumanAdmin(user)` is true,
  and otherwise SHALL answer 403 with code `owner_action_forbidden` and audit
  the refusal.
- IF the caller is relayed (`RelaySurface`), a surface token (`Surface`), or
  the service principal THEN THE SYSTEM SHALL refuse the owner action with
  403 and SHALL NOT signal, record or decide anything.
- THE SYSTEM SHALL NOT change `isHumanAdmin`, `CheckHumanPrincipal`, relay
  checks, on-behalf-of attribution or the authorization of the existing
  `/abandon`, `/approve` and `/human-input/{request_id}/response` routes.
- WHEN a human-input response is delivered through
  `POST /api/v1/human-input/{request_id}/response`, whatever its value, THE
  SYSTEM SHALL NOT call `SignalAbandon`, SHALL NOT create an owner action and
  SHALL NOT decide any `aar_`.

Non-decision of the grant

- WHEN an owner action of kind `request_changes` or `defer` succeeds THE
  SYSTEM SHALL leave the DevLoop's `mctl-agents-approve` grant in its prior
  state, SHALL NOT call `DecideActionApproval`, and SHALL NOT write
  `approved_by`/`decided_by` or any `aar_` outcome.
- WHEN an owner action of kind `request_cancel` succeeds THE SYSTEM SHALL NOT
  decide, deny, consume or expire the grant; the grant closes only through an
  existing lifecycle rule (expiry, or the worker's own handling of an
  abandoned run).
- IF the newest grant of the DevLoop execution is not `pending` THEN THE
  SYSTEM SHALL refuse `request_changes` and `defer` with 409 and the existing
  typed code for that state (`closedApprovalCodes`, or
  `approval_already_decided` for `approved`).
- IF the DevLoop has no grant to act on THEN THE SYSTEM SHALL refuse
  `request_changes` and `defer` with 409 `approval_grant_missing`.

Stale-card binding

- WHEN an owner action carries a `binding` THE SYSTEM SHALL validate it with
  the Slice 1 rules (`decisionBinding.missingFields`, `bindingMatches`) and,
  if `binding.approval_ref` is not the execution's newest grant or a digest
  differs, SHALL answer 409 `approval_context_changed` with
  `details.current_approval_ref` and SHALL record no action and send no
  signal.
- WHILE `MCTL_APPROVAL_BINDING=enforce` THE SYSTEM SHALL refuse an owner
  action without `binding` with 422 `approval_binding_missing`; WHILE it is
  `observe` THE SYSTEM SHALL accept it and audit `approval.binding_absent`
  with route `dev_loop_owner_action`.
- IF a `request_cancel` carries a binding and the DevLoop has no grant THEN
  THE SYSTEM SHALL answer 409 `approval_grant_missing`.

Cancellation semantics

- WHEN `request_cancel` targets a running execution THE SYSTEM SHALL describe
  the execution, signal abandon pinned to the described `run_id` through the
  same code path as `AbandonDevLoopWorkflow`, and record the run id.
- WHEN the abandon signal is delivered and the grant is `pending` or absent
  THE SYSTEM SHALL report `cancellation_pending`.
- WHEN the abandon signal is delivered and the grant is `approved`,
  `in_flight`, `consumed` or `executed` THE SYSTEM SHALL report
  `cancellation_effects_unknown`, because the implement step may already have
  produced effects.
- WHEN the execution has already finished with an `abandoned: ` result and
  did not reach implement THE SYSTEM SHALL report `cancelled` (known stopped).
- WHEN the execution has already finished with an `abandoned: ` result and
  did reach implement THE SYSTEM SHALL report `cancellation_effects_unknown`.
- WHEN the execution has already finished without an abandon result THE
  SYSTEM SHALL report `already_finished` and send no signal.
- IF the abandon signal fails with a transport or availability error THEN THE
  SYSTEM SHALL answer 502/503, keep the owner action in state `requested`
  with no outcome, and SHALL let a replay with the same idempotency key retry
  the signal to the same `run_id`.
- IF the described run ended and a new run took the workflow id between
  describe and signal THEN THE SYSTEM SHALL answer 409 `cancellation_run_changed`
  and SHALL NOT signal the new run.
- THE SYSTEM SHALL NEVER start, restart or terminate a workflow, or roll back
  any effect, on the owner-action path.
- WHEN `GET /api/v1/agents/dev-loop/{workflow_id}/owner-actions/{id}` is
  called for a cancel THE SYSTEM SHALL re-observe the run and report the
  current outcome (`cancellation_pending` may become `cancelled` or
  `cancellation_effects_unknown`), without sending any signal.

Idempotency

- WHEN a request repeats an `idempotency_key` already used by the same
  principal with identical content THE SYSTEM SHALL return the original
  owner action with `replayed: true` and perform no new signal or write
  other than the retry case above.
- IF the same principal reuses an `idempotency_key` with different content
  THEN THE SYSTEM SHALL answer 409 `owner_action_idempotency_conflict`.
- WHEN a `request_cancel` targets a run that already has a recorded cancel,
  under any key or principal, THE SYSTEM SHALL return that existing action
  with `replayed: true` and SHALL NOT signal again.
- WHEN a `request_changes` or `defer` targets a grant that already has an open
  action of the same kind THE SYSTEM SHALL return the existing action with
  `replayed: true`.

Privacy

- THE SYSTEM SHALL accept no free-text field on the owner-action route; the
  body carries `action`, `idempotency_key`, optional `binding` and optional
  `reason_code` matching `^[a-z0-9._:-]{1,64}$`; unknown fields are refused.
- THE SYSTEM SHALL write only ids, digests, codes and states into the owner
  action row, the abandon signal payload and the audit log, never proposal
  text or owner free text.

## Out of scope

- Stale-card approval binding itself (mctlhq/mctl-api#869, Slice 1); this
  proposal only reuses it.
- Delegation enrollment and policy evaluation (Slice 3).
- Telegram card rendering and notification (mctlhq/mctl-agents#907).
- Rollback or reversal of already-applied effects (branches, PRs, merges).
- Delivering request-changes feedback text to the investigator; changes are
  still made by editing proposal files through a PR, as today.
- A DevLoop-side Temporal signal for request-changes or defer (needs an
  mctl-agents workflow change).
- New MCP tools; this slice is REST plus OpenAPI only.
- Changing the authorization of the existing `/abandon` route.

## Open questions

- Should `request_changes` and `defer` signal the DevLoop (a new Temporal
  signal in mctl-agents) or remain durable records read by the card renderer
  and the shepherd? This proposal records them only; a signal can be added
  later without changing the contract.
- Should `restartIfAbandoned` refuse to restart a run cancelled through an
  owner action when someone later calls `/agents/dev-loop/start` for the same
  issue? This proposal leaves restart behaviour unchanged (an explicit start
  is a separate admin act) and records the cancelling `oa_` id in the
  abandon reason so a later change can detect it.
- Should a relayed human (Telegram) be allowed `defer` and `request_changes`,
  given they decide nothing? This proposal requires a direct human admin for
  all three, matching the issue's invariant that a relay gains no authority;
  relaxing it would be a separate decision.
- Does `defer` need an explicit `until` time? This proposal records defer
  without a deadline; the grant's own `expires_at` still applies.
- How mctlhq/mctl-agents#773 should surface `approval_context_changed` on an
  owner-action refusal; this proposal returns the same details as the approve
  route so one renderer can handle both.
