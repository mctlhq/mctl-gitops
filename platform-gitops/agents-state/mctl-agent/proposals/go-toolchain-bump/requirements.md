# Move build toolchain from Go 1.24 to the current patched Go release

## Context
mctl-agent is built with Go 1.24 and exposes a public webhook endpoint (`agent.mctl.ai`) built on net/http, x/net and crypto/x509. The 2026-11-07 inbox lists open stdlib/x/net CVEs (CVE-2026-97045 Medium, CVE-2026-78661 High 7.5) and the crypto/x509 distrust fix CVE-2026-111943. Stdlib fixes can only be picked up by changing the toolchain.

Several facts are UNVERIFIED and must be confirmed before the bump: the target version "Go 1.26.10" comes only from Alertmanager v0.34.2 release notes (the golang/go releases page returned nothing); the affected-version ranges of the x/net CVEs are unknown; and it is not known whether Go 1.24 is affected at all or whether `govulncheck` reports reachable findings in the current binary.

## User stories
- AS a platform operator I WANT the agent built with a patched Go toolchain SO THAT the public webhook endpoint is not exposed to known stdlib/x509/x/net vulnerabilities.
- AS the mctl-agent owner I WANT the target Go version verified from an authoritative source SO THAT we do not pin to an unconfirmed version.

## Acceptance criteria (EARS)
- WHEN the proposal is started THE SYSTEM SHALL record the latest Go patch from go.dev/dl and confirm whether Go 1.24 is affected by CVE-2026-78661, CVE-2026-97045 and CVE-2026-111943.
- WHEN `govulncheck` is run against the current (pre-bump) binary THE SYSTEM SHALL have its output stored with the PR as the baseline.
- WHEN the toolchain is bumped THE SYSTEM SHALL build with the verified target version in `go.mod` (`go`/`toolchain` directives), the Dockerfile builder image and CI.
- WHEN `govulncheck` is run against the post-bump binary THE SYSTEM SHALL report no reachable findings for the CVEs listed above.
- WHEN the full test suite runs on the new toolchain THE SYSTEM SHALL pass, including the table-driven skill tests.
- WHILE the new version runs in `admins` THE SYSTEM SHALL keep RSS within 10% of the pre-bump baseline.
- IF the verified target differs from "Go 1.26.10" THEN THE SYSTEM SHALL use the verified version and update this proposal's docs accordingly.
- IF Go 1.24 is confirmed unaffected by all listed CVEs THEN THE SYSTEM SHALL downgrade priority and record the finding rather than force the bump.

## Out of scope
- Bumping third-party dependencies (chi, sqlite, go-github, anthropic SDK); handled separately.
- Argo CD / Alertmanager Go CVEs (platform-level).
- Changes to the `labs` tenant (the agent runs in `admins`).
