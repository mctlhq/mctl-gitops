# Tasks: svgo-billion-laughs-dos

- [ ] 1. Run `npm ls svgo` (and `npm ls vite-svg-loader`) to confirm the exact currently
      resolved versions — DoD: exact version strings recorded in the PR description.
- [ ] 2. Identify the minimum `svgo` version with CVE-2026-29074 / GHSA-xpqw-6gx7-v673
      fixed, and the minimum `vite-svg-loader` version that resolves to it (depends on 1)
      — DoD: target version numbers documented with a link to the fix changelog/commit.
- [ ] 3. Bump `vite-svg-loader` in `package.json` to the target version (or add an
      `overrides`/`resolutions` entry pinning `svgo` directly if `vite-svg-loader` has
      not yet released a fixed version) (depends on 2) — DoD: lockfile updated,
      `npm ls svgo` shows the fixed version resolved.
- [ ] 4. Run `nuxt build` locally/in CI and visually spot-check the rendered SVGs on
      `/`, `/docs`, `/privacy` (depends on 3) — DoD: build succeeds with no errors, no
      visible regression in SVG rendering.
- [ ] 5. Update `context/architecture.md`'s dependency listing for `vite-svg-loader`
      version (note: this edit is executed outside spec-writer's read-only access to
      `context/`, as a follow-up by whoever lands the change) (depends on 3) — DoD:
      architecture doc reflects the new pinned version.

## Tests
- [ ] T1. Run `npm audit` (or project's SCA tool) after the bump and confirm zero
      reported vulnerabilities for `svgo`/`vite-svg-loader`.
- [ ] T2. Feed a synthetic Billion-Laughs-style SVG (nested XML entity references) into
      the build pipeline and confirm it is rejected or bounded rather than hanging /
      exhausting memory.
- [ ] T3. Full `nuxt build` passes with all existing repo SVG assets, output byte-diffed
      against pre-upgrade build to confirm no unexpected content changes.

## Rollback
Revert the `package.json`/lockfile change (and remove the `overrides` entry if one was
added) to restore the prior `vite-svg-loader` pin. Since this is a build/dev-time-only
dependency with no runtime deploy step involved, rollback is a simple git revert plus a
re-run of `npm install` — no production redeploy or data migration is required.
