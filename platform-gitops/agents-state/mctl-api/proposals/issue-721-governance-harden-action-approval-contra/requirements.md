# Harden the action-approval governance contract after #700

## Context

mctl-api#700 (PR #717, docs follow-up #720) added the decision-context and
authority contract for action approvals (`aar_`): mandatory decision context,
`context_digest` binding, `fresh_until`, and execution-time revalidation in
`internal/governance.Revalidate`. The final review of that work found gaps
where the normative document, production configuration and edge-case semantics
can still drift from the intended governance boundary:

- `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` is off by default (`helm/values.yaml`),
  so an approval under an unregistered policy rule can be created, approved
  and spent in production.
- Create-time precedence is an accident of handler ordering: governance
  completeness (422) runs before the store's structural validation (400), and
  the idempotent replay lookup happens only after the retried body passes
  every check.
- The compatibility backfill in `actionApprovalSchema` rewrites every legacy
  row, including terminal history, never reconstructs `risk_level`, and has no
  measured pre-state or postcondition. `Revalidate` does not re-check context
  completeness, so a legacy approved row lacking `risk_level` could still be
  spent.
- Two clocks govern the lifecycle: the handler's `Options.Clock` (nil in
  production, falling back to `time.Now`) and `workitems.Store.now`
  (`time.Now().UTC()`, not injectable outside the package). The F4 stale test
  moves only the handler clock.

This proposal hardens the existing contract. It adds no new authorization,
policy or approval framework and leaves durable decision/execution-attempt
records to #701.

## User stories

- AS a platform operator I WANT production to refuse any approval whose policy
  identity/version is not registered SO THAT no side effect executes under a
  policy the server cannot revalidate.
- AS an operator rolling out strict policy I WANT a producer inventory,
  refusal observability and a one-variable rollback SO THAT enforcement does
  not silently break a legitimate producer.
- AS an API client author I WANT one documented, tested precedence between
  400, 422, 409 and replay outcomes SO THAT my retry logic is deterministic.
- AS a reviewer of governance evidence I WANT the legacy backfill to be a
  bounded, idempotent migration with a measurable postcondition SO THAT
  reconstructed rows are not an indefinite second source of truth.
- AS a security reviewer I WANT one injected clock to define decision time,
  freshness, expiry and revalidation SO THAT the authorization boundary cannot
  observe inconsistent times.

## Acceptance criteria (EARS)

### Registered policy invariant

- WHILE strict policy mode is enabled THE SYSTEM SHALL refuse to consume or
  grant-spend an approval whose `policy_rule_id` is not in the registered
  policy set, with `409 approval_policy_drift` and
  `details.reapproval_required=true`, without spending it.
- WHILE strict policy mode is enabled, WHEN a create request names an
  unregistered `policy_rule_id`, THE SYSTEM SHALL refuse it with
  `422 approval_policy_unregistered` and store nothing.
- WHILE strict policy mode is enabled, WHEN a create request names a
  registered rule at a version other than the registered one, THE SYSTEM
  SHALL refuse it with `409 approval_policy_drift` and store nothing.
- WHILE strict policy mode is enabled, WHEN a human approves a pending
  request under an unregistered rule or a superseded version, THE SYSTEM SHALL
  refuse the approve with the same typed code and leave the request pending.
- WHEN a registered policy's version changes after an approval was decided
  THE SYSTEM SHALL refuse the spend with `409 approval_policy_drift`,
  `reapproval_required=true`, in strict and non-strict mode alike.
- WHILE strict policy mode is disabled, WHEN an approval under an unregistered
  rule is created, decided or spent, THE SYSTEM SHALL record
  `policy_status=unregistered` (with action_kind, policy_rule_id,
  policy_version and requester) in the audit entry and a structured warning log.
- WHEN the API starts THE SYSTEM SHALL log the strict-policy mode and the
  registered policy rule ids and versions.

### Precedence contract

- WHEN a create request is malformed (undecodable, oversized, header/body
  idempotency key mismatch, field length/format/enum violation, or secret
  material in any field) THE SYSTEM SHALL answer a specific `400` refusal
  before any governance completeness or policy check.
