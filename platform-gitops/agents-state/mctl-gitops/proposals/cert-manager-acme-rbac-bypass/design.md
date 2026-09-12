# Design: cert-manager-acme-rbac-bypass

## Current state
cert-manager is deployed via Helm to serve both `admins` and `labs` tenants, following the
pattern described in `context/architecture.md` (External Secrets Operator + Vault provide
DNS-provider credentials to ClusterIssuers). The version is pinned per-tenant in
`platform-gitops/services/<tenant>/<cert-manager-svc>/`. cert-manager ships a default
`edit`-aggregated ClusterRole (labeled for aggregation onto Kubernetes' built-in `edit`
role) that grants broad permissions on cert-manager custom resources, including
`create`/`update` on `acme.cert-manager.io` `Challenge` and `Order` objects — resources
that are meant to be created only by the cert-manager controller itself as part of
reconciling a Certificate against an Issuer's configured DNS01 solver.

Because any namespace user who holds Kubernetes' `edit` role automatically inherits this
aggregated ClusterRole, they can create a Challenge/Order resource directly, specifying a
ClusterIssuer whose DNS01-solver credentials they would otherwise have no path to invoke,
bypassing the Issuer-level policy that is supposed to gate which namespaces may use which
DNS credentials.

## Proposed solution
Two coordinated changes, both control-plane only:

1. **Version confirmation/bump.** Check the cert-manager version pinned in
   `platform-gitops/services/admins/<cert-manager-svc>/` and
   `platform-gitops/services/labs/<cert-manager-svc>/`. If either is below 1.19.6 (1.19.x
   line) or 1.20.3 (1.20.x line), bump to the matching fixed patch release, following the
   same rolling-update pattern already used in `cert-manager-dns-dos-patch` (labs first,
   then admins). If both are already on 1.21.x+, this step is a documentation-only
   confirmation.

2. **RBAC tightening.** Add a platform-owned `ClusterRole` patch (via a Kustomize patch or
   an explicit override manifest alongside the cert-manager Helm release in
   `platform-gitops/services/<tenant>/<cert-manager-svc>/`) that removes the
   `create`/`update` verbs on `acme.cert-manager.io` `challenges` and `orders` from the
   aggregated `edit` ClusterRole, or disables cert-manager's own RBAC aggregation for those
   two resource kinds entirely (cert-manager supports disabling the `edit`/`view`
   aggregated-ClusterRole feature via a Helm value on recent chart versions; prefer that
   route over a hand-rolled patch to stay upstream-idiomatic if the value exists on the
   pinned chart version). Only the cert-manager controller's own ServiceAccount retains
   create/update rights on Challenge/Order — which is all that is needed, since users are
   expected to interact only with `Certificate` resources.

Both changes are additive/restrictive at the control-plane RBAC and image-tag level; no
Certificate, Issuer, or ClusterIssuer manifest across either tenant needs to change.

## Alternatives
**a. Rely on the version bump alone, without RBAC tightening.**
Rejected: the CVE advisory itself recommends the RBAC tightening as a defense-in-depth
measure independent of the code fix, because the underlying design flaw (the `edit`
ClusterRole is broader than the ACME resource model assumes) is not itself changed by a
patch release — future regressions or a compromised/legacy pinned version would remain
exposed. Version bump alone treats the symptom, not the RBAC-design root cause the CVE
calls out.

**b. Move DNS-provider credentials out of ClusterIssuer into per-tenant namespaced Issuers
exclusively.**
Rejected: a broader architectural change that touches every tenant's Certificate/Issuer
wiring, and does not by itself prevent a namespace user from creating an Order/Challenge
referencing a namespaced Issuer they aren't meant to invoke directly either — the RBAC gap
is the actual bug, not the Issuer scope. Out of proportion to a patch-style fix.

**c. Deny all direct kubectl/API access to ACME resources via a NetworkPolicy or admission
webhook instead of an RBAC ClusterRole patch.**
Rejected: RBAC is the correct enforcement layer for "who can create this Kubernetes
resource kind" — a NetworkPolicy operates at the network layer and cannot express
object-kind restrictions; a new admission webhook adds an extra moving part (webhook
availability becomes a dependency for all Challenge/Order writes) for something Kubernetes
RBAC already solves natively and that cert-manager's own Helm chart increasingly supports
disabling.

## Platform impact
**Migrations:** None. The RBAC patch modifies an aggregated ClusterRole's rules; no CRD
schema changes. The version bump (if needed) is a drop-in patch release per cert-manager's
own compatibility guarantees.

**Backward compatibility:** Full for legitimate usage. Users continue to create
`Certificate` resources exactly as before; the controller (not the end user) creates the
resulting Challenge/Order objects on their behalf, so no existing certificate-issuance
workflow changes. Only direct, user-initiated creation of Challenge/Order objects is
blocked — a capability no legitimate workflow relies on.

**Resource impact (`labs`):** None. This is an RBAC rule change plus (at most) a controller
version bump — no new pods, no change to controller resource requests/limits. Not flagged
as risky for the `labs` memory constraint.

**Risks and mitigations:**
- Risk: a tenant's automation or scaffolder template unexpectedly relies on directly
  creating Challenge/Order resources (nonstandard usage). Mitigation: audit
  `platform-gitops/argo-workflows/service-templates/` and `backstage-templates/` for any
  direct Challenge/Order manifest generation before landing the RBAC patch; none expected,
  since the standard path is always via `Certificate`.
- Risk: disabling chart-level RBAC aggregation (if using the Helm value route)
  inadvertently also removes `view` permissions users rely on to inspect Challenge/Order
  status for debugging. Mitigation: scope the change to `create`/`update` verbs only,
  retaining `get`/`list`/`watch` for visibility; verify with a `kubectl auth can-i` check
  post-change.
- Risk: controller version bump (if needed) causes a brief reconciliation gap. Mitigation:
  same rolling-update / labs-first sequencing already validated in
  `cert-manager-dns-dos-patch`.
