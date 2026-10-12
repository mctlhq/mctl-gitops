# Design: issue-489-authz-decide-tenant-roles-for-work-items

## Current state

Role model (from #487 / #478):

- `internal/operations/roles.go` defines `RoleViewer < RoleDeveloper <
  RoleOwner`, plus the non-tenant `RoleAdmin` and `RoleAuthenticated`. The
  `RoleViewer` comment already says "No write operation accepts it".
  `EffectiveTenantRole` combines the tenant-level and team-level member
  lists.
- `internal/api/tenant_role.go`: `checkTenantRole(user, tenant, min, what)`
  returns a `roleRefusal` (403 denied, 503 unavailable, 500 misconfigured).
  Admins pass. A caller without a GitHub-proven login
  (`auth.User.GitHubLogin()` false: Dex, generic OIDC) is refused. The role
  is read per request through `GitReader.MemberRoles`. `requireTenantRole`
  wraps it with an audit entry and a plain `writeError` response.
  `operationMinRole` reads a registry minimum.
- Users with a GitHub-proven login: direct GitHub users
  (`auth.NewGitHubUser`), surface-relayed subjects (`auth.NewRelayedUser`)
  and agent-delegated subjects (`auth.NewDelegatedUser`), all in
  `internal/auth/oidc.go` with `githubLogin: true`. The service principal
  (`auth.NewServiceUser`) carries `admins`.
- Existing gates: `handlers_alerts.go` (`incidentWriteRole = developer`),
  `handlers_domains.go` (`requireDomainRole`), `handlers_erpact_sites.go`
  (owner), `handlers_commerce.go` (`commerceTenantRole = owner`), and the
  generic execute path through the registry `MinRole`
  (`internal/operations/registry.go`).

Handlers named in #489 (routes in `internal/api/router.go`, write group
around lines 524-568):

| Route | Handler | Today |
|---|---|---|
| `POST /work-items` | `CreateWorkItem` (`handlers_work_items.go`) | `HasTenantAccess(body.Tenant)` only |
| `PATCH /work-items/{id}` | `TransitionWorkItem` | `visibleWorkItem` (tenant access + visibility) |
| `POST /work-items/{id}/intents` | `AppendWorkItemIntent` | `visibleWorkItem` |
| `POST /work-items/{id}/executions` | `AttachWorkItemExecution` | `visibleWorkItem` |
| `POST /work-items/{id}/resume` | `ResumeWorkItem` | `visibleWorkItem` |
| `POST /work-items/{id}/surface-refs` | `LinkWorkItemSurface` | `visibleWorkItem` + `delegatedActorIsSubject` |
| `POST /work-items/{id}/execution-requests` | `CreateExecutionRequest` (`handlers_execution_requests.go`) | not service + `visibleWorkItem` |
| `POST /work-items/{id}/executions/{eid}/snapshot` | `SealWorkItemSnapshot` (`handlers_work_item_snapshots.go`) | direct service principal only |
| `POST /action-approvals`, `/consume` | `handlers_action_approvals.go` | `isDirectService` |
| `POST /action-approvals/{id}/decision` | `DecideActionApproval` | `isHumanAdmin`, never the requester |
| `POST /agents/dev-loop/{id}/approve` | `ApproveDevLoopWorkflow` (`handlers_dev_loop.go`) | `requireTemporalAdmin` (admin) |
| `POST /human-input/{id}/response` | `RespondHumanInput` (`handlers_human_input_response.go`) | GitHub-proven `github:<login>` in `RequestedFrom.ActorRefs` (`humaninput.Request.CanRespond`) |
| `POST /surface-identities/challenges`, `/redeem`, `/{id}/revoke` | `handlers_surface_identity.go` | per principal: the human requests, the surface principal redeems |
| `POST /repos/sync` | `SyncRepos` (`handlers_repos.go`) | `HasTenantAccess(req.Team)`, then proxied to the portal `github-app-connect` plugin |

Work-item handlers answer with typed codes through `writeErrorCode` (`wiCode*`
constants in `handlers_work_items.go`). `canSeeWorkItem` answers 404 rather
than 403 for invisible items. Repo sync matters for authorization because
`build_repo_gate.go` limits builds to repositories connected to the team in
the portal, so a sync widens what the tenant may build.

MCP: `internal/mcp/workitems.go` (`mctl_request_work_item_execution`) and
`mctl_sync_repos` in `internal/mcp/server.go` call the REST routes
(`apiPost`), so a REST gate covers them.

