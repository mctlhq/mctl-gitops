# Distinct agent actor and delegated subject for policy and audit

## Context

mctl-api already has a canonical principal model (`prn_<ulid>`, kinds
`human` | `agent` | `service`, `internal/principals/store.go:57-104`,
`internal/auth/principal.go:45-50`) and already records a two-identity
mutation on one path: the surface relay, where the linked human is the actor
and the relaying surface principal is the carrier
(`auth.NewRelayedUser`, `internal/auth/oidc.go:287-302`;
`workitems.Mutation{Actor, ActingPrincipal, ActorPrincipalID, ViaPrincipalID, Surface}`,
`internal/workitems/inputs.go:15-36`; `audit.Entry.PrincipalID` /
`ViaPrincipalID`, `internal/audit/logger.go`). Every agent run, by contrast,
authenticates as one static admin service principal, `mctl-agent`
(`auth.ServiceUserID`, `internal/auth/oidc.go:242-251`, minted from
`MCTL_AGENT_SERVICE_TOKEN` at `internal/auth/oidc.go:446-452`).
`auth.KindAgent` is declared and never produced by
`auth.User.Identity()` (`internal/auth/principal.go:109-129`).

The consequence is that audit cannot answer "which agent, on which run,
acting for whom". Worse, the one agent-for-human path in the codebase is an
unbound string: `mctl-agents-approve` lets any `user.IsService()` caller put
an arbitrary login in `input["approver"]`
(`internal/api/handlers_write.go:171-196`), while the audit row records
`mctl-agent`. This proposal makes an agent run a first-class,
non-admin, per-execution actor; makes the on-behalf-of subject derivable
only from a record mctl-api already holds; and retires the free-text
approver. It reuses the existing `Mutation` / audit columns rather than
opening a second trail.

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
  SO THAT a rule can condition on "agent X acting for human Y" and not just
  on "a service called".
- AS a human approver I WANT my approval to be recorded against my canonical
  principal wherever it is later relayed SO THAT the approval is provable and
  not a login string an agent typed.

## Acceptance criteria (EARS)

### Agent principals

- WHEN an agent run authenticates with an agent run token THE SYSTEM SHALL
  resolve it to a canonical principal of kind `agent` (`auth.KindAgent`),
  distinct per agent name, via `auth.Identity{Provider: "agent",
  Subject: "agent:<name>", Kind: KindAgent}`.
- WHILE a caller is an agent principal THE SYSTEM SHALL treat it as not an
  admin (`User.IsAdmin()` false), as belonging to no tenant
  (`User.Groups` empty), and SHALL grant it only the permissions its run
  token carries, through the existing `User.HasPermission` mechanism
  (`internal/auth/oidc.go:347-358`).
- IF an agent run token names an agent that has no `AgentDefinition` row in
  the agent registry (`internal/agentregistry/store.go`) THEN THE SYSTEM
  SHALL refuse to mint the token with HTTP 400 `agent_unknown`.

### Execution-scoped credentials

- WHEN the `mctl-agent` service principal calls
  `POST /api/v1/agent-run-tokens` with `{agent, execution_id, ttl_seconds}`
  THE SYSTEM SHALL verify that `execution_id` names a non-terminal
  `WorkItemExecution` (`we_`, `internal/workitems/types.go:26`) it already
  stores, mint an opaque token `art_<ulid>`, persist only its hash, and
  return the plaintext token exactly once.
- WHILE an agent run token is unexpired and unrevoked THE SYSTEM SHALL admit
  it as an agent principal bound to that agent, that execution, that
  execution's work item, and the subject principal the server derived at mint
  time.
- IF an agent run token is expired, revoked, or unknown THEN THE SYSTEM SHALL
  answer HTTP 401 and SHALL NOT fall back to any other principal.
- WHEN `ttl_seconds` is absent THE SYSTEM SHALL default it to 3600 and SHALL
  refuse any value above 86400 with HTTP 400.
- WHEN the execution reaches a terminal phase (`Succeeded` | `Failed` |
  `Error`) THE SYSTEM SHALL treat every run token bound to it as revoked.

### Delegation: subject from a server-held grant, never from the caller

- WHEN an agent principal sends `X-MCTL-On-Behalf-Of: <grant_ref>` THE SYSTEM
  SHALL resolve `grant_ref` against a record it already holds — an execution
  request (`xr_`, `internal/workitems/execution_requests.go:45`), an action
  approval (`aar_`, `internal/workitems/action_approvals.go:42`), a work item
  (`wi_`), or a surface identity link — and SHALL take the subject principal
  from that record's stored principal id, never from the header, the body or
  any other caller-supplied value.
- IF the resolved grant is not bound to the run token's own execution or work
  item THEN THE SYSTEM SHALL refuse the request with HTTP 403
  `grant_not_bound`.
- IF the grant record carries no resolved subject principal id (the column is
  `''`, as phase 1 permits) THEN THE SYSTEM SHALL refuse the request with
  HTTP 403 `grant_subject_unresolved` rather than falling back to a string.
- IF an agent principal sends `X-MCTL-On-Behalf-Of` on a route that is not on
  the delegation allowlist THEN THE SYSTEM SHALL answer HTTP 400
  `delegation_not_supported`.
