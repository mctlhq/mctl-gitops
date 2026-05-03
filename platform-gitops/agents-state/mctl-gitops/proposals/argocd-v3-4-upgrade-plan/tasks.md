# Tasks: argocd-v3-4-upgrade-plan

## Phase 1 — RC7 staging in `labs`

- [ ] 1. Review ArgoCD v3.4.0 changelog and ApplicationSet API diff — DoD: A written
  summary (committed to `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/changelog-review.md`)
  lists all: (a) deprecated or removed ApplicationSet fields relative to v3.3.x; (b) new
  required fields; (c) any changes to the ArgoCD Application CRD that affect manifests in
  `platform-gitops/apps/`. Source: https://github.com/argoproj/argo-cd/releases and the
  v3.4.0 migration guide.

- [ ] 2. Correct any deprecated fields in `platform-gitops/apps/` manifests (depends on 1)
  — DoD: All deprecated or removed ApplicationSet/Application fields identified in task 1
  are updated to their v3.4-compatible equivalents. The changes pass `argocd app diff`
  against the current v3.3.9 cluster without unexpected resource mutations. This PR is
  mergeable and safe to apply before the version bump.

- [ ] 3. Record `labs` ArgoCD pod memory baseline — DoD: Current memory consumption of
  all ArgoCD pods in `labs` is recorded (via `kubectl top pods -n argocd` or Prometheus
  query) and committed to
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/labs-memory-baseline.txt`.
  Timestamp and the ArgoCD version at measurement time are included.

- [ ] 4. Deploy ArgoCD RC7 to `labs` and measure memory delta (depends on 2, 3) — DoD:
  The ArgoCD version pin in the `labs` Application manifest is updated to RC7. ArgoCD
  syncs and all pods restart on the new image. Memory consumption after stabilization is
  recorded in
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/labs-memory-post-rc7.txt`.
  The delta is computed and committed. IF the delta would push `labs` over its quota,
  this task produces a STOP recommendation and Phase 2 is blocked.

- [ ] 5. Verify ApplicationSet reconciliation in `labs` (depends on 4) — DoD: Running
  `argocd app list` and `argocd appset list` against `labs` shows all Applications and
  ApplicationSets in `Synced` / `Healthy` state. Any object in `Degraded` or `Unknown`
  state is investigated and resolved before the 24-hour monitoring window begins.

- [ ] 6. Monitor `labs` for 24 hours post-RC7 (depends on 5) — DoD: No ArgoCD pod
  restarts, no ApplicationSet reconciliation errors, and no memory quota alerts are
  recorded during the 24-hour window. Result documented in
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/labs-24h-health-report.md`.

## Phase 2 — GA promotion to `admins`

- [ ] 7. Update version pin to ArgoCD v3.4.0 GA in bootstrap Application manifest
  (depends on 6, GA tag published) — DoD: The ArgoCD Application manifest in
  `platform-gitops/apps/` references the GA image tag for v3.4.0. The commit message
  references this proposal slug. The PR is reviewed and merged.

- [ ] 8. Verify ArgoCD sync and health in `admins` (depends on 7) — DoD: After the
  PR merges and ArgoCD self-upgrades, `argocd app list` shows all Applications as
  `Synced` and `Healthy` in `admins`. Running ArgoCD server version is confirmed as
  v3.4.0 via `argocd version --server`.

## Tests

- [ ] T1. All ApplicationSets produce correct Applications after upgrade — run
  `argocd appset list` and `argocd app list` in both `labs` and `admins`; assert zero
  objects in `Degraded`, `Unknown`, or `OutOfSync` state after the upgrade stabilizes.

- [ ] T2. `labs` memory stays within quota — query `kubectl top pods -n argocd`
  (or Prometheus `container_memory_working_set_bytes`) after Phase 1 stabilizes and
  confirm total ArgoCD memory consumption in `labs` does not exceed the tenant quota.
  If it does, Phase 2 is blocked.

- [ ] T3. `argocd sync` on a test Application succeeds end-to-end — select one
  non-critical Application in `labs`, force an `argocd app sync`, and confirm the
  sync completes without error and the target cluster state matches the desired state.

## Rollback

**Phase 1 rollback (labs):** Revert the RC7 version pin commit for `labs`. ArgoCD
re-syncs `labs` to v3.3.9. No data migration is required; ArgoCD state is stored in
the cluster's etcd and is version-tolerant for downgrades within the same minor series.
If a deprecated-field correction PR was merged, it remains in place (it is safe for v3.3.9).

**Phase 2 rollback (admins):** Revert the GA version pin commit. ArgoCD will self-sync
back to v3.3.9 on the next reconciliation cycle. All ApplicationSets and Applications
continue operating normally under v3.3.9. No downtime beyond the rolling restart window
(seconds to minutes depending on cluster size).