Docs: `docs/work-context-contract.md` "Identity and authorization" says
authorization is `IsAdmin` + `HasTenantAccess` + visibility, with no
mention of roles. No document describes tenant roles; `docs/` has no
`tenant-roles.md`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/tenants/*/values.yaml` (admins, commerce-proof,
  erpact, karabu, labs, mctl): 8 `owner` and 2 `developer` member entries
  (both in `erpact`); no `viewer` entry in any tenant. A `developer` minimum
  on work-item writes and repo sync therefore refuses no current member.
- `mctl_get_service_config(team=admins, service=mctl-api)`: "service not
  found". mctl-api is not a catalogue service in `services/`, so its
  deployed env (for example whether a gitops reader is wired, which the 503
  path depends on) was not observed. Recorded under Open questions.
- The portal `github-app-connect` plugin's sync rule (said to allow
  `viewer`) lives in mctl-portal and was not observed here; it is taken from
  the issue.

## Proposed solution

### Decisions

| Group | Decision | Mechanism |
|---|---|---|
| Work items: create, transition, intent, attach execution, resume, surface-ref | `developer` | new `requireWorkItemRole` |
| Execution requests: create | `developer` (it starts a paid agent run) | `requireWorkItemRole` |
| Snapshot seal; execution-request claim/fulfil/reject | no tenant role: service principal only | unchanged, documented |
| Action approvals: decide | no tenant role: human platform admin only, which is stricter than `owner` | unchanged, documented |
| Action approvals: create/consume | no tenant role: service principal only | unchanged, documented |
| DevLoop approve/abandon | no tenant role: platform admin only | unchanged, documented |
| Human-input responses | no tenant role: tied to the named respondent; an answer is information, not authorization | unchanged, documented |
| Surface identities: challenge, redeem, revoke | no tenant role: they bind a principal to a surface identity and are not tenant-scoped | unchanged, documented |
| `POST /repos/sync` | `developer` in mctl-api; portal follow-up to match | `requireTenantRole` |
| Dex / generic OIDC callers | no tenant role, refused on gated writes; deferred to #377 / #435 | unchanged, documented |
| Reads | not restricted by role; tenant membership plus visibility is enough | unchanged, documented |

Why `developer` for work items: `viewer` is defined as passing no write
(`roles.go`), and an execution request costs a real agent run, which is
the same class as the `developer` operations in the registry. Splitting
"create a note" (viewer) from "start a run" (developer) would make viewer
mean something different here than everywhere else, so every work-item
mutation uses the same minimum.

### Code changes

1. `internal/api/handlers_work_items.go`
   - Add `const workItemWriteRole = operations.RoleDeveloper`, next to the
     `incidentWriteRole` pattern in `handlers_alerts.go`.
   - Add typed codes `wiCodeRoleForbidden = "tenant_role_forbidden"` and
     `wiCodeRoleUnavailable = "tenant_role_unavailable"`.
   - Add `func (h *Handlers) requireWorkItemRole(w, r, user, tenant, op
     string) bool`. It calls `checkTenantRole(user, tenant,
     workItemWriteRole, "work item "+op)`. On refusal it writes the same
     audit entry shape `requireTenantRole` writes (operation
     `work_item.<op>`, status `denied` or `error`, `RiskMedium`), logs the
     `error` case with `slog.Error`, and answers with `writeErrorCode`: 403
     becomes `tenant_role_forbidden`, 503 becomes `tenant_role_unavailable`,
     and 500 keeps a generic code. This preserves the typed-code contract
     of the work-item API. To avoid duplicating audit code, factor the
     audit-and-log part of `requireTenantRole` into
     `auditRoleRefusal(r, user, tenant, operation, risk, d roleRefusal)` in
     `tenant_role.go` and call it from both.
   - Call it in `CreateWorkItem` after the `HasTenantAccess` check and
     before `mutationFor`. In `TransitionWorkItem`, `AppendWorkItemIntent`,
     `AttachWorkItemExecution`, `ResumeWorkItem` and `LinkWorkItemSurface`,
     call it right after `visibleWorkItem` with `item.Tenant`, so an
     invisible item still answers 404 first.
   - Update the package comment ("Authorization is re-evaluated ...") to
     name the `developer` minimum.
2. `internal/api/handlers_execution_requests.go`: in
   `CreateExecutionRequest`, call `requireWorkItemRole(..., item.Tenant,
   "execution_request")` after `visibleWorkItem` and before
   `refuseExecutionIdentity`. Add a "who may" line to the file comment.
3. `internal/api/handlers_repos.go`: in `SyncRepos`, after
   `HasTenantAccess(req.Team)`, call `h.requireTenantRole(w, r, user,
   req.Team, repoSyncRole, "repos.sync", operations.RiskLow)` with `const
   repoSyncRole = operations.RoleDeveloper`. The portal proxy is reached
   only on pass.
4. No code change for approvals, human input, surface identities, snapshot
   seal or DevLoop approve. Each handler file's header comment gets one
   line, "No tenant role: <reason>; see docs/tenant-roles.md", so the
   decision sits next to the code.
5. New `docs/tenant-roles.md`: the role ladder, where roles are read
   (`members[].role`, per request, GitHub-proven login), the table above
   plus the #487 gates (execute registry `MinRole`, domains, incidents,
   ERPact, commerce), "viewer passes no write", "reads are not role-gated",
   and the Dex/OIDC paragraph pointing at #377 and #435.
6. `docs/work-context-contract.md`, "Identity and authorization": add the
   `developer` minimum to the authorization bullet and link the new doc.

Gate placement relative to delegation: relayed and delegated subjects carry
`githubLogin: true` and the human's groups, so `checkTenantRole` evaluates
the human, which is the intended subject. Agent principals belong to no
tenant and already stop at `visibleWorkItem` (404) or `HasTenantAccess`.

## Alternatives

1. **Allow `viewer` to create work items and add intents, require
   `developer` only for execution requests and resume.** It is closer to
   "a viewer can file a note", but it makes `viewer` a writing role in one
   API and not in others, against the `RoleViewer` definition. A viewer's
   work item is also an input an approver then acts on. Dropped for
   consistency; it can be relaxed later by changing one constant per route.
2. **Put work-item minimums in the operations registry and read them with
   `operationMinRole`.** Work-item routes are not registry operations (they
   do not go through `ExecuteOperation`). Adding pseudo-operations only to
   carry a role would show them in `mctl_list_operations`. Dropped in
   favour of a named constant, the pattern `handlers_alerts.go` and
   `handlers_commerce.go` use.
3. **Require tenant `owner` to decide action approvals.** Today only a
   human platform admin may decide, and that is stricter. Letting a tenant
   owner decide would widen authority, and action approvals carry no
   tenant field to scope it with. Dropped; documented instead.
4. **Keep repo sync at "any member" to match the portal.** The sync widens
   the set of repositories `build_repo_gate.go` lets the tenant build, so a
   write that changes the tenant's build surface would stay open to a
   read-only role. Dropped; the mctl-api route is raised now and the portal
   follow-up closes the gap.

## Platform impact

- Migrations: none. No schema or registry change.
- Backward compatibility: callers with `developer`/`owner`, admins and the
  service principal are unaffected. Gitops shows no `viewer` members today,
  so no deployed member loses access. Dex/OIDC non-admin callers lose work-item
  writes and repo sync. Per #489 no known caller is affected; this is the
  same rule #487 already applies to every other tenant write.
- New failure mode: work-item writes and repo sync now depend on the gitops
  reader (`GitReader.MemberRoles`). If it is unavailable, non-admin writes
  answer 503 `tenant_role_unavailable` instead of succeeding. This is the
  same dependency #487 added to execute, and it fails closed by design.
  Mitigation: the `/ready` checks and the existing slog error line make it
  visible.
- Resource impact: one in-memory members lookup per gated write against the
  already-loaded checkout. Negligible.
- MCP: no tool added or removed, so the `server_test.go` tool count is
  unchanged. MCP callers get the REST 403/503 bodies through `apiPost`.
- Risks: a gate placed before `visibleWorkItem` would leak existence (403
  vs 404). Mitigation: placement is fixed after `visibleWorkItem`, and a
  test covers a viewer of tenant A probing an item in tenant B (404) and a
  viewer probing a private item of another principal in their own tenant
  (404, not 403).

## Open questions

- Portal parity for repo sync (see requirements.md). Follow-up needed in
  mctl-portal.
- Deployed mctl-api configuration was not observable
  (`mctl_get_service_config` returned not found). Whether a gitops reader is
  wired in every replica, which the gate needs, is assumed from #487
  already relying on it in production.
- Private-item owners downgraded to `viewer` lose writes on their own
  items. Intended here; a reviewer may want an exception.
