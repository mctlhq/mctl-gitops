# Authority and decision-context contract with execution-time revalidation for action approvals

## Context

mctl-api already has the pieces of a governed decision: canonical principals
(`prn_`, `internal/principals`), principal-mode platform admin
(`ADMIN_PRINCIPALS`, `internal/auth/principal_authz.go`), tenant roles
(`docs/tenant-roles.md`), and single-use action approvals (`aar_`,
`internal/workitems/action_approvals.go`) that bind an exact intent hash over
execution, action kind, target, args digest, policy rule id/version, artifact
hash and work item. What is missing is one explicit contract that says which
of these facts make up the decision context, which authority evidence is
captured when a human decides, and which facts are checked again before the
side effect. Today `ConsumeActionApproval` checks only state, intent hash and
`expires_at`. The decider's authority (still a platform admin? principal still
active?) and the current version of the policy the approval was granted under
are never checked at spend time. An approval therefore stays spendable for up
to `MaxApprovalTTL` (7 days) even after the decider was removed from
`ADMIN_PRINCIPALS`, their principal was disabled or merged away, or the
policy changed.

This proposal treats stored authority claims as evidence, not as authorization.
It adds a minimal decision-context record built from existing identifiers, a
decision freshness bound, and a server-side revalidation step before every
`aar_` consume. That step returns typed refusals that tell the caller it needs
a new approval. It covers G6/G7 of the mctlhq/.github#182 decision-assurance
audit and the F3/F4/F6/F9 scenarios as this proposal interprets them (see
Open questions).

## User stories

- AS a platform operator I WANT an approval to stop being spendable once its decider loses the authority they decided with SO THAT a removed or disabled admin's past decisions cannot still authorize side effects.
- AS a platform operator I WANT an approval granted under a policy version that is no longer current to be refused SO THAT a policy change forces a new human decision.
- AS an auditor I WANT every decided approval to carry a reconstructable decision context (intent, actor, subject, tenant, target, intent hash, policy, risk, authority basis, decision time, freshness) as references and hashes SO THAT I can answer "who authorized exactly what, under which authority and policy" without payloads being logged.
- AS an agent or service consuming an approval I WANT drift and expiry to come back as distinct typed codes with a reapproval hint SO THAT I can ask for a new approval instead of retrying blindly.

## Acceptance criteria (EARS)

Decision context and authority evidence

