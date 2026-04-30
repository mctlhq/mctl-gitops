# Tasks: client-go-version-drift

- [ ] 1. Bump `k8s.io/client-go` and coordinated modules to v0.36.0 — run
  the following commands and commit the resulting `go.mod` and `go.sum`:
  ```
  go get k8s.io/client-go@v0.36.0
  go get k8s.io/api@v0.36.0
  go get k8s.io/apimachinery@v0.36.0
  go mod tidy
  ```
  DoD: `go.mod` references `k8s.io/client-go v0.36.0`, `k8s.io/api v0.36.0`,
  and `k8s.io/apimachinery v0.36.0`; `go mod tidy` exits 0; `go.sum` is
  consistent; no unrelated module version changes are introduced.

- [ ] 2. Audit API type usage for removed or deprecated types (depends on 1)
  — search the codebase for all imports of `k8s.io/api/*` packages and all
  string literals that reference versioned API group paths
  (e.g., `"batch/v1beta1"`, `"apps/v1beta*"`, `"extensions/v1beta*"`).
  For each, verify it is still present in the Kubernetes 1.36 / client-go
  v0.36 API surface. Update any removed or deprecated references to their
  v0.36 replacements.
  DoD: A checklist of all k8s API types and group strings used in mctl-api
  is documented in this task's PR description; every entry is marked
  "present in v0.36" or "replaced with <new path>"; no deprecated API
  references remain in the codebase.

- [ ] 3. Compile and fix any type errors (depends on 2) — run
  `go build ./...` and resolve any compilation errors introduced by the
  module bump. No business logic may be altered to work around type changes;
  only API type references may be updated.
  DoD: `go build ./...` exits 0 with zero errors on the feature branch.

- [ ] 4. Run full test suite (depends on 3) — execute `go test -race ./...`.
  No test logic may be deleted or skipped to force a pass.
  DoD: `go test -race ./...` exits 0 with zero failures and zero data-race
  reports; no test cases removed or marked skipped relative to the baseline.

- [ ] 5. Update CI workflow if Go or k8s version matrix entries are pinned
  (depends on 1) — check CI configuration for any hard-coded client-go or
  Kubernetes version references and update them to v0.36.0.
  DoD: CI pipeline passes on the feature branch; no jobs reference v0.32
  in their configuration.

- [ ] 6. Bump image tag in ArgoCD Helm values and open pull request (depends
  on 4, 5) — update `image.tag` (or equivalent) in the GitOps repository
  to the new image digest. Confirm `PodDisruptionBudget` (`minAvailable: 1`)
  is present in the `admins` tenant manifests.
  DoD: PR is open; ArgoCD diff shows only the image tag change; at least one
  reviewer has approved; no changes to `labs` tenant manifests.

- [ ] 7. Staged rollout and observation (depends on 6) — merge the PR and
  monitor the rolling update in the `admins` tenant. Observe Kubernetes API
  call success rates, pod/service/cronjob listing latency, and error rate for
  30 minutes post-deployment.
  DoD: All pods running the new image; `/healthz` returns HTTP 200;
  Kubernetes API call error rate is 0%; pod/service listing p99 latency is
  within 10% of the pre-upgrade baseline; Prometheus dashboard screenshot
  attached to the PR.

## Tests

- [ ] T1. Unit — `go test -race ./...` passes with zero failures and zero
  data-race reports on the upgraded codebase.
- [ ] T2. Integration — existing tests covering `get_service_status`,
  pod listing, service listing, and cronjob listing pass against the upgraded
  binary connected to a Kubernetes API server.
- [ ] T3. API type audit — the PR description contains a complete checklist
  of all `k8s.io/api/*` types and group strings used in mctl-api, with each
  confirmed present in client-go v0.36.
- [ ] T4. Container smoke test — `/healthz` returns HTTP 200 within 5 s of
  startup; Kubernetes API calls to list pods succeed in the staging environment.
- [ ] T5. No regression in MCP tools — at least one end-to-end invocation of
  `get_service_status` and `get_workflow_logs` via MCP Inspector succeeds
  against staging after the upgrade.

## Rollback

If the upgraded deployment causes Kubernetes API call failures, elevated error
rates, or any on-call alert within the observation window:

1. In the GitOps repository, revert the `image.tag` commit (or open a revert
   PR) to restore the previous client-go v0.32-based image digest.
2. ArgoCD detects the drift and syncs automatically (or trigger manually with
   `argocd app sync mctl-api`), rolling the `admins` tenant back within one
   rolling-update cycle.
3. The PodDisruptionBudget (`minAvailable: 1`) ensures at least one healthy
   replica serves traffic throughout the rollback.
4. Because all Kubernetes API calls in mctl-api are stateless reads (no
   writes or watches that persist state between pod generations), rollback is
   clean and immediate — no partially-written resources or stale watch
   caches to reconcile.
5. After rollback, open a post-mortem issue documenting the failure mode,
   with specific attention to which API type or client-go behaviour changed,
   before re-attempting the upgrade.

No database migrations, Vault policy changes, or CRD updates are introduced
by this proposal, so rollback is a pure image-tag revert.
