# Design: nuxt-4-6-4-security-upgrade-v2

## Current state
See context/architecture.md. Baseline version must be confirmed from package.json (docs disagree: 4.3.1 vs 4.6.2).

## Proposed solution
Bump nuxt to 4.6.4 and refresh the lockfile (include vue 3.5.45 patch if it builds clean). Review behaviour changes: error detail stripping, dev-server allowedHosts, GET/HEAD-only caching rules. Verify prerender of /, /docs, /privacy.

## Alternatives
- Do nothing: leaves known advisories or drift.
- Bundle with a major upgrade: rejected, higher risk.

## Platform impact
- Migrations: none.
- Backward compatibility: see behaviour notes above.
- Resource impact: none for `labs` (build-time only, admins tenant).
- Risks: regressions; mitigated by CI tests and a revertable PR.
