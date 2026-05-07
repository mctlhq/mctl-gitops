# cert-manager DoS via Crafted DNS Response (GHSA-gx3x-vq4p-mhhv)

## Context

The platform relies on cert-manager to issue and renew TLS certificates for all services
across the `admins` and `labs` tenants. GHSA-gx3x-vq4p-mhhv (published February 2, 2026)
describes a vulnerability in which a specially crafted DNS response causes the cert-manager
controller to panic, resulting in a process restart loop. While the controller is down,
certificate issuance and renewal halt entirely. Services with short-lived certificates
would lose valid HTTPS at renewal time, producing end-user TLS errors and breaking
automated pipelines that depend on healthy TLS endpoints.

The fix was released in cert-manager v1.20.2 on April 11, 2026. The same release also
resolves invalid YAML generation when both `webhook.config` and `webhook.volumes` are
configured simultaneously, and bumps Go to 1.26.2 for dependency security updates. No
existing cert-manager proposal covers this advisory. The upgrade is a controller-only
replacement with no schema changes, making it a low-effort, high-impact patch.

## User stories

- AS a platform operator I WANT the cert-manager controller upgraded to v1.20.2
  SO THAT crafted DNS responses can no longer panic the controller and halt all certificate
  operations.
- AS a service owner relying on TLS I WANT certificate issuance and renewal to continue
  uninterrupted during and after the cert-manager upgrade SO THAT my service never presents
  an expired or missing TLS certificate to users.

## Acceptance criteria (EARS)

- WHEN a crafted DNS response is received by the cert-manager controller THE SYSTEM SHALL
  not panic and SHALL continue processing certificate requests normally.
- WHEN cert-manager is upgraded to v1.20.2 THE SYSTEM SHALL continue issuing and renewing
  certificates for all Certificate resources without interruption.
- WHILE the cert-manager controller is rolling over to v1.20.2 THE SYSTEM SHALL not revoke
  or invalidate any currently issued certificates already stored as Kubernetes Secrets.
- IF `webhook.config` and `webhook.volumes` are both set in the cert-manager Helm values
  THE SYSTEM SHALL generate valid, parseable YAML for the webhook configuration.
- WHEN the upgrade is complete THE SYSTEM SHALL have no outstanding GHSA-gx3x-vq4p-mhhv
  exposure in any tenant.

## Out of scope

- Migrating from cert-manager to any alternative certificate manager (e.g., Venafi,
  step-issuer, or manual certificate management).
- Changes to certificate issuance policies, ClusterIssuers, or ACME challenge solver
  configuration beyond what is required for the version upgrade.
- Upgrading cert-manager to any version beyond v1.20.2 (e.g., v1.21.x).
