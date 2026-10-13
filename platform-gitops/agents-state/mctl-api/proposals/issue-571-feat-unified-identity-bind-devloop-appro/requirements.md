# Requirements: issue-571 — bind DevLoop approvals to canonical principals (#376 Slice C)

Source: mctlhq/mctl-api#571 (parent mctlhq/mctl-api#376, epic
mctlhq/.github#91); counterpart mctlhq/mctl-agents#636. Hand-written
proposal (Claude Code session for the owner), not an issue-investigator
run. It narrows the accepted #376 design (`issue-376-…/design.md` §5) to
what the code on mctl-api `main` at `548a541` actually needs, and records
the owner's five decisions of 2026-10-13. Line references must be re-read
before editing.

## Context

Slices A and B of #376 are on `main`: agent run tokens (`art_`, minted by
`MintAgentRunToken`, `isDirectService` only, bound to a `we_` execution and
its work item), the delegation gate (`agentPrincipalGate`,
`handlers_agent_identity.go`), `internal/delegation` grants (`xr_`, `aar_`,
`wi_`, surface links) bound by execution or work item
(`delegation.go:196-199`), and Slice D's `GET /api/v1/identity/self`.

What is left is the DevLoop approval itself. Today:

- the Temporal worker submits `mctl-agents-approve` with the static
  `mctl-agent` service token and relays the human as free text in
  `input["approver"]` (`handlers_write.go:208-252`, service principals
  only);
- the operation is `AdminOnly`, `MinRole: admin` (`registry.go:923-935`), so
  a run token — never admin — cannot call it, and a delegated subject has
  `admins` dropped;
- the delegation allowlist (`handlers_agent_identity.go:95-106`) has no
  operation route;
- the #376 design put the Temporal workflow id in `aar_.execution_id`, but
  the gate binds a grant only to the run's `we_` or work item, so such a
  grant would always be `grant_not_bound`;
