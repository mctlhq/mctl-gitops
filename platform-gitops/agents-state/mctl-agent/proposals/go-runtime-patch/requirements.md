# Go Runtime Security Patch: Upgrade Go toolchain to 1.24.8

## Context
The mctl-agent service is compiled with Go 1.24. On 2026-04-07, the Go security team published a batch of 10 CVEs affecting the 1.24.x toolchain line, all fixed in Go 1.24.8 (and 1.25.2). The most critical vulnerabilities include arbitrary code execution during builds (CVE-2026-27140), compiler memory corruption (CVE-2026-27143/27144), a crypto/tls deadlock (CVE-2026-32283), and crypto/x509 denial-of-service vectors (CVE-2026-32280/32281). Continuing to build and ship mctl-agent with an unpatched compiler leaves the service, and any CI/CD pipeline that builds it, exposed to these vulnerabilities.

This proposal has the highest possible urgency: the fix is a one-line toolchain bump with no API changes and no behavioural regressions expected.

## User stories
- AS a platform engineer I WANT mctl-agent to be compiled with a patched Go toolchain SO THAT known compiler and stdlib CVEs do not put production workloads at risk.
- AS a security reviewer I WANT the `go.mod` `toolchain` directive and the container base image to pin Go ≥ 1.24.8 SO THAT automated vulnerability scanners report no outstanding critical findings on the binary.

## Acceptance criteria (EARS)
- WHEN the service is built, THE SYSTEM SHALL use Go toolchain ≥ 1.24.8 as declared in `go.mod`.
- WHEN a container image is produced, THE SYSTEM SHALL use a base image that bundles Go 1.24.8 or later (for scratch/distroless images: the compiled binary must have been produced by Go ≥ 1.24.8).
- WHEN `go version` is executed against the produced binary, THE SYSTEM SHALL report a version string ≥ `go1.24.8`.
- WHILE the service is running, THE SYSTEM SHALL expose the Go runtime version via the `/healthz` or `/readyz` response body so that the version is observable without cracking the binary.
- IF a future CVE is published against go1.24.x before 1.25 is adopted, THE SYSTEM SHALL follow the same patch-bump process within 5 business days of the fix release.

## Out of scope
- Upgrading to Go 1.25.x or Go 1.26.x — this proposal is a security patch only; a full minor-version upgrade is a separate proposal.
- Changing any Go source code logic, packages, or dependencies.
- Upgrading the base OS image beyond what is needed to obtain Go 1.24.8.
