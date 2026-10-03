# Distinct agent actor and delegated subject for policy and audit

## Context

mctl-api already has a canonical principal model (`prn_<ulid>`, kinds
`human` | `agent` | `service`, `internal/principals/store.go:77-105`,
`internal/auth/principal.go:45-50`) and already records a two-identity
mutation on one path: the surface relay, where the linked human is the
subject and the relaying surface principal is the carrier
(`auth.NewRelayedUser`, `internal/auth/oidc.go:287-302`;
`workitems.Mutation{Actor, ActingPrincipal, ActorPrincipalID, ViaPrincipalID,
Surface}`, `internal/workitems/inputs.go:15-36`; `audit.Entry.PrincipalID` /
`ViaPrincipalID`, `internal/audit/logger.go`). Every agent run, by contrast,
authenticates as one static admin service principal, `mctl-agent`
(`auth.ServiceUserID`, `internal/auth/oidc.go:242-251`, minted from
`MCTL_AGENT_SERVICE_TOKEN` at `internal/auth/oidc.go:446-452`).
`auth.KindAgent` (`internal/auth/principal.go:48`) is declared and never
produced by `auth.User.Identity()` (`principal.go:109-129`).

The consequence is that audit cannot answer "which agent, on which run,
acting for whom". Worse, the one agent-for-human path in the codebase is an
unbound string: `mctl-agents-approve` lets any `user.IsService()` caller put
an arbitrary login in `input["approver"]`
(`internal/api/handlers_write.go:171-196`), while the audit row records
`mctl-agent`. This proposal makes an agent run a first-class, non-admin,
per-execution actor; makes the on-behalf-of subject derivable only from a
record mctl-api already holds; and retires the free-text approver by binding
it to an `ActionApprovalRequest` (`aar_`), which already carries
`DecidedByPrincipalID`, a state machine, an expiry and a human-admin-only
decide rule (`internal/workitems/action_approvals.go:99-134`,
`internal/api/handlers_action_approvals.go:315-341`). It reuses the existing
`Mutation` / audit columns rather than opening a second trail.

**This is a revision.** It answers the six review findings recorded on the
issue: the legacy approver relay now defaults ON with an explicit release
order and named mctl-agents counterpart work (F1); `approval_ref` is an
`aar_` id and never an audit row id (F2); there is exactly one rule for
deriving the subject, and the mint no longer derives one (F3); `agent` is
noted as a reserved provider name for the #374 federation registry (F4);
every run-token mint is audited (F5); tasks are sliced into four shippable
groups (F6).

## User stories

- AS a platform operator I WANT every agent-initiated write to name which
  agent and which execution performed it SO THAT an audit query can attribute
  a side effect to one run rather than to "some admin".
- AS a platform operator I WANT an agent credential that is scoped to one
  agent and one execution and expires SO THAT a leaked credential cannot act
  as the whole platform forever.
- AS a security reviewer I WANT it to be structurally impossible for an agent
  to name an arbitrary human as the subject of its action SO THAT the agent
  path is not a generic impersonation relay.