- WHEN a human admin decides an action approval THE SYSTEM SHALL record, on the `aar_` row, the authority evidence: the decider's canonical principal id, the authority basis (`platform_admin`), the authz mode in force (`principal`, `shadow` or `legacy`), the operation risk level when the action kind is a registered operation, and `fresh_until`.
- THE SYSTEM SHALL set `fresh_until` at decision time to the earlier of `expires_at` and `decided_at + ACTION_APPROVAL_MAX_DECISION_AGE` (default 24h).
- WHEN an action approval is read through `GET /api/v1/action-approvals/{id}` or listed THE SYSTEM SHALL include a `decision_context` object. It SHALL contain intent source (`execution_id`, `work_item_id`, `agent_run_id`), actor/subject (`actor_kind`, `actor_name`, `requested_by_principal_id`, `subject_principal_id`), tenant (empty until mctl-api#489 binds one), target, `args_digest`, `artifact_hash`, `intent_hash`, `policy_rule_id`, `policy_version`, decision, risk level, authority evidence, `decided_at`, `expires_at`, `fresh_until`, and `schema_version` `decisioncontext/v1`.
- THE SYSTEM SHALL build the decision context only from identifiers, digests, timestamps and typed enums already stored. It SHALL NOT add the decision reason text, operation arguments or any payload to the context or to the audit log.
- THE SYSTEM SHALL reuse the existing canonical identifiers (`prn_` principal ids, `we_` execution ids, `wi_` work item ids, `policy_rule_id`/`policy_version`, `intent_hash`) and SHALL NOT introduce a second principal, role or policy namespace.

Execution-time revalidation

- WHEN an action approval is about to be consumed, through `POST /api/v1/action-approvals/{id}/consume` or through the grant path `spendApprovalGrant`, THE SYSTEM SHALL revalidate the live authority and policy facts before the consume compare-and-set and before any operation is submitted.
- IF the decider's principal id is no longer in the current `ADMIN_PRINCIPALS` set (principal mode) THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_authority_revoked`, and `reapproval_required: true`.
- IF the approval records no `decided_by_principal_id` THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_authority_revoked`, and `reapproval_required: true`.
- IF the decider's principal is disabled, merged away, deleted, or not a human principal THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_decider_disabled`, and `reapproval_required: true`.
- IF the approval's `policy_rule_id` is in the server's policy registry and its stored `policy_version` is not the registry's current version THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_policy_drift`, and `reapproval_required: true`.
- IF `fresh_until` is set and is not after the current time THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_stale`, and `reapproval_required: true`, and the consume compare-and-set SHALL enforce the same bound atomically.
- IF a live authority fact cannot be read (principal store unreachable, or authz mode unknown) THEN THE SYSTEM SHALL refuse with HTTP 503, code `approval_authority_unavailable`, and SHALL NOT treat the failed read as a pass.
- WHEN a revalidation refusal occurs THE SYSTEM SHALL leave the approval unspent (state stays `approved`), SHALL record an `action_approval.consume_refused` audit entry with the typed code and ids only, and SHALL NOT submit the operation.
- WHILE an approval was decided before this change (no `fresh_until`, no recorded authority basis) THE SYSTEM SHALL still revalidate the decider's live authority and policy version, SHALL apply only `expires_at` for freshness, and SHALL report `authority_basis: "unrecorded"` in its decision context.
- WHEN revalidation passes and the consume succeeds THE SYSTEM SHALL record in the consume audit entry that revalidation passed, with `policy_version`, `authority_basis` and `fresh_until`.

## Out of scope

- Break-glass approvals or an emergency override path (the issue excludes this explicitly).
- Binding approvals to a tenant (mctl-api#489 / mctl-agents#631). The context carries an empty `tenant` field reserved for it.
- Tenant-owner deciders. Deciding stays human platform admin only (#571, `docs/tenant-roles.md`).
- A general policy engine, or moving the policy source of truth out of the code. The registry is a static Go map of rule id to current version.
- Revalidating the requesting service's own authority. The requester is authenticated afresh on every consume call already.
- Revoking or rewriting approvals proactively when an admin is removed. Revalidation is lazy, at spend time.
- New MCP tools. The MCP tool count stays unchanged.
- Work-item approvals (#353) and DevLoop Temporal signals, apart from the shared `aar_` grant path.

## Open questions

- The F3/F4/F6/F9 scenario definitions live in mctlhq/.github#182, which this run could not read. This proposal maps them as F3 = decider authority revoked after decision, F4 = policy version drift between decision and execution, F6 = approval expired or decision too old, F9 = decider principal disabled/merged or authority unobservable. A reviewer should check this mapping against #182 and adjust the tests.
- The default `ACTION_APPROVAL_MAX_DECISION_AGE` is 24h. Should it vary by risk level (for example 1h for `high`)? The proposal ships one global bound, configurable by env.
- An unregistered `policy_rule_id` (a client-supplied rule the server has no registry entry for) is currently accepted and recorded as `policy_revalidation: "unregistered"`. Should it instead fail closed once every producer's rules are registered? The proposal keeps fail-open-with-evidence for compatibility and puts a strict mode behind `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY=true`.
- In `legacy`/`shadow` authz modes, admin is decided by login groups, not by `ADMIN_PRINCIPALS`. The proposal revalidates the principal's status in all modes, and admin membership against `ADMIN_PRINCIPALS` only in principal mode, which is the current mode per `docs/tenant-roles.md`. In legacy mode it records `authority_basis_check: "skipped_legacy_mode"`.
