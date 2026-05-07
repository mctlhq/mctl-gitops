# Design: cert-manager-dns-dos-patch

## Current state

cert-manager is deployed via Helm to the platform cluster and manages TLS certificates for
all services across the `admins` and `labs` tenants. The running version is pre-v1.20.2
(exact version recorded in `context/current-version.md`). The controller operates as a
single Deployment; certificates it issues are stored as standard Kubernetes Secrets and
remain valid independently of the controller's liveness. cert-manager watches Certificate
resources and reconciles them through ACME (HTTP-01 and DNS-01) challenges.

GHSA-gx3x-vq4p-mhhv is present in all cert-manager versions prior to v1.20.2. An attacker
or misbehaving DNS server that can produce a crafted response to the controller's DNS
queries can trigger an unhandled panic, crashing the controller process. Kubernetes restarts
the pod, but if the crafted DNS condition persists, the controller enters a crash loop and
all certificate renewals are blocked.

## Proposed solution

Bump the cert-manager Helm chart version to v1.20.2 in both `admins` and `labs`. No
configuration changes are required: the API surface of cert-manager is unchanged between
the current version and v1.20.2, and the rolling update strategy of the controller
Deployment ensures that existing running Pods are replaced one at a time. Certificates
already issued and stored as Kubernetes Secrets remain valid during the rollover — the
controller's absence during the brief restart window does not invalidate issued certs.

The Go 1.26.2 bump included in v1.20.2 closes any Go-runtime-level dependency
vulnerabilities without requiring any action from the platform team.

Deployment order: apply to `labs` first, confirm all Certificate resources remain `Ready`,
then apply to `admins`. Because this is a single-controller replacement with no storage
migration, both tenants can be updated in the same change window if `labs` validates
cleanly.

## Alternatives

**a. Pin the DNS resolver to avoid crafted responses**

Rejected: operationally complex (requires custom CoreDNS configuration to sanitize
responses) and does not fix the root cause in cert-manager. Any future DNS interaction
could re-expose the vulnerability through a different code path. Maintenance burden is
disproportionate to a chart version bump.

**b. Run cert-manager without DNS validation (disable DNS-01 solvers)**

Rejected: this breaks ACME DNS-01 challenges, which are used for wildcard certificates and
for services that cannot expose HTTP-01 challenge endpoints. Disabling DNS validation would
require re-architecting issuers for affected services — a larger change than upgrading the
chart.

**c. Migrate to Venafi or another certificate manager**

Rejected: too invasive and out of scope. cert-manager is well-integrated with the platform's
ArgoCD and ESO workflows. A migration would require replacing all ClusterIssuers,
Certificate resources, and ACME configurations across both tenants, with no security
advantage over a patch upgrade.

## Platform impact

**Migrations**

None. The Helm chart version bump applies in place; no CRD schema migrations are required
between the current version and v1.20.2.

**Backward compatibility**

Full backward compatibility. The Certificate, ClusterIssuer, and Issuer CRD schemas are
unchanged. Existing ACME solver configurations remain valid.

**Resource impact**

The controller replacement is a rolling update with no additional replicas. No increase in
memory or CPU usage is expected. `labs`: no risk — this is a controller image swap, not an
additional workload. The `labs` tenant memory limit is not affected.

**Risks and mitigations**

| Risk | Mitigation |
|---|---|
| Controller crash loop during rollover if crafted DNS is actively in play | Short rollover window; Kubernetes liveness probe restarts pod quickly; existing certs remain valid |
| Webhook YAML change breaks an existing webhook configuration | Validate webhook rendering in `labs` before applying to `admins`; review diff of rendered webhook config |
| Unexpected cert renewal failure after upgrade | Monitor Certificate resource status for 30 minutes post-upgrade; rollback procedure ready |
