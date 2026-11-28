# Design: anthropic-sdk-v215-upgrade

## Current state
See context/architecture.md. Anthropic client is vendored or direct HTTP per architecture.md.

## Proposed solution
Check usage with `go list -m all`; if present, bump to v2.15.0, fix any compile issues, run tests.

## Alternatives
- Do nothing: leaves the gap described in requirements.md.
- Larger redesign: rejected as disproportionate to the effort.

## Platform impact
- Migrations: none.
- Backward compatibility: preserved.
- Resource impact: negligible; no increase in `labs` memory.
- Risks and mitigations: v2 API drift — mitigated by running diagnose fixtures.
