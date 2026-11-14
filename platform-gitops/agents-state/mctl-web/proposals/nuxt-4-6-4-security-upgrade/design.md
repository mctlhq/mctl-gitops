# Design: nuxt-4-6-4-security-upgrade

## Current state
Nuxt SSG/SSR frontend with prerender of `/`, `/privacy`, `/docs` (see `context/architecture.md`). Recorded Nuxt version is inconsistent: 4.3.1 (architecture.md, ADR 0001) vs 4.6.2 (current-version.md). Truth is in `package.json` and the lockfile (to verify, V1). Related earlier proposals exist in this folder (e.g. `nuxt-upgrade-4-6-2`, `nuxt-4-6-behavior-audit`, `nuxt-security-upgrade`); the implementer should check for overlap and supersede or merge rather than duplicate.

## Proposed solution
1. Verify the baseline version and the advisory list against official Nuxt GitHub advisories.
2. Bump `nuxt` to 4.6.4 and ensure `nitropack` resolves to 2.13.6+ (override only if the lockfile does not pick it up).
3. Optionally fold in Vue core 3.5.45 (empty release notes, low risk) in the same refresh; skip if any peer conflict.
4. Build, run the prerender, and smoke-test output. Review behaviour changes: stripped production error details (check nothing in the app or Worker parses error bodies) and dev server Host checks (check local/CI dev flows and any proxy hostnames).
5. The `/_nuxt/@fs/` read issue is dev-server only; mitigation is the upgrade plus not exposing the dev server to untrusted networks.

Why this way: a patch/minor bump within Nuxt 4 matches ADR 0001 (track Nuxt releases) and is the smallest change that carries the fixes.

## Alternatives
- Stay put and apply route-level mitigations: dropped, leaves known-vulnerable code and does not cover Nitro fixes.
- Jump to a newer Nuxt line or add vue-router 5 / vueuse 15: dropped, breaking changes with no security driver.
- Pin only nitropack: dropped, misses the Nuxt-side fixes.

## Platform impact
- Migrations: none; lockfile change only. Context docs need reconciliation (human step).
- Backward compatibility: error responses lose detail in production; dev server Host checks may break custom hostnames.
- Resource impact: build step only, `admins` tenant. No expected runtime memory increase; `labs` untouched.
- Risks and mitigations: unverified CVE data (verify before citing); unclear baseline (verify first); prerender regressions (build and diff `dist/`); overlap with existing proposals (check before starting).
