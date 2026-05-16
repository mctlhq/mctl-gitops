# Design: argocd-v3-4-2-stability-patch

## Current state
ArgoCD is deployed at `ops.mctl.ai` via the App-of-Apps bootstrap chart located
under `platform-gitops/bootstrap/`. The bootstrap chart (and any values file it
references) pins the ArgoCD image tag. The existing `argocd-v3-4-upgrade-plan-v2`
proposal sets that pin to `v3.4.0` GA.

At v3.4.0 the permission validator contains a code path that panics under specific
RBAC evaluation conditions, causing the ArgoCD server pod to crash and restart.
The Go runtime bundled in v3.4.0 also carries known CVEs addressed in subsequent
patch releases.

ArgoCD reconciles both `admins` and `labs` tenant namespaces. A crash of the
ArgoCD server immediately halts GitOps reconciliation for all tenants until the
pod recovers, increasing mean time to sync for any in-flight change.

## Proposed solution
Change the single pinned ArgoCD image tag in the bootstrap manifest from `v3.4.0`
to `v3.4.2`. This is a one-line edit in `platform-gitops/bootstrap/` (the exact
file is the ArgoCD Helm values override or the bootstrap Application manifest,
whichever carries the `image.tag` or equivalent field).

Because v3.4.2 is a patch release:
- No CRD migrations are required.
- No ApplicationSet schema changes are required.
- The Kubernetes rolling update strategy built into the ArgoCD Deployment resource
  handles the transition: the new pod must pass its readiness probe before the old
  pod is terminated.

This proposal is intentionally scoped to the version bump only. All other
migration steps from the `argocd-v3-4-upgrade-plan-v2` proposal remain unchanged
and should be applied first (or concurrently, with this patch superseding the
version number in that plan).

Architecture reference: `context/architecture.md` — ArgoCD App-of-Apps section
and bootstrap path conventions.

## Alternatives

**Option A — Ship v3.4.0 now and patch later.**
Rejected. The permission validator panic is reproducible under normal RBAC workloads.
Shipping v3.4.0 to production and planning a follow-up bump introduces an
unnecessary availability risk. The cost of the patch is a one-line change; the
cost of a production incident is much higher.

**Option B — Pin to `latest` or a floating minor tag such as `v3.4`.**
Rejected. The platform convention is explicit immutable tags for all workloads
(`context/architecture.md` — "Every platform change = a git commit here"). A
floating tag breaks reproducibility and would cause uncontrolled upgrades on pod
restarts.

**Option C — Wait for v3.5.x and skip v3.4 entirely.**
Rejected. v3.5 is not yet released and carries unknown migration scope. v3.4.2 is
available now, fixes the immediate defect, and the `argocd-v3-4-upgrade-plan-v2`
migration work is already in progress. Abandoning that work would waste sunk effort
and delay remediation.

## Platform impact

### Migrations
None. No CRD changes exist between v3.4.0 and v3.4.2. No ApplicationSet schema
changes. No data migrations.

### Backward compatibility
Fully backward compatible. Existing ArgoCD Applications, ApplicationSets, and
AppProjects are unaffected.

### Resource impact
Negligible. The ArgoCD server Deployment is in the `admins` namespace. Tenant
`labs` is close to its memory limit but is not affected — ArgoCD does not run in
`labs`. No new workloads or sidecars are introduced.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| New image pull failure (registry unavailable) | Low | Pre-pull image in CI smoke step; ArgoCD pod keeps running until new pod is Ready |
| Unexpected regression in v3.4.2 | Very low | Patch releases are low-risk; verify with post-deploy sync smoke test |
| Bootstrap manifest typo in tag | Low | PR review + CI diff check; rollback is a one-line revert |
