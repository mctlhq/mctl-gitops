# Unified identity: delegation grants for agent principals (#376 slice B)

## Context

Slice A of mctlhq/mctl-api#376 landed in #423 (`73acd14`) and made an agent
run a first-class, non-admin principal: `auth.NewAgentUser` builds a user whose
`agent`, `execID`, `workItemID` and `runID` fields come from a resolved
`art_` run token (`internal/auth/agent.go:76-85`), `principalOf` renders it as
`agent:<name>` (`internal/api/handlers_work_items.go:75-83`), and every write
already stamps `via_execution_id` on `work_item_events` and `audit_events`
(`internal/api/clientmeta.go:190-191`, `internal/audit/postgres.go:53`). What
Slice A deliberately did **not** give the agent is a way to say *who it is
acting for*: `auth.AgentRun` has no subject field, and the comment at
`internal/auth/agent.go:29-32` states outright that a run token "cannot say who
the agent is acting for" and that delegation is a separate mechanism layered on
top.

Slice B is that mechanism. It is the last missing half of the audit story: today
a delegated agent write is indistinguishable from an agent acting for itself,
so `actor_principal_id` records the agent for work a human actually asked for,
and the approver-retirement work in Slice C (which replaces the free-text
`input["approver"]` relay) has nothing to read a subject from. The design is
the accepted proposal `issue-376-feat-unified-identity-represent-agent-ac`
(approved 2026-09-29), design.md section 3 and tasks.md B1-B3; this proposal
implements it and does not re-design it. The single rule the whole slice exists
to make structural is: **the mint binds the execution and the work item; the
`X-MCTL-On-Behalf-Of` header only selects a grant already bound to that
execution or work item; the subject is always read out of the selected grant
row.** Nothing a caller supplies — no header value, no body field, no token
claim — may ever produce a subject.

## User stories

- AS a platform auditor I WANT a delegated agent write to record the human
  subject in `actor_principal_id` and `agent:<name>` in `acting_principal` /
  `via_principal_id` SO THAT I can tell work an agent did for a person from
  work it did for itself.
- AS the DevLoop Temporal worker I WANT to send
  `X-MCTL-On-Behalf-Of: <grant_ref>` naming an `xr_`, `aar_`, `wi_` or surface
  link my run is already bound to SO THAT a call I make for a human is
  attributed to that human without my ever transmitting their identity.
- AS a security reviewer I WANT the subject to be readable only out of a stored
  grant row bound to the presenting run token SO THAT a compromised or buggy
  agent cannot name an arbitrary principal and inherit its access.
- AS a platform operator I WANT every delegation refusal audited with a typed
  code SO THAT a misconfigured worker is diagnosable from `audit_events`
  instead of from a log grep.
- AS an API client I WANT a delegated request never to carry the `admins` group
  SO THAT delegation can never be a privilege-escalation path into admin-only
  routes.

## Acceptance criteria (EARS)

### The grant resolver (`internal/delegation`)

- WHEN a run token bound to execution `E` and work item `W` presents a grant
  ref THE SYSTEM SHALL resolve the subject from exactly one stored source,
  selected by the ref's own id prefix: `work_item_execution_requests.requested_by`
  / `requested_by_principal_id` for `xr_`, `action_approval_requests.decided_by`
  / `decided_by_principal_id` for `aar_`, `work_items.owner_principal` /
  `owner_principal_id` for `wi_`, and a `surfaceid` link's `principal` for
  `sil_`.
- WHILE resolving a grant THE SYSTEM SHALL read the subject only from the
  stored row, never from the header value, the request body, the run token, or
  any other caller-supplied input.
- WHEN a resolved grant's execution id and work item id are both different from
  the presenting run token's `ExecutionID()` and `WorkItemID()` THE SYSTEM
  SHALL refuse with `grant_not_bound` and resolve no subject.
- WHEN the presented ref names no readable grant row THE SYSTEM SHALL refuse
  with `grant_not_bound` — deliberately the same code as an out-of-scope grant,
  so the endpoint is not an existence oracle for record ids.
