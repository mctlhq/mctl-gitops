# Design: issue-489-authz-decide-tenant-roles-for-work-items

## Current state

The role gate (mctl-api#478/#487):

- `internal/api/tenant_role.go`
  - `checkTenantRole(user, tenant, min, what)` returns a `roleRefusal`. It dispatches on `h.opts.TenantAuthzMode`:
    - `legacy` and `shadow` use `checkTenantRoleByLogin`, keyed on `user.GitHubLogin()`, which must be proven. Otherwise the result is 403 "your sign-in does not carry a tenant role".
    - `principal` uses `checkTenantRoleByPrincipal`, keyed on `user.PrincipalID()`. A non-human caller gets 403; an unresolved principal gets 503.
  - `roleGate` passes `user.IsAdmin()` first.
  - `decideWrittenRole` turns an unreadable role into 503 (`auditStatus "error"`), not a member into 403, and an unknown role into 403.
  - `requireTenantRole` wraps the check: it audits the refusal and answers with `writeError`, which carries no typed code.
  - `operationMinRole` reads `MinRole` from the registry.
- `internal/operations/roles.go`:
  - The ranking is `RoleViewer` < `RoleDeveloper` < `RoleOwner`.
  - The `RoleViewer` doc comment says "No write operation accepts it".
  - `RoleAdmin` and `RoleAuthenticated` are not tenant roles.
- Callers today: `handlers_write.go:228` (generic execute, `op.MinRole`), `handlers_domains.go`, `handlers_alerts.go` (`incidentWriteRole = operations.RoleDeveloper`), `handlers_commerce.go` (`commerceTenantRole = RoleOwner`) and `handlers_erpact_sites.go`.
- Tests: `internal/api/tenant_role_test.go`, using the `stubRoles` and `erpactMember` helpers, with per-handler `*_RoleGate` tests such as `TestIncidentWrites_RoleGate`. Also `tenant_role_execute_test.go`, `tenant_role_mcp_test.go` and `tenant_role_stub_test.go`.

The groups left out. Routes are in `internal/api/router.go`, all inside the 20/min write-budget group except the claim/fulfil/reject group.

1. **Work items** (`internal/api/handlers_work_items.go`).
   - The top-of-file comment and `docs/work-context-contract.md` ("Identity and authorization") define authorization as `IsAdmin()` or `HasTenantAccess(tenant)`, plus `visibility`.
   - `CreateWorkItem` checks `user.HasTenantAccess(body.Tenant)` and returns 403 `tenant_forbidden`.
   - `TransitionWorkItem`, `AppendWorkItemIntent` (`handlers_work_item_intents.go`), `AttachWorkItemExecution`, `ResumeWorkItem` and `LinkWorkItemSurface` call only `visibleWorkItem`, which returns 404 when the item is not visible.
   - Every work-item mutation goes through `mutationFor`, which binds the idempotency key to `principalOf(user)`.
   - `SealWorkItemSnapshot` (`handlers_work_item_snapshots.go`) already refuses anyone who is not the direct service principal.
   - Result: any tenant member, `viewer` included, can create, transition, add intents to, attach executions to, resume and link work items.
2. **Execution requests** (`internal/api/handlers_execution_requests.go`).
   - `CreateExecutionRequest` refuses the service principal (403 `execution_request_requester_forbidden`) and otherwise needs only `visibleWorkItem`.
   - `Claim`/`Fulfil`/`RejectExecutionRequest` are service principal only (`executionPlatform`).
   - A request is what makes the execution platform start a paid run.
   - Result: a `viewer` can request execution.
3. **Action approvals** (`handlers_action_approvals.go`).
   - Create and consume: direct service principal only (`isDirectService`).
   - Decide: `isHumanAdmin` only (`DecideActionApproval`, line 372); the requester of a request may not decide it.
   - `ApproveDevLoopWorkflow` (`handlers_dev_loop.go:455-471`) also requires `isHumanAdmin`.
   - No tenant role is involved: a tenant `owner` who is not a platform admin is already refused.
4. **Human-input responses** (`handlers_human_input_response.go`, `handlers_human_input.go`).
   - The respondent is derived from authentication (`callerActorRefs`) and must be one of the sealed request's `actor_refs` (`respondentRef` / `req.CanRespond`).
   - The service principal cannot answer.
   - The file header states: "An answer is information, not authorization. This endpoint never signals approve."
5. **Surface identities** (`handlers_surface_identity.go`).
   - `CreateSurfaceChallenge`/`RedeemSurfaceChallenge` link the caller's own `humanPrincipal` (a proven GitHub login; never the service principal, a surface or a relayed subject).
   - `RevokeSurfaceIdentity` lets the owner, or an admin, revoke.
   - No tenant appears in the request or in the link.
   - `relaySubject` later re-derives the linked human's tenants on every relayed request, and the result is a `NewRelayedUser` with `githubLogin: true`. So the role gate already applies to whatever a relayed human does.
6. **Repo sync** (`handlers_repos.go:143` `SyncRepos`).
   - It checks `user.HasTenantAccess(req.Team)` and proxies to `{BackstageInternalURL}/api/github-app-connect/repos/sync`. The issue states the portal plugin allows `viewer`.
   - The MCP tool `mctl_sync_repos` calls this route (`internal/mcp/server.go:1272`).
   - There is no `sync-repos` registry operation, so `operationMinRole` has nothing to read.

Identity facts the design depends on:

- `auth.NewRelayedUser` and `auth.NewDelegatedUser` (`internal/auth/oidc.go:396`, `:426`) both set `githubLogin: true` and drop the `admins` group. A gate keyed on `GitHubLogin()` therefore covers humans who reach mctl-api through Telegram or an agent delegation.
- `NewServiceUser` carries `platformAdmin: true`, so `roleGate` passes it.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/`: tenants `admins`, `karabu` and `labs`. There is no `mctl-api` service directory, because mctl-api is platform-deployed outside `services/`. Its `TENANT_AUTHZ_MODE` could **not** be observed here (gap recorded under Open questions).
- `grep role: tenants/*/values.yaml`: 9 `owner` entries, 2 `developer` entries and **no** `viewer` entries. No tenant member deployed today would be refused by a `developer` gate.
- `services/labs/mctl-telegram/values.yaml` refers to the `platform/mctl-api/surface-tokens` Vault path. Telegram is a deployed relaying surface, so relayed work-item writes are a live path. It is covered because relayed users carry a GitHub login.
- No mctl MCP tool calls were needed beyond the gitops reads. Deployed mctl-api env vars were not read.

## Proposed solution

### 1. Work-item and execution-request writes: `developer`

In `internal/api/handlers_work_items.go`:

- Add the constant `workItemWriteRole = operations.RoleDeveloper` with a comment linking #489. Its value is the same as `incidentWriteRole`.
- Add a typed code `wiCodeRoleRequired = "tenant_role_required"`.
- Add a helper:

  ```go
  // requireWorkItemRole gates a human work-item write on the tenant role.
  // Machine principals keep their existing principal rules.
  func (h *Handlers) requireWorkItemRole(w http.ResponseWriter, r *http.Request, user *auth.User, tenant, op string) bool
  ```

  The helper:
  - Returns true without a check for `user.IsService()`, and for an agent principal that is not acting for a delegated human (`AgentName()` set and `GitHubLogin()` not proven; see Open questions). Both are platform machinery governed by their own rules (snapshot seal, executionPlatform, delegation binding).
  - Otherwise calls `h.checkTenantRole(user, tenant, workItemWriteRole, "work item "+op)`.
  - On a refusal, writes the audit entry in the same shape as `requireTenantRole` (`Operation: "work_item."+op`, `Status: d.auditStatus`, `RiskLevel: RiskLow`, `Message: d.detail`, `Parameters{"tenant"}`). It answers `writeErrorCode(w, d.status, code, d.message, nil)`, where code is `wiCodeRoleRequired` for a 403 and `wiCodeUnavailable` for a 503. This keeps the typed codes clients of the work-item API branch on.
  - Refactor: extract the audit and log half of `requireTenantRole` into `auditRoleRefusal(r, user, tenant, operation, risk, d)` so the two do not drift. `requireTenantRole` then calls it and keeps `writeError`.

Call sites, all placed **after** `visibleWorkItem` (or, for create, after the `HasTenantAccess` check) and **before** `mutationFor` or any store call:

- `CreateWorkItem` with `body.Tenant`.
- `TransitionWorkItem`, `AppendWorkItemIntent`, `AttachWorkItemExecution`, `ResumeWorkItem`, `LinkWorkItemSurface` and `CreateExecutionRequest`, each with `item.Tenant`.

This order means:

- A caller who cannot see the item still gets 404, so nothing leaks.
- A replay of an idempotency key is re-authorized.
- A refusal touches no state.

`SealWorkItemSnapshot` and the claim/fulfil/reject handlers are not changed: they are already service-only.

Update the header comment of `handlers_work_items.go` and `docs/work-context-contract.md` "Identity and authorization" to say that reads need tenant access and visibility, and that human writes also need `developer`.

Why `developer` rather than `owner`:

- A work item and an execution request are ordinary and recoverable. A transition can be superseded, a run can be rejected or abandoned.
- `roles.go` reserves `owner` for destructive or `RiskHigh` actions.
- `viewer` must pass no write.

### 2. Approvals, human input, surface identities: no tenant gate, documented

- **Action approval decide / DevLoop approve**: stays `isHumanAdmin`. A tenant role must not be a way in. An approval authorizes a hashed side effect, often on the platform's own repos, and #571 deliberately makes it a platform human act. Adding "or tenant owner" would widen authority. Adding "and tenant owner" means nothing for an admin, because admins pass every role.
- **Human-input responses**: stay tied to `actor_refs`. The request names who may answer, and the answer is information the workflow validates, never approval. A role check would refuse someone the workflow explicitly asked, or admit someone it did not.
- **Surface identities**: a link binds a surface-native id to the caller's own principal. It carries no tenant, and every relayed request re-derives tenants and roles from the linked human (`relaySubject`, then `checkTenantRole` on whatever write follows). There is no tenant to gate on.
- Each decision gets one sentence in `docs/tenant-roles.md`, and a short comment at the top of the respective handler file pointing to it.

### 3. Repo sync: `developer`

In `handlers_repos.go`:

- Add `repoSyncRole = operations.RoleDeveloper`.
- In `SyncRepos`, after the `HasTenantAccess` check and before the upstream request is built, call `h.requireTenantRole(w, r, user, req.Team, repoSyncRole, "repos-sync", operations.RiskLow)`.
- Use `normalizeIdentifier(req.Team)` if the domain handlers do; match `requireDomainRole`.

Rationale: a sync registers repositories against the team, and those repositories are what `onboard`/`deploy` (`developer`) build from. It is a write, so `viewer` must not pass it.

Keeping the portal in step: open a follow-up issue in `mctlhq/mctl-portal` to raise its `github-app-connect` sync permission to `developer`. Until that lands, the API is the stricter of the two, which is the safe direction.

### 4. Dex / OIDC callers and read-only `viewer`: documented

No code change. `docs/tenant-roles.md` states the following:

- In `legacy`/`shadow` mode a role is read by a proven GitHub login. A Dex or generic OIDC token has none and is refused on every role-gated write. `principal` mode (#377) reads it by `prn_` instead. Giving such identities roles belongs with #377/#435.
- `viewer` passes no write. No read is gated by role, by design.

### 5. `docs/tenant-roles.md`

A new document with one table. Columns: route, handler, minimum role or "none", and reason. It covers every tenant-scoped write route in `router.go`: the existing #487 gates and the decisions above. It also has a short section on modes and on callers without a role. Link it from `docs/work-context-contract.md` and from the `tenant_role.go` header comment.

## Alternatives

- **Keep work items at membership only, and gate just `execution-requests` and `resume`.**
  - This only blocks the paid part.
  - Dropped: it leaves `viewer` able to transition, supersede or cancel shared tenant work, which contradicts `RoleViewer`'s "no write accepts it". It also needs two policies to explain instead of one.
- **Require `owner` for approvals, in addition to or instead of the named approver.**
  - Dropped: "instead of" widens approval authority to every tenant owner, against #571. "In addition to" is a no-op for the human admins who are the only deciders. For human input, the named respondent is the stronger and more precise rule.
- **Put work items and repo sync into the operations registry so `operationMinRole` supplies the role.**
  - Dropped: they are not Argo operations. Registering fake entries would surface them in `mctl_list_operations` and the portal allowlist tests. A named constant next to `incidentWriteRole` is the established pattern for non-registry writes.
- **Repo sync: keep `viewer` to stay in step with the portal.**
  - Dropped: being in step with a too-permissive rule is not a goal. The API can tighten on its own, and the portal follows.

## Platform impact

- **Migrations**: none. No store schema changes.
- **Backward compatibility**:
  - New 403s are returned only to members whose effective role is below `developer`, meaning `viewer` or an unknown role. Deployed tenants have no `viewer` entries today (see Current state).
  - Callers without a proven GitHub login in legacy/shadow mode would start getting 403 on work-item writes and repo sync. Such a caller, for example a Dex-authenticated human creating work items, is a behaviour change. No known caller is affected (the issue says so, and Telegram and agent delegation carry GitHub logins), but this must be called out in the release note.
  - The new error code `tenant_role_required` is additive.
- **Availability**:
  - A gitops reader outage now turns work-item writes and repo sync into 503 where they used to succeed. This is the same fail-closed contract as every other gate.
  - The role read is an in-memory checkout lookup, so the per-request cost is negligible.
- **Risks and mitigations**:
  1. Breaking a machine caller of work items (mctl-agents dispatcher, agent run tokens). Mitigation: the service principal passes as an admin, agent principals with no delegated human are explicitly exempt, and a test asserts each.
  2. Leaking item existence through 403. Mitigation: the gate runs after `visibleWorkItem`, and a test asserts 404 for an invisible item from a `viewer` of another tenant.
  3. Portal/API drift on repo sync. Mitigation: a follow-up issue in mctl-portal.
- **Shadow mode**: `checkTenantRole` already calls `shadowTenantRole`, so the new call sites also feed the principal-mode comparison metrics with no extra work.
