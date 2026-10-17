# Tasks: issue-489-authz-decide-tenant-roles-for-work-items

- [ ] 1. Extract the audit/log half of `requireTenantRole` in `internal/api/tenant_role.go` into `auditRoleRefusal(r, user, tenant, operation, risk, d roleRefusal)`. `requireTenantRole` calls it and keeps `writeError`. — DoD: no behaviour change; the existing `tenant_role_test.go` and `tenant_role_execute_test.go` pass unchanged.
- [ ] 2. Confirm, in `internal/auth/agent.go` and `oidc.go`, how an agent run token that acts for no delegated human is represented (`AgentName()` set, `GitHubLogin()` false) and whether it can carry non-admin tenant access. Record the answer in a comment on the helper from task 3. — DoD: a comment in code states why such callers are exempt, or that they are routed through the gate.
- [ ] 3. In `internal/api/handlers_work_items.go`, add `workItemWriteRole = operations.RoleDeveloper`, `wiCodeRoleRequired = "tenant_role_required"` and `(*Handlers).requireWorkItemRole` (depends on 1, 2). The helper exempts the service principal and undelegated agent principals, calls `checkTenantRole`, audits via `auditRoleRefusal` as `work_item.<op>`, and answers `writeErrorCode` with `tenant_role_required` (403) or `work_items_unavailable` (503). — DoD: the helper compiles and has unit tests (T1-T3).
- [ ] 4. Call `requireWorkItemRole` in `CreateWorkItem` (after `HasTenantAccess`), and in `TransitionWorkItem`, `AppendWorkItemIntent` (`handlers_work_item_intents.go`), `AttachWorkItemExecution`, `ResumeWorkItem`, `LinkWorkItemSurface` and `CreateExecutionRequest` (`handlers_execution_requests.go`), each after `visibleWorkItem` and before `mutationFor` (depends on 3). — DoD: every human work-item mutation route in `router.go` is gated; `SealWorkItemSnapshot` and claim/fulfil/reject are untouched.
- [ ] 5. In `internal/api/handlers_repos.go`, add `repoSyncRole = operations.RoleDeveloper` and call `h.requireTenantRole(..., req.Team, repoSyncRole, "repos-sync", operations.RiskLow)` in `SyncRepos` after `HasTenantAccess` and before the upstream request. Normalize the team name the same way `requireDomainRole` does. — DoD: a `viewer` gets 403 and the portal stub receives no call.
- [ ] 6. Add a short "Authorization (mctl-api#489)" comment to `handlers_action_approvals.go`, `handlers_human_input_response.go` and `handlers_surface_identity.go`. Each states that the handler checks no tenant role and why, and points to `docs/tenant-roles.md`. — DoD: comments present; no code change in these files.
- [ ] 7. Write `docs/tenant-roles.md` (depends on 4, 5). It holds the route-to-minimum-role table for every tenant-scoped write in `router.go` (#487 gates plus this proposal), "none + reason" rows for approvals, DevLoop approve, human input, surface identities, snapshot and claim/fulfil/reject, a section on `TENANT_AUTHZ_MODE` and callers without a proven GitHub login (Dex, generic OIDC, see #377/#435), and the statement that `viewer` passes no write and no read is gated by role. Link it from `docs/work-context-contract.md` "Identity and authorization" (and update that section's rule) and from the `tenant_role.go` header. — DoD: the doc exists and links resolve.
- [ ] 8. File a follow-up issue in `mctlhq/mctl-portal` to raise the `github-app-connect` repo-sync permission to `developer`, and reference it from `docs/tenant-roles.md`. — DoD: the issue link is in the doc and in the PR description.
- [ ] 9. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./...`. Note in the PR description the new 403/503 on work-item writes and repo sync, and the effect on Dex/OIDC callers. — DoD: CI green; the PR says it closes #489 and that #16 can be closed.

## Tests

Put these in `internal/api/tenant_role_test.go` next to `TestIncidentWrites_RoleGate`, reusing `stubRoles`, or in a new `tenant_role_work_items_test.go`.

- [ ] T1. `TestWorkItemWrites_RoleGate`, table-driven over create, transition, intents, executions, resume, surface-refs and execution-requests:
  - A `viewer` gets 403 `tenant_role_required`, the store is unchanged and a `denied` audit entry is written.
  - A `developer` and an `owner` succeed.
  - An admin succeeds.
  - A member with an unknown role gets 403.
  - A member not listed in the checkout gets 403.
- [ ] T2. `TestWorkItemWrites_RoleUnreadableIsUnavailable`: a nil `GitReader` or a reader error returns 503 `work_items_unavailable`, writes an `error` audit entry and leaves the store unchanged.
- [ ] T3. `TestWorkItemWrites_MachineCallersExempt`:
  - `auth.NewServiceUser()` can still attach an execution and seal a snapshot.
  - An undelegated agent principal is not refused by the role gate.
  - A delegated user (`NewDelegatedUser`) and a relayed user (`NewRelayedUser`) whose role is `viewer` are refused.
- [ ] T4. `TestWorkItemWrites_InvisibleItemIs404BeforeRole`: a caller without access to the item's tenant gets 404 `work_item_not_found`, not 403, and no role read is made (the stub counts calls).
- [ ] T5. `TestWorkItemWrites_ReplayReauthorized`: a developer creates an item with an idempotency key. Their role is then lowered to `viewer`, and the same request returns 403.
- [ ] T6. `TestWorkItemReads_ViewerAllowed`: a `viewer` can `GET` the item, its events, executions and execution requests.
- [ ] T7. `TestSyncRepos_RoleGate`, using the `handlers_repos_test.go` upstream stub:
  - A `viewer` gets 403 and the upstream receives no request.
  - A `developer` is proxied.
  - An unreadable role returns 503 with no upstream call.
- [ ] T8. `TestCheckTenantRole_DexCallerRefusedOnWorkItems` (legacy mode): a user without a proven GitHub login who holds tenant access is refused on create with 403.
- [ ] T9. Principal mode: rerun T1's viewer and developer cases with `TenantAuthzMode = TenantAuthzPrincipal` and a stub `PrincipalMembership`.
- [ ] T10. Regression guards:
  - `DecideActionApproval` by a tenant `owner` who is not an admin still returns 403 `approval_decider_forbidden`.
  - `RespondHumanInput` by an `owner` who is not in `actor_refs` still returns 403 `not_eligible`.
- [ ] T11. If tool descriptions change, update the MCP tool expectations in `internal/mcp` (`tenant_role_mcp_test.go`). The tool count does not change.

## Rollback

All changes are in-process authorization checks and docs. There is no migration and no stored state.

- To roll back, revert the PR, or redeploy the previous mctl-api image tag. Either restores membership-only authorization for work items and repo sync.
- For a partial rollback, set `workItemWriteRole` or `repoSyncRole` to the previous behaviour. There is no flag; it is a one-line revert of the call site.
- Audit entries written while the gate was live remain valid history.
- The mctl-portal follow-up is independent and can be held back separately.
