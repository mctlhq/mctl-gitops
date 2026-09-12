# Restrict ClusterIssuer DNS-Credential Exposure via ACME Challenge/Order RBAC (CVE-2026-62290)

## Context
cert-manager's default `edit` ClusterRole (aggregated onto namespace users who hold the
`edit` role) grants create/update permissions on `acme.cert-manager.io` `Challenge` and
`Order` resources. This lets any user with `edit` access in a namespace create a
Challenge/Order directly, bypassing the DNS01-solver policy configured on the namespace's
Issuer, and reach the DNS provider credentials attached to a cluster-scoped ClusterIssuer
that the user was never meant to invoke directly. This is CVE-2026-62290 (CVSS 7.3),
affecting cert-manager 1.18.0-1.19.5 (fixed 1.19.6) and 1.20.0-1.20.2 (fixed 1.20.3).

Our fleet's most recently observed release is 1.21.2, which postdates the fix range, but
that has not been confirmed against the version actually pinned in this repo's
`platform-gitops/services/<tenant>/<cert-manager-svc>/` configuration. Because cert-manager
serves both `admins` and `labs` tenants and any namespace with `edit`-level users could
exploit this, the RBAC posture needs review regardless of the exact pinned version, since
the CVE's own advisory recommends tightening the default `edit` ClusterRole binding
independent of the code fix.

## User stories
- AS a platform security engineer I WANT to confirm the cert-manager version is not in the
  vulnerable range and tighten the RBAC that lets namespace users create ACME Challenge/Order
  resources SO THAT a namespace `edit` user cannot bypass Issuer DNS01-solver policy to
  reach ClusterIssuer DNS credentials.
- AS a tenant developer with `edit` access to my namespace I WANT to keep issuing
  Certificates through the normal Issuer/ClusterIssuer flow SO THAT my legitimate
  certificate requests are unaffected by the RBAC tightening.

## Acceptance criteria (EARS)
- WHEN the cert-manager version pinned in `platform-gitops/services/<tenant>/<cert-manager-svc>/`
  is inspected THE SYSTEM SHALL confirm it is at or above 1.19.6 (on the 1.19.x line) or
  1.20.3 (on the 1.20.x line), or already on a later line (1.21.x+) that postdates the fix.
- IF the confirmed version is below the fixed range THEN THE SYSTEM SHALL bump it to the
  smallest patched release on the matching minor line before any RBAC change is considered
  sufficient on its own.
- WHEN the default `edit`-aggregated ClusterRole is reviewed THE SYSTEM SHALL remove or
  scope down the implicit `create`/`update` permission on `acme.cert-manager.io`
  `Challenge` and `Order` resources so that namespace `edit` users cannot create them
  directly.
- WHEN a namespace user creates a Certificate resource referencing an Issuer/ClusterIssuer
  they are authorized to use THE SYSTEM SHALL continue to reconcile it through the normal
  Challenge/Order flow (created by the cert-manager controller itself, not the end user).
- IF a namespace user without explicit Challenge/Order create rights attempts to create an
  ACME Challenge or Order resource directly THEN THE SYSTEM SHALL deny the request via
  RBAC.
- WHILE the RBAC change is in effect THE SYSTEM SHALL NOT require any change to existing
  Certificate or Issuer manifests across `admins` or `labs`.

## Out of scope
- CVE-2026-25518 (DNS-response-triggered controller panic) — already covered by
  `cert-manager-dns-dos-patch`.
- Any change to how ClusterIssuer DNS credentials are stored (they remain in Vault via
  External Secrets Operator, per existing architecture) — this proposal only restricts who
  can trigger their use.
- A full RBAC redesign of the `edit` ClusterRole beyond the ACME Challenge/Order resources
  implicated by this CVE.
- Any change to `labs` tenant workload memory allocation — this is a control-plane RBAC and
  version change.
