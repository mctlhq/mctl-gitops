# Go 1.24 EOL + Extended Stdlib CVE Set — Upgrade to go1.26.2

## Context

mctl-api v4.14.0 runs on Go 1.24, which reached end-of-life on 2026-02-11 and
will receive no further security patches. The original proposal
`go-upgrade-stdlib-cves` covered three CVEs (CVE-2026-32280, CVE-2026-32282,
CVE-2026-32283). Since that proposal was written, seven additional standard-library
CVEs have been disclosed that are all fixed exclusively in go1.26.2. The full
remediated set now comprises ten CVEs, making the upgrade more urgent and the
security case stronger.

The new CVEs span critical attack surfaces used by mctl-api in production:
CVE-2026-32289 affects `html/template` (used in error pages and email
notifications), CVE-2026-32288 enables a DoS via malformed tar archives in
`archive/tar`, CVE-2026-27140 is an RCE reachable through SWIG-generated code
invoked by `cmd/go` during build, CVE-2026-27143 and CVE-2026-27144 allow
unsafe memory access in `cmd/compile`, and CVE-2026-33810 lets an attacker
bypass x509 wildcard certificate validation in `crypto/x509` — directly
threatening the OIDC/JWKS trust chain that mctl-api uses to authenticate
every Dex JWT request. This proposal supersedes and extends the original
`go-upgrade-stdlib-cves` proposal; the required action (upgrade to go1.26.2) is
identical but the acceptance scope is broader.

## User stories

- AS a platform engineer I WANT mctl-api to run on go1.26.2 SO THAT all ten
  known stdlib CVEs (original three plus seven newly disclosed) are remediated
  and the service is no longer running on an EOL Go toolchain.
- AS a security officer I WANT a single upgrade that closes the full CVE set
  SO THAT I can sign off the change without scheduling multiple separate
  upgrade cycles.
- AS an on-call engineer I WANT the ArgoCD rollout to be incremental SO THAT
  a bad build is caught before it affects all replicas.
- AS a developer I WANT the CI pipeline to validate the upgraded binary
  SO THAT no new test logic needs to be written to justify the sign-off.

## Acceptance criteria (EARS)

- WHEN the Docker image for mctl-api is built, THE SYSTEM SHALL use a
  `golang:1.26.2-alpine` (or distroless equivalent) build stage.
- WHEN `go version` is executed inside the running container, THE SYSTEM SHALL
  report `go1.26.2` or later.
- WHEN the CI pipeline runs against the upgraded codebase, THE SYSTEM SHALL
  pass all existing unit, integration, and race-detector tests without
  modification to test logic.
- WHEN mctl-api starts after the upgrade, THE SYSTEM SHALL respond on `/healthz`
  and `/metrics` within the existing SLO thresholds.
- WHEN a TLS 1.3 connection receives multiple consecutive key-update messages
  (CVE-2026-32283 reproduction pattern), THE SYSTEM SHALL handle them without
  abnormal CPU or memory growth.
- WHEN the OIDC/JWKS endpoint presents a wildcard certificate, THE SYSTEM SHALL
  validate it correctly and NOT allow a bypass (CVE-2026-33810).
- WHILE the rolling update is in progress, THE SYSTEM SHALL keep at least one
  healthy replica serving traffic (PodDisruptionBudget enforced).
- IF the new image fails its liveness probe within the configured
  `failureThreshold`, THEN THE SYSTEM SHALL automatically roll back to the
  previous image via the ArgoCD sync policy.
- IF `go mod tidy` introduces transitive dependency changes, THEN THE SYSTEM
  SHALL compile and pass the full test suite before the PR is merged.

## Out of scope

- Upgrading third-party Go module dependencies beyond what is required for
  clean compilation under Go 1.26.
- Refactoring application code to adopt Go 1.25/1.26 language features.
- Changes to TLS termination architecture (e.g., offloading to a sidecar).
- Remediating CVEs in non-Go dependencies (OS packages, PostgreSQL, etc.).
- Any change to `labs` tenant workloads or resource quotas.
- Addressing the seven new CVEs via any mechanism other than the go1.26.2
  toolchain upgrade (no partial backports or runtime mitigations).
