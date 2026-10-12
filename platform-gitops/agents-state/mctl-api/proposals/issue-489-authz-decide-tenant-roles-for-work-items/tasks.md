# Tasks: issue-489-authz-decide-tenant-roles-for-work-items

- [ ] 1. Factor the audit-and-log half of `requireTenantRole` in
  `internal/api/tenant_role.go` into `auditRoleRefusal(r, user, tenant,
  operation, risk, d roleRefusal)`; `requireTenantRole` calls it. — DoD:
  no behaviour change; `tenant_role_test.go`, `tenant_role_execute_test.go`
  and `tenant_role_mcp_test.go` pass unchanged.
- [ ] 2. In `internal/api/handlers_work_items.go`, add `workItemWriteRole =
  operations.RoleDeveloper`, typed codes `tenant_role_forbidden` /
  `tenant_role_unavailable`, and `requireWorkItemRole` (uses
  `checkTenantRole` + `auditRoleRefusal` + `writeErrorCode`). (depends on
  1) — DoD: compiles; 403 maps to `tenant_role_forbidden`, 503 to
  `tenant_role_unavailable`, 500 keeps a generic code.
- [ ] 3. Call `requireWorkItemRole` in `CreateWorkItem` (after
  `HasTenantAccess`, before `mutationFor`) and, right after
  `visibleWorkItem`, in `TransitionWorkItem`, `AppendWorkItemIntent`,
  `AttachWorkItemExecution`, `ResumeWorkItem` and `LinkWorkItemSurface`;
  update the package comment. (depends on 2) — DoD: every work-item
  mutation route except snapshot seal is gated; invisible items still 404.
- [ ] 4. Call `requireWorkItemRole(..., item.Tenant, "execution_request")` in
  `CreateExecutionRequest` (`handlers_execution_requests.go`) after
  `visibleWorkItem` and before `refuseExecutionIdentity`; extend the file's
  "Who may do what" comment. (depends on 2) — DoD: a viewer gets 403
  `tenant_role_forbidden` and no request row is written.
- [ ] 5. In `SyncRepos` (`internal/api/handlers_repos.go`), add `repoSyncRole =
  operations.RoleDeveloper` and call `requireTenantRole(w, r, user,
  req.Team, repoSyncRole, "repos.sync", operations.RiskLow)` after
  `HasTenantAccess`. — DoD: a viewer never reaches the portal proxy.
- [ ] 6. Add a one-line "No tenant role: <reason>; see docs/tenant-roles.md"
  note to the header comments of `handlers_action_approvals.go`,
  `handlers_human_input_response.go`, `handlers_surface_identity.go`,
  `handlers_work_item_snapshots.go` and the approve/abandon section of
  `handlers_dev_loop.go`. — DoD: comment-only diff in those files.
- [ ] 7. Write `docs/tenant-roles.md` with the role ladder, the per-handler
  decision table (the #487 gates plus every row of #489), "viewer passes no
  write", "reads are not role-gated", and the Dex/generic-OIDC paragraph
  referencing #377 and #435. — DoD: every row of the #489 table has a
  decision and a reason.
- [ ] 8. Update `docs/work-context-contract.md` "Identity and authorization"
  to name the `developer` minimum on work-item writes and link
  `docs/tenant-roles.md`. (depends on 7) — DoD: the doc no longer says
  authorization is only `IsAdmin` + `HasTenantAccess` + visibility.
- [ ] 9. Wire a role source into the existing tests that perform work-item or
  repo-sync writes as non-admin GitHub users: set `GitReader: rolesOf(...)`
  (`tenant_role_stub_test.go`) with `developer` for those users in
  `handlers_work_items_test.go` (`workItemsEnv`),
  `handlers_execution_requests_test.go`, `handlers_work_item_intents_test.go`,
  `handlers_surface_relay_test.go`, `handlers_delegation_surface_refs_test.go`,
  `handlers_agent_identity_test.go`, `handlers_agent_run_tokens_test.go`,
  `handlers_evidence*_test.go`, `handlers_usage_writer_test.go`,
  `handlers_repos_test.go` and `internal/mcp/workitems_test.go` wherever they
  hit a gated route. (depends on 3, 4, 5) — DoD: `go test ./...` green with
  no assertion weakened.
- [ ] 10. Run `go fmt`, `go vet`, `golangci-lint`. (depends on all) — DoD:
  clean.

## Tests

New file `internal/api/tenant_role_workitems_test.go` (and repo-sync cases in
`handlers_repos_test.go`), using `rolesOf`:

- [ ] T1. Table test over all seven gated work-item routes: `viewer` -> 403
  `tenant_role_forbidden`, store unchanged, one `denied` audit entry;
  `developer` and `owner` -> the route's existing success status.
- [ ] T2. Admin (`admins` group) and `auth.NewServiceUser()` pass the gate
  on create/attach/resume without any `MemberRoles` call (`stubRoles.calls`
  is 0).
- [ ] T3. A Dex/OIDC user (not GitHub-proven) with tenant access -> 403
  `tenant_role_forbidden` on create; the message mentions signing in with
  the GitHub-linked account.
- [ ] T4. `stubRoles.err` set -> 503 `tenant_role_unavailable`, `error`
  audit entry, no write; nil `GitReader` -> 503 as well.
- [ ] T5. Existence is not leaked: a viewer of tenant A on an item of tenant B,
  and a viewer on another principal's private item in their own tenant, both
  get 404 `work_item_not_found`, never 403, and `MemberRoles` is not called.
- [ ] T6. Surface relay: a relayed subject who is `viewer` is refused on
  `POST /work-items/{id}/execution-requests`; the same relayed subject as
  `developer` succeeds. Same pair for an agent-delegated subject
  (`NewDelegatedUser`) on `POST /work-items/{id}/surface-refs`.
- [ ] T7. Multi-team role resolution is honoured: tenant-level `owner` plus
  team-level `viewer` (`"t/u=owner|viewer"`) passes; an unrecognised role
  string is refused.
- [ ] T8. `SealWorkItemSnapshot`, `DecideActionApproval`,
  `RespondHumanInput` and surface-identity redeem behave as before with a
  `viewer`-only role source (regression: no tenant role gate added).
- [ ] T9. `SyncRepos`: viewer -> 403 and the fake portal server receives no
  request; developer -> proxied (fake server hit once with the caller's id).
- [ ] T10. MCP: `mctl_request_work_item_execution` as a viewer surfaces the
  403 `tenant_role_forbidden` body; the `server_test.go` tool count is
  unchanged.

## Rollback

All changes are additive checks plus docs, with no schema or data change.
Revert the PR (or set `workItemWriteRole` / `repoSyncRole` to
`operations.RoleViewer` as a hot patch, which every member satisfies while
Dex/OIDC callers stay refused) and redeploy mctl-api through the normal
release. Nothing persisted depends on the gate, so no data repair is needed.
