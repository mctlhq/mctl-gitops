# Design: vault-v2-major-upgrade-plan

## Current state

Vault (pre-2.0.0, last version tracked in `context/current-version.md`) is deployed via
Helm and exposed to the platform as the `vault-backend` ClusterSecretStore used by External
Secrets Operator. All tenant secrets flow through this store; ExternalSecret manifests live
under `platform-gitops/services/` and `platform-gitops/argo-workflows/secrets/`.

Four individual CVE proposals are in flight:
- `vault-cve-2026-token-exposure` — CVE-2026-4525 (auth mount token forwarding)
- `vault-kvv2-deletion-bypass` — CVE-2026-3605 (KVv2 glob-policy delete bypass)
- `vault-ldap-null-bind-bypass` — LDAP null-bind (separate advisory)
- `vault-ssrf-acme-patch` — CVE-2026-5052 (PKI ACME SSRF)

CVE-2026-5807 (unauthenticated DoS via root-token generation/rekey cycle) has no proposal
and is fixed only in v2.0.0. All four of the above CVEs are also fixed in v2.0.0, making a
full major-version upgrade the most efficient remediation path.

## Proposed solution

A staged upgrade in three phases:

**Phase 1 — Audit and path remediation (no version change)**

Scan all ExternalSecret manifests in `platform-gitops/services/` and
`platform-gitops/argo-workflows/secrets/` for paths containing `//`. Vault v2.0.0 enforces
path canonicalization and will reject any double-slash paths with a clear error. Correct all
occurrences and merge the fix to the default branch before any Vault version change.

**Phase 2 — Staging in `labs`**

Pin the Vault Helm chart to v2.0.0 in the `labs` namespace. Verify:
- ESO `vault-backend` ClusterSecretStore reconnects successfully (ESO compatibility with
  Vault v2.0.0 was confirmed in the v2.0.0 release notes).
- All ExternalSecret objects in `labs` sync to `Ready`.
- Vault policies apply correctly under the new UBI 10 base image and Go 1.26.2 runtime.
- Memory consumption of the new UBI 10-based image is measured against the `labs` tenant
  memory limit. **If consumption increases beyond available headroom, promotion to `admins`
  is blocked until capacity is extended or the image is slimmed.**
- CVE-2026-5807 attack vector cannot trigger a DoS (smoke-tested by invoking the
  initiate/cancel root-token generation cycle and confirming Vault remains responsive).

**Phase 3 — Promotion to `admins`**

Update the Vault Helm chart version to v2.0.0 in the `admins` namespace. Monitor ArgoCD
sync and ESO controller logs. Retire individual CVE patch proposals as superseded.

The Docker helpers migration from internal to `moby/moby` and the UBI 10 base image change
are transparent to the platform — no manifest changes are required beyond the chart version
bump.

## Alternatives

**a. Stay on latest v1.x and apply individual CVE patches**

Rejected because CVE-2026-5807 is fixed only in v2.0.0 (no backport to v1.x). Continuing
on v1.x leaves an unauthenticated DoS vector open indefinitely, which is unacceptable for a
system that is the root of all platform secrets.

**b. Migrate to Kubernetes-native Secrets (remove Vault)**

Rejected as too invasive and explicitly out of scope per the ADR boundary. All tenants
currently depend on the `vault-backend` ClusterSecretStore; removing Vault would require
reworking every ExternalSecret manifest and the platform's secret rotation workflows. This
is a multi-quarter effort.

**c. Run parallel Vault instances during migration**

Rejected as over-engineered. A staged per-tenant upgrade (labs first, then admins) provides
sufficient isolation. Running parallel clusters would double the memory footprint in both
tenants and introduce secret-synchronization complexity with no material risk reduction over
the staged approach.

## Platform impact

**Migrations**

All ExternalSecret manifests containing double-slash paths must be corrected before the
Vault chart version is changed. This is a one-time, auditable change tracked in Phase 1.

**Backward compatibility**

ESO v2.x is confirmed compatible with Vault v2.0.0 per the Vault release notes. The
`vault-backend` ClusterSecretStore configuration requires no changes other than the server
version it targets. Auth plugin token forwarding behavior change (CVE-2026-4525 fix) may
require review of any custom auth mounts that rely on `Authorization` header pass-through.

**Resource impact**

The UBI 10 base image is expected to be marginally larger than UBI 9. Memory consumption
MUST be measured in `labs` before promoting to `admins`. **`labs` is near its memory limit;
this proposal is flagged as potentially risky for `labs` until the Phase 2 memory
measurement is complete.**

**Risks and mitigations**

| Risk | Mitigation |
|---|---|
| Double-slash path in an ExternalSecret not caught by audit | Phase 1 grep is mandatory; ArgoCD diff review required before merge |
| UBI 10 image exceeds `labs` memory limit | Measure in Phase 2; block promotion if limit is breached |
| Auth plugin behavior change breaks existing auth mounts | Review all auth mounts using `Authorization` header pass-through before upgrade |
| ESO loses connectivity to Vault during rolling restart | Vault HA or single-instance with short rolling window; existing secrets cached in Kubernetes Secrets remain valid |
