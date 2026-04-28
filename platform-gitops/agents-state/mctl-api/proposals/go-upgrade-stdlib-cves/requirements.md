# Go Runtime Upgrade: Remediate stdlib CVEs (Go 1.24 → Go 1.26)

## Context

mctl-api v4.14.0 runs on Go 1.24 (last patch: go1.24.13, 2026-02-04). Three
Go standard-library CVEs have been disclosed that affect Go 1.24 and are only
fixed in Go 1.26.x:

- **CVE-2026-32280** — Denial of service in certificate chain building
  (`crypto/x509`).
- **CVE-2026-32282** — Symlink escape via `Root.Chmod` (`os` package).
- **CVE-2026-32283** — Denial of service in `crypto/tls` triggered by multiple
  TLS 1.3 key-update messages.

mctl-api performs TLS termination and JWT certificate validation on every
inbound request. CVE-2026-32283 is therefore a direct availability risk: an
unauthenticated attacker can send crafted TLS 1.3 key-update messages and
exhaust the server's resources, taking the API offline for all tenants.
CVE-2026-32280 also threatens the JWKS/OIDC certificate validation path.
Go 1.26.2 (released 2026-04-07) is the current stable release and contains
fixes for all three CVEs.

## User stories

- AS a platform engineer I WANT mctl-api to run on Go 1.26.2 SO THAT all three
  known stdlib CVEs are remediated and the service is no longer exposed to
  DoS attacks via TLS.
- AS a security officer I WANT evidence that the upgraded binary passes the
  existing test suite SO THAT the upgrade can be signed off without a manual
  regression cycle.
- AS an on-call engineer I WANT the ArgoCD rollout to be incremental SO THAT
  a bad build can be caught before it affects all replicas.

## Acceptance criteria (EARS)

- WHEN the Docker image for mctl-api is built, THE SYSTEM SHALL use a Go 1.26.2
  base image (`golang:1.26.2-alpine` or equivalent distroless variant).
- WHEN `go version` is executed inside the running container, THE SYSTEM SHALL
  report `go1.26.2` or later.
- WHEN the CI pipeline runs against the upgraded codebase, THE SYSTEM SHALL
  pass all existing unit, integration, and race-detector tests without
  modification to test logic.
- WHEN mctl-api starts after the upgrade, THE SYSTEM SHALL expose its
  `/healthz` and `/metrics` endpoints and respond within the existing SLO
  thresholds.
- WHEN a TLS 1.3 connection receives multiple consecutive key-update messages
  (CVE-2026-32283 reproduction pattern), THE SYSTEM SHALL handle them without
  abnormal CPU/memory growth or connection termination outside of normal
  limits.
- WHILE the rolling update is in progress, THE SYSTEM SHALL keep at least one
  healthy replica serving traffic (PodDisruptionBudget enforced).
- IF the new image fails its liveness probe within the configured
  `failureThreshold`, THEN THE SYSTEM SHALL automatically roll back to the
  previous image via the ArgoCD sync policy.

## Out of scope

- Upgrading any third-party Go module dependencies beyond what is required to
  compile cleanly under Go 1.26.
- Refactoring application code to adopt new Go 1.25/1.26 language features.
- Changes to the TLS termination architecture (e.g., offloading TLS to a
  sidecar or ingress).
- Addressing CVEs in non-Go dependencies (OS packages, PostgreSQL, etc.).
- Any change to the `labs` tenant workloads or resource quotas.
