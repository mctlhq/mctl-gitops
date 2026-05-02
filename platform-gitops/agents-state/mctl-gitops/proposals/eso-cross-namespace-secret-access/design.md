# Design: eso-cross-namespace-secret-access

## Current state

As documented in `context/architecture.md`, External Secrets Operator is deployed as a
cluster-wide controller. A single `ClusterSecretStore` named `vault-backend` authenticates to
Vault at `secrets.mctl.ai` and is used by every tenant namespace (`admins`, `labs`) to resolve
secrets into Kubernetes Secrets. ExternalSecret manifests are stored in
`platform-gitops/argo-workflows/secrets/` and are reconciled by ArgoCD via the App-of-Apps pattern.

Under this topology the ESO controller runs with a cluster-scoped service account that has
the permission to call Vault for any path. ESO's internal `getSecretKey` helper resolves a
Vault key reference at reconciliation time. Before the CVE-2026-22822 fix, ESO did not
validate that the requesting ExternalSecret's namespace matched the Vault path namespace
segment it was trying to read. Any namespace that could create an ExternalSecret could therefore
craft a manifest that reads from another namespace's Vault path simply by referencing that path
directly, bypassing the intended tenant isolation.

The current ESO version is at or below `helm-chart-2.4.0` (the chart line established by
`eso-dns-exfil-patch`). CVE-2026-22822 was published 2026-01-20 and is fixed in ESO
`helm-chart-2.4.1` or the first subsequent release that includes the patch.

## Proposed solution

### Primary fix: upgrade ESO to helm-chart-2.4.1 (or latest patched release)

The upstream advisory for CVE-2026-22822 confirms the fix is included in the ESO controller
release bundled with `helm-chart-2.4.1`. The upgrade is a standard Helm chart version bump,
consistent with how previous ESO patches were applied on this platform.

Steps:

1. Confirm that `helm-chart-2.4.1` bundles the CVE-2026-22822 fix by inspecting the upstream
   release notes at `https://github.com/external-secrets/external-secrets/security/advisories`.
   Record the exact ESO controller image tag for audit traceability.
2. Audit all ExternalSecret manifests in `platform-gitops/argo-workflows/secrets/` to confirm
   that no manifest cross-references a Vault path outside its own tenant namespace. Any such
   manifest must be corrected before the upgrade proceeds.
3. Update the ESO Helm chart version pin in the relevant ArgoCD Application manifest inside
   `platform-gitops/apps/` from the current version to `helm-chart-2.4.1`.
4. If the new chart introduces updated CRDs, apply the CRD manifests first (before rolling the
   operator Deployment) using `kubectl apply -f` against the chart's `crds/` directory.
5. Commit the change, open a PR, and let ArgoCD reconcile via the App-of-Apps pattern.
6. After rollout, verify that the `ClusterSecretStore vault-backend` remains `Ready`, all
   ExternalSecret resources return to `Ready=True`, and no cross-namespace secret read succeeds
   in a controlled test (see tasks.md T2).

### Secondary hardening: namespace-scoping annotation or Vault policy verification

After the upgrade, verify that the Vault policies attached to the AppRole/Kubernetes auth used
by ESO limit each tenant's readable paths to their own namespace prefix (e.g.,
`secret/data/admins/*` is not readable by the auth role used for `labs`). This is a defence-in-
depth measure that ensures even if a future ESO bug re-opens the path, Vault itself will deny the
cross-namespace read.

## Alternatives

### Option 1: RBAC-only patch without upgrading ESO

Add a Kubernetes `ValidatingWebhookConfiguration` that rejects ExternalSecret objects whose
`spec.data[].remoteRef.key` path contains a namespace segment other than the submitting namespace.
This is a compensating control, not a fix — the vulnerable code path in ESO remains reachable
through any means that bypasses the webhook (e.g., direct API server access with sufficient RBAC).
Dropped: incomplete mitigation; the webhook adds operational complexity and still leaves
CVE-2026-22822 technically open.

### Option 2: Migrate from ClusterSecretStore to per-namespace SecretStore

Decompose the single `ClusterSecretStore vault-backend` into a `SecretStore` per tenant
namespace, each using a separate Vault AppRole scoped only to that namespace's paths. This is the
architecturally cleanest solution for long-term tenant isolation but requires: rewriting all
ExternalSecret manifests to reference the namespace-local `SecretStore`, provisioning new Vault
AppRoles, updating the bootstrap configuration, and testing all tenants. The blast radius is
significantly wider than a Helm chart version bump. This option is valuable as a follow-on
hardening proposal but is not appropriate as the immediate CVE response. Dropped for this
proposal; recommended as a future ADR.

### Option 3: Block getSecretKey at the Vault policy level only

Tighten the Vault policy so that the ESO AppRole cannot read any path that does not match the
caller's namespace. This mitigates the immediate risk without touching the ESO version. However
it requires Vault policy changes (write operation against production Vault), the policy logic
must correctly map Kubernetes namespace to Vault path prefix for every tenant, and ESO's
vulnerable code path remains open to any future misconfiguration. Dropped as the sole fix;
acceptable as a defence-in-depth measure alongside the upgrade.

## Platform impact

### Migrations

- The ESO Helm chart version in `platform-gitops/apps/` must be bumped to `helm-chart-2.4.1`.
- If `helm-chart-2.4.1` introduces new or modified CRD versions for `ExternalSecret`,
  `ClusterSecretStore`, or `SecretStore`, the CRDs must be applied before the operator rolls.
  Use `kubectl diff` to assess the delta before applying.

### Backward compatibility

`helm-chart-2.4.1` is a patch release on the v2.4.x line. No breaking changes to the
ExternalSecret or ClusterSecretStore APIs are expected. All existing ExternalSecret manifests
that correctly reference their own tenant's Vault paths will continue to function without
modification.

### Resource impact

ESO runs in the `admins` tenant namespace. No ESO pods run inside the `labs` namespace. A patch-
level Helm chart upgrade is not expected to increase the controller's memory or CPU footprint.
However, as `labs` is near its memory limit, the post-upgrade monitoring step (task 5) must
confirm that no new pods are scheduled into `labs` as a side-effect of this change. This upgrade
carries LOW memory risk for `labs`.

### Risks and mitigations

- **Risk:** `helm-chart-2.4.1` is confirmed to fix CVE-2026-22822 based on the advisory text but
  the chart contents have not yet been verified in this environment.
  **Mitigation:** Task 1 requires explicit confirmation that the patched controller image is
  bundled before any change is committed.
- **Risk:** ExternalSecret reconciliation pauses during the operator rolling update, causing a
  temporary gap in secret rotation for tenant workloads.
  **Mitigation:** ESO upgrades via a rolling Deployment update; existing Kubernetes Secrets
  remain in place throughout. The pause in rotation is expected to be under 60 seconds.
- **Risk:** A CRD schema update in the new chart causes existing ExternalSecret objects to fail
  validation.
  **Mitigation:** Run `kubectl apply --dry-run=server` against the new CRDs before committing;
  on incompatibility, apply CRDs manually prior to the operator rollout.
- **Risk:** Cross-namespace read isolation is not fully enforced after upgrade because Vault
  policies are too broad.
  **Mitigation:** Defence-in-depth Vault policy review is included as a task; a controlled
  cross-namespace read test (T2) must pass before the fix is considered complete.
