# Tasks: sass-upgrade-1-99

- [ ] 1. Bump sass in package.json — Update the version specifier for `sass` from `1.98.0` to
  `^1.99.0` (or `1.99.0` exact) in the Nuxt app's `package.json`. DoD: `package.json` contains
  the new specifier and no other unrelated dependency changes.

- [ ] 2. Regenerate lock file (depends on 1) — Run `npm install` in the Nuxt app root.
  DoD: `package-lock.json` resolves `sass` to `1.99.0`; `npm ci` succeeds from clean state.

- [ ] 3. Run build and capture deprecation warnings (depends on 2) — Execute `nuxt build` and
  collect any sass deprecation warnings from the Vite build output. DoD: build exits 0; a
  complete list of any new deprecation warnings is captured in a comment on the PR or in a
  separate tracking note for the `sass-deprecation-fix` proposal.

- [ ] 4. Verify CSS output correctness (depends on 3) — Diff the compiled CSS in `dist/` against
  the output from 1.98.0 (or visually inspect key pages) to confirm no unintended style changes.
  DoD: no visible layout or styling regressions on `/`, `/docs`, `/privacy`, or the tenant form.

- [ ] 5. Coordinate with sass-deprecation-fix (depends on 3) — If step 3 surfaces deprecation
  warnings, ensure a tracking comment links this PR to the `sass-deprecation-fix` work item so
  they are resolved in the correct sequence. DoD: no open deprecation warnings are left
  untracked; either they are fixed in this PR or a linked follow-up issue exists.

- [ ] 6. Commit (depends on 4, 5) — Commit `package.json` and `package-lock.json` atomically.
  DoD: single commit; CI pipeline passes; `nuxt build` in CI shows sass 1.99.0 in the build log.

## Tests

- [ ] T1. `npm ci && nuxt build` exits 0 in a clean CI environment with sass 1.99.0.
- [ ] T2. The Vite/sass build log confirms `sass 1.99.0` (or newer 1.99.x) is the active
  compiler version.
- [ ] T3. All prerendered pages (`/`, `/docs`, `/privacy`) render without visual regressions
  compared to the 1.98.0 build — verified by screenshot diff or manual review.
- [ ] T4. Any sass deprecation warnings surfaced during the build are documented and linked to
  the `sass-deprecation-fix` proposal.

## Rollback
Revert `package.json` and `package-lock.json` to the prior committed versions and run `npm ci`.
No Worker code, Cloudflare configuration, or Kubernetes manifests are affected.