- IF a request body carries an identity field (`on_behalf_of`,
  `subject`, `delegated_actor`, `approver`, `acting_principal`) THEN THE
  SYSTEM SHALL reject it with HTTP 400, extending the existing rejection in
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
  principal as both `Actor` and `ActorPrincipalID`, leaving
  `ActingPrincipal` / `ViaPrincipalID` empty.
- WHEN any agent request is audited THE SYSTEM SHALL populate
  `audit.Entry.PrincipalID` and `audit.Entry.ViaPrincipalID` on the same rule
  and SHALL additionally record the bound execution id in a new
  `via_execution_id` column on `audit_events` and `work_item_events`.
- WHILE recording THE SYSTEM SHALL add no new audit table, no new event
  stream, and no second set of actor columns.

### Retiring `input["approver"]`

- WHEN any caller submits `mctl-agents-approve` with an `approver` field in
  the request body THE SYSTEM SHALL reject it with HTTP 400, for a service
  and agent caller as it already does for a human
  (`internal/api/handlers_write.go:176-195`).
- WHEN a human admin acting directly submits `mctl-agents-approve` THE SYSTEM
  SHALL derive `approver` from `user.ID` and `approver_principal_id` from
  `user.PrincipalID()`.
- WHEN an agent principal submits `mctl-agents-approve` THE SYSTEM SHALL
  require an `approval_ref` naming a decision record mctl-api holds, SHALL
  derive `approver` and `approver_principal_id` from that record's
  `decided_by` / `decided_by_principal_id`, and SHALL refuse with HTTP 400
  `approval_ref_required` when it is absent.
- IF the named decision record is not in a decided state, is expired, or does
  not correspond to the proposal being approved THEN THE SYSTEM SHALL refuse
  with HTTP 409 `approval_ref_invalid` and SHALL audit the refusal, as
  `auditActionApprovalRefusal` already does
  (`internal/api/handlers_action_approvals.go:320-321`).
- WHILE `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` is set to `true` THE SYSTEM
  SHALL accept the pre-existing service relay of `input["approver"]`, SHALL
  log a deprecation warning and SHALL audit it as
  `approver.legacy_relay`; the flag defaults to unset.

### Policy and evidence interplay (#197 / ADR 014, mctl-agents#199)

- WHEN an action approval is created by an agent principal THE SYSTEM SHALL
  store and serve `actor_principal_id`, `actor_kind`, `actor_name`,
  `subject_principal_id`, `subject_kind`, `agent_run_id` and `execution_id`
  on the `ActionApprovalRequest` payload.
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
- IdP federation and swappable identity providers — #374.
- Removing `MCTL_AGENT_SERVICE_TOKEN`. It stays as the token that mints run
  tokens and as the dispatcher/claim credential; only its use as the actor of
  agent work is retired.
- MCP tool wrappers for any new route. Adding tools forces coordinated
  updates to `internal/mcp/server_test.go` (`TestNewMCPServer_ToolCount`) and
  `internal/mcp/annotations_test.go`; the REST + OpenAPI contract is what
  mctl-agents needs first.
- Changing the surface relay contract (mctl-api#350) or its routes. This
  proposal generalises its pattern; it does not alter it.
- Backfilling agent identity onto historical `audit_events` or
  `work_item_events` rows. Correlation is forward-only, as
  `docs/principals.md:73-77` already states for the phase-1 dual-write.

## Open questions

- **Which grant is canonical for the dev-loop approve relay?** The dev-loop
  approve endpoint (`internal/api/handlers_dev_loop.go:139-183`) today
  signals Temporal with `map[string]string{"approver": approver}` and writes
  an audit row carrying the same value plus the caller's principal. There is
  no dedicated durable decision record for it. This proposal treats that
  audit event's id as the `approval_ref` (it is server-written, append-only
  and already carries `PrincipalID`), and notes a dedicated
  `dev_loop_approvals` record as the cleaner long-term answer. Reviewer
  should confirm reading audit as an authorization source is acceptable, or
  ask for the dedicated record in this proposal instead.
- **Header vs. body for the grant reference.** `X-MCTL-On-Behalf-Of` mirrors
  `X-MCTL-Surface-Actor`, but MCP tool arguments are flat strings and a
  header-only contract would be unusable from a future MCP surface — the
  reason `expected_state_version` is a body field
  (`docs/work-context-contract.md`). Proceeding with the header because the
  agent path is HTTP-only today; a body alias is a cheap follow-up.
- **Per-agent vs. per-execution principal.** This proposal mints one
  `prn_` per *agent name* and carries the execution on the run token and in
  `via_execution_id`, rather than one principal per execution. A
  principal-per-execution would make the `principals` table grow without
  bound and gains nothing that the execution column does not already give.
  Recorded in case the reviewer wants the stronger form.
- **Which agent names exist.** The agent registry
  (`internal/agentregistry`) holds `issue-investigator`, `implementer`,
  `shepherd`, `incident-responder`, `service-agent`, `mentor` among others.
  Whether every one of them gets a principal on day one, or only the ones
  that write, is a rollout choice; this proposal mints on first token request
  for a registered agent.
- **Permission vocabulary.** `auth.HasPermission` models exactly one
  permission today (`usage:write`, `internal/auth/oidc.go:347-358`). The set
  an agent run token may carry is left to the implementation, starting with
  the routes mctl-agents calls; it is deliberately not a new RBAC system.
