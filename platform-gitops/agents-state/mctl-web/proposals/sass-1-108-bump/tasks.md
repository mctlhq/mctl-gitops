# Tasks: sass-1-108-bump

- [ ] 1. Build on sass 1.98.0 and save the CSS output and warnings as a baseline — DoD: baseline artifact stored.
- [ ] 2. Set `sass` to exact `1.108.0` and regenerate the lockfile (depends on 1) — DoD: lockfile resolves sass 1.108.0 only.
- [ ] 3. Rebuild and diff CSS and warnings against baseline (depends on 2) — DoD: no unexpected diff or new warnings.
- [ ] 4. Deploy via the normal pipeline (depends on 3) — DoD: pages render correctly in `admins`.

## Tests
- [ ] T1. `nuxt build` succeeds with sass 1.108.0.
- [ ] T2. Lockfile contains no sass 1.106.x or 1.107.x.
- [ ] T3. Visual check of `/`, `/docs`, `/privacy` shows no styling regressions.

## Rollback
Revert the commit (restore `sass` 1.98.0 and the old lockfile) and redeploy. No runtime state is affected.
