# Design: issue-537-fix-operations-reject-reserved-tenant-na

## Current state
- `internal/operations/registry.go` defines `create-tenant` in `builtinOperations`. Its `tenant_name` parameter has only `Pattern: "^[a-z0-9][a-z0-9-]{1,62}$"`.
- `Registry.ValidateInput(op, input)` (registry.go, around line 216) walks `op.Parameters` and checks required, enum and pattern. It has no notion of a value deny-list and no per-operation hooks. It returns `[]string` error messages.
- `internal/api/handlers_write.go` (the generic `POST /api/v1/operations/{name}/execute` handler) runs `StripUndeclared`, RBAC, the create-tenant one-workspace rule, `ApplyDefaults`, then `ValidateInput`. On errors it returns 400 `{"error":"validation failed","validationErrors":[...]}`. Then come `checkTenantIsNew` (non-admins only), the Backstage notification and `h.opts.Executor.Submit(...)`.
- `internal/mcp/server.go` `mctl_create_tenant` (around line 655) does not submit directly. It calls `s.apiPost(ctx, "/api/v1/operations/create-tenant/execute", params)`, so MCP inherits REST validation.
- `operations.Executor.Submit(ctx, op, params, userID, team)` (`internal/operations/executor.go:125`) builds and creates the Argo Workflow and does no parameter validation. Its other direct callers (`handlers_domains.go`, `handlers_platform_skills.go`) do not submit `create-tenant` today, but nothing prevents a future caller from doing so.
- `internal/gitops/reader.go` keeps its own copy of the format regex (`tenantNameRE`) for `TenantExists`. That copy is unrelated to reserved names.
- The gitops source of truth, `tenant_name_reserved()` in `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml` (mctl-gitops#1770), is a shell `case`. It matches the exact names `argocd argo-workflows argo-events kube-system kube-public kube-node-lease default cert-manager traefik vault external-secrets monitoring temporal backstage minio database forgejo zitadel local-path-storage system-upgrade observability-eval` and the globs `kube-* argo* *-system platform-* mctl-* grafana-* vault*`. It runs before the existence and `reprovision` handling, so it applies to admins and reprovisions alike.

## Proposed solution
1. **New file `internal/operations/tenant_names.go`**, the single home of the rule:
   - A header comment that points at `mctl-gitops: platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml, tenant_name_reserved()` (as of mctl-gitops#1770). The comment says the two lists must change together.
   - `reservedTenantNames` (`map[string]struct{}` of the 21 exact names).
   - `reservedTenantNamePrefixes = []string{"kube-", "argo", "platform-", "mctl-", "grafana-", "vault"}` and `reservedTenantNameSuffixes = []string{"-system"}`. These are a literal translation of the shell globs (`X*` becomes a prefix, `*X` a suffix). Plain `strings.HasPrefix`/`HasSuffix` is used rather than `path.Match`, so the semantics are obvious and identical to `case`.
   - `func IsReservedTenantName(name string) bool`.
   - `func checkReservedTenantName(op Operation, params map[string]string) error`. It returns `fmt.Errorf("tenant_name: %q is reserved for a platform namespace; choose another name", name)` when `op.WorkflowTemplate == "create-tenant"` and the name is reserved, and `nil` otherwise. Keying on `WorkflowTemplate` rather than `Name` means a hand-built `Operation` that targets the same template is still covered.
2. **`Registry.ValidateInput`**: after the parameter loop, call `checkReservedTenantName(op, input)` and append its message to `errors`. REST, and therefore MCP, gets a 400 with a clear `validationErrors` entry before the audit-param, existence-check, Backstage and Submit steps. Admins included, matching gitops.
3. **`Executor.Submit`**: at the top, before namespace and name generation and before the `dynamicClient == nil` check (so it is unit-testable), return `checkReservedTenantName(op, params)` as an error if it is non-nil. This makes the rule non-bypassable for any internal caller that skips `ValidateInput`, which is the issue's "not bypassable by calling a lower-level function" requirement.
4. **`internal/mcp/server.go`**: append one sentence to the `mctl_create_tenant` description, for example "Platform namespace names (e.g. kube-*, argo*, *-system, vault) are reserved." No new tool, so the tool count in `server_test.go` is unchanged.

Existing tenants are unaffected. Only `create-tenant` (by template) is checked. Delete, deploy and the other operations keep their current validation.

## Alternatives
- **Extend `ParameterDef` with a `Reserved []string` or `Validate func(string) error` field.** It is more generic, but a func field cannot round-trip through the JSON operation schema (`GET /operations`). Also, a field on the registry entry would not protect `Executor.Submit` callers who build their own `Operation`. That was dropped in favour of a template-keyed check that both layers call.
- **Encode the rule in the `Pattern` regex** (negative lookahead is not supported by Go RE2, and an expanded positive regex would be unreadable). Dropped: the resulting error message ("must match pattern ...") is also not the "clear validation error" the issue asks for.
- **Check only in `handlers_write.go`.** That is the smallest diff, but it leaves `Executor.Submit` bypassable, contrary to the issue. Dropped.
- **Fetch the list from mctl-gitops at runtime** (via `GitReader`). This would remove drift, but it adds a failure mode (an unsynced checkout) to a static check and couples validation to the gitops checkout. Dropped; the source-pointer comment and the out-of-scope CI sync check cover drift.

## Platform impact
- No migrations and no schema or API shape changes. The 400 response format is the existing `validationErrors` one.
- Backward compatibility: requests that previously succeeded at the API but were guaranteed to fail in Argo now fail earlier. No request that could have succeeded end to end is newly rejected, provided the lists match the gitops rule.
- Resource impact: negligible. A map lookup and seven prefix and suffix comparisons per create-tenant request. Fewer doomed Argo workflows.
- Risk: list drift between the API and gitops. Mitigation: a single definition with a source-pointer comment, and table tests that enumerate every entry, so a change is visible in review. Residual risk: if gitops later relaxes a name, the API keeps rejecting it until it is updated. That fails closed, which is acceptable for a security control.
- Risk: the `argo*` and `vault*` globs reject benign names such as `argonaut`. This matches gitops behaviour; it is recorded as an open question.
