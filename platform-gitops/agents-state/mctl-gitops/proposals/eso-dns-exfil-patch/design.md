# Design: eso-dns-exfil-patch

## Current state
External Secrets Operator is deployed as a cluster-wide controller with the ClusterSecretStore
named `vault-backend`, which authenticates to Vault at `secrets.mctl.ai` and resolves secrets into
Kubernetes Secrets for all tenant namespaces (see `context/architecture.md`). ExternalSecret
manifests are committed under `platform-gitops/argo-workflows/secrets/` and reconciled by ArgoCD
via the App-of-Apps pattern (ADR-0001). ESO is currently on a v2.x release in the v2.0.0–v2.2.0
range affected by CVE-2026-34984. The v2 template engine exposes the full Sprig function library,
including `getHostByName`, to template authors.

## Proposed solution
Upgrade ESO to **v2.2.1** (or the first release that removes `getHostByName` from the accessible
template function set), delivered via the **argo-cd Helm chart `helm-chart-2.4.1`** once the patch
inclusion is verified.

Steps:
1. Verify that `helm-chart-2.4.1` bundles ESO controller v2.2.1+ by inspecting the chart's
   `Chart.yaml` and the controller image tag. If not, identify the correct chart version.
2. Audit all ExternalSecret manifests in `platform-gitops/argo-workflows/secrets/` for any use of
   `getHostByName`; none are expected in legitimate platform templates, but the audit is required.
3. Update the ESO Helm chart version pin in the relevant ApplicationSet or Helm values file inside
   `platform-gitops/`.
4. Commit, push, and let ArgoCD reconcile the ESO upgrade.
5. Verify all ExternalSecrets remain `Ready=True` after the upgrade.
6. Add a policy check (OPA/Conftest or a simple grep gate in CI) that rejects ExternalSecret
   manifests containing `getHostByName` in their `spec.target.template` fields.

The ClusterSecretStore `vault-backend` and its Vault AppRole / Kubernetes auth configuration are
not modified by this change.

## Alternatives

### Option A: Disable the entire v2 template engine (use v1 templates only)
ESO v2 allows falling back to v1 templates via a feature flag. This eliminates `getHostByName`
completely but also removes legitimate v2 template capabilities and may break existing manifests.
Dropped because upgrading to the patched version is less disruptive and does not regress template
functionality.

### Option B: Egress DNS firewall rule to block unexpected resolver queries
A network policy or CoreDNS plugin could block DNS queries from the ESO controller that do not
match known internal domains. This is a useful defence-in-depth measure but does not fix the
vulnerability — the function remains callable and may succeed against whitelisted domains.
Dropped as a primary fix; kept as a recommended defence-in-depth addition.

### Option C: Remove write access to `platform-gitops/argo-workflows/secrets/` for all but
platform engineers
Tightening ACL on the secrets directory prevents untrusted contributors from introducing malicious
templates, but does not fix the vulnerability for platform engineers themselves and is a process
control, not a technical fix. Dropped as a primary fix.

## Platform impact

**Migrations**
- The ESO Helm chart version pin in `platform-gitops/` must be updated to `helm-chart-2.4.1` (or
  the identified patched version).
- CRDs for ESO (ExternalSecret, ClusterSecretStore, SecretStore, etc.) may have new versions; they
  should be applied before the controller is rolled.
- Existing ExternalSecret objects do not need to be recreated; the upgrade is in-place.

**Backward compatibility**
- ESO v2.2.1 is a patch release on v2.x; no breaking changes to the ExternalSecret or
  ClusterSecretStore APIs are expected.
- Templates not using `getHostByName` continue to work without modification.
- Any template using `getHostByName` will fail after the upgrade; the pre-upgrade audit (task 2)
  ensures no legitimate platform templates are affected.

**Resource impact (`labs`)**
- ESO runs in the `admins` tenant. No ESO pods run inside `labs` namespaces. This upgrade does
  not increase memory or CPU usage in `labs`. There is no impact on the `labs` memory budget.

**Risks and mitigations**
- Risk: `helm-chart-2.4.1` release notes failed to load (per inbox); the patch inclusion is
  unconfirmed.
  Mitigation: task 1 explicitly requires inspecting the chart contents before proceeding.
- Risk: ExternalSecret reconciliation stalls during controller restart, causing temporary
  secret-read failures for tenant workloads.
  Mitigation: ESO rolls out with a Deployment rolling update strategy; existing Kubernetes Secrets
  already synced remain in place during the rollover. No secret loss is expected.
- Risk: A new ESO CRD version introduces a field that conflicts with existing objects.
  Mitigation: run `kubectl diff` on CRDs before applying; validate with a dry-run
  `kubectl apply --dry-run=server`.