- WHEN a resolved grant's `*_principal_id` column is the empty string THE
  SYSTEM SHALL refuse with `grant_subject_unresolved` and SHALL NOT fall back
  to the adjacent principal string.
- WHEN a resolved grant's subject string is not a `github:`-prefixed principal
  THE SYSTEM SHALL refuse with `grant_subject_unresolved`.
- WHEN the ref is a `sil_` surface link THE SYSTEM SHALL treat the grant as
  bound only IF a `work_item_surface_refs` row exists for the run token's work
  item whose `surface` equals the link's surface and whose `actor_external_id`
  equals the link's `external_id`.
- IF the presented `sil_` link is revoked or expired THEN THE SYSTEM SHALL
  refuse with `grant_not_bound`, reusing `surfaceid.ErrLinkRevoked` /
  `ErrLinkExpired` rather than a second liveness rule.
- WHEN the work item named by a `wi_` grant, or the work item binding an
  `xr_`/`aar_` grant, is owned by a principal other than the grant's own
  subject THE SYSTEM SHALL record the **grant's** subject and SHALL NOT consult
  the work item's owner: the grant is the authority, the work item only the
  binding scope.
- IF the store backing a grant source is unconfigured or unreachable THEN THE
  SYSTEM SHALL answer HTTP 503 `delegation_unavailable` and SHALL NOT treat the
  failure as a refusal or proceed undelegated.

### The gate (`agentPrincipalGate`)

- WHEN a caller that is not an agent principal sends `X-MCTL-On-Behalf-Of` THE
  SYSTEM SHALL answer HTTP 400 `delegation_not_accepted` before any handler
  runs — including a human, a surface principal, a relayed subject, the
  `mctl-agent` service principal, the usage writer and the evidence writer.
- WHEN an agent principal sends `X-MCTL-On-Behalf-Of` on a route outside the
  delegation allowlist THE SYSTEM SHALL answer HTTP 400
  `delegation_not_supported`.
- WHEN an agent principal calls an allowlisted route without
  `X-MCTL-On-Behalf-Of` THE SYSTEM SHALL pass the request through unchanged, as
  the agent acting for itself.
- WHEN an agent principal sends a resolvable, bound grant on an allowlisted
  route THE SYSTEM SHALL replace the context user with
  `auth.NewDelegatedUser(subject, groups, actingAgent)` before the handler runs.
- WHILE a request is delegated THE SYSTEM SHALL ensure the context user's
  `Groups` never contains `admins`, its `ActingPrincipal()` is
  `agent:<name>`, its `ViaPrincipalID()` is the acting agent's `prn_`, its
  `PrincipalID()` is the grant's `SubjectPrincipalID`, and its `IsAgent()` is
  false.
- WHILE a request is delegated THE SYSTEM SHALL keep the acting agent's
  execution id, work item id and run id on the delegated user, so
  `clientmeta.go` and `mutationFor` continue to stamp `via_execution_id`.
- WHEN the tenant lookup for a delegated subject fails THE SYSTEM SHALL grant
  no tenant groups, exactly as `relaySubject` does
  (`handlers_surface_identity.go:213-221`).
- IF `auth.AttachPrincipal` for the delegated subject returns
  `ErrPrincipalDisabled` or `ErrIdentityRefused` THEN THE SYSTEM SHALL refuse
  the request rather than proceed without a principal id: delegated agent work
  fails closed where a relay degrades.
- WHEN any delegation refusal occurs THE SYSTEM SHALL write exactly one audit
  entry with `Operation = "agent_identity.delegation_refused"`,
  `Status = "failed"`, and parameters carrying the acting principal, the
  presented ref, the route, and the typed reason code.
- WHILE a request is delegated THE SYSTEM SHALL count it against the per-user
  rate-limit buckets under the subject's id, the same behaviour a surface relay
  already has via `rateLimitSubject` (`router.go:827-833`).

### Body-field refusal (`forbiddenIdentityFields`)

