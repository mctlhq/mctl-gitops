# Design: labs-plugin-reuse-memory-validation

## Current state
`labs` is close to its memory limit (`context/architecture.md`).

## Proposed solution
Use `mcp__mctl__mctl_get_resource_usage` / `mctl_get_openclaw_sizing_recommendation` for `labs` (read-only) before and after the upgrade, including a model-switch exercise. Record results in the upgrade ticket.

## Alternatives
- Rely on release notes: rejected, unverified.

## Platform impact
- No migrations; read-only measurement; zero memory impact.
- Risk: short observation window misses peaks; use at least 24h including a model switch.
