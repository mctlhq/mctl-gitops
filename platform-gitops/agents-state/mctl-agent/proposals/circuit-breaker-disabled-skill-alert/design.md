# Design: circuit-breaker-disabled-skill-alert

## Current state
See context/architecture.md. Breaker state is held in the skill metrics SQLite tables.

## Proposed solution
Add a state-transition hook in the breaker that publishes a metric and a notification once per transition (not per failure), and fires an AlertManager rule on the gauge.

## Alternatives
- Do nothing: leaves the gap described in requirements.md.
- Larger redesign: rejected as disproportionate to the effort.

## Platform impact
- Migrations: none.
- Backward compatibility: preserved.
- Resource impact: negligible; no increase in `labs` memory.
- Risks and mitigations: notification storms — mitigated by transition-only emission.
