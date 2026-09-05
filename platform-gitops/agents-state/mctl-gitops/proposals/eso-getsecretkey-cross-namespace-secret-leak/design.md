# Design: eso-getsecretkey-cross-namespace-secret-leak

## Current state
Per `context/architecture.md`, External Secrets Operator + Vault
(`vault-backend` ClusterSecretStore) is the platform's tech stack for
secret delivery. ExternalSecret manifests live under
`platform-gitops/argo-workflows/secrets/`, and the ESO controller itself is
deployed as a chart, likely referenced from `platform-gitops/bootstrap/` or
a dedicated Application under `platform-gitops/apps/` (following the same
App-of-Apps pattern as other platform components). The controller runs
with elevated RBAC across tenant namespaces so it can render secrets into
`admins`, `labs`, and other tenants' namespaces. CVE-2026-22822 lets the
`getSecretKey` template function (introduced for the senhasegura DSM
provider) abuse that elevated RBAC to read secrets outside the requesting
namespace. Affected range: 0.20.2–<1.2.0. Fixed in 1.2.0 by removing the
function outright.

## Proposed solution
1. Locate the ESO Helm chart version pin in this repo (bootstrap chart
   values or an Application definition in `platform-gitops/apps/`).
2. Bump the chart version to one that bundles operator >=1.2.0 — the
   researcher's scan shows `helm-chart-2.10.0` (Aug 28, 2026) as latest,
   which post-dates the fix.
3. Grep `platform-gitops/argo-workflows/secrets/` (and any other
   ExternalSecret manifests in the repo) for use of `getSecretKey` before
   bumping, since the function is removed in the fixed version and any
   existing usage would break at upgrade time. None is expected given the
   architecture doc only references Vault as the backend (not senhasegura
   DSM), but this must be confirmed rather than assumed.
4. Let the ApplicationSet/App-of-Apps sync flow roll out the new chart
   version — no manual `kubectl apply` or Helm CLI invocation outside git.
5. No ClusterSecretStore, RBAC, or ExternalSecret schema changes are
   needed; this is purely a controller version bump.

## Alternatives
- **Patch/vendor a fork with `getSecretKey` disabled instead of bumping the
  chart** — rejected: unnecessary maintenance burden when an official fixed
  release already exists and is newer than our current pin.
- **Restrict ESO's RBAC via a NetworkPolicy or reduced ClusterRole instead
  of upgrading** — rejected: a narrower RBAC role is a bigger, riskier
  change to a controller that legitimately needs cross-namespace access to
  do its job; the upstream fix (removing the vulnerable function) is
  targeted and lower-risk.
- **Defer until the next scheduled major review** — rejected: CVSS 8.8
  critical, directly hits the secret-isolation model between tenants
  (including the memory-constrained `labs` tenant), and the fix is a
  low-effort chart bump with no known breaking usage in this repo.

## Platform impact
- **Migrations:** None expected. If the `getSecretKey` audit (task 3 in
  tasks.md) finds actual usage, those specific ExternalSecret manifests
  would need rewriting before the bump — but no such usage is currently
  known in this repo.
- **Backward compatibility:** ExternalSecret and ClusterSecretStore CRDs
  are unaffected by this fix; existing manifests under
  `platform-gitops/argo-workflows/secrets/` continue to work unchanged
  unless they use the removed function.
- **Resource impact (labs):** Per the analyst's rationale, the ESO
  controller's memory footprint is negligible and this patch does not
  increase `labs` memory usage. No new workloads or resource requests are
  added to `labs`; task list includes an explicit post-upgrade check of
  ESO controller memory to confirm this.
- **Risks and mitigations:**
  - Risk: an existing ExternalSecret manifest uses `getSecretKey` and
    breaks on upgrade. Mitigation: explicit grep/audit task before bumping
    (task 2 in tasks.md), performed as a precondition, not an afterthought.
  - Risk: chart bump pulls in unrelated behavioral changes bundled in
    helm-chart-2.10.0. Mitigation: review the chart's changelog for the
    delta between current pin and 2.10.0, focusing on RBAC/CRD changes.
