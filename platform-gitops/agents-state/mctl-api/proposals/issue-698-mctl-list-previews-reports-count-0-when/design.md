# Design: issue-698-mctl-list-previews-reports-count-0-when

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

## Current state

- `internal/api/router.go:540` routes `GET /api/v1/previews` to `Handlers.ListPreviews`.
- `internal/api/handlers_read.go:683` `ListPreviews`:
  - checks user (401), `team` (400), `user.IsAdmin() || user.HasTenantAccess(team)` (403);
  - calls `h.opts.ArgoCD.ListApps(team)` (`ArgoStatusClient` in `internal/api/interfaces.go`);
  - on `argocd.ErrUnauthenticated`, `argocd.ErrForbidden` and any other error it writes HTTP 200 with `items: []`, `count: 0` and an `error` / `note` string;
  - on success filters app names by prefix `preview-{team}-` or `preview-{team}-{service}-` and returns `items`, `count`, `team`.
- `internal/mcp/server.go:2127` `toolListPreviews` calls `s.apiGet` and returns the body as a text result. `apiGet` goes through `doRequest`, which (per the comment above `apiGetStatus`, `server.go:2434`) turns every status >= 400 into an error, so the tool already returns `NewToolResultError` for a non-2xx answer. The 200-with-`count: 0` body is the only reason the MCP result looks successful.
- The tool description (`server.go:2132-2137`) says previews are "ArgoCD applications" named `preview-{team}-{service}-{id}`.
- Kubernetes access exists: `internal/k8s/quotas.go` `QuotaClient` wraps a `kubernetes.Interface` built from in-cluster config (KUBECONFIG fallback), with `GetNamespaceUsage` and `NamespaceAbsent` (NotFound vs. error). It is constructed optionally in `cmd/api/main.go:904-909` and injected as `QuotaReader` (`router.go:65`, nil in local/test). `handlers_workspace_access.go:124` already reads `{tenant}-preview` through it and treats any error as unavailable.
- `go.mod` already depends on `k8s.io/client-go v0.36.4`; `client-go/kubernetes/fake` can be used in tests.

How previews are actually created (mctl-gitops, read-only):

- `argo-workflows/cluster-templates/wft-preview-deploy.yaml`: `NS="${TEAM}-preview"` (line 357), `PREVIEW_ID=$(echo "${ARGO_WORKFLOW_NAME}" | tr -cd 'a-z0-9' | tail -c 6)` (line 400), `RELEASE="preview-${COMPONENT}-${PREVIEW_ID}"` (line 401), `helm upgrade --install "${RELEASE}" .../helm-charts/base-service` (line 463) with `blueGreen.enabled=false`, pod labels `mctl.ai/preview=true` and `mctl.ai/preview-id`, and release label `mctl.ai/expires-at` (Helm storage Secret only).
- `helm-charts/base-service/templates/deployment.yaml` + `_helpers.tpl`: the Deployment carries `app.kubernetes.io/instance: {{ .Release.Name }}` and `app.kubernetes.io/managed-by: Helm`; its name is `fullname`, which may append the chart name, so the instance label (not the name) identifies the release.
- `helm-charts/tenant/templates/preview.yaml`: creates `{tenant}-preview` and Role `mctl-api-preview-quota-reader` granting the `mctl-api/mctl-api` ServiceAccount `get,list` on `resourcequotas` only, commented "without granting workflow or secret access".
- `bootstrap/templates/mctl-platform/mctl-api-rbac.yaml`: ClusterRole `mctl-api-customer-namespace-reader` grants `namespaces get` cluster-wide.

Deployed state checked:

- `mctl_list_previews(team=labs, service=psa-smoke)` (MCP, 2026-10-24): returned `{"count":0,"items":[],"note":"ArgoCD query failed: parsing argocd list response: missing items array"}`. Defect 1 reproduces in production today. I could not observe whether a `labs-preview` release exists right now (no read-only tool lists Helm releases); the issue reports one existed on 2026-10-18.
- `$MCTL_GITOPS_ROOT/tenants/labs/values.yaml`: `preview:` block present (preview enabled for labs, with quotas).
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api-rbac.yaml` and `helm-charts/tenant/templates/preview.yaml`: mctl-api has no Deployment or Secret read access in any `{tenant}-preview` namespace today.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/wft-preview-deploy.yaml`: release naming and namespace as cited above.

## Proposed solution

### 1. A preview reader in `internal/k8s`

New file `internal/k8s/previews.go`:

```go
type PreviewRelease struct {
    Release, Service, PreviewID, Namespace string
    Replicas, ReadyReplicas, AvailableReplicas int32
    CreatedAt time.Time
}

// ErrNamespaceAbsent is returned only for an observed NotFound on the namespace.
var ErrNamespaceAbsent = errors.New("preview namespace absent")

type PreviewClient struct{ client kubernetes.Interface }

func NewPreviewClient(cs kubernetes.Interface) *PreviewClient
func (c *PreviewClient) ListPreviewReleases(ctx context.Context, team, service string) ([]PreviewRelease, error)
func ParsePreviewRelease(release string) (service, id string, ok bool)
```