- WHEN any request body carries `on_behalf_of`, `subject`, `delegated_actor` or
  `acting_principal` THE SYSTEM SHALL answer HTTP 400 with the
  actor-not-accepted code on `POST /api/v1/agent-run-tokens`, on
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve`, and on every
  delegation-allowlisted route.
- WHILE refusing those keys on the dev-loop approve route THE SYSTEM SHALL
  leave the route's existing `approver`-equals-caller tolerance, its admin
  check and its EOF-tolerant decode unchanged — those belong to Slice C.

## Out of scope

- Slice C in its entirety: expressing the dev-loop approval as an `aar_`,
  tightening `requireTemporalAdmin` to `isHumanAdmin`, binding
  `mctl-agents-approve` to `approval_ref`, the
  `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` flag, and the mctl-agents-side worker
  changes (C4-C9). No change to `handlers_write.go` or to
  `requireTemporalAdmin`.
- Slice D: `GET /api/v1/identity/self`, widening `actionApprovalColumns` /
  `ActionApprovalRequest` with the stored principal-id columns (D1), and the
  `actor_kind` / `actor_name` / `subject_principal_id` / `subject_kind` /
  `agent_run_id` approval fields (D2).
- The Slice A P3 items deferred on #423.
- Anything from #374 / #422: identity federation, the refresh store, the OAuth
  token paths. `internal/auth/refreshstore`, `oauth_*.go` and
  `internal/auth/federation*.go` are not touched.
- Any new MCP tool. `internal/mcp/server_test.go`'s
  `TestNewMCPServer_ToolCount` must stay untouched.
- Any per-agent aggregate rate-limit ceiling (the analogue of
  `surfaceAggregateLimit`). Noted as a risk in design.md, not built here.

## Open questions

- **The delegation allowlist is not enumerated by the accepted proposal.** Its
  design.md only says "a route outside the delegation allowlist". We proceed
  with the narrowest set that makes C7 possible — the work-item and human-input
  routes a relayed human can already reach: `POST /work-items/{id}/intents`,
  `POST /work-items/{id}/surface-refs`,
  `POST /work-items/{id}/execution-requests`,
  `POST /human-input/{request_id}/response`, `GET /work-items/{id}`,
  `GET /human-input`, `GET /human-input/{request_id}`. Deliberately excluded:
  `POST /work-items` (creation names an owner, so there is no prior grant to
  bind to), `POST /agent-run-tokens`, `POST /agents/dev-loop/*`,
  `POST /operations/{name}/execute` and every `/surface-identities/*` route.
  A reviewer should confirm this set against what the Temporal worker will
  actually call in C7.
- **Binding for a `sil_` surface-link grant** is not stated in the accepted
  proposal — a link carries neither an execution nor a work item. We bind it
  through `work_item_surface_refs.actor_external_id`, whose own doc comment
  (`internal/workitems/types.go:237-239`) says it "resolves to a principal only
  through a SurfaceIdentityLink (mctl-api#350)". Confirm that reading.
- **Refusal statuses.** The issue specifies 400 for `delegation_not_accepted`
  and `delegation_not_supported`; design.md specifies 403 for
  `grant_not_bound` and `grant_subject_unresolved`. We follow both literally,
  which means the gate answers 400 for header/route problems and 403 for grant
  problems. `surfacePrincipalGate` answers 403 for its route-allowlist case, so
  this slice is deliberately *not* symmetric with it on that one code.
- **One code beyond the issue's list.** A nil or unreachable store must not read
  as a refusal, so we add 503 `delegation_unavailable`, modelled on
  `sidCodeUnavailable`. Confirm the name.
- **Non-GitHub subjects.** Every stored subject string today is namespaced
  (`github:`, `oidc:`, `service:`). `auth.NewRelayedUser` takes a bare GitHub
  login and sets `githubLogin: true`. We keep `NewDelegatedUser` a true sibling
  and refuse a non-`github:` subject as `grant_subject_unresolved`, rather than
  invent a delegated Dex/OIDC principal. If delegation for an OIDC human is
  wanted, it is a follow-up.
