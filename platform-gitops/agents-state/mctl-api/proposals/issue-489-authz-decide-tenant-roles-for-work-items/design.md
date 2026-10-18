# Design: issue-489-authz-decide-tenant-roles-for-work-items

## Current state

The tenant role gate (#478 / #487) lives in `internal/api/tenant_role.go`:

- `Handlers.checkTenantRole(user, tenant, min, what)` dispatches on `opts.TenantAuthzMode`:
  - `TenantAuthzPrincipal` uses `checkTenantRoleByPrincipal`. It reads `opts.PrincipalMembership.MemberRolesForPrincipal(tenant, prn)` (`internal/gitops/principal_membership.go:157`). It refuses a non-human `Identity()` with 403 and an unresolved human principal with 503.
  - Legacy and shadow use `checkTenantRoleByLogin`. It needs `user.GitHubLogin()` and reads `GitReader.MemberRoles`. Shadow also calls `shadowTenantRole`.
  - Both start with `roleGate`: `IsAdmin()` passes, `RoleAdmin` refuses non-admins, and a non-tenant minimum is a 500. `decideWrittenRole` maps "not listed", "unknown role" and "insufficient" to 403, and "could not read" to 503.
- `requireTenantRole` audits and writes `writeError(status, message)`. Existing per-handler constants: `incidentWriteRole = operations.RoleDeveloper` (`handlers_alerts.go:35`) and `commerceTenantRole = operations.RoleOwner` (`handlers_commerce.go:61`).
- The header comment of `tenant_role.go` still describes the legacy rule: "Dex or other OIDC token ... has no role here". In principal mode such a human has a role through its `prn_` membership (`TestZitadelOnlyPrincipal_TenantRole` in `internal/api/tenant_authz_principal_test.go` already proves this).

Work items (`internal/api/handlers_work_items.go`, `handlers_execution_requests.go`, `handlers_work_item_snapshots.go`), routes in `internal/api/router.go:590-640`:

- `CreateWorkItem` checks only `user.HasTenantAccess(body.Tenant)`, then 403 `tenant_forbidden`.
- `TransitionWorkItem`, `AppendWorkItemIntent`, `AttachWorkItemExecution`, `ResumeWorkItem`, `LinkWorkItemSurface` and `CreateExecutionRequest` check only `visibleWorkItem`, then `canSeeWorkItem`: admin, or tenant access plus (`VisibilityTenant` or `OwnerPrincipal == principalOf(u)`). So today a `viewer` can do all of these writes.
- `CreateExecutionRequest` refuses `user.IsService()` (`requester_forbidden`). Claim, fulfil and reject need `isDirectService`. `SealWorkItemSnapshot` needs `user.IsService()` and no relay.

Identity shapes (`internal/auth`):

- `NewServiceUser()` (`oidc.go:192`) has `platformAdmin: true`, so it passes `roleGate`.
- `NewAgentUser` (`agent.go:76`) is "never an admin, belongs to no tenant". `PrincipalAuthz.Apply` (`principal_authz.go`) sets `Groups = nil` for every non-human that is not service or dev. So an undelegated agent token has no `HasTenantAccess` on any tenant, and `visibleWorkItem` already returns 404 for it. Its `Identity().Kind` is `KindAgent`, so `checkTenantRoleByPrincipal` would refuse it with 403 if it ever got that far.
- Delegated subjects (`NewDelegatedUser`, `NewDelegatedPrincipalUser`, `oidc.go:448` and the following code) are human and carry the human's principal (`tokenPrincipal`). They drop "admins". `delegationRoutes` (`handlers_agent_identity.go:95`) allows delegation on `POST .../intents`, `.../surface-refs`, `.../execution-requests` and `/human-input/{id}/response`.
- Relayed subjects (`NewRelayedUser`, `NewRelayedPrincipalUser`) are human, drop "admins", and carry `relaySurface`.
- A ZITADEL-only human is `NewFederatedUser(..., KindHuman)` with a principal and no GitHub login.

Other groups:

- Action approvals (`handlers_action_approvals.go`): deciding needs `isHumanAdmin` (lines 66, 372). Creating needs `isHumanAdmin || isDirectService` (310).
- Human input (`handlers_human_input.go:130`, `handlers_human_input_response.go`): the respondent must match `actor_refs` through `callerActorRefs` / `respondentRef`.
- Surface identities (`handlers_surface_identity.go`, `handlers_identity_link.go`): per-principal.
- `SyncRepos` (`handlers_repos.go:143`) checks `HasTenantAccess(req.Team)` and then proxies to `{BackstageInternalURL}/api/github-app-connect/repos/sync`. There is no role check. MCP `mctl_sync_repos` calls this route (`internal/mcp/server.go:1272`).
- There is no `docs/tenant-roles.md` today.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/tenants/*/values.yaml` lists six tenants: admins, commerce-proof, erpact, karabu, labs, mctl. Every `members[]` entry has a `principalId` and role `owner` or `developer`. There are no `viewer` entries. erpact: mashkovd, obukhov23 = owner; grerik, octongues = developer. labs: mashkoffdmitry, mashkovd = owner. The comment in the labs values says the owner signs in through ZITADEL and is mapped to that login. All other tenants have a single owner.
- `grep -i viewer tenants/` returned nothing.
- `mctl_get_service_config team=admins service=mctl-api` returned an error: "service not found: admins/mctl-api". `grep TENANT_AUTHZ_MODE services/` found nothing. **Not observed:** the deployed `TENANT_AUTHZ_MODE`. The owner's statement (principal since 2026-10-17) is taken as given.
- **Not observed:** ZITADEL `customers` org membership. No tool in this run reads it.

## Proposed solution

### 1. Role constants (one place each)

In `internal/api/tenant_role.go`, next to the existing gate:

```go
// workItemWriteRole is the minimum tenant role for every work-item write a
// person or surface makes (mctl-api#489). viewer passes no write, private
// items included.
const workItemWriteRole = operations.RoleDeveloper
// workItemExecutionRole is the minimum for asking the platform to run work:
// POST /work-items/{id}/execution-requests and /resume. One constant for
// both (owner decision on #489).
const workItemExecutionRole = operations.RoleDeveloper
// reposSyncRole is the minimum for POST /repos/sync. The portal plugin must
// match it.
const reposSyncRole = operations.RoleDeveloper
```

### 2. Work-item gate helper

Add `func (h *Handlers) requireWorkItemRole(w, r, user, tenant string, min operations.Role, operation string) bool` in `handlers_work_items.go`. It calls `h.checkTenantRole(user, tenant, min, "work item "+operation)`. On a refusal it logs the audit entry the same way `requireTenantRole` does (`operation`, tenant, `auditStatus`, detail). It answers with `writeErrorCode` and a typed code, so that work-item clients keep machine-readable errors:

- `wiCodeRoleForbidden = "tenant_role_forbidden"` for 403.
- `wiCodeRoleUnavailable = "tenant_role_unavailable"` for 503.
- The 500 (no minimum configured) keeps `writeError`.

To avoid two audit/log code paths, extract the audit+log part of `requireTenantRole` into `auditRoleRefusal(r, user, tenant, operation, risk, d)`. Both helpers use it.

Call sites. The check always runs after the 404 visibility check and before the body decode and any store call:

| Handler | Tenant | Min |
|---|---|---|
| `CreateWorkItem` | `body.Tenant`, after `HasTenantAccess` | `workItemWriteRole` |
| `TransitionWorkItem` | `item.Tenant` | `workItemWriteRole` |
| `AppendWorkItemIntent` | `item.Tenant` | `workItemWriteRole` |
| `AttachWorkItemExecution` | `item.Tenant` | `workItemWriteRole` |
| `LinkWorkItemSurface` | `item.Tenant` | `workItemWriteRole` |
| `ResumeWorkItem` | `item.Tenant` | `workItemExecutionRole` |
| `CreateExecutionRequest` | `item.Tenant`, after the `IsService` refusal and `visibleWorkItem` | `workItemExecutionRole` |

The create body must be decoded before its tenant is known, so the check in `CreateWorkItem` runs right after the existing `HasTenantAccess` check and before `mutationFor` and `Create`.

No gate is added on `SealWorkItemSnapshot` or on claim/fulfil/reject. They already require the service principal, which is stricter. A comment says so.

### 3. Machine-caller exemption, keyed on the principal

No new predicate is needed. The exemption already follows from the principal:

- The service principal is `platformAdmin`, so `roleGate` passes it in every mode.
- An agent token acting for no human principal is `KindAgent`, has no tenant groups, and gets 404 at `visibleWorkItem` / `tenant_forbidden` at create before the gate. If a future token of this kind carried a non-admin tenant scope, it would reach `checkTenantRoleByPrincipal` and be refused as non-human. That matches the owner's rule.
- A delegated or relayed request is decided as the human principal it names.

The implementer writes this as a comment on `requireWorkItemRole`, citing `auth.NewAgentUser`, `PrincipalAuthz.Apply` and `NewDelegatedPrincipalUser`. No `GitHubLogin()` check appears anywhere in the new code. A unit test pins down each part of the exemption (T5, T6), so a later change to the agent token shape fails a test instead of silently granting a role.

### 4. `POST /repos/sync`

In `SyncRepos`, after `HasTenantAccess(req.Team)`, call `h.requireTenantRole(w, r, user, req.Team, reposSyncRole, "repos-sync", operations.RiskLow)`. Return before building the upstream request. The response body format changes from the `http.Error` JSON string to `writeError`, which has the same `{"error": ...}` shape.

### 5. Documentation

Add `docs/tenant-roles.md`:

- **Modes.** `principal` is current: the role is read from `members[].principalId` and `role`, and holds for GitHub, ZITADEL and other OIDC humans alike. `legacy` and `shadow` are rollback modes: login-keyed, and in those modes a Dex or generic OIDC human holds no tenant role and is refused on every role-gated write.
- **Role table.** `viewer` passes no write. `developer` covers ordinary writes, work items, execution requests, repo sync and incidents. `owner` covers destructive, RiskHigh and commerce writes. Operation minimums are listed in `internal/operations/registry.go`.
- **Ungated writes, and why:**
  - Action-approval decisions are human platform admin only (#571). A tenant `owner` cannot approve.
  - Human-input responses are tied to the request's `actor_refs`.
  - Surface identities and surface principals are per-principal identity binding, unrelated to tenants.
  - Snapshot sealing and claim/fulfil/reject are service principal only.
- **Reads** are never role-gated. Membership (plus work-item visibility) is the only read check.
- **Machine callers.** The exemption as described in section 3.

Update the header comment of `internal/api/tenant_role.go` so that the "Dex or other OIDC token ... is refused" paragraph is scoped to legacy/shadow mode, and principal mode is described as current.

### 6. Release note

Based on the GitOps membership read above, no member holds `viewer`. So no listed member starts getting 403 from these gates. The release note states this, lists the members by tenant with their roles, and says that the ZITADEL `customers` org was not observable from the proposal run. It must be re-checked against `TryNamespacesForPrincipal` output at release time.

## Alternatives

1. **Require `owner` for execution requests and resume.** Dropped. The owner chose `developer`. Execution is recoverable and already bounded by the platform's own checks (one open request, state version).
2. **Exempt machine callers with "`AgentName()` set and `GitHubLogin()` not proven".** Dropped. This is a legacy predicate. In principal mode a ZITADEL human has no GitHub login, and a delegated human is not `AgentName()`. Keying on `IsAdmin`/service plus `Identity().Kind` is correct in every mode, and it is what `checkTenantRoleByPrincipal` already does.
3. **Reuse `requireTenantRole` unchanged for work items.** Dropped. Its `writeError` response has no typed code, and the work-item API contract (`docs/work-context-contract.md`) uses typed codes everywhere. A thin wrapper that shares the audit path keeps one decision and one audit format.
4. **Gate action-approval decisions on tenant `owner`.** Dropped by the owner. #571 deliberately ties approval to a human platform admin, and a tenant role would widen it.

## Platform impact

- **Migrations:** none. There is no schema change and no new env var.
- **Backward compatibility:** `developer` and `owner` members are unaffected. A `viewer` member, of whom none are deployed, loses work-item writes and repo sync. A caller whose role cannot be read now gets 503 on these routes, where before the write went through. This fails closed, like every other gated write.
- **Cost:** in principal mode, one membership read per gated write, from the in-memory gitops checkout that already serves `HasTenantAccess`. Negligible.
- **Risks and mitigations:**
  - A service-run path that is not the service principal could be broken (for example a worker using a non-admin token to attach executions). Mitigation: T5/T6, and a check of current callers of `/executions` and `/resume`. In this codebase they are service-only, because agents have no tenant access.
  - The portal and the API could disagree on repo sync until the companion portal issue lands. mctl-api is the stricter one, so this does not widen access.
  - The shadow comparison logs a disagreement for every new gate in shadow mode. This is expected, and it is the reason shadow mode exists.
- **MCP:** no tool is added or removed, so the `server_test.go` count is unchanged.
