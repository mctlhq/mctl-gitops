# Tenant roles for work items, execution requests, approvals and repo sync

## Context

mctl-api#487 (the fix for #478) added a minimum tenant role check to tenant writes: everything sent to `POST /api/v1/operations/{name}/execute`, custom domains, incidents, commerce and the ERPact owner actions. All of them go through `Handlers.checkTenantRole` / `requireTenantRole` in `internal/api/tenant_role.go`. Four groups of write handlers were left out on purpose, because they needed a design decision first: work items and execution requests, action approvals and human-input responses, surface identities, and `POST /api/v1/repos/sync`. Issue #489 asks for a decision on each group. Each decision ends in either a gate with tests, or a line in the docs that says why there is no gate.

The owner has accepted the decision matrix. `developer` is required for work-item writes, execution requests and `POST /repos/sync`. Reads get no role gate. Action approvals stay with human platform admins only (#571). Human-input responses stay tied to `actor_refs`. Surface identities carry no tenant role. The live authorization mode is `TENANT_AUTHZ_MODE=principal`, deployed since 2026-10-17 (#377). So this proposal treats principal mode as the primary path, where the role is read by `prn_` principal through `checkTenantRoleByPrincipal`. Legacy and shadow modes are rollback modes and are kept as regression rows. The machine-caller exemption depends on what the principal is, not on whether a GitHub login is present.

## User stories

- AS a tenant owner I WANT a `viewer` in my tenant to be unable to create, change or run work items SO THAT read-only members stay read-only on every write path, not only on operations.
- AS a tenant developer I WANT to keep creating work items, adding intents, linking surfaces and requesting executions in my tenant SO THAT my daily workflow is unchanged.
- AS a human who signs in only through ZITADEL (no GitHub login) I WANT my role to come from my `prn_` membership SO THAT I am treated exactly like a GitHub-linked member with the same role.
- AS the execution platform (the service principal) I WANT to keep attaching executions, resuming, claiming, fulfilling and sealing snapshots SO THAT the gate does not break the run loop.
- AS a platform operator I WANT `docs/tenant-roles.md` to say which writes need which role, which have no role gate and why, and which authorization mode is current SO THAT #16 can be closed and nobody has to read the code to find the policy.
- AS a portal user I WANT `POST /repos/sync` to need the same role in mctl-api and in the portal plugin SO THAT the two surfaces do not disagree.

## Acceptance criteria (EARS)

Principal mode (primary path):

- WHILE `TENANT_AUTHZ_MODE=principal`, WHEN a human caller sends `POST /api/v1/work-items`, `PATCH /api/v1/work-items/{id}`, `POST /api/v1/work-items/{id}/intents`, `POST /api/v1/work-items/{id}/executions`, `POST /api/v1/work-items/{id}/resume`, `POST /api/v1/work-items/{id}/surface-refs` or `POST /api/v1/work-items/{id}/execution-requests` for a tenant, THE SYSTEM SHALL read that caller's role on the tenant by principal id (`MemberRolesForPrincipal`) and require at least `developer`.
- WHILE in principal mode, IF the caller's effective role on the tenant is `viewer`, THEN THE SYSTEM SHALL answer 403 with the typed code `tenant_role_forbidden`, write a `denied` audit entry, and change nothing in the work-items store. This includes creating a `private` work item.
- WHILE in principal mode, IF the caller is a human signed in only through ZITADEL (or another federated OIDC provider) whose `prn_` membership gives `developer` or `owner`, THEN THE SYSTEM SHALL allow the write, with no GitHub login needed.
- WHILE in principal mode, IF a ZITADEL-only human with role `viewer` calls any gated route directly, through a surface relay (`NewRelayedPrincipalUser`), or through an agent delegation (`NewDelegatedPrincipalUser`, `X-MCTL-On-Behalf-Of`), THEN THE SYSTEM SHALL refuse with 403 `tenant_role_forbidden`.
- IF the role cannot be read (the membership reader is missing or fails, or a human's principal is unresolved), THEN THE SYSTEM SHALL answer 503 with the code `tenant_role_unavailable` and an `error` audit entry, and SHALL NOT perform the write.
- IF the caller cannot see the work item (it is in another tenant, or it is someone else's private item), THEN THE SYSTEM SHALL answer 404 `work_item_not_found` before the role check runs, so that a role refusal never confirms that an item exists.
- WHEN a caller sends `POST /api/v1/repos/sync` for a team, THE SYSTEM SHALL require at least `developer` on that team before proxying to the portal plugin, and SHALL NOT send any upstream request when it refuses.

Machine callers:

- WHEN the caller is the service principal (`auth.NewServiceUser`, a platform admin), THE SYSTEM SHALL pass the role gate, so that attach-execution, resume, snapshot sealing and claim/fulfil/reject behave as they do today.
- WHILE an agent run token acts for no human (no `X-MCTL-On-Behalf-Of`), THE SYSTEM SHALL give it no tenant role. Today such a token holds no tenant groups (`auth.NewAgentUser`; `PrincipalAuthz.Apply` clears groups for non-humans), so it never reaches a tenant work item. IF a future token of this kind carries a non-admin tenant scope, THEN THE SYSTEM SHALL send it through the gate, where it is refused as a non-human caller.
- WHEN an agent token delegates for a human, THE SYSTEM SHALL decide the role of the delegated human principal, not the agent's.

Rollback modes (regression):

- WHILE `TENANT_AUTHZ_MODE=legacy` or `shadow`, THE SYSTEM SHALL decide the same routes with the login-keyed decision (`checkTenantRoleByLogin`). In shadow mode it SHALL also record the principal comparison through `shadowTenantRole`.

Ungated groups (documented):

- WHILE handling `POST /api/v1/action-approvals/{id}/decision`, THE SYSTEM SHALL keep the existing human-platform-admin-only rule (`isHumanAdmin`), and SHALL NOT let any tenant role, `owner` included, approve.
- WHILE handling `POST /api/v1/human-input/{request_id}/response`, THE SYSTEM SHALL keep authorization tied to the request's `actor_refs` (`callerActorRefs` / `respondentRef`), with no tenant role check.
- WHILE handling `/api/v1/surface-identities/*` and `/api/v1/surface-principals/*`, THE SYSTEM SHALL keep per-principal authorization with no tenant role check.
- WHILE handling any GET route, THE SYSTEM SHALL NOT check a tenant role. Tenant membership (and per-item visibility for work items) stays the only read check.

## Out of scope

- Changing the minimum role of any operation already gated by #487.
- Changing the portal plugin (`/api/github-app-connect/repos/sync` in the portal repo) itself. This proposal raises mctl-api to `developer` and requires a companion issue for the portal, so that both surfaces match (see Open questions).
- Membership keyed on a canonical principal for legacy mode (#377, #435). Principal mode already provides it.
- Role checks on reads, and any new role beyond `viewer` / `developer` / `owner`.
- Changes to the execution platform's claim/fulfil/reject (service principal only) and to snapshot sealing (service only). Both are already stricter than `developer`.
- Changes to the MCP tool count. The MCP work-item and repo-sync tools call the REST routes and inherit the gate.

## Open questions

- The deployed value of `TENANT_AUTHZ_MODE` could not be observed from this run: the mctl-api Helm values are not in the gitops checkout given here, and `mctl_get_service_config admins/mctl-api` returned "service not found". The owner says principal mode is live, and this proposal takes that as given.
- ZITADEL `customers` org membership could not be listed from this run. In principal mode an org membership grants no tenant role without a GitOps `principalId` entry, so the release-note list comes from the GitOps members lists. If a customer principal gets a tenant through some other channel, the list must be re-checked before release.
- The portal plugin currently allows `viewer` on repo sync. mctl-api will refuse `viewer` first. Until the portal is raised too, a viewer who calls the portal plugin directly can still sync. The implementer should open the companion portal issue and link it from the docs.
