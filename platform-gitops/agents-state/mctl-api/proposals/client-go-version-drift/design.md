# Design: client-go-version-drift

## Current state

mctl-api v4.14.0 depends on `k8s.io/client-go` v0.32, which corresponds to
the Kubernetes 1.32 API surface. The library is used to:

- List and watch **pods** — for the `get_service_status` MCP tool and REST
  endpoints that surface pod health to the UI/CLI.
- List **services** — for service discovery and status reporting.
- List **cronjobs** (`batch/v1`) — for scheduled-job status.
- Query **workflow custom resources** (Argo Workflows CRDs) — for workflow
  status in the `get_workflow_logs` and related MCP tools.

As of 2026-04-22, `kubernetes/client-go` v0.36.0 is the current stable release
(corresponding to Kubernetes 1.36). The gap is four minor versions (v0.32 →
v0.33 → v0.34 → v0.35 → v0.36). Each minor version ships together with the
corresponding `k8s.io/api`, `k8s.io/apimachinery`, and `k8s.io/client-go`
modules, which must all be bumped together.

Key API changes between v0.32 and v0.36 to verify:
- `batch/v1` CronJob (stable since k8s 1.21) — no removal risk; confirm field
  additions are backward compatible.
- `apps/v1` Deployment/ReplicaSet — no removal risk in this range.
- `core/v1` Pod/Service — stable; no removal risk.
- Any alpha/beta API types mctl-api may reference — must be audited
  during the upgrade.

No direct CVEs affecting v0.32 are known at the time of this proposal.

Architecture reference: `context/architecture.md` — `client-go 0.32`,
Kubernetes API for pods/services/cronjobs/workflows, `admins` tenant,
Kubernetes + ArgoCD platform.

## Proposed solution

This is a module-version bump following the standard `k8s.io` group upgrade
pattern. All `k8s.io/*` modules must move together because they are released
as a coordinated set.

1. **`go.mod` update** — use `go get` to pin the following modules to their
   v0.36.0 tags:
   ```
   go get k8s.io/client-go@v0.36.0
   go get k8s.io/api@v0.36.0
   go get k8s.io/apimachinery@v0.36.0
   go get k8s.io/client-go/tools/...@v0.36.0
   ```
   Run `go mod tidy` to resolve transitive dependencies. Expected transitive
   changes: `sigs.k8s.io/structured-merge-diff`, `k8s.io/utils`,
   `sigs.k8s.io/json` minor version bumps — verify each is compatible.

2. **API type audit** — search the mctl-api codebase for every import of a
   `k8s.io/api/*` package and every use of a versioned API group string
   (e.g., `"batch/v1beta1"`, `"apps/v1beta*"`). For each, verify it is
   still present in the v0.36 API surface. Update any removed or deprecated
   API references to their v0.36 replacements.

3. **Compile and test** — run `go build ./...` and `go test -race ./...`.
   Fix any compilation errors arising from removed or renamed types; no test
   logic may be deleted.

4. **ArgoCD deployment** — image tag bump in Helm values → GitOps PR →
   ArgoCD sync → rolling pod replacement on `admins` tenant.

The choice to bump directly to v0.36.0 (rather than stepping through v0.33,
v0.34, v0.35 individually) is deliberate: the `k8s.io` modules maintain
strong Go API stability between minor versions, and incremental PRs for each
minor hop would quadruple the review burden with no reduction in risk.

## Alternatives

**A. Bump only to v0.33 or v0.34 and schedule further bumps later.**
Partial upgrades reduce the per-PR change surface but perpetuate the problem.
The upgrade cost is dominated by the API audit (task 2), which must be done
regardless of the target version. Jumping to the current stable v0.36.0
eliminates drift entirely and avoids repeated upgrade cycles. Rejected.

**B. Replace direct client-go usage with controller-runtime.**
`controller-runtime` provides a higher-level abstraction (manager, reconciler,
cache) that is well-suited for operator-style workloads but adds significant
complexity for mctl-api's use case, which is read-only status querying and
does not require a reconciliation loop. The migration cost is disproportionate
to the benefit. Rejected.

**C. Defer until a CVE or breaking cluster upgrade forces the issue.**
Deferral allows drift to compound. If the cluster is upgraded to Kubernetes
1.33+ and mctl-api still uses v0.32 client types, API calls that reference
removed types will fail silently or return unexpected errors at runtime —
harder to diagnose than a compile-time type mismatch caught during a planned
upgrade. The effort is low (Impact: 2, Effort: 2); deferral is not
cost-effective. Rejected.

## Platform impact

**Migrations**
None. The upgrade is a Go module version bump. No database schema changes,
no Kubernetes CRD additions, no Vault policy changes.

**Backward compatibility**
`k8s.io/client-go` follows Kubernetes API stability guarantees: stable (`v1`,
`apps/v1`, `batch/v1`) API types are backward compatible across minor versions.
Alpha and beta API types require auditing (task 2 in the task list). All
current API types used by mctl-api (`core/v1`, `apps/v1`, `batch/v1`) are
stable and not scheduled for removal.

The `k8s.io/client-go` library itself (transport, informer, lister interfaces)
maintains Go API compatibility within minor version bumps; the risk of
compile-time breakage is low and caught immediately by `go build ./...`.

**Resource impact**
No change in memory or CPU footprint is anticipated. The `labs` tenant does
not run mctl-api and is unaffected. No resource risk flag required.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|---|---|---|
| A transitive `k8s.io/*` module introduces a breaking Go API change | Low | `go build ./...` on the feature branch catches this before merge |
| mctl-api references a beta API type removed between v0.32 and v0.36 | Low-Medium | Task 2 (API audit) explicitly searches for versioned group strings and beta imports |
| client-go v0.36 changes watch/informer behaviour in a way that affects pod-listing latency | Low | Existing integration tests cover the Kubernetes query paths; observe latency metrics for 30 minutes post-deployment |
| Rolling update exposes mixed client versions during the rollout window | Very Low | All Kubernetes API calls are stateless reads; no shared state between pod generations |
