# Design: wrangler-4-169-upgrade-oidc-eval

## Current state
See context/architecture.md. Recorded versions are inconsistent (architecture.md: Nuxt 4.3.1; current-version.md: 4.6.2); package.json is the source of truth.

## Proposed solution
Bump wrangler in cloudflare-worker, keep compat date, run wrangler deploy --dry-run in CI, and write a short ADR-style note on oidc_tokens feasibility (account enablement required, no local dev support).

## Alternatives
- Do nothing: rejected, leaves known exposure or drift.
- Larger migration (e.g. Nitro v3 experimental): rejected as too risky for the scope.

## Platform impact
- Migrations: none beyond dependency/config changes.
- Backward compatibility: minor/patch bumps only; no route or API changes.
- Resource impact: negligible; build-time only. No change for `labs` (not deployed there).
- Risks and mitigations: build regression, mitigated by CI build plus prerender smoke test; revert the lockfile to roll back.
