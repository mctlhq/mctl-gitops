# Upgrade go-chi/chi from v5.2.1 to v5.2.5

## Context
mctl-agent uses `go-chi/chi v5.2.1` as its HTTP router, serving REST API endpoints,
the AlertManager webhook, the Telegram webhook, the MCP endpoint, and health probes (see
`context/architecture.md`). CVE-2025-69725 (CVSS 4.7 Medium) is an open-redirect
vulnerability in chi's `RedirectSlashes` middleware introduced in v5.2.2. mctl-agent on
v5.2.1 is not directly vulnerable because the affected code did not exist in v5.2.1, but it
sits immediately adjacent to the vulnerable version range.

Upgrading to v5.2.5 — the first release that includes the hardened `RedirectSlashes`
implementation — eliminates forward exposure: any future patch or dependency update that
inadvertently moves the chi version into the v5.2.2–v5.2.4 range would otherwise introduce
the vulnerability silently. The v5.2.1 → v5.2.5 upgrade is a drop-in patch with no API
changes, a minimum Go version already satisfied by the service's Go 1.24 runtime, and
negligible binary size delta.

## User stories
- AS a platform security engineer I WANT mctl-agent to run on chi v5.2.5 SO THAT the
  service is protected against any accidental re-introduction of the CVE-2025-69725 attack
  surface by future dependency changes.
- AS a platform engineer I WANT the chi upgrade to be a no-op from an API perspective SO
  THAT no existing route handlers or middleware registrations require modification.

## Acceptance criteria (EARS)
- WHEN mctl-agent is built after the upgrade THE SYSTEM SHALL reference
  `github.com/go-chi/chi/v5 v5.2.5` in `go.mod` and the v5.2.1 entry SHALL be absent.
- WHEN `go build ./...` is executed after the upgrade THE SYSTEM SHALL complete with zero
  compilation errors and zero `go vet` warnings.
- WHEN any existing HTTP endpoint (`POST /api/v1/alerts`, `POST /api/v1/telegram`,
  `POST /mcp`, `GET /healthz`, `GET /readyz`, etc.) receives a valid request THE SYSTEM
  SHALL respond identically to its behaviour on v5.2.1 for the same input.
- IF `RedirectSlashes` middleware is registered on any route in mctl-agent THE SYSTEM SHALL
  use the v5.2.5 hardened implementation and SHALL NOT perform an open redirect.
- WHILE mctl-agent is running after the upgrade THE SYSTEM SHALL produce no increase in
  HTTP error rate across any endpoint compared to the pre-upgrade baseline.

## Out of scope
- Adopting new chi v5.2.5 features (graceful shutdown refactor) beyond the version bump.
- Enabling `RedirectSlashes` middleware if it is not currently registered (this proposal
  makes no changes to middleware configuration).
- Upgrading chi beyond v5.2.5 (e.g., a hypothetical v6).
- Hardening any other HTTP router behaviour or endpoint security posture.