- the gate accepts only a `github:` subject (`handlers_agent_identity.go:190-195`),
  which refuses every ZITADEL-only approver once GitHub sign-in is retired
  (mctlhq/mctl-api#525).

Nothing here adds an IdP, a membership authority, a grant model or an audit
trail: the grant is the existing `ActionApprovalRequest`, the actor is the
existing run token, the subject is the existing `prn_`.

## Owner decisions (2026-10-13)

- D1. A run token may complete `mctl-agents-approve` only through an
  explicit `action_approval` grant (`aar_`) that a human admin decided. The
  admin gate stays on the human decision, not on the agent.
- D2. The delegation allowlist grows only by the routes mctl-agents#636
  actually calls (narrow method + path).
- D3. The `we_` execution id is canonical; the Temporal workflow id is an
  attribute (the execution's `engine_ref`: the workflow id, or
  `<workflow_id>#<request_id>` for a run dispatched from an execution
  request, mctl-agents#461).
- D4. Minting run tokens and creating `aar_` keep requiring the static
  service token in Slice C; replacing that credential is separate work.
- D5. The approval subject is the canonical `prn_`, not a `github:` login.
- D6. Every DevLoop has a canonical `we_`: issue → work item → `we_`
  execution (`engine=temporal`, `engine_ref=<workflow_id>`). The work item
  linked to the GitHub issue is reused, or created idempotently through the
  existing route and linked to that issue; no synthetic or unlinked work
  item is ever created. (Was open question Q1.) The link is the work item's
  `external_key` = the issue URL, which the create route already dedupes
  on; this replaced a surface-ref lookup route on 2026-10-13, before any
  implementation.

## Requirements (EARS)

### Canonical execution (D6)

- R0. WHEN a DevLoop was dispatched from an execution request THE worker
  SHALL use the `we_` the dispatcher fulfilled that request with
  (`engine_ref = <workflow_id>#<request_id>`) and SHALL NOT create a work
  item or attach another execution; R0a-R0b apply to every other start.
- R0a. WHEN a DevLoop starts THE worker SHALL obtain its issue's work item
  through `POST /api/v1/work-items` with `external_key` =
  `https://github.com/<owner>/<repo>/issues/<number>` (owner and repo
  lowercased, number in decimal without leading zeros) and an idempotency key
  derived only from that issue ref, in the tenant mapped from the target
  service; the route returns the existing open item for that
  `(tenant, external_key)` instead of a second one.
- R0b. THE worker SHALL then attach its execution through
  `POST /api/v1/work-items/{id}/executions` with `engine=temporal`,
  `engine_ref=<workflow_id>` (idempotent on that triple), so a restarted or
  retried DevLoop gets the same work item and the same `we_`, never a
  duplicate.
- R0c. A create error, `409 external_key_in_use` included, SHALL fail the
  DevLoop start; THE worker SHALL NOT retry with another `external_key`,
  another idempotency key or another tenant.
- R0d. A DevLoop that cannot obtain a `we_` SHALL stop before its approval
  gate with a typed error; it SHALL NOT run without one, and SHALL NOT
  create a work item that is not linked to its issue.

### Grant shape (D3)

- R1. WHEN the DevLoop reaches its approval gate THE worker SHALL create the
  `aar_` with `execution_id` = the run's `we_` (R0 or R0b),
  `action_kind` = `mctl-agents-approve`, `target` = `<service>/<slug>`,
  `policy_rule_id` = `dev-loop.human-approval`, `policy_version` = `v1`.
- R2. THE SYSTEM SHALL refuse to create a DevLoop `aar_` whose
  `execution_id` is not an existing, non-terminal `we_` (no free-form
  workflow ids, no `we_` check bypass).
- R3. WHEN a human admin approves through
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` THE SYSTEM SHALL
  resolve `workflow_id` to its one open `we_` (non-terminal, `engine`
  `temporal`, `engine_ref` equal to `workflow_id` or starting with
  `<workflow_id>#`), refuse more than one with 409 `execution_ambiguous`,
  decide the pending `aar_` for that `we_` and
  action kind through the existing `DecideActionApproval` rules, and
  signal `{approval_ref: "aar_…"}`; IF no such `we_` or pending `aar_`
  exists THEN it SHALL keep today's behaviour (legacy relay) while the
  legacy flag is on, and refuse with 409 `approval_grant_missing` when it
  is off.
- R4. THE DevLoop approve route SHALL accept only a human admin
  (`isHumanAdmin`), so a service or agent principal can never perform the
  human act. `requireTemporalAdmin` itself is unchanged: the shepherd reads
  `GET /api/v1/agents/dev-loop/{workflow_id}` with the service token.

### Exercising the grant (D1, D2)

- R5. THE delegation allowlist SHALL gain exactly
  `POST ^/api/v1/operations/mctl-agents-approve/execute$`. No dev-loop route
  is added: the worker receives the approve signal, it never calls
  `/agents/dev-loop/*`. Any further route needs its own amendment.
- R6. WHEN an agent run presents `X-MCTL-On-Behalf-Of: aar_…` on that route
  THE SYSTEM SHALL authorize `mctl-agents-approve` from the grant and not
  from the caller's admin status: the `aar_` must be bound to the run's
  `we_` (existing `grant_not_bound`), have `action_kind`
  `mctl-agents-approve`, a `target` equal to the request's
  `<service>/<slug>`, and be consumed by the existing intent-hash CAS
  (`ConsumeActionApproval`) before the operation is submitted. Expired,
  denied, pending, consumed, unbound or mismatched grants SHALL refuse with
  the existing typed codes and submit nothing.
- R7. THE SYSTEM SHALL keep refusing `mctl-agents-approve` to an agent run
  without a grant, to a delegated subject on any other grant kind, and to a
  non-admin human, exactly as today.
- R8. THE recorded approver SHALL be taken from the consumed grant
  (`decided_by`, `decided_by_principal_id`), never from the request body;
  an `approver` field in the body of a grant-authorized call SHALL be
  refused (400), like `forbiddenIdentityFields`.

### Subject (D5)

- R9. THE delegation gate SHALL derive the subject from the grant's
  `SubjectPrincipalID` (`prn_`) through the principal store, for every IdP
  (GitHub, ZITADEL), and SHALL NOT require a `github:` subject. A grant
  without a `SubjectPrincipalID`, or whose principal is disabled or
  unresolvable, SHALL refuse (`grant_subject_unresolved` / 503 on a store
  outage), never fall back to the login string.

### Credentials (D4)

- R10. `MintAgentRunToken` and `CreateActionApproval` SHALL keep their
  `isDirectService` gate unchanged in this slice.

### Legacy relay and its retirement

- R11. `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` SHALL default to `true`; WHILE
  it is true the service-principal relay of `input["approver"]` keeps
  working and every use SHALL write exactly one `approver.legacy_relay`
  audit entry (approver string, calling principal, operation, service,
  slug).
- R12. WHEN the flag is `false` THE SYSTEM SHALL refuse any
  `mctl-agents-approve` call that carries a free-text `approver` from a
  service principal (400 `legacy_approver_disabled`, audited) and SHALL
  accept the approval only through R6.
- R13. A mutation pin SHALL prove R12: with the refusal removed, the
  flag-off test fails.

## Acceptance (from #571 and #636, made testable)

- A1. A human decision is exercised by the bound agent execution through its
  `aar_`, and the recorded approval names the human's `prn_` as subject and
  the agent run (`agent:<name>`, `art_`, `we_`) as actor.
- A2. Another execution or work item presenting the same `aar_` is refused
  (`grant_not_bound`); a second use is refused (consumed).
- A3. An audit-row id, a workflow id or an arbitrary string as
  `approval_ref` is refused.
- A4. Expired, denied, pending and unresolved-subject grants fail closed
  and submit nothing.
- A5. With the flag on, the legacy relay keeps working and writes exactly
  one `approver.legacy_relay` per use; with it off, the free-text path is
  refused (R12, R13).
- A6. A ZITADEL-only human (no GitHub identity) can approve end to end.
- A7. Live: a natural DevLoop approval after mctl-agents#636 ships records
  actor and subject separately, and zero `approver.legacy_relay` entries
  appear over a full DevLoop cycle (the Saturday cron plus one
  issue-triggered loop) before the flag is turned off.

## Out of scope

- Replacing the static service token for minting and `aar_` creation (D4).
- Any other operation becoming grant-authorizable.
- Authorization of tenants by principal (#377).