- IF a structurally valid create request lacks mandatory decision context
  after registry and policy defaults THEN THE SYSTEM SHALL answer
  `422 approval_context_incomplete` with `details.missing_fields`.
- WHEN a structurally valid create request reuses an idempotency key whose
  stored request has the same canonical intent hash THE SYSTEM SHALL return
  that request with `200`, even if the retried body would now fail
  completeness, strict-policy or open-execution checks.
- WHEN a create request reuses an idempotency key whose stored request has a
  different intent hash THE SYSTEM SHALL answer
  `409 approval_idempotency_conflict`.
- WHEN a consume or grant spend targets a request that is not `approved`
  THE SYSTEM SHALL answer the state refusal (`approval_not_approved`,
  `approval_denied`, `approval_expired`, `approval_consumed`) and SHALL NOT
  answer an authority, policy, freshness or context code.
- IF any validation or revalidation step refuses a consume, decide or grant
  spend THEN THE SYSTEM SHALL leave the approval's stored state, `consumed_at`
  and `fresh_until` unchanged.

### Context completeness at spend

- IF an approved request's decision context is incomplete at spend time THEN
  THE SYSTEM SHALL refuse with `409 approval_context_incomplete` and
  `details.reapproval_required=true` without spending it.

### Legacy migration

- WHEN the store initializes THE SYSTEM SHALL log, per state, the count of
  rows that still need legacy governance reconstruction before mutating any.
- WHILE `ACTION_APPROVAL_LEGACY_BACKFILL=count` THE SYSTEM SHALL log the
  counts and mutate no row.
- THE SYSTEM SHALL restrict legacy backfill mutation to live rows (state
  `pending` or `approved` and `expires_at` in the future by the store clock).
- THE SYSTEM SHALL NOT reconstruct `risk_level`; for a registered action kind
  the live registry value applies, and for an unregistered one the row stays
  incomplete and cannot be approved or spent.
- WHEN the migration runs again THE SYSTEM SHALL change no row.
- WHEN the migration completes THE SYSTEM SHALL log the count of live rows
  with incomplete stored governance context; that count SHALL be reachable
  through a store method used by tests.

### One clock

- THE SYSTEM SHALL use one clock function, constructed in `cmd/api`, for the
  store's decision time, `fresh_until`, lazy expiry, consume compare-and-set,
  and the handler's revalidation `Now`.
- WHEN an F4 stale or expired test advances the injected clock THE SYSTEM
  SHALL refuse the spend through the same handler-to-store path production uses.

### Documentation

- THE SYSTEM SHALL keep `docs/decision-context-contract.md` and
  `internal/openapi/openapi.yaml` consistent with the precedence, strict-policy
  and spend-time completeness behaviour above.

## Out of scope

- Durable decision / execution-attempt history (#701).
- Reimplementing F3/F4/F6/F9 or replacing the authority/policy model.
- A policy engine, a database-backed policy registry, or a new approval service.
- Break-glass design.
- Audit/evidence redesign beyond the extra `policy_status` audit parameter.
- Rewriting terminal rows already touched by the #700 backfill.

## Open questions

- Which producers besides mctl-agents (DevLoop grant, `mctl-agents-approve`
  under `dev-loop.human-approval` v1) create action approvals in production,
  and under which rules? The in-repo test producer uses `merge-needs-human` v3
  (`github.merge_pr`), which is unregistered. The design gates the flip on an
  audit-based inventory and assumes any legitimate producer is registered in
  `governance.Policies` first.
- The deployed value of `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY` could not
  be observed: mctl-api is not in the mctl-gitops service catalogue checked by
  this run. The design assumes it is unset (off), matching `helm/values.yaml`.
- A new code, `approval_policy_unregistered`, is proposed for create-time
  refusal; the alternative is reusing `approval_policy_drift`. The proposal
  takes the distinct code because "never registered" and "moved on" call for
  different client actions.
- Whether strict mode should eventually stop being configurable (hard-coded
  on). The design keeps the variable as the rollback path.
