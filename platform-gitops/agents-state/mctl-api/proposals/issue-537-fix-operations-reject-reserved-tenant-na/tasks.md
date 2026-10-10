# Tasks: issue-537-fix-operations-reject-reserved-tenant-na

- [ ] 1. Add `internal/operations/tenant_names.go` with `reservedTenantNames` (the 21 exact names), `reservedTenantNamePrefixes` (`kube-`, `argo`, `platform-`, `mctl-`, `grafana-`, `vault`), `reservedTenantNameSuffixes` (`-system`), `IsReservedTenantName(name string) bool` and `checkReservedTenantName(op Operation, params map[string]string) error`. It applies only when `op.WorkflowTemplate == "create-tenant"`. Add a header comment that points at `tenant_name_reserved()` in mctl-gitops `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml` (mctl-gitops#1770). — DoD: the file compiles, the list mirrors the gitops `case` exactly, and the comment names the sync source.
- [ ] 2. (depends on 1) In `Registry.ValidateInput` (`internal/operations/registry.go`), call `checkReservedTenantName` after the parameter loop and append the error message. — DoD: `ValidateInput` returns a `tenant_name: "<name>" is reserved ...` entry for reserved names on create-tenant only.
- [ ] 3. (depends on 1) At the top of `Executor.Submit` (`internal/operations/executor.go`), before the `dynamicClient == nil` check, return the `checkReservedTenantName` error. — DoD: a direct `Submit` call with a reserved name errors without touching Kubernetes, even on an `Executor{}` with no client.
- [ ] 4. Append a reserved-names sentence to the `mctl_create_tenant` description in `internal/mcp/server.go`. — DoD: the description is updated and the tool count is unchanged.
- [ ] 5. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./...`. — DoD: all clean.

## Tests
- [ ] T1. `internal/operations/tenant_names_test.go`, `TestIsReservedTenantName`, table-driven:
  - every one of the 21 exact names is reserved;
  - glob cases are reserved, documenting the gitops rule (`X*` is a prefix, `*X` is a suffix): `kube-system-team`, `kube-foo`, `argo`, `argonaut`, `argocd-x`, `billing-system`, `platform-x`, `mctl-foo`, `grafana-x`, `vault2`, `vaultwarden`;
  - look-alikes that the rule does NOT cover are accepted: `billing`, `team-kube`, `my-argo`, `system-team`, `systems`, `mykube-system2`, `defaults`, `monitoring-team`, `team-vault`.

  Note: `defaults` and `monitoring-team` are allowed, because exact names do not imply prefixes. The test comment states this explicitly.
- [ ] T2. `TestValidateInputRejectsReservedTenantName` (`registry_test.go`): with the real `create-tenant` op from `NewRegistry`, every reserved name gives an error containing `is reserved`, and `billing` gives no error. A `delete-tenant` op with `tenant_name: kube-system` gives no reserved error, which shows the scope is create-only. This fails if the call in task 2 is removed.
- [ ] T3. `TestSubmitRejectsReservedTenantName` (`executor_test.go`): `(&Executor{}).Submit(ctx, createTenantOp, {"tenant_name":"kube-system"}, "u", "kube-system")` returns an error mentioning `reserved`, not the "kubernetes client not available" error. This fails if task 3 is removed.
- [ ] T4. Handler test in `internal/api` (alongside the existing create-tenant execute tests): `POST /api/v1/operations/create-tenant/execute` with `tenant_name=argocd`, as both a regular user and an admin, returns 400 with `validationErrors`, and the fake Executor records zero `Submit` calls.

## Rollback
Revert the PR. The change is purely additive validation with no persisted state, migrations or config. After the revert, reserved names are again rejected only by the gitops WorkflowTemplate's `tenant_name_reserved` step, which is the behaviour before this change.
