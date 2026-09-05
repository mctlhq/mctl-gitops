# Bump External Secrets Operator chart past CVE-2026-22822

## Context
External Secrets Operator (ESO) is the platform's sole sanctioned mechanism
for delivering secrets from Vault into tenant namespaces (`vault-backend`
ClusterSecretStore, per `context/architecture.md`). CVE-2026-22822 (CVSS
8.8, critical) is a flaw in ESO's `getSecretKey` template function (added
for the senhasegura DSM provider) that abused the controller's elevated
RBAC to exfiltrate secrets across namespace boundaries — directly
undermining the tenant secret-isolation model that `admins`, `labs`, and
other tenants depend on. The affected range is 0.20.2–<1.2.0, fixed in
1.2.0 by removing the vulnerable function entirely.

A newer chart, `external-secrets` helm-chart-2.10.0, was released Aug 28,
2026 and already bundles a fixed operator version. This proposal is a
straightforward chart-version bump wherever the ESO chart is pinned for
this platform (bootstrap chart or a dedicated Application in
`platform-gitops/apps/`), not an architecture change — ExternalSecret
manifests under `platform-gitops/argo-workflows/secrets/` are unaffected
since they only consume ESO's CRDs, not the vulnerable template function.

## User stories
- AS a tenant operator I WANT the ESO controller to run a patched version
  SO THAT another tenant's ExternalSecret cannot exfiltrate my namespace's
  Vault-backed secrets.
- AS the mctl-gitops maintainer I WANT the ESO chart pinned to >=1.2.0 (or
  the chart version bundling it) SO THAT the `getSecretKey` exfiltration
  path is fully removed rather than just mitigated.
- AS a platform security reviewer I WANT confirmation that no ExternalSecret
  manifest in this repo used the vulnerable `getSecretKey` function SO THAT
  I know no functional migration is needed alongside the version bump.

## Acceptance criteria (EARS)
- WHEN the ESO chart version pin is updated THE SYSTEM SHALL deploy an
  operator version >=1.2.0 (or later, e.g. the chart bundling
  helm-chart-2.10.0) in which `getSecretKey` has been removed.
- WHEN the ESO chart bump is applied THE SYSTEM SHALL continue reconciling
  all existing ExternalSecret/ClusterSecretStore resources against
  `vault-backend` without manual re-creation.
- IF any ExternalSecret manifest in this repo references the `getSecretKey`
  template function THEN THE SYSTEM SHALL flag it for rewrite before the
  version bump is rolled out (function is removed in the fixed version).
- WHILE the ESO chart bump is being rolled out THE SYSTEM SHALL be applied
  through the existing ApplicationSet/App-of-Apps sync flow, not a manual
  `kubectl apply`.
- IF the bump is applied to a namespace shared with `labs` workloads THEN
  THE SYSTEM SHALL confirm no measurable memory increase to the ESO
  controller footprint, consistent with `labs` being close to its memory
  limit.

## Out of scope
- Rewriting ExternalSecret manifests to use alternative template functions,
  unless the audit in the acceptance criteria finds an actual usage of
  `getSecretKey` in this repo (none is currently known).
- Adding new secret providers (e.g. senhasegura DSM) or removing existing
  ones — this proposal only addresses the CVE via version bump.
- Any change to the Vault `vault-backend` ClusterSecretStore configuration
  itself.
