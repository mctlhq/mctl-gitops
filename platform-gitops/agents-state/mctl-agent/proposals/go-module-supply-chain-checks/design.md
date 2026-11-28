# Design: go-module-supply-chain-checks

## Current state
See context/architecture.md. CI is the only place dependencies are checked, mostly by hand.

## Proposed solution
Add a CI job step with go mod verify, readonly mode and a go.mod diff summary script.

## Alternatives
- Do nothing: leaves the gap described in requirements.md.
- Larger redesign: rejected as disproportionate to the effort.

## Platform impact
- Migrations: none.
- Backward compatibility: preserved.
- Resource impact: negligible; no increase in `labs` memory.
- Risks and mitigations: false positives on proxy outages — mitigated by retry.
