# Design: argocd-v3-4-upgrade-plan-v2

## Current state

The platform runs ArgoCD v3.3.9 in `admins` (and RC7 in `labs` following the preparation
work from `argocd-v3-4-upgrade-plan`). All ArgoCD resources are managed through the
App-of-Apps ApplicationSet pattern documented in ADR 0001 (see `context/decisions/0001-app-of-apps-pattern.md`).
The ArgoCD version is pinned via an image tag in the bootstrap Application manifest under
`platform-gitops/apps/`. The preparation proposal (`argocd-v3-4-upgrade-plan`) completed:
changelog review, deprecated-field corrections, RC7 staging in `labs`, baseline memory
recording, and 24-hour RC7 health monitoring. All Phase 1 tasks from that proposal are done
and their outputs are committed to `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/`.

ArgoCD v3.4.0 GA was published on May 5, 2026. Its notable additions over v3.3.x include
cluster reconciliation pausing (useful for planned maintenance windows), Microsoft Teams
Adaptive Cards webhook notifications, and Helm value globs for flexible chart templating.
It subsumes all v3.3.x security patches, including CVE-2026-42880.

Tenant `labs` is near its memory quota limit. A memory delta between the RC7 baseline and
the GA build must be measured before `admins` promotion.

## Proposed solution

Execution proceeds in two sequential steps. Both steps reuse the same git-commit-and-sync
mechanism that ArgoCD uses to self-manage its own upgrade.

### Step A — GA pin in `labs`

1. Update the ArgoCD version pin in the `labs`-scoped Application manifest (or the shared
   bootstrap manifest for `labs` if a per-tenant override is used) from RC7 to `v3.4.0`.
   Commit with a message referencing this proposal slug.
2. ArgoCD performs a rolling restart of its own pods in `labs`. The rolling update strategy
   ensures at least one ArgoCD server replica remains available throughout.
3. After pod stabilization, query `kubectl top pods -n argocd` (or the equivalent Prometheus
   metric `container_memory_working_set_bytes`) to capture the GA memory footprint. Compare
   against the RC7 baseline stored in
   `platform-gitops/agents-state/argocd-v3-4-upgrade-plan/labs-memory-post-rc7.txt`.
4. Run `argocd app list` and `argocd appset list` against `labs` to confirm all objects are
   `Synced` and `Healthy`.
5. Begin the 24-hour stability monitoring window for GA in `labs`. No `admins` change occurs
   during this window.

### Step B — GA promotion to `admins`

1. After the 24-hour window closes with no incidents (no pod restarts, no reconciliation
   errors, no memory quota alerts), update the version pin in the `admins` bootstrap
   Application manifest under `platform-gitops/apps/` to `v3.4.0`. Commit and push.
2. ArgoCD performs a rolling restart of its own pods in `admins` using the same rolling
   update strategy. At least one replica stays available.
3. After pod stabilization, verify `argocd version --server` returns `v3.4.0` and
   `argocd app list` shows all Applications in `admins` as `Synced` and `Healthy`.
4. Document the upgrade completion in
   `platform-gitops/agents-state/argocd-v3-4-upgrade-plan-v2/admins-upgrade-complete.md`.

### Memory guard for `labs`

If the GA memory footprint in `labs` exceeds the RC7 baseline by more than 10 percent, or
if total ArgoCD memory in `labs` would breach the tenant quota, Step B is blocked until
either the quota is increased or ArgoCD resource limits are tuned (e.g., reducing the
number of replicas in `labs` to 1 during the transition period). This decision must be
documented in writing before Step B proceeds.

### New features — no action in this proposal

Cluster reconciliation pausing, Teams webhook, and Helm value globs are available once
v3.4.0 is running but are not configured by this proposal. Feature enablement proposals
can be raised separately after the upgrade stabilizes.

## Alternatives

**A. Skip GA validation in `labs` and upgrade `admins` directly.**
The preparation proposal (`argocd-v3-4-upgrade-plan`) explicitly required a 24-hour `labs`
confirmation before `admins` promotion. Skipping this gate removes the only pre-production
validation step and re-introduces the risk of discovering regressions in production. The
memory delta between RC7 and GA is also unknown. Rejected.

**B. Use an automated deployment pipeline (e.g., Renovate Bot PR merged on CI green).**
Automating the ArgoCD self-upgrade removes the manual memory check and the 24-hour gate,
which are critical constraints given `labs` is near quota. Automation is a valid long-term
improvement but is not safe to introduce while `labs` has no memory headroom. Rejected for
this cycle.

**C. Stay on RC7 indefinitely in `labs` and upgrade `admins` directly to GA.**
RC7 is not a supported release; it will not receive further security patches. Running
production (`admins`) ahead of staging (`labs`) on GA while `labs` runs an unsupported
build creates an inverted testing model. Rejected.

## Platform impact

- **Migrations:** No data migrations required. The ArgoCD application database in etcd is
  forward-compatible from v3.3 to v3.4. Deprecated-field corrections from the preparation
  proposal are already merged.
- **Backward compatibility:** ArgoCD follows semver; no breaking API changes are introduced
  between v3.3 and v3.4. ApplicationSet CRD compatibility was verified in the preparation
  proposal. The App-of-Apps pattern (ADR 0001) is unchanged.
- **Resource impact for `labs`:** `labs` is near its memory quota. The GA build's memory
  footprint relative to RC7 is unknown until Step A completes. If the delta is adverse, Step
  B is blocked. This is the primary risk for this proposal and is flagged accordingly.
- **Risks and mitigations:**
  - Risk: GA build consumes meaningfully more memory than RC7 in `labs`, pushing `labs`
    over quota. Mitigation: mandatory memory comparison in Step A; Step B blocked if the
    delta is adverse.
  - Risk: A regression introduced between RC7 and GA causes ApplicationSet failures in
    `labs`. Mitigation: 24-hour stability window in `labs` before `admins` promotion;
    rollback path is a single `git revert` + ArgoCD self-sync.
  - Risk: ArgoCD self-upgrade leaves `admins` with zero available replicas during restart.
    Mitigation: rolling update strategy enforced; at least one replica kept available.
  - Risk: New v3.4.0 features are inadvertently enabled by default and affect existing
    Applications. Mitigation: verify ApplicationSet and Application health after each step;
    new features are not explicitly configured by this proposal.
