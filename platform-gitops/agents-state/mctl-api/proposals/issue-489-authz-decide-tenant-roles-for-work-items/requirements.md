# Tenant roles for work items, approvals, surface identities and repo sync

## Context

mctl-api#487 (the fix for #478) added a per-request tenant role gate
(`checkTenantRole` / `requireTenantRole` in `internal/api/tenant_role.go`,
roles in `internal/operations/roles.go`). It covers `POST
/operations/{name}/execute`, custom domains, incidents and the ERPact owner
actions. Four groups of write handlers were deliberately left out because a
tenant role does not map onto them without a decision: work items and
execution requests, action approvals and human-input responses, surface
identities, and `POST /api/v1/repos/sync`. Two cross-cutting points are also
unstated: callers signed in through Dex or generic OIDC hold no tenant role,
and reads are not restricted by role.

Issue #489 asks for one decision per group and, for each, either a gate with
tests or a documented reason for having none. This proposal makes those
decisions: every tenant-scoped write in the work-item and repo-sync groups
gets a `developer` minimum; approvals, human-input responses and surface
identities stay on their existing (stricter or principal-scoped) rules with
no tenant role; and a new `docs/tenant-roles.md` records every decision,
including the Dex/OIDC gap and the "reads are not role-gated" rule. That
lets #16 be closed against #487 and this change.

## User stories

- AS a tenant owner I WANT a `viewer` in my tenant to be unable to create,
  change or start work items SO THAT read-only members cannot spend agent
  runs or change shared work.
- AS a tenant developer I WANT to keep creating work items, adding intents,
  transitioning them and requesting their execution SO THAT the role gate
  does not get in the way of ordinary work.
- AS a tenant owner I WANT only `developer` or above to sync repositories
  into my tenant SO THAT a viewer cannot widen the set of repositories the
  tenant may build.
- AS a platform operator I WANT one document listing, for every write
  handler group, which tenant role it needs or why it needs none SO THAT
  the authorization model can be reviewed without reading every handler.
- AS a caller signed in through Dex or generic OIDC I WANT a clear refusal
  message SO THAT I know to sign in with a GitHub-linked account.

## Acceptance criteria (EARS)

Work items and execution requests

- WHEN a non-admin caller sends `POST /api/v1/work-items` for a tenant they
  belong to AND their effective role on that tenant is `viewer` THE SYSTEM
  SHALL answer 403 with typed code `tenant_role_forbidden`, write no work
  item, and record a `denied` audit entry.
- WHEN a non-admin caller whose effective role is `developer` or `owner`
  sends any of `POST /work-items`, `PATCH /work-items/{id}`, `POST
  /work-items/{id}/intents`, `POST /work-items/{id}/executions`, `POST
  /work-items/{id}/resume`, `POST /work-items/{id}/surface-refs` or `POST
  /work-items/{id}/execution-requests` THE SYSTEM SHALL behave exactly as
  before this change.
- IF the caller may not see the work item named by `{id}` THEN THE SYSTEM
  SHALL answer 404 `work_item_not_found` before any role check, so the role
  gate never discloses that an item exists.
- IF the caller's role cannot be read (gitops reader missing or failing)
  THEN THE SYSTEM SHALL answer 503 with typed code
  `tenant_role_unavailable` and perform no write.
- IF the caller has no GitHub-proven login (Dex or generic OIDC) and is not
  a platform admin THEN THE SYSTEM SHALL refuse every gated work-item write
  with 403 `tenant_role_forbidden` and a message telling them to sign in
  with their GitHub-linked account.
- WHILE a request is relayed by a surface principal or delegated by an
  agent run token THE SYSTEM SHALL check the role of the relayed or
  delegated human subject, not of the surface or agent.
- WHILE the caller is a platform admin (including the service principal,
  which carries the `admins` group) THE SYSTEM SHALL pass the work-item
  role gate.
- WHEN `POST /work-items/{id}/executions/{execution_id}/snapshot` is called
  THE SYSTEM SHALL keep its existing service-principal-only rule and SHALL
  NOT add a tenant role check.

Approvals, human input, surface identities

- WHEN `POST /api/v1/action-approvals/{id}/decision` is called THE SYSTEM
  SHALL keep requiring a human platform admin acting directly
  (`isHumanAdmin`) and SHALL NOT accept a tenant `owner` in its place.
- WHEN `POST /api/v1/human-input/{request_id}/response` is called THE SYSTEM
  SHALL keep requiring that the caller's `github:<login>` is in the
  request's `requested_from.actor_refs` and SHALL NOT add a tenant role
  check.
- WHEN a surface identity challenge, redeem or revoke is called THE SYSTEM
  SHALL keep its per-principal rules and SHALL NOT add a tenant role check.

Repository sync

- WHEN a non-admin caller sends `POST /api/v1/repos/sync` for a team whose
  effective role is below `developer` THE SYSTEM SHALL answer 403, SHALL NOT
  proxy the request to the portal plugin, and SHALL record a `denied` audit
  entry.
- WHEN a caller with `developer` or `owner` on the team sends `POST
  /api/v1/repos/sync` THE SYSTEM SHALL proxy it to the portal plugin as
  before.

Documentation

- THE SYSTEM SHALL ship `docs/tenant-roles.md` stating, for every write
  handler group named in #489 and #487, the minimum tenant role or the
  reason it has none; that `viewer` passes no write; that reads are not
  restricted by tenant role; and that Dex and generic OIDC callers hold no
  tenant role until #377 / #435.
- THE SYSTEM SHALL update the "Identity and authorization" section of
  `docs/work-context-contract.md` to state the `developer` minimum on
  work-item writes and link to `docs/tenant-roles.md`.

## Out of scope

- Changing the portal's `github-app-connect` plugin (mctl-portal) to require
  `developer` on its own sync route. A follow-up issue is filed there; this
  repository only gates the mctl-api route.
- Giving Dex or generic OIDC identities a tenant role, or keying membership
  on a canonical principal (#377, #435).
- Any role restriction on reads (GET routes, MCP read tools).
- Changing who may decide action approvals or approve DevLoop workflows.
- New MCP tools; MCP work-item and repo tools proxy the REST routes and
  inherit the gate unchanged.

## Open questions

- Repo sync: the issue offers "keep in step with the portal" or "raise both
  to developer". This proposal raises the mctl-api route to `developer` and
  leaves the portal change to a follow-up in mctl-portal, so for a while the
  two disagree (the portal UI would still let a viewer sync). The portal
  plugin's current rule could not be verified from this repository; it is
  taken from the issue text. Deployed state shows no `viewer` member in any
  tenant today, so the window has no affected user.
- A private work item's owner who is later downgraded to `viewer` loses
  write access to their own item. This proposal treats that as intended
  (role is read per request, like #487); a reviewer may prefer an
  owner-of-item exception.
- An idempotent replay of a create by a caller who has since become a
  viewer is refused rather than replayed, because the gate runs before the
  store. Treated as acceptable.
