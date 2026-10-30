# Tasks: issue-698-mctl-list-previews-reports-count-0-when

## Amendments (2026-10-24, reviewer) — these override the rest of this file

- **A1. RBAC is not the implementer's job.** design.md section 4 says the
  mctl-gitops RBAC is a separate PR that this change only references, but
  task 7 told the implementer to open it. The design wins. The grant is
  mctlhq/mctl-gitops#2124: Role and RoleBinding `mctl-api-preview-reader`,
  `get,list` on `apps/deployments` in `{tenant}-preview`, no secret verbs,
  pinned read-only by `tests/test_tenant_preview_rbac.py`. A reviewer
  authored it, and it is merged and synced before this proposal is
  approved. The implementer makes no change outside mctlhq/mctl-api and
  opens no PR in any other repository.
- **A2. Rollout order is RBAC, then API.** The RBAC lands first, so the new
  `ListPreviews` never meets a forbidden read in a synced tenant. A tenant
  whose app has not synced still gets 503, which is correct: never a false
  empty list.
- **A3. Source of truth confirmed.** Reading Deployments by the
  `app.kubernetes.io/instance` label, rather than Helm release Secrets, is
  accepted for the reason given: `list secrets` cannot be narrowed to Helm
  storage.

- [ ] 1. Add `internal/k8s/previews.go` with `PreviewRelease`, `ErrNamespaceAbsent`, `PreviewClient`, `NewPreviewClient(kubernetes.Interface)`, `ListPreviewReleases(ctx, team, service)` and `ParsePreviewRelease(release)`; extract a shared `newClientset()` from `NewQuotaClient` in `internal/k8s/quotas.go`. — DoD: lists Deployments in `{team}-preview` by `app.kubernetes.io/managed-by=Helm`, parses `app.kubernetes.io/instance` as `preview-<service>-<id>` (last hyphen, id `^[a-z0-9]{1,6}$`), filters service exactly, returns wrapped errors for every API failure and `ErrNamespaceAbsent` only on an observed namespace NotFound; `go vet` clean.
- [ ] 2. Add `PreviewLister` interface to `internal/api/interfaces.go` and a `PreviewLister` field to the handler options in `internal/api/router.go` (depends on 1). — DoD: compiles; nil allowed.
- [ ] 3. Wire `k8s.NewPreviewClient` in `cmd/api/main.go` next to the quota client, nil with an `slog.Warn` if the clientset cannot be built (depends on 1, 2). — DoD: server starts in and out of cluster.
- [ ] 4. Rewrite `ListPreviews` in `internal/api/handlers_read.go` (depends on 2): remove the ArgoCD call and prefix filter; nil lister or any error -> 503 via `writeError` with no `items`/`count`; `ErrNamespaceAbsent` -> 200 with `count: 0`, `preview_namespace: "absent"`; success -> 200 with snake_case items, `count`, `team`, `namespace`, `preview_namespace: "present"`. Keep 401/400/403. — DoD: no code path returns `count` alongside a failed read.
- [ ] 5. Update the `mctl_list_previews` description in `internal/mcp/server.go` `toolListPreviews` to describe Helm releases in `{team}-preview` named `preview-{service}-{id}`, the error-on-failed-read behaviour and the `preview_namespace: "absent"` meaning. — DoD: no mention of ArgoCD applications; tool count in `server_test.go` unchanged.
- [ ] 6. Update docs/OpenAPI for `/api/v1/previews` if `internal/openapi` describes it (grep first). — DoD: response schema and 503 documented, or confirmed not present.
- [ ] 7. ~~Cross-repo RBAC PR~~ (removed by A1). Instead, the mctl-api PR description names mctlhq/mctl-gitops#2124 as the merged RBAC prerequisite. — DoD: no file outside this repository is changed.

## Tests

- [ ] T1. `internal/k8s/previews_test.go` with `client-go/kubernetes/fake`: a Deployment labelled `app.kubernetes.io/instance=preview-psa-smoke-abc123`, `managed-by=Helm` in `labs-preview` is returned for `(labs, psa-smoke)` and for `(labs, "")` with `Service=psa-smoke`, `PreviewID=abc123`.
- [ ] T2. Same fixture: `(labs, psa)` returns nothing; a Deployment named `preview-labs-psa-smoke-abc123` style (team segment) is parsed as service `labs-psa-smoke` and not returned for `psa-smoke`; non-Helm and non-`preview-` Deployments are ignored.
- [ ] T3. Fake reactor returning Forbidden / generic error on deployment list -> error returned, not empty slice; empty list + namespace NotFound -> `ErrNamespaceAbsent`; empty list + namespace get error -> error; empty list + namespace present -> empty slice, nil.
- [ ] T4. `ParsePreviewRelease` table test: valid, missing prefix, empty service, id too long, id with uppercase, no hyphen.
- [ ] T5. Handler tests (`internal/api`, stub `PreviewLister`): failing lister -> 503 and body has no `count` / `items` key; nil lister -> 503; `ErrNamespaceAbsent` -> 200 `count: 0`, `preview_namespace: "absent"`; success -> 200 with items and `count`; 401/400/403 unchanged; ArgoCD stub is not called.
- [ ] T6. MCP test: `toolListPreviews` against an httptest server answering 503 -> `IsError: true`; answering 200 with items -> text result containing the body.
- [ ] T7. `go fmt`, `go vet`, `golangci-lint`, `go test ./...` pass.

## Rollback

Revert the mctl-api PR: the handler returns to the ArgoCD query (and its 200-with-`count: 0` behaviour). The mctl-gitops RBAC addition is read-only and can stay or be reverted independently; it has no effect without the new code. No data or schema migration is involved.
