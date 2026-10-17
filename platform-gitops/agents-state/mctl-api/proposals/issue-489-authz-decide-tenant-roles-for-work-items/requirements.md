# Tenant roles for work items, approvals, surface identities and repo sync

## Context

mctl-api#487 (the fix for #478) added a minimum tenant role to tenant writes:
the generic `POST /api/v1/operations/{name}/execute` path, custom domains,
incidents, commerce and the ERPact site actions, all through
`Handlers.requireTenantRole` in `internal/api/tenant_role.go`. Four groups of
write handlers were left out on purpose, because each needed a decision
first: work items and execution requests, action approvals and human-input
responses, surface identities, and `POST /api/v1/repos/sync`. Two related
points were also left unwritten: Dex and generic OIDC callers hold no tenant
role, and `viewer` restricts no reads.

This proposal makes a decision for each group. Where the decision is a gate,
it adds the gate and tests. Where it is no gate, it adds a sentence to the
docs saying why. When this lands, #16 can be closed against #487 and this
issue. Summary of the decisions:

| Group | Decision |
|---|---|
| Work-item mutations and execution requests (human callers) | Gate at `developer` |
| Work-item reads | No role gate. `viewer` reads (documented) |
| Snapshot seal, execution-request claim/fulfil/reject | No change. Service principal only, as today |
| Action approval decide, DevLoop approve | No tenant role. Stays human platform admin only (mctl-api#571); `owner` is not enough |
| Human-input responses | No tenant role. Stays tied to the named respondent (`actor_refs`); an answer is information, not authorization |
| Surface identities (challenge, redeem, revoke) | No tenant role. Per-principal, no tenant involved |
| `POST /repos/sync` | Gate at `developer` in mctl-api; matching portal change filed as a follow-up |
| Dex / generic OIDC callers | No change. Documented as holding no tenant role until #377/#435 |

## User stories

- AS a tenant owner I WANT a `viewer` in my tenant to be unable to create, change or request execution of work items SO THAT a read-only member cannot start paid agent runs or change shared work.
- AS a tenant developer I WANT to keep creating work items, adding intents and requesting executions SO THAT my everyday workflow is unchanged.
- AS a `viewer` I WANT to keep reading work items, their events, executions and execution requests SO THAT I can follow my tenant's work.
- AS a platform admin I WANT approvals to stay with human admins and named respondents SO THAT holding a tenant role never becomes a way to approve a side effect.
- AS a security reviewer I WANT one document listing every tenant-scoped write with its minimum role, or the reason it has none SO THAT I can audit the policy without reading every handler.

## Acceptance criteria (EARS)

Work items and execution requests

- WHEN a human caller (direct, surface-relayed or agent-delegated) sends `POST /api/v1/work-items` for a tenant they can access and their effective role on that tenant is below `developer` THE SYSTEM SHALL answer 403 with error code `tenant_role_required`, create nothing, and write a `denied` audit entry.
- WHEN a human caller whose role on the item's tenant is below `developer` sends `PATCH /api/v1/work-items/{id}`, `POST /api/v1/work-items/{id}/intents`, `/executions`, `/resume`, `/surface-refs` or `/execution-requests` for an item they can see THE SYSTEM SHALL answer 403 `tenant_role_required` and change nothing.
- WHEN the caller cannot see the work item THE SYSTEM SHALL answer 404 `work_item_not_found` before it checks any role, so the role check never reveals that an item exists.
- WHEN a human caller with role `developer` or `owner` on the item's tenant sends any of the requests above THE SYSTEM SHALL behave as it does today.
- IF the caller's role cannot be read (reader not configured, gitops read error, principal not resolved) THEN THE SYSTEM SHALL answer 503, perform no mutation, and write an `error` audit entry.
- WHILE the caller is the service principal THE SYSTEM SHALL apply the existing principal rules unchanged. The service principal is a platform admin, so the role gate passes it in every `TENANT_AUTHZ_MODE`.
- WHILE a work-item request is a read (`GET` on items, events, executions, snapshots, execution requests, evidence) THE SYSTEM SHALL NOT check a tenant role. A `viewer` who can see the item SHALL read it as today.
- WHILE a work-item idempotency key is replayed by a caller whose role was since lowered below `developer` THE SYSTEM SHALL refuse the replay with 403. The role is checked before the store is touched.

Approvals, human input and surface identities

- WHEN a tenant `owner` who is not a human platform admin sends `POST /api/v1/action-approvals/{id}/decision` or `POST /api/v1/agents/dev-loop/{workflow_id}/approve` THE SYSTEM SHALL keep refusing it with 403 `approval_decider_forbidden`, as today.
- WHEN an eligible respondent named in a request's `actor_refs` answers `POST /api/v1/human-input/{request_id}/response` THE SYSTEM SHALL accept it whatever tenant role they hold. WHEN a caller who is not named answers THE SYSTEM SHALL keep refusing it with 403 `not_eligible`, even if they are a tenant `owner`.
- WHEN a caller creates, redeems or revokes a surface identity link THE SYSTEM SHALL apply only the existing per-principal rules and check no tenant role.

Repo sync

- WHEN a non-admin caller sends `POST /api/v1/repos/sync` for a team they can access and their role there is below `developer` THE SYSTEM SHALL answer 403, not call the portal, and write a `denied` audit entry.
- WHEN a caller with role `developer` or `owner` sends `POST /api/v1/repos/sync` THE SYSTEM SHALL proxy it to the portal as today.
- IF the role cannot be read for `POST /api/v1/repos/sync` THEN THE SYSTEM SHALL answer 503 and not call the portal.

Callers without a role, and documentation

- WHILE `TENANT_AUTHZ_MODE` is `legacy` or `shadow` and the caller's sign-in did not prove a GitHub login (a Dex or generic OIDC token) THE SYSTEM SHALL refuse every role-gated write with 403, including the new gates. This is the existing `checkTenantRoleByLogin` behaviour, now written down.
- THE SYSTEM SHALL ship `docs/tenant-roles.md`. It lists every tenant-scoped write route with its minimum role, or with the reason it has none, and states that `viewer` passes no write and that no read is restricted by role.

## Out of scope

- Changing `mctl-portal`'s own repo-sync permission. This proposal files it as a follow-up issue. Until that lands, a `viewer` can still sync through the portal UI directly.
- Giving Dex or generic OIDC identities a tenant role. That belongs with #377 and #435 (membership keyed on a canonical principal).
- Adding a role check to reads, or a role finer than `viewer`/`developer`/`owner`.
- Changing who may decide action approvals or approve DevLoops (mctl-api#571), or the eligibility rules for human input (mctl-api#261).
- Moving the work-item minimum role into `internal/operations/registry.go`. Work items are not registry operations.

## Open questions

- Should `owner` instead of `developer` be required to request execution (`/execution-requests`, `/resume`)? It starts a paid run but can be recovered from. This proposal uses `developer`, the same as `trigger-issue`-style registry operations, and keeps the role in one constant so it is a one-line change.
- Is a `viewer` meant to be allowed to create a `private` work item as a personal scratch item? This proposal gates every work-item mutation alike, on the rule in `internal/operations/roles.go` that no write accepts `viewer`.
- Agent run tokens that act for no delegated human (`auth.User.AgentName()` set, no GitHub login): this proposal exempts them from the gate, on the reading that they are platform machinery like the service principal. The implementer must confirm in `internal/auth/agent.go` that such a token cannot carry a non-admin tenant scope. If it can, it should go through the gate, so that `checkTenantRoleByPrincipal` refuses it as a non-human.
- Deployed `TENANT_AUTHZ_MODE` for mctl-api could not be observed (see design.md, "Deployed state checked"). The design works in every mode, but how the rollout plays out depends on which mode is live.
