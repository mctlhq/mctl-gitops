# Design: automated-dependency-update-prs

## Current state
Manual bumps; see context/architecture.md for the stack.

## Proposed solution
Add `.github/dependabot.yml` (gomod ecosystem), weekly schedule, one group for minor/patch updates, majors ungrouped with a `major-bump` label. Security updates follow Dependabot defaults. CI (including the govulncheck gate) validates each PR.

## Alternatives
- Renovate: more flexible but needs an extra app/hosting.
- Keep manual: causes repeated proposals.

## Platform impact
- Migrations: none. Backward compatibility: none affected.
- Resource impact: none at runtime; no effect on `labs`.
- Risks: PR noise; mitigated by grouping and a PR limit.
