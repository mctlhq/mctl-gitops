# Tasks: vue-patch-3-5-33

- [ ] 1. Determine whether `vue` is specified explicitly in `package.json` or resolved transitively through Nuxt. — DoD: the version-management approach for vue is captured.
- [ ] 2. Update `vue` to `"^3.5.33"` explicitly (or via `npm update vue` / `pnpm update vue`) and regenerate the lockfile. — DoD: the lockfile contains vue@3.5.33, no peer-dependency conflicts.
- [ ] 3. Run `nuxt build` and confirm there are no errors. — DoD: exit code 0, no new Vue warnings.
- [ ] 4. Open a PR, merge, deploy. — DoD: prod works correctly.

## Tests

- [ ] T1. `nuxt build` finishes with exit code 0.
- [ ] T2. In a browser at `mctl.ai` — no Vue warnings in DevTools Console.
- [ ] T3. The tenant registration form (`/`) validates correctly (vee-validate + yup are not broken).

## Rollback

Restore the previous `vue` version in `package.json`, regenerate the lockfile, rebuild and deploy. Takes under 5 minutes — isolated patch.

## Note

If the Nuxt upgrade to 4.4.2 (proposal `nuxt-upgrade-4-4-2`) already includes Vue 3.5.33 as a transitive dependency, this proposal can be considered subsumed and closed without a separate PR.
