# Upgrade Go Toolchain to v1.26.2

## Context
mctl-agent is built with Go 1.24. On 2026-04-07 the Go team released Go 1.26.2 (and the parallel 1.25.9 patch) containing security fixes for 7 CVEs that directly affect the mctl-agent runtime environment: CVE-2026-27143 (compiler memory corruption via induction-variable overflow), CVE-2026-27140 (arbitrary code execution at build time via cmd/go SWIG trust-layer bypass), CVE-2026-32283 (TLS 1.3 deadlock via multiple key-update messages), CVE-2026-32288 (archive/tar memory exhaustion on crafted sparse archives), CVE-2026-32280 and CVE-2026-32281 (crypto/x509 DoS via unbounded intermediate-certificate or policy-mapping validation), and CVE-2026-32282 (symlink race in Root.Chmod on Linux).

Two of the seven CVEs are critical-severity: the compiler memory-corruption bug (CVE-2026-27143) affects any binary produced with the vulnerable toolchain, and the build-time code-execution bug (CVE-2026-27140) can be triggered during CI/CD. The remaining five affect the running service directly (TLS, tar, x509). Until the toolchain is upgraded, every mctl-agent build and every deployed instance carries these vulnerabilities.

## User stories
- AS a platform security engineer I WANT mctl-agent to be built with Go 1.26.2 SO THAT the seven open CVEs are closed before they can be exploited in build or runtime.
- AS a developer I WANT the upgrade to introduce no breaking changes to the existing code SO THAT I can merge it without refactoring work.
- AS an SRE I WANT the labs tenant memory footprint to remain unchanged after the upgrade SO THAT the tenant does not breach its memory limit.

## Acceptance criteria (EARS)
- WHEN a CI build of mctl-agent completes THEN THE SYSTEM SHALL use Go 1.26.2 or later as the compiler toolchain, verified by `go version` output in the build log.
- WHEN mctl-agent is deployed after this change THE SYSTEM SHALL pass all existing unit and integration tests without modification to test logic.
- WHILE mctl-agent is running in the labs tenant THE SYSTEM SHALL NOT increase resident memory (RSS) relative to the Go 1.24 baseline, measured at steady-state under nominal alert load.
- IF the Go 1.26.2 toolchain produces a compilation error in any mctl-agent package THEN THE SYSTEM SHALL block the CI pipeline and emit a failing build status before any image is pushed.
- WHEN a security scanner runs against the published container image THE SYSTEM SHALL report zero HIGH or CRITICAL toolchain-level CVEs that are fixed in Go 1.26.2.
- IF any go.mod or go.sum file is changed during the upgrade THEN THE SYSTEM SHALL regenerate and commit both files as part of the same PR.

## Out of scope
- Upgrading any non-toolchain dependencies (go-github, chi, sqlite, etc.) — those are separate proposals.
- Switching from Go modules to an alternative build system.
- Changing the container base image beyond what is necessary to consume Go 1.26.2 binaries.
- Modifying skill logic or API behaviour.
- Any changes to the labs tenant resource quotas.
