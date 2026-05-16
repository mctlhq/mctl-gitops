# Upgrade Go toolchain to 1.26.3 (HTTP/2 CVE and XSS patch)

## Context

mctl-agent is built with Go 1.24, which reached end-of-active-support in February 2026.
The existing `go-upgrade-1-26` proposal targets Go 1.26.2; on 2026-05-07 the Go team
released go1.26.3 and go1.25.10 patching five additional CVEs that are not covered by
1.26.2:

- **CVE-2026-33814** — `net/http` HTTP/2 transport enters an infinite loop when it receives
  a SETTINGS_MAX_FRAME_SIZE of 0 from a peer. mctl-agent's chi-based webhook server and
  outbound calls to GitHub/Anthropic APIs both use HTTP/2, making this directly exploitable.
- **CVE-2026-39826 / CVE-2026-39823** — Two html/template XSS bypasses via whitespace
  insertion in `type` attributes and `meta` refresh content URLs (the latter a bypass of
  the 1.26.1 fix for CVE-2026-27142).
- **CVE-2026-42499 / CVE-2026-39820** — Quadratic string operations in `net/mail`
  `consumePhrase` / `consumeComment` enable DoS via crafted email-address headers.
- **CVE-2026-42501** — Malicious module proxies can serve altered toolchains by bypassing
  checksum validation in `cmd/go`.

Staying on Go 1.24 or only upgrading to 1.26.2 leaves the service exposed to all five of
the above vulnerabilities.

## User stories

- AS a platform engineer I WANT mctl-agent to be built with Go 1.26.3 SO THAT all five
  CVEs released on 2026-05-07 are remediated and the toolchain is on the current security
  patch track.
- AS an operator I WANT the chi-based webhook server to be free of the HTTP/2 infinite-loop
  vulnerability SO THAT a malicious AlertManager or Telegram peer cannot hang the agent.
- AS a platform engineer I WANT the Go module proxy checksum validation to be intact SO
  THAT CI builds cannot be silently tampered with by a compromised proxy.

## Acceptance criteria (EARS)

- WHEN mctl-agent is built, THE SYSTEM SHALL use Go toolchain 1.26.3 or a later patch
  in the 1.26.x series.
- WHEN the HTTP/2 transport receives a SETTINGS_MAX_FRAME_SIZE of 0, THE SYSTEM SHALL
  return an error rather than entering an infinite loop (CVE-2026-33814 remediated).
- WHEN `go mod verify` or `go mod download` runs against a proxy, THE SYSTEM SHALL reject
  responses that fail checksum validation (CVE-2026-42501 remediated).
- IF any existing unit or integration test fails after the toolchain bump, THE SYSTEM SHALL
  NOT be released until all tests pass.
- WHILE mctl-agent is running, THE SYSTEM SHALL exhibit no regressions in webhook
  processing latency compared to the Go 1.24 baseline (verified via smoke test).

## Out of scope

- Application-level code changes beyond updating `go.mod` toolchain and go directives.
- Upgrading third-party dependencies (chi, go-github, anthropic-sdk-go, sqlite) — covered
  by separate proposals.
- Changes to CRDs, ArgoCD manifests, or GitOps configuration.
- Backporting fixes to Go 1.24 or Go 1.25.
