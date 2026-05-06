# Tasks: argocd-v3-4-upgrade-plan-v2

## Step A — Deploy GA to `labs`

- [ ] 1. Update ArgoCD version pin to v3.4.0 GA in the `labs` Application manifest — DoD:
  The `labs`-scoped ArgoCD Application manifest (or `labs` Helm values override) references
  the `v3.4.0` image tag. A PR is opened, reviewed, and merged. The commit message
  references this proposal slug (`argocd-v3-4-upgrade-plan-v2`).

- [ ] 2. Confirm rolling restart completes with at least one replica available (depends on 1)
  — DoD: `kubectl rollout status deployment/argocd-server -n argocd` exits 0 in `labs`.
  During the restart, `argocd app list --server ops.mctl.ai` continues to respond (no
  complete outage). `argocd version --server` returns `v3.4.0`.

- [ ] 3. Measure GA memory footprint in `labs` and compare to RC7 baseline (depends on 2)
  — DoD: `kubectl top pods -n argocd` output (or equivalent Prometheus query for
  `container_memory_working_set_bytes`) is recorded and committed to
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan-v2/labs-memory-post-ga.txt`.
  A delta calculation is written as a comment in the same file. If the delta exceeds 10
  percent of the RC7 baseline OR total ArgoCD memory would breach the `labs` quota, a
  STOP recommendation is appended and task 7 (Step B) is blocked until resolved.

- [ ] 4. Verify ApplicationSet and Application health in `labs` (depends on 2) — DoD:
  `argocd appset list` and `argocd app list` against `labs` show zero objects in
  `Degraded`, `Unknown`, or `OutOfSync` state. Any object not in `Synced`/`Healthy` within
  ten minutes of pod stabilization is investigated and resolved before the monitoring window
  begins.

- [ ] 5. Perform end-to-end sync test in `labs` (depends on 4) — DoD: A non-critical
  Application in `labs` is selected; `argocd app sync <app>` is run and completes
  successfully. The target cluster state matches the desired manifest state. No errors appear
  in the ArgoCD application controller logs for that sync.

- [ ] 6. Run 24-hour stability monitoring window for GA in `labs` (depends on 3, 4, 5)
  — DoD: For a continuous 24-hour period: no ArgoCD pod restarts in `labs`, no
  ApplicationSet or Application reconciliation errors in ArgoCD logs, no memory quota alerts
  fired for the `labs` namespace. A health summary is committed to
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan-v2/labs-24h-ga-health-report.md`.
  Task 7 is unblocked only after this file is committed.

## Step B — Promote GA to `admins`

- [ ] 7. Update ArgoCD version pin to v3.4.0 GA in the `admins` bootstrap Application
  manifest (depends on 6, and task 3 must not have a STOP recommendation) — DoD: The
  ArgoCD Application manifest under `platform-gitops/apps/` references the `v3.4.0` image
  tag for `admins`. A PR is opened, reviewed, and merged. The commit message references this
  proposal slug.

- [ ] 8. Confirm rolling restart completes with at least one replica available (depends on 7)
  — DoD: `kubectl rollout status deployment/argocd-server -n argocd` exits 0 in `admins`.
  During the restart, `argocd app list` continues to respond. `argocd version --server`
  returns `v3.4.0`.

- [ ] 9. Verify ApplicationSet and Application health in `admins` (depends on 8) — DoD:
  `argocd appset list` and `argocd app list` against `admins` show zero objects in
  `Degraded`, `Unknown`, or `OutOfSync` state within ten minutes of pod stabilization.
  All three ApplicationSets (`apps`, `tenants`, `openclaw-skills`) are present and healthy.

- [ ] 10. Document upgrade completion (depends on 9) — DoD: A summary file is committed to
  `platform-gitops/agents-state/argocd-v3-4-upgrade-plan-v2/admins-upgrade-complete.md`
  containing: upgrade timestamp, final ArgoCD version string from `argocd version --server`,
  confirming Application and ApplicationSet counts, and a note that no regressions were
  observed.

## Tests

- [ ] T1. Rolling restart maintains availability — during the restart in each tenant, issue
  `argocd app list` every 30 seconds. Assert that the command never returns a connection
  error for more than 60 consecutive seconds (i.e., at least one replica remains responsive).

- [ ] T2. All ApplicationSets produce correct Applications post-upgrade — run
  `argocd appset list` and `argocd app list` in both `labs` and `admins` after each
  step completes. Assert zero objects in `Degraded`, `Unknown`, or `OutOfSync` state.

- [ ] T3. `labs` memory stays within quota after GA deployment — query
  `container_memory_working_set_bytes` for all ArgoCD pods in `labs` after pod
  stabilization. Assert total is below the `labs` tenant memory quota. If it is not,
  Step B (tasks 7–10) must not proceed.

- [ ] T4. GA memory delta vs RC7 baseline is documented and within threshold — compare the
  value in `labs-memory-post-ga.txt` to `labs-memory-post-rc7.txt` (from the preparation
  proposal). Assert the increase is less than 10 percent. Document the result regardless.

- [ ] T5. End-to-end sync completes without error in `admins` — after task 9 passes, select
  one non-critical Application in `admins`, force `argocd app sync <app>`, and confirm the
  sync completes successfully with the target state matching desired state.

## Rollback

**Step A rollback (`labs`):** Revert the commit that updated the `labs` version pin to
v3.4.0 GA. ArgoCD detects the revert and self-syncs back to RC7 (or to v3.3.9 if the RC7
pin was also reverted). No data migration is required. All ApplicationSets and Applications
continue operating normally. Deprecated-field corrections from the preparation proposal
remain in place and are safe for both versions.

**Step B rollback (`admins`):** Revert the commit that updated the `admins` bootstrap
Application manifest to v3.4.0. ArgoCD detects the revert on the next reconciliation cycle
and initiates a rolling restart back to v3.3.9. Rollback time is bounded by the rolling
update strategy (seconds to minutes depending on replica count). No etcd data migration is
required; ArgoCD state is tolerant of downgrades within the same minor series. All
ApplicationSets and Applications continue operating normally under v3.3.9.

If rollback must be initiated before ArgoCD itself is healthy enough to self-sync, apply
the reverted manifest directly: `kubectl apply -f platform-gitops/apps/<argocd-app>.yaml`
from a machine with cluster-admin access.
