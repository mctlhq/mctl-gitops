# Design: nuxt-security-upgrade

## Current state
Nuxt 4.3.1 (SSR=true, prerender `/`, `/privacy`, `/docs`), Vue 3.5.30, vue-router 4.6.4. See `context/architecture.md`. The Worker in `cloudflare-worker/` is deployed separately and is unaffected by the Nuxt version.

## Proposed solution
Bump `nuxt` to 4.6.4 in `package.json` and regenerate the lockfile so nitropack resolves to 2.13.6. Run `nuxt build` and the existing tests, compare bundle/server output, then roll out `admins` first, then `labs` after a memory check. Update `context/current-version.md` and add an ADR through the maintainer (the agent does not edit `context/`). Do this as one hop rather than stepping through 4.4.x/4.5.x because every intermediate release is already superseded and one hop yields one regression window.

## Alternatives
- Stop at 4.4.4: fixes CVE-2026-114131 only; leaves 4.6.x advisories open. Dropped.
- Stay on 4.3.1 and mitigate at the edge: does not fix the framework flaws and is fragile. Dropped.
- Step through each minor: more PRs and the same end state. Dropped.

## Platform impact
- Migrations: none for data; lockfile regeneration only.
- Backward compatibility: 4.6 behaviour changes (error details, x-forwarded-proto opt-in, GET/HEAD-only cached route rules) are covered by `nuxt-4-6-behavior-audit`; ship together or that one immediately after.
- Resource impact: expected roughly neutral. `labs` is close to its memory limit, so this is flagged as a memory risk; measure RSS/working set of the new image against baseline in `admins` before promoting to `labs`.
- Risks and mitigations: SSR regressions (mitigate with build + smoke tests of the three routes); memory growth on `labs` (gate rollout on measured delta, rollback via previous image tag); mctl MCP metrics were unavailable at research time, so the baseline must be captured manually.
