# Design: nuxt-path-confusion-regression-tests-v2

## Current state
See context/architecture.md. Baseline version must be confirmed from package.json (docs disagree: 4.3.1 vs 4.6.2).

## Proposed solution
Add a small Node script (no new dependencies) run in deploy.yml between build and deploy. It starts the preview server, probes a fixed path list, and asserts status and body. Worker probes run against wrangler dev locally.

## Alternatives
- Do nothing: leaves known advisories or drift.
- Bundle with a major upgrade: rejected, higher risk.

## Platform impact
- Migrations: none.
- Backward compatibility: see behaviour notes above.
- Resource impact: none for `labs` (build-time only, admins tenant).
- Risks: regressions; mitigated by CI tests and a revertable PR.
