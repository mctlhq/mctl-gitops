# Authority and decision-context contract with execution-time revalidation for action approvals

## Context

mctl-api already has the parts of a governed decision. It has canonical
principals (`prn_`, `internal/principals`), principal-mode platform admin
(`ADMIN_PRINCIPALS`, `internal/auth/principal_authz.go`) and tenant roles
(`docs/tenant-roles.md`). It also has single-use action approvals (`aar_`,
`internal/workitems/action_approvals.go`), each bound to an exact intent hash
over execution, action kind, target, args digest, policy rule id/version,
artifact hash and work item. What is missing is one explicit contract with three
parts:

1. Which context a reviewer must be shown, and which context the decision is
   bound to.
2. Which authority evidence is captured when a human decides.
3. Which facts are checked again just before the side effect.

Today `DecideActionApproval` will approve a request that carries no risk
classification, no intent/source reference and no policy decision or reasons.
The reviewer effectively sees "Approve operation?" (#182 F6). `ConsumeActionApproval`
checks only state, intent hash and `expires_at`. The decider's current authority
and the current policy version are never checked when the approval is spent. An
approval therefore stays spendable for up to `MaxApprovalTTL` (7 days), even
after the decider is removed from `ADMIN_PRINCIPALS`, the decider's principal is
disabled or merged away, or the policy changes.

This proposal treats stored authority claims as evidence, never as
authorization. It adds five things:

- a mandatory decision context, built only from existing identifiers and
  references, that is shown to the reviewer;
- a context digest that binds the decision to that context;
- authority evidence captured at decision time;
- a freshness bound;
- a server-side revalidation step before every `aar_` consume, which returns
  typed refusals carrying `reapproval_required`.

It covers G6/G7 of the mctlhq/.github#182 decision-assurance audit. It uses the
authoritative #182 scenario mapping given in the issue: F3 authority loss, F4
staleness/expiry, F6 reviewer context, F9 policy drift.

## User stories

- AS a human approver I WANT every approval I am asked to decide to show its target, payload digest, risk and side-effect classification, intent/source, and policy id/version/decision/reasons SO THAT I never approve a bare "Approve operation?".
- AS a platform operator I WANT an approval that lacks any mandatory context field to be impossible to approve SO THAT no grant can exist for an action whose context a reviewer could not see.
- AS a platform operator I WANT an approval to stop being spendable once its decider loses the authority they decided with SO THAT a removed or disabled admin's past decisions cannot still authorize side effects.
- AS a platform operator I WANT an approval granted under a policy version that is no longer current to be refused SO THAT a policy change forces a new human decision.
- AS an auditor I WANT every decided approval to carry a reconstructable decision context and the digest it was decided on, as references and hashes SO THAT I can answer "who authorized exactly what, under which authority and policy" without payload logging.
- AS an agent or service consuming an approval (mctl-agents) I WANT drift, staleness and revocation to come back as typed codes with `reapproval_required: true` SO THAT I can key on one flag and request a new approval instead of matching code substrings.

## Acceptance criteria (EARS)

### Decision context (F6)

- THE SYSTEM SHALL define the mandatory decision context (schema `decisioncontext/v1`) of an action approval as follows:
  - target: `target`
  - exact payload: `args_digest`, `intent_hash`, and `artifact_hash` when set
  - risk/side-effect classification: `risk_level` (`low|medium|high`) and `side_effect` (`none|read|write|destructive|external`)
  - intent/source: `intent_source`, a typed reference such as `work_item:wi_...`, `execution:we_...` or `github_issue:<owner>/<repo>#<n>`, plus `execution_id`
  - policy: `policy_rule_id`, `policy_version`, `policy_decision` (`require_approval`), and `policy_reasons` (a bounded list of reason codes)
- WHEN an action approval is created THE SYSTEM SHALL accept the optional body fields `risk_level`, `side_effect`, `intent_source`, `policy_decision` and `policy_reasons`, and SHALL apply the existing bounds and secret scanning to them.
- WHEN `action_kind` is a registered operation THE SYSTEM SHALL derive `risk_level` from `operations.Registry`, and IF the client sent a different `risk_level` THEN THE SYSTEM SHALL refuse the create with HTTP 400, code `approval_context_invalid`.
- WHEN `policy_rule_id` is in the server policy registry (`governance.Policies`) THE SYSTEM SHALL fill any omitted `side_effect`, `policy_decision` and `policy_reasons` from that registry entry, so that existing producers such as the DevLoop gate need no change.
- WHEN an action approval is read through `GET /api/v1/action-approvals/{id}` or the list THE SYSTEM SHALL include a `decision_context` object. It SHALL contain every mandatory field, plus actor/subject (`actor_kind`, `actor_name`, `requested_by_principal_id`, `subject_principal_id`), `tenant` (empty and reserved for mctl-api#489), the authority evidence, `created_at`, `decided_at`, `expires_at`, `fresh_until`, `context_digest`, `context_complete` and `missing_fields`.
- THE SYSTEM SHALL compute `context_digest` as `sha256:<hex>` over a length-prefixed canonical encoding (`mctl-decision-context/v1`) of the mandatory fields, in a fixed order.
- IF a decision `approve` is made on a request whose decision context is missing any mandatory field THEN THE SYSTEM SHALL refuse with HTTP 422, code `approval_context_incomplete`, naming the missing fields in `details.missing_fields`, SHALL leave the request `pending`, and SHALL NOT create a grant.
- WHEN a decision `deny` is made on a request with incomplete context THE SYSTEM SHALL accept it, because a denial creates no grant.
- WHEN a decision body carries `context_digest` (the digest the reviewer was shown) and it differs from the request's current digest THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_context_changed`, with `reapproval_required: true`, and SHALL NOT approve.
- WHEN an approval is decided THE SYSTEM SHALL store the digest it was decided on as `decided_context_digest`.
- WHEN an approval is consumed THE SYSTEM SHALL recompute the context digest from the stored row and the live registry-derived fields (operation risk level, policy registry entry). IF it differs from `decided_context_digest` THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_context_changed`, with `reapproval_required: true`.
- THE SYSTEM SHALL build the decision context only from identifiers, digests, timestamps, typed enums and reason codes. It SHALL NOT add the decision reason free text, operation arguments or any payload to the context or to the audit log.
- THE SYSTEM SHALL reuse the existing canonical identifiers (`prn_` principals, `we_` executions, `wi_` work items, `policy_rule_id`/`policy_version`, `intent_hash`, `operations.RiskLevel`) and SHALL NOT introduce a second principal, role or policy namespace.

### Authority evidence at decision time

- WHEN a human admin approves an action approval THE SYSTEM SHALL record on the `aar_` row:
  - `decided_by_principal_id` (existing);
  - `authority_basis` = `platform_admin`;
  - `authz_mode` = `principal`, `shadow` or `legacy`;
  - `decided_context_digest`;
  - `fresh_until`.
- THE SYSTEM SHALL set `fresh_until` at decision time to the earlier of `expires_at` and `decided_at + ACTION_APPROVAL_MAX_DECISION_AGE` (default 24h).

### Execution-time revalidation (F3, F4, F9)

- WHEN an action approval is about to be consumed, through `POST /api/v1/action-approvals/{id}/consume` or through the grant path `spendApprovalGrant`, THE SYSTEM SHALL revalidate the decision context, freshness, live authority and policy facts before the consume compare-and-set and before any operation is submitted.
- IF `fresh_until` is set and is not after the current time THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_stale`, with `reapproval_required: true`. The consume compare-and-set SHALL enforce the same bound atomically. (F4)
- IF `expires_at` is not after the current time THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_expired` (existing), now with `reapproval_required: true`. (F4)
- IF `decided_by_principal_id` is empty, or (in principal mode) is not in the current `ADMIN_PRINCIPALS` set THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_authority_revoked`, with `reapproval_required: true`. (F3)
- IF the decider's principal is disabled, merged away, deleted, or not a human principal THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_decider_disabled`, with `reapproval_required: true`. (F3)
- IF a live authority fact cannot be read (the principal store is unreachable or cannot check a principal's kind) THEN THE SYSTEM SHALL refuse with HTTP 503, code `approval_authority_unavailable`, SHALL fail closed, SHALL leave the approval unspent, and SHALL NOT treat the failed read as a pass. (F3)
- IF the approval's `policy_rule_id` is in `governance.Policies` and its stored `policy_version` is not the current registry version THEN THE SYSTEM SHALL refuse with HTTP 409, code `approval_policy_drift`, with `reapproval_required: true`. (F9)
- WHEN a new approval is created and decided under the current policy version after a drift refusal THE SYSTEM SHALL consume it successfully. (F9)
- WHEN any revalidation refusal occurs THE SYSTEM SHALL leave the approval in state `approved` (unspent), SHALL record an `action_approval.consume_refused` audit entry carrying only the typed code and ids, and SHALL NOT submit the operation.
- WHILE an approval was decided before this change (no `fresh_until`, no `authority_basis`, no `decided_context_digest`) THE SYSTEM SHALL still revalidate the decider's live authority and policy version, SHALL apply only `expires_at` for freshness, SHALL skip the consume-time digest comparison, and SHALL report `authority_basis: "unrecorded"` in its decision context.
- WHEN revalidation passes and the consume succeeds THE SYSTEM SHALL record `revalidation: passed`, `policy_version`, `authority_basis`, `context_digest` and `fresh_until` in the consume audit entry.

### Contract document

- THE SYSTEM SHALL ship `docs/decision-context-contract.md`. It SHALL define the mandatory fields, what is captured versus revalidated, the refusal codes, freshness semantics, the privacy rule, and the #182 mapping exactly as F3 = authority loss, F4 = staleness/expiry, F6 = reviewer context, F9 = policy drift. Test names SHALL use the same mapping.

## Out of scope

- Break-glass approvals or emergency overrides (excluded by the issue).
- Binding approvals to a tenant (mctl-api#489 / mctl-agents#631). The context carries an empty, reserved `tenant`.
- Tenant-owner deciders. Deciding stays human-platform-admin only (#571, `docs/tenant-roles.md`).
- A general policy engine. `governance.Policies` is a static Go map of rule id to current version and defaults.
- Revalidating the requester's own authority. The requester is authenticated afresh on every consume.
- Proactive revocation sweeps when an admin is removed. Revalidation is lazy, at spend time.
- New MCP tools. The MCP tool count in `server_test.go` is unchanged.
- Work-item approvals (#353) and Temporal signal semantics, beyond the shared `aar_` decide and grant paths.
- A reviewer UI. mctl-portal or mctl-telegram rendering of `decision_context` is follow-up work on those repos.

## Open questions

- Default `ACTION_APPROVAL_MAX_DECISION_AGE` is 24h, one global bound. Should it vary by `risk_level` (for example 1h for `high`)?
- `side_effect` enum values (`none|read|write|destructive|external`) are proposed here, because no existing classification beyond `operations.RiskLevel` was found in the code. The reviewer should confirm them against #182 or #91.
- `intent_source` reference grammar: this proposal accepts `<kind>:<ref>` with kind in `work_item|execution|github_issue|incident|operator`. If `intent_source` is omitted, the server falls back to `work_item:<work_item_id>`, else `execution:<execution_id>`. Is an execution reference acceptable as an intent source, or must producers send the upstream issue or work item?
- Should an unregistered `policy_rule_id` fail closed? The proposal records `policy_revalidation: "unregistered"` and fails closed only under `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY=true`. An unregistered rule must still supply `policy_decision`, `policy_reasons` and `side_effect` itself, or it cannot be approved (F6).
- In `legacy`/`shadow` authz modes, admin is derived from login groups, not from `ADMIN_PRINCIPALS`. The proposal checks the decider's principal status in all modes, and checks admin membership only in principal mode (recording `skipped_legacy_mode` otherwise). The deployed `TENANT_AUTHZ_MODE` was not observable in this run (see design.md).
- Pending `aar_` rows created before deploy with an unregistered policy and no context fields cannot be approved after deploy. They must be recreated. This is believed to be rare, because the DevLoop gate uses the registered `dev-loop.human-approval` rule.
