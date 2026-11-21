# Design: worker-toolchain-bump-compat-date-v2

## Current state
See context/architecture.md. Baseline version must be confirmed from package.json (docs disagree: 4.3.1 vs 4.6.2).

## Proposed solution
Pin wrangler to the release bundling the new workerd, evaluate moving compatibility_date to a recent date in staging, add try/catch handling around outbound fetches if missing.

## Alternatives
- Do nothing: leaves known advisories or drift.
- Bundle with a major upgrade: rejected, higher risk.

## Platform impact
- Migrations: none.
- Backward compatibility: see behaviour notes above.
- Resource impact: none for `labs` (build-time only, admins tenant).
- Risks: regressions; mitigated by CI tests and a revertable PR.
