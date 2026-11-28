# Design: govulncheck-ci-gate

## Current state
No automated vulnerability gate; CVEs are found manually by the daily researcher (context/architecture.md).

## Proposed solution
Add a CI job running `govulncheck ./...` pinned to a tool version, on PRs and nightly, with a small waiver file (id, reason, expiry) parsed by a wrapper script.

## Alternatives
- Dependabot only: no reachability filtering, noisy.
- Trivy image scan: complements but not reachability-aware.

## Platform impact
- Migrations: none. Compatibility: CI only.
- Resource impact: none at runtime; `labs` unaffected.
- Risks: false-positive blocking; mitigated by expiring waivers.
