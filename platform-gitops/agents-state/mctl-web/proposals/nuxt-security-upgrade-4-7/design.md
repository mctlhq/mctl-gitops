# Design: nuxt-security-upgrade-4-7

## Current state
See context/architecture.md. Recorded versions are inconsistent (architecture.md: Nuxt 4.3.1; current-version.md: 4.6.2); package.json is the source of truth.

## Proposed solution
Run `npx nuxt upgrade --dedupe`, review the 4.7 changelog for template diagnostics (NUXT_B4025), fix warnings, update vue to 3.5.46 in the same PR, and update context docs via the reconcile proposal. Purge CDN cached _payload.json if cache/swr/isr route rules are used.

## Alternatives
- Do nothing: rejected, leaves known exposure or drift.
- Larger migration (e.g. Nitro v3 experimental): rejected as too risky for the scope.

## Platform impact
- Migrations: none beyond dependency/config changes.
- Backward compatibility: minor/patch bumps only; no route or API changes.
- Resource impact: negligible; build-time only. No change for `labs` (not deployed there).
- Risks and mitigations: build regression, mitigated by CI build plus prerender smoke test; revert the lockfile to roll back.
