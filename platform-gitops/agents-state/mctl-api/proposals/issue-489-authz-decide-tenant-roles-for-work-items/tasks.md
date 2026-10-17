# Tasks: issue-489-authz-decide-tenant-roles-for-work-items

- [ ] 1. Add the constants `workItemWriteRole`, `workItemExecutionRole` and `reposSyncRole` (all `operations.RoleDeveloper`) in `internal/api/tenant_role.go`. Each gets a doc comment citing #489. — DoD: `go vet` is clean, and each constant is the only place its minimum is declared.
- [ ] 2. Extract the audit+log part of `requireTenantRole` into `auditRoleRefusal`. Keep `requireTenantRole`'s behaviour byte-identical. (depends on 1) — DoD: the existing `tenant_role_test.go`, `tenant_role_execute_test.go`, `tenant_role_mcp_test.go` and `tenant_authz_principal_test.go` pass unchanged.
- [ ] 3. Add `wiCodeRoleForbidden = "tenant_role_forbidden"`, `wiCodeRoleUnavailable = "tenant_role_unavailable"` and `requireWorkItemRole` in `internal/api/handlers_work_items.go`. Its comment records the machine-caller exemption: the service principal passes as platform admin; an agent token acting for no human has no tenant groups (`auth.NewAgentUser`, `PrincipalAuthz.Apply`) and, if it ever has a tenant scope, is refused as non-human by `checkTenantRoleByPrincipal`; delegated and relayed requests are decided as the named human principal. It contains no `GitHubLogin()` check. (depends on 2) — DoD: compiles, and the typed codes appear in error bodies.
- [ ] 4. Call `requireWorkItemRole` in `CreateWorkItem` (after `HasTenantAccess`), `TransitionWorkItem`, `AppendWorkItemIntent`, `AttachWorkItemExecution` and `LinkWorkItemSurface` with `workItemWriteRole`, and in `ResumeWorkItem` and `CreateExecutionRequest` with `workItemExecutionRole`. In every item route the call goes after `visibleWorkItem` and before the body decode and any store write. Add a comment on `SealWorkItemSnapshot` and `executionPlatform` saying why they have no role gate. (depends on 3) — DoD: T1 to T8 pass.
- [ ] 5. Gate `SyncRepos` in `internal/api/handlers_repos.go` with `requireTenantRole(..., reposSyncRole, "repos-sync", operations.RiskLow)` after `HasTenantAccess` and before the upstream request is built. (depends on 1) — DoD: T9 passes, and the upstream stub records no call on a refusal.
- [ ] 6. Rewrite the header comment of `internal/api/tenant_role.go`: principal mode is current, and the "Dex / other OIDC has no role" rule applies only to legacy and shadow. — DoD: the comment matches `checkTenantRoleByPrincipal`'s behaviour.
- [ ] 7. Write `docs/tenant-roles.md`. It covers: principal mode as current and legacy/shadow as rollback modes; the role table; the gated routes and their minimums; the ungated writes and why (action approvals human-admin only #571, human input tied to `actor_refs`, surface identities per-principal, snapshot and claim/fulfil/reject service-only); reads are never role-gated; the machine-caller exemption; and a link to the companion portal issue for repo sync. (depends on 4, 5) — DoD: every row of #489's table has a decision in the doc.
- [ ] 8. Open the companion issue in the portal repo to raise `/api/github-app-connect/repos/sync` to `developer`, and link it from `docs/tenant-roles.md`. — DoD: the issue exists and is linked.
- [ ] 9. Release note: say that no GitOps member holds `viewer` (list tenants and members with roles as of release), so no listed member starts getting 403. Re-check principal membership, including any ZITADEL `customers` org principals (for example in `labs`), against the gitops checkout and `TryNamespacesForPrincipal` at release time, and list anyone who would be refused. — DoD: the note is in the PR description and the CHANGELOG entry.
- [ ] 10. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD: all green, and the MCP tool count in `server_test.go` is unchanged.

## Tests

New file `internal/api/tenant_role_work_items_test.go`, table-driven over all seven gated work-item routes plus repo sync. It uses `principalUser`, `stubPrincipalMembership`/`principalRoles` and `rolesOf` from the existing test helpers.

Principal mode (main cases):

- [ ] T1. Principal mode, a GitHub-linked human with principal role `developer`: every gated route succeeds (201/200). With `owner` it also succeeds.
- [ ] T2. Principal mode, principal role `viewer`: every gated route answers 403 `tenant_role_forbidden`, writes a `denied` audit entry, and the store is unchanged (no item, intent, execution, surface ref or execution request created). This covers `POST /work-items` with `visibility=private`.
- [ ] T3. Principal mode, a ZITADEL-only human (`auth.NewFederatedUser("zitadel", ..., auth.KindHuman)`, no GitHub login) with role `viewer` is refused 403 on every gated route in three ways: (a) direct; (b) relayed through `NewRelayedPrincipalUser`; (c) delegated through `NewDelegatedPrincipalUser` on the delegation-allowlisted routes (`intents`, `surface-refs`, `execution-requests`). The same identity with `developer` succeeds in all three.
- [ ] T4. Principal mode, membership reader missing or failing, or a human with an unresolved principal: 503 `tenant_role_unavailable`, an `error` audit entry, and no store write.
- [ ] T5. The service principal (`auth.NewServiceUser()`) passes the gate on `AttachWorkItemExecution` and `ResumeWorkItem` in principal, legacy and shadow modes. It still gets `requester_forbidden` on `CreateExecutionRequest`, so that existing behaviour is unchanged.
- [ ] T6. An undelegated agent token (`auth.NewAgentUser`) on a tenant item: 404 `work_item_not_found` (no tenant access), never 200. An agent-shaped caller that is given a tenant group directly in the test is refused 403 by the gate (non-human), which pins down "a tenant-scoped machine token goes through the gate".
- [ ] T7. Ordering: a `viewer` of tenant A asking about an item in tenant B, or about another principal's private item, gets 404, not 403. A role refusal never reveals that an item exists.
- [ ] T8. The login is never consulted in principal mode: the legacy `GitReader` is wired to say `owner` while the principal reader says `viewer`, and the result is 403 on every route. This mirrors `TestCheckTenantRole_PrincipalMode`.
- [ ] T9. `POST /repos/sync`: principal `viewer` gets 403 and the upstream test server receives no request. `developer` is proxied. An unreadable role gives 503.

Rollback modes (regression rows):

- [ ] T10. Legacy mode: a GitHub-proven `viewer` (`rolesOf("erpact/dan=viewer")`) is refused on every gated route, and `developer` passes. A Dex/OIDC human with no GitHub login is refused 403 ("does not carry a tenant role").
- [ ] T11. Shadow mode: the decision equals the legacy decision, and `shadowTenantRole` records the principal comparison for a gated work-item write.

Ungated groups (pin down "no gate"):

- [ ] T12. A non-admin tenant `owner` is refused on `POST /action-approvals/{id}/decision`, which stays human admin only. A human-input response by a tenant `viewer` named in `actor_refs` succeeds, and one by a tenant `owner` not named in `actor_refs` is refused. GET work-item routes by a `viewer` member succeed.

## Rollback

Revert the PR. The change is code and docs only: no schema, no env var and no gitops change, so a revert restores today's behaviour (membership-only work-item writes and repo sync) on the next deploy. If only one gate causes trouble, set its constant (for example `workItemExecutionRole` or `reposSyncRole`) to `operations.RoleViewer` in a hotfix. That keeps the gate and its audit trail but admits every listed member. Do not switch `TENANT_AUTHZ_MODE` back to legacy for this. That is a rollback of #377, it is unrelated, and in legacy mode ZITADEL-only humans would lose all role-gated writes.
