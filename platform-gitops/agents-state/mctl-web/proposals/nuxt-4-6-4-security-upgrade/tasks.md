# Tasks: nuxt-4-6-4-security-upgrade

- [ ] 1. Read the real Nuxt version from `package.json` and lockfile; report the 4.3.1 vs 4.6.2 discrepancy — DoD: baseline recorded in the PR description.
- [ ] 2. Verify CVE-2026-128077, -128071, -128074, -128075 (and related) against official Nuxt GitHub advisories; resolve whether 4.6.4 fully fixes CVE-2026-128071 — DoD: table of ID, severity, affected range, fixed version, status (confirmed/unverified).
- [ ] 3. Check overlap with existing proposals (`nuxt-upgrade-4-6-2`, `nuxt-4-6-behavior-audit`, `nuxt-security-upgrade`) (depends on 1) — DoD: supersede/merge decision noted.
- [ ] 4. Bump `nuxt` to 4.6.4, confirm `nitropack` >= 2.13.6, optionally Vue 3.5.45 (depends on 1, 2) — DoD: lockfile updated, `npm ls nuxt nitropack` shows target versions.
- [ ] 5. Review behaviour changes (error detail stripping, dev Host checks) (depends on 4) — DoD: no code path depends on error bodies; dev docs updated if hostnames need allowing.
- [ ] 6. Build and prerender; compare `dist/` routes (depends on 4) — DoD: `/`, `/docs`, `/privacy` generated, CI green.
- [ ] 7. Hand off to humans: update `context/current-version.md` and add ADR (depends on 6) — DoD: ADR merged citing only verified advisories.

## Tests
- [ ] T1. `nuxt build` succeeds in CI.
- [ ] T2. Prerendered HTML for the three routes matches the pre-upgrade output apart from expected hash changes.
- [ ] T3. A forced production error returns no stack or internal details.
- [ ] T4. Dev server starts locally and rejects a bogus Host header.

## Rollback
Revert the lockfile/`package.json` commit and redeploy the previous build via `deploy.yml`; static output means no data migration.