- `ListPreviewReleases` lists `AppsV1().Deployments(team+"-preview")` with label selector `app.kubernetes.io/managed-by=Helm`, then keeps a Deployment only if `ParsePreviewRelease(labels["app.kubernetes.io/instance"])` succeeds and (when `service != ""`) the parsed service equals `service` exactly. Results are de-duplicated by release and sorted by release name.
- `ParsePreviewRelease` requires prefix `preview-`, splits on the LAST hyphen, requires the id to match `^[a-z0-9]{1,6}$` and the service to be non-empty. This makes service `psa` unable to match `preview-psa-smoke-abc123` (its parsed service is `psa-smoke`).
- If the list returns NotFound-style emptiness it is still ambiguous, so on an empty list the client calls the existing namespace `Get`: NotFound -> `ErrNamespaceAbsent`; error -> wrapped error; found -> empty slice, nil. Every API error is returned wrapped with `fmt.Errorf("listing preview deployments in %s: %w", ns, err)`; nothing becomes an empty slice.
- Refactor `NewQuotaClient` to share a `newClientset()` helper, and construct `PreviewClient` from the same clientset in `cmd/api/main.go`.

### 2. Handler

`internal/api/interfaces.go`: add

```go
type PreviewLister interface {
    ListPreviewReleases(ctx context.Context, team, service string) ([]k8s.PreviewRelease, error)
}
```

and `PreviewLister PreviewLister` to the handler options (`router.go`, next to `QuotaReader`). Wire it in `cmd/api/main.go` (nil when the clientset cannot be built, with the existing warning pattern).

`ListPreviews` keeps the 401/400/403 checks, then:

- `h.opts.PreviewLister == nil` -> `writeError(w, 503, "preview listing unavailable: kubernetes client not configured")`.
- `errors.Is(err, k8s.ErrNamespaceAbsent)` -> 200 `{"items": [], "count": 0, "team", "namespace", "preview_namespace": "absent"}`.
- any other error -> `slog.Warn` + `writeError(w, 503, "could not list previews in <ns>: <err>")`. The body is the standard error body: no `items`, no `count`.
- success -> 200 `{"items": [...], "count": len, "team", "namespace", "preview_namespace": "present"}`. Items are JSON objects with snake_case keys (`release`, `service`, `preview_id`, `namespace`, `replicas`, `ready_replicas`, `available_replicas`, `created_at`) and a derived `url` is NOT included (the platform domain is not known to this handler reliably). `items` is always a non-nil slice.
- The ArgoCD call and the `argocd` prefix filter are removed from this handler.

### 3. MCP tool

`toolListPreviews` handler code is unchanged: a 503 already becomes `NewToolResultError("Failed to list previews for <team>: ...")` through `apiGet`/`doRequest`. Only the description changes to: lists preview Helm releases deployed by `mctl_create_preview` into `{team}-preview`, named `preview-{service}-{id}`; a failed read is a tool error, never an empty list; an empty list with `preview_namespace: "absent"` means the preview namespace does not exist. Tool count is unchanged, so `server_test.go` expectations hold.

### 4. RBAC (mctl-gitops, cross-repo prerequisite)

Add to `helm-charts/tenant/templates/preview.yaml` a Role/RoleBinding `mctl-api-preview-reader` (or extend `mctl-api-preview-quota-reader`) granting the `mctl-api` ServiceAccount `get,list` on `apps/deployments` in `{tenant}-preview`. No secret access. Namespace `get` is already granted cluster-wide. This is a separate PR in mctl-gitops; it is referenced here, not implemented by this repo's change.

## Alternatives

- **Read Helm release Secrets (`owner=helm`, `name=preview-<service>-*`).** Most faithful to "a release exists", and would expose `mctl.ai/expires-at` and release status. Dropped: needs `list secrets` in the preview namespace, which RBAC cannot restrict to Helm storage Secrets and would let mctl-api read every ExternalSecret-synced preview credential; the tenant chart explicitly avoids granting mctl-api secret access. Even a metadata-only client still needs the full `list secrets` verb.
- **List Pods with `mctl.ai/preview=true`.** Labels are set by the deploy workflow, but pods disappear when a release is scaled to zero or crash-loops between restarts, and a Deployment with N replicas yields N entries. Deployments are the stable one-per-release object.
- **Keep ArgoCD and only fix the error path.** Fixes defect 1 but leaves an endpoint that can never return a real preview. Rejected.
- **Soft result `{"state": "unknown"}` with HTTP 200.** The issue allows it, but MCP callers would then see a successful tool result and need to parse state. A non-2xx answer turns into an MCP tool error with no extra code, which is the more fail-closed default.

## Platform impact

- **API contract change:** `items` entries change shape (from `argocd.AppStatus` to preview-release objects) and failures move from 200 to 503. Since the endpoint has never returned a real preview, no working caller depends on the old item shape. Callers that tolerated 200-with-`note` will now get an error; that is the intended fix.
- **Rollout order:** merge and sync the mctl-gitops RBAC first; otherwise each tenant gets 503 (forbidden) from this endpoint until its tenant app syncs. Both orders are safe: neither returns a false empty list.
- **Resource impact:** one namespaced Deployment list (plus at most one namespace get on an empty result) per call; negligible. No ArgoCD call on this path any more.
- **Security:** new grant is read-only `get,list deployments` in preview namespaces; Deployment specs can contain plain env values from preview values files. This is narrower than secrets and equal to what tenant members can already see. Tenant authorization in the handler is unchanged.
- **No migrations.**
- **Risk:** a preview whose Helm install failed before creating the Deployment is not listed. Mitigation: documented in the tool description and Open questions; `wft-preview-deploy` uses `--wait`, so such a release also fails the workflow visibly.
