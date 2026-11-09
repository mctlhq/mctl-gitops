# Upgrade Nuxt 4.3.1 to 4.6.4 (with nitropack 2.13.6)

## Context
`context/architecture.md` pins Nuxt 4.3.1, which is inside the vulnerable range of CVE-2026-114131 (incorrect authorization, CVSS 6.5, fixed in 4.4.4). Later advisories are fixed in 4.6.x: CVE-2026-119200 (encoded-path bypass, CVSS 6.5), CVE-2026-114133 (useHeadSafe server-island XSS), CVE-2026-120309 (getRouterParam mismatch), CVE-2026-114130 (NuxtLink XSS), plus dev-server issues and three Nitro advisories. Nuxt 4.6.4 (2 Nov) bundles all fixes and nitropack 2.13.6.

This is a minor-line bump inside Nuxt 4 and is consistent with ADR 0001 (track Nuxt releases). The `labs` tenant is near its memory limit, so memory must be verified before rollout there. Behaviour changes in 4.6.x are handled by the companion proposal `nuxt-4-6-behavior-audit`.

## User stories
- AS a platform operator I WANT mctl-web on Nuxt 4.6.4 SO THAT known authorization, XSS and path-bypass CVEs are closed.
- AS a maintainer I WANT the version docs updated after the upgrade SO THAT context matches reality (per ADR 0001).

## Acceptance criteria (EARS)
- WHEN the upgrade is merged THE SYSTEM SHALL build with nuxt 4.6.4 and nitropack 2.13.6 pinned in the lockfile.
- WHEN a request such as `/%2e/admin` is made THE SYSTEM SHALL NOT render a page keyed to `/admin`.
- WHEN `nuxt build` runs THE SYSTEM SHALL prerender `/`, `/privacy` and `/docs` without errors.
- WHEN dependency audit runs THE SYSTEM SHALL report none of the listed Nuxt CVEs.
- WHILE deployed to `labs` THE SYSTEM SHALL keep memory usage no more than 5% above the pre-upgrade baseline.
- IF post-upgrade memory on `labs` exceeds that threshold THEN THE SYSTEM SHALL block the `labs` rollout and keep the previous version there.
- WHEN the upgrade is released THE SYSTEM SHALL have `context/current-version.md` updated and a new ADR added (by the maintainer; `context/` is read-only for the agent).

## Out of scope
- Vue core 3.5.45 bump (may ride along but is not required).
- vue-router v5, vueuse v15, vee-validate/yup changes.
- Review of 4.6 behaviour-change opt-ins (see `nuxt-4-6-behavior-audit`).
- Sass bump (see `sass-1-108-bump`).