- AS a policy author (mctl-agents#197 / ADR 014) I WANT the checkpoint and the
  evidence envelope (mctl-agents#199) to read named actor and subject fields
  SO THAT a rule can condition on "agent X acting for human Y" and not just on
  "a service called".
- AS a human approver I WANT my approval to be recorded against a durable,
  single-use decision record carrying my canonical principal SO THAT what the
  agent later relays is provable and not a login string it typed.
- AS a release manager I WANT the mctl-api release to keep working against
  today's mctl-agents worker SO THAT no DevLoop approval breaks while the two
  repos ship independently.

## Acceptance criteria (EARS)

### Agent principals

- WHEN an agent run authenticates with an agent run token THE SYSTEM SHALL
  resolve it to a canonical principal of kind `agent` (`auth.KindAgent`),
  distinct per agent name, via `auth.Identity{Provider: "agent",
  Subject: "agent:<name>", Display: "<name>", Kind: KindAgent}`.
- WHILE a caller is an agent principal THE SYSTEM SHALL treat it as not an
  admin (`User.IsAdmin()` false), as belonging to no tenant (`User.Groups`
  empty), as not a service (`User.IsService()` false), and SHALL grant it only
  the permissions its run token carries, through the existing
  `User.HasPermission` mechanism (`internal/auth/oidc.go:347-358`).
- WHILE the #374 federation provider registry exists THE SYSTEM SHALL treat
  `agent` as a reserved provider name that no configured federation provider
  may claim, refused at boot, so no external IdP can mint identities in the
  `(agent, ...)` namespace.
- IF an agent run token names an agent that has no `AgentDefinition` row in
  the agent registry (`internal/agentregistry/store.go`) THEN THE SYSTEM SHALL
  refuse to mint the token with HTTP 400 `agent_unknown`.

### Execution-scoped credentials

- WHEN the `mctl-agent` service principal acting directly calls
  `POST /api/v1/agent-run-tokens` with `{agent, execution_id, ttl_seconds?,
  permissions?}` THE SYSTEM SHALL verify that `execution_id` names a
  non-terminal `WorkItemExecution` it already stores, mint an opaque token
  `art_<ulid>`, persist only its SHA-256 hash, and return the plaintext token
  exactly once.
- WHILE an agent run token is unexpired and unrevoked THE SYSTEM SHALL admit
  it as an agent principal bound to exactly three things: that agent, that
  execution, and that execution's work item. THE SYSTEM SHALL NOT bind any
  subject to the token.
- IF an agent run token is expired, revoked, or unknown THEN THE SYSTEM SHALL
  answer HTTP 401 and SHALL NOT fall back to any other principal.
- WHEN `ttl_seconds` is absent THE SYSTEM SHALL default it to 3600 and SHALL
  refuse any value above 86400 with HTTP 400.
- WHEN the execution reaches a terminal phase (`Succeeded` | `Failed` |
  `Error`) THE SYSTEM SHALL treat every run token bound to it as revoked.
- WHEN a run token is minted THE SYSTEM SHALL write one audit entry
  `agent_run_token.mint` recording the token id (`art_`), the agent name and
  agent principal id, the bound execution id and work item id, the granted
  TTL and expiry, the requested permissions, and the minting principal
  (`issued_by_principal_id`), and SHALL NEVER record the plaintext token.
- WHILE minting is performed with the static `MCTL_AGENT_SERVICE_TOKEN` THE
  SYSTEM SHALL record no subject on the mint entry, because the mint derives
  none; the subject appears only on the delegated request that presents a
  grant.
- WHEN a mint is refused THE SYSTEM SHALL audit the refusal with its typed
  code, as `auditActionApprovalRefusal` already does
  (`internal/api/handlers_action_approvals.go:320-321`).

### Delegation: one rule for deriving the subject

The rule, stated once and applied everywhere:

> The mint binds the execution and the work item only. The
> `X-MCTL-On-Behalf-Of` header only *selects* a grant that is itself bound to
> that execution or that work item. The subject is always read from the
> selected grant row, never from the token, never from the header, never from
> the body.

- WHEN an agent principal sends `X-MCTL-On-Behalf-Of: <grant_ref>` THE SYSTEM
  SHALL resolve `grant_ref` against a record it already holds — an execution
  request (`xr_`), an action approval (`aar_`), a work item (`wi_`) or a
  surface identity link — and SHALL take the subject principal id and subject
  string from that record's stored columns.
- IF the resolved grant is not bound to the run token's own execution id or
  work item id THEN THE SYSTEM SHALL refuse the request with HTTP 403
  `grant_not_bound`.
- IF the grant record carries no resolved subject principal id (the column is
  `''`, as #373 phase 1 permits) THEN THE SYSTEM SHALL refuse the request with
  HTTP 403 `grant_subject_unresolved` rather than falling back to a string.
- WHILE a request is delegated THE SYSTEM SHALL derive the subject from the
  grant row alone, even where the bound work item's own owner names a
  different principal; THE SYSTEM SHALL NOT read the work item owner, the
  execution requester, or any other field as a subject at request time.
- IF an agent principal sends `X-MCTL-On-Behalf-Of` on a route that is not on
  the delegation allowlist THEN THE SYSTEM SHALL answer HTTP 400
  `delegation_not_supported`.
- IF a non-agent caller sends `X-MCTL-On-Behalf-Of` THEN THE SYSTEM SHALL
  answer HTTP 400 `delegation_not_accepted`, the rule
  `surfacePrincipalGate` already applies to `X-MCTL-Surface-Actor`
  (`internal/api/handlers_surface_identity.go:121-173`).
- IF a request body carries an identity field (`on_behalf_of`, `subject`,
  `delegated_actor`, `approver`, `acting_principal`) THEN THE SYSTEM SHALL
  reject it with HTTP 400, extending the existing rejection in
  `internal/api/handlers_work_items.go:66-70` to every route this proposal
  touches.
- WHILE a request is delegated THE SYSTEM SHALL never confer admin on it and
  SHALL restrict its tenant groups to the subject's groups minus `admins`,
  the rule `auth.NewRelayedUser` already applies
  (`internal/auth/oidc.go:292-301`).

### Recording (reuse, no parallel trail)

- WHEN a delegated agent request writes a work-item mutation THE SYSTEM SHALL
  populate the existing `workitems.Mutation` fields with the subject as
  `Actor` / `ActorPrincipalID` and the agent principal as `ActingPrincipal`
  (`agent:<name>`) / `ViaPrincipalID` — the same assignment the surface relay
  already makes (`internal/api/handlers_work_items.go:231-235`).
- WHEN a non-delegated agent request writes THE SYSTEM SHALL record the agent
  principal as both `Actor` and `ActorPrincipalID`, leaving `ActingPrincipal`
  and `ViaPrincipalID` empty.
- WHEN any agent request is audited THE SYSTEM SHALL populate
  `audit.Entry.PrincipalID` and `audit.Entry.ViaPrincipalID` on the same rule
  and SHALL additionally record the bound execution id in a new
  `via_execution_id` column on `audit_events` and `work_item_events`.
- WHILE recording THE SYSTEM SHALL add no new audit table, no new event
  stream, and no second set of actor columns.

### Retiring `input["approver"]`

- WHEN a DevLoop reaches its approval gate THE SYSTEM SHALL express that
  approval as an `ActionApprovalRequest` (`aar_`) with
  `action_kind = "mctl-agents-approve"`, `target = "<service>/<slug>"` and
  `execution_id` set to the DevLoop workflow id, so the decision has a state
  machine, an expiry and a single-use consume.
- WHEN a human admin acting directly calls
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` THE SYSTEM SHALL decide
  the pending `aar_` for that workflow through the existing
  `DecideActionApproval` store call — recording `DecidedBy`,
  `DecidedByPrincipalID` and `DecidedViaPrincipalID` — and SHALL include the
  `aar_` id in the Temporal signal payload as `approval_ref` beside the
  existing `approver` key.
- IF no pending `aar_` exists for that workflow when the endpoint is called
  THEN THE SYSTEM SHALL create one server-side with
  `requested_by = "mctl-agent"` before deciding it, so the decision is never
  a self-decision (`workitems.ErrApprovalSelfDecision`).
- WHEN the dev-loop approve endpoint is called by a caller that is not a human
  admin acting directly THE SYSTEM SHALL refuse it, tightening
  `requireTemporalAdmin` (`internal/api/handlers_dev_loop.go:42-54`), which
  today admits the `mctl-agent` service principal because it carries the
  `admins` group.
- WHEN any caller submits `mctl-agents-approve` with an `approver` field in
  the request body THE SYSTEM SHALL reject it with HTTP 400 unless the legacy
  relay is enabled, for a service and agent caller as it already does for a
  human (`internal/api/handlers_write.go:176-195`).
- WHEN a human admin acting directly submits `mctl-agents-approve` THE SYSTEM
  SHALL derive `approver` from `user.ID` and `approver_principal_id` from
  `user.PrincipalID()`.
- WHEN an agent principal submits `mctl-agents-approve` THE SYSTEM SHALL
  require `approval_ref` to be an `aar_` id, SHALL consume it exactly once
  through `ConsumeActionApproval`, and SHALL derive `approver` and
  `approver_principal_id` from that record's `decided_by` and
  `decided_by_principal_id`. THE SYSTEM SHALL refuse with HTTP 400
  `approval_ref_required` when it is absent.
- IF `approval_ref` names a record that is not approved, is expired, is
  already consumed, or whose `action_kind` / `target` do not match the
  `service` and `slug` being approved THEN THE SYSTEM SHALL refuse with HTTP
  409 `approval_ref_invalid` and SHALL audit the refusal.
- IF `approval_ref` names anything that is not an `aar_` id — in particular an
  audit event id — THEN THE SYSTEM SHALL refuse it with HTTP 400
  `approval_ref_invalid`. Audit rows are evidence, not grants: they carry no
  state, no expiry and no single-use rule.

### Rollout of the legacy approver relay

- WHILE `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` is unset or `true` THE SYSTEM
  SHALL accept the pre-existing service relay of `input["approver"]`. The flag
  **defaults to on**, so the mctl-api release alone changes no caller's
  behaviour.
- WHEN the legacy relay path is taken THE SYSTEM SHALL log a deprecation
  warning and SHALL write an audit entry `approver.legacy_relay` recording the
  relayed approver string, the calling principal and the operation — on every
  use, without exception, so the verify step can assert the count is zero.
- WHEN `MCTL_AGENTS_APPROVE_LEGACY_APPROVER=false` THE SYSTEM SHALL reject a
  body-supplied `approver` from every caller kind and SHALL require
  `approval_ref` from an agent principal.
- WHILE the two repositories ship independently THE SYSTEM SHALL be rolled out
  in this order and no other: (1) mctl-api release with the legacy relay on;
  (2) mctl-agents release that mints run tokens, sends `approval_ref` and
  sends `X-MCTL-On-Behalf-Of`; (3) verify zero `approver.legacy_relay` audit
  entries across a full DevLoop cycle; (4) mctl-api follow-up release flipping
  the default to off.

### Policy and evidence interplay (#197 / ADR 014, mctl-agents#199)

- WHEN an action approval is created or decided THE SYSTEM SHALL store and
  serve `actor_principal_id`, `actor_kind`, `actor_name`,
  `subject_principal_id`, `subject_kind`, `agent_run_id` and `execution_id` on
  the `ActionApprovalRequest` payload.
- WHEN a caller reads `GET /api/v1/identity/self` THE SYSTEM SHALL return the
  resolved actor (principal id, kind, name), the resolved subject when the
  request is delegated, the bound execution and work item, and the grant kind
  and ref — the fields the policy checkpoint and the evidence envelope read.
- WHILE no delegation is in force THE SYSTEM SHALL return a null `subject`
  block rather than repeating the actor, so a rule can distinguish
  "agent acting for itself" from "agent acting for a human".

## Out of scope

- Moving authorization and tenant membership onto principal ids — that is
  #377 (phase 2). Authorization in this proposal still runs on `User.ID`,
  `User.Groups`, `User.IsAdmin()` and `User.HasPermission`.
- IdP federation and swappable identity providers — #374. This proposal only
  asserts that `agent` is reserved in that registry.
- Removing `MCTL_AGENT_SERVICE_TOKEN`. It stays as the token that mints run
  tokens, creates action approvals and claims work; only its use as the actor
  of agent work is retired.
- The mctl-agents worker changes themselves. They are named here and listed in
  tasks.md so the release order is reviewable, but they ship from mctl-agents.
- MCP tool wrappers for any new route. Adding tools forces coordinated updates
  to `internal/mcp/server_test.go` (`TestNewMCPServer_ToolCount`) and
  `internal/mcp/annotations_test.go`; the REST + OpenAPI contract is what
  mctl-agents needs first.
- Changing the surface relay contract (mctl-api#350) or its routes. This
  proposal generalises its pattern; it does not alter it.
- Backfilling agent identity onto historical `audit_events` or
  `work_item_events` rows. Correlation is forward-only, as
  `docs/principals.md:73-77` already states for the phase-1 dual-write.

## Open questions

Carried forward for the owner to decide at approval; none blocks the work.

- **Header vs. body for the grant reference.** `X-MCTL-On-Behalf-Of` mirrors
  `X-MCTL-Surface-Actor`, but MCP tool arguments are flat strings and a
  header-only contract would be unusable from a future MCP surface — the
  reason `expected_state_version` is a body field
  (`docs/work-context-contract.md`). Proceeding with the header because the
  agent path is HTTP-only today; a body alias is a cheap follow-up.
- **Per-agent vs. per-execution principal.** This proposal mints one `prn_`
  per *agent name* and carries the execution on the run token and in
  `via_execution_id`, rather than one principal per execution. A
  principal-per-execution would make the `principals` table grow without bound
  and gains nothing that the execution column does not already give. Recorded
  in case the reviewer wants the stronger form.
- **Which agent names exist.** The agent registry (`internal/agentregistry`)
  holds `issue-investigator`, `implementer`, `shepherd`,
  `incident-responder`, `service-agent`, `mentor` among others. Whether every
  one gets a principal on day one, or only the ones that write, is a rollout
  choice; this proposal mints on first token request for a registered agent.
- **Permission vocabulary.** `auth.HasPermission` models exactly one
  permission today (`usage:write`, `internal/auth/oidc.go:347-358`). The set an
  agent run token may carry is left to the implementation, starting with the
  routes mctl-agents calls; it is deliberately not a new RBAC system.
- **`policy_rule_id` / `policy_version` for the dev-loop `aar_`.** Both are
  required non-empty fields on `ActionApprovalInput`
  (`internal/workitems/action_approvals.go:234-240`). This proposal uses the
  constants `dev-loop.human-approval` / `v1` until #197 / ADR 014 supplies a
  real rule id, so the record is honest about being a gate with no policy
  engine behind it yet.
- **Who files the mctl-agents counterpart issue.** No existing mctl-agents
  issue carries the worker-side tasks (checked at investigation time). Tasks
  C4-C8 below are written so they can be lifted verbatim into a new
  mctl-agents issue; the owner decides whether to file it before or at
  approval.
