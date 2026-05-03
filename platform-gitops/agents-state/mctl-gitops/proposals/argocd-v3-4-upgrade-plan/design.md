# Design: argocd-v3-4-upgrade-plan

## Current state

ArgoCD v3.3.9 is deployed in the `admins` tenant. The platform uses the App-of-Apps
ApplicationSet pattern (see `context/architecture.md`; this pattern is an accepted ADR and
is not changed by this proposal). Application manifests live under `platform-gitops/apps/`.
The ArgoCD version is pinned in the bootstrap Application manifest via an image tag or Helm
chart version value.

There is no automated version tracking mechanism; upgrades are manual, git-driven operations.
No upgrade plan exists for v3.4.x, and no staging environment other than tenant `labs` is
available for pre-production testing. Tenant `labs` is near its memory quota limit, so any
memory increase introduced by the upgrade must be measured and assessed before the upgrade
is applied to `admins`.

ArgoCD v3.4.0 RC7 was published April 30, 2026. GA is anticipated within days to weeks.

## Proposed solution

A two-phase rollout separates risk between the staging environment and production.

**Phase 1 — RC7 staging in `labs`.**

1. Review the ArgoCD v3.4.0 changelog and ApplicationSet API diff against v3.3.x.
   Identify any deprecated fields used in `platform-gitops/apps/*.yaml`.
2. Correct any deprecated fields in a preparatory PR, mergeable independently of the
   version bump.
3. Update the ArgoCD version pin to RC7 (or the GA tag when available) in a `labs`-scoped
   override or a dedicated staging Application manifest.
4. Record `labs` Prometheus memory metrics for the ArgoCD pods before and after the upgrade.
5. Run `argocd app list` and `argocd appset list` against `labs` to confirm all objects
   reconcile correctly.
6. Monitor `labs` for 24 hours. If no regression is observed, proceed to Phase 2.

**Phase 2 — GA promotion to `admins`.**

1. When ArgoCD v3.4.0 GA is tagged, update the version pin in the bootstrap Application
   manifest under `platform-gitops/apps/` to the GA tag.
2. Commit and push. ArgoCD self-manages its own upgrade via the App-of-Apps pattern; the
   server will perform a rolling restart.
3. Verify all ApplicationSets and Applications are `Synced` and `Healthy` in `admins`
   after the upgrade.

Both phases use ArgoCD's rolling update strategy, ensuring at least one replica is available
throughout. The rollback path is a single `git revert` + ArgoCD sync, with no data migration
required.

**Memory concern for `labs`.**
Because `labs` is near its memory quota, memory consumption of ArgoCD pods in `labs` must
be measured before and after the RC7 deployment (task 4 in Phase 1). If the delta exceeds
the available headroom in `labs`, the upgrade to `admins` must not proceed until the `labs`
quota is increased or ArgoCD resource requests/limits are tuned. This is flagged as a risk.

## Alternatives

**Wait for GA and upgrade reactively.**
This is the current implicit plan. The risk is that GA is announced without preparation,
forcing a rushed upgrade and skipping the `labs` staging phase. Deprecated API fields may
cause immediate ApplicationSet reconciliation failures. Rejected.

**Skip v3.4.x and wait for v3.5.**
This approach would accumulate skipped minor versions, which increases API drift and
complicates future upgrades. ArgoCD minor releases also carry security fixes; skipping them
unnecessarily extends exposure time. Rejected.

**Automated GitOps version tracking (Renovate Bot).**
Renovate Bot could open PRs automatically when new ArgoCD releases are tagged. This is a
valid long-term improvement but is out of scope for a targeted upgrade plan proposal. The
existing manual process is sufficient for this upgrade cycle.

## Platform impact

- **Migrations:** Deprecated ApplicationSet fields (if any are found in the changelog review)
  must be updated before Phase 2. These are manifest-only changes with no data migration.
- **Backward compatibility:** Minor version upgrade (v3.3 to v3.4). ArgoCD follows semver;
  no breaking API changes are expected within a minor release. The ApplicationSet CRD version
  must be verified not to introduce a new required field.
- **Resource impact:** Memory delta is unknown until Phase 1 measurement. If ArgoCD v3.4
  consumes meaningfully more memory than v3.3.9, `labs` quota must be reviewed. This is
  flagged as a risk for the `labs` tenant. The `admins` tenant has more headroom and is
  not expected to be at risk.
- **Risks and mitigations:**
  - Risk: `labs` memory quota exceeded after RC7 deployment. Mitigation: measure memory
    before and after; halt Phase 2 if `labs` would be pushed over quota.
  - Risk: ApplicationSet API change breaks reconciliation. Mitigation: changelog and API
    diff review in task 1; preparatory field correction PR before the version bump.
  - Risk: RC7 contains a regression not present in GA. Mitigation: Phase 2 uses the GA
    tag, not RC7; RC7 testing is for preparatory confidence only.
