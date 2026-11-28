# Design: nuxt-runtime-config-validation

## Current state
See context/architecture.md. Recorded versions are inconsistent (architecture.md: Nuxt 4.3.1; current-version.md: 4.6.2); package.json is the source of truth.

## Proposed solution
After the Nuxt 4.7 upgrade, define the runtimeConfig schema with yup (Standard Schema), remove apiSecret if unused (grep usage first), and add a CI check that the build starts with valid env.

## Alternatives
- Do nothing: rejected, leaves known exposure or drift.
- Larger migration (e.g. Nitro v3 experimental): rejected as too risky for the scope.

## Platform impact
- Migrations: none beyond dependency/config changes.
- Backward compatibility: minor/patch bumps only; no route or API changes.
- Resource impact: negligible; build-time only. No change for `labs` (not deployed there).
- Risks and mitigations: build regression, mitigated by CI build plus prerender smoke test; revert the lockfile to roll back.
