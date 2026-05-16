# Tasks: argocd-v3-4-2-stability-patch

- [ ] 1. Locate the ArgoCD version pin in the bootstrap manifest — DoD: the exact
  file path and field name (e.g., `image.tag`, `global.image.tag`, or equivalent)
  within `platform-gitops/bootstrap/` that controls the ArgoCD server image tag
  are documented in the PR description.

- [ ] 2. Bump ArgoCD image tag from `v3.4.0` to `v3.4.2` (depends on 1) — DoD:
  a single commit changes the tag to `v3.4.2`; `git diff` shows exactly one
  field changed; no other manifest lines are modified.

- [ ] 3. Open a PR and pass CI (depends on 2) — DoD: PR is open against the main
  branch; CI linting and YAML validation pass; at least one platform-engineer
  approval is recorded; PR description references this proposal slug and links to
  the ArgoCD v3.4.2 release notes at
  https://github.com/argoproj/argo-cd/releases.

- [ ] 4. Merge PR and confirm ArgoCD self-syncs the bootstrap Application (depends
  on 3) — DoD: ArgoCD Application `bootstrap` (or equivalent) shows `Synced` and
  `Healthy` in the ArgoCD UI at `ops.mctl.ai` within 10 minutes of merge.

- [ ] 5. Verify running ArgoCD pod image digest (depends on 4) — DoD:
  `kubectl get pod -n <argocd-namespace> -o jsonpath='{.items[*].spec.containers[*].image}'`
  returns a tag or digest that resolves to `v3.4.2`; no pod is still running the
  old image.

## Tests

- [ ] T1. Post-deploy RBAC smoke test — trigger a sync operation as a restricted
  tenant service account that exercises the RBAC permission validator; confirm the
  ArgoCD server pod does not restart (check `kubectl get pod` restart count before
  and after).

- [ ] T2. Sync correctness test — verify that at least one Application in each
  tenant namespace (`admins`, `labs`) reaches `Synced` + `Healthy` status after
  the upgrade without manual intervention.

- [ ] T3. CVE scan — run a container image scan (e.g., Trivy) against the
  `v3.4.2` image and confirm no critical Go-runtime CVEs flagged against v3.4.0
  remain open.

- [ ] T4. Readiness probe gate — confirm that during the rolling update the old
  pod was not terminated before the new pod passed its readiness probe (verify via
  Deployment events or pod timestamps in the rollout window).

## Rollback
Revert the version bump commit (one-line change) and open an expedited PR. Once
merged, ArgoCD will self-sync back to v3.4.0. Because there are no CRD changes
between these versions, no additional rollback steps are needed. If the ArgoCD
server is already crashed and cannot self-sync, apply the reverted bootstrap
manifest directly with `kubectl apply` or `helm upgrade` as an emergency break-glass
action, then file a post-incident review.
