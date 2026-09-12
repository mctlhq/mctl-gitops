# Tasks: vite-dev-server-file-read-cve

- [ ] 1. Check whether `proposals/nuxt-security-patch/` has already landed (Nuxt bumped
      to ≥4.5.1) — DoD: documented status (landed / not landed) at time of this spike.
- [ ] 2. Run `npm ls --all vite` against the current installed dependency tree (post
      Nuxt upgrade if task 1 found it landed, otherwise against Nuxt 4.3.1 as currently
      pinned) (depends on 1) — DoD: exact resolved Vite version(s) recorded, including
      any distinct versions pulled in by `@cloudflare/vite-plugin` vs. Nuxt's own
      internal Vite dependency.
- [ ] 3. Compare each resolved Vite version against the fixed thresholds for
      CVE-2025-31125 (6.2.4/6.1.3/6.0.13/5.4.16/4.5.11) and CVE-2026-53571
      (8.0.16/7.3.5/6.4.3) (depends on 2) — DoD: documented conclusion of "affected" or
      "not affected" for each CVE.
- [ ] 4a. IF not affected: close this proposal as "not applicable," recording the
      confirmed Vite version and the fixed-threshold comparison (depends on 3) — DoD:
      conclusion documented, no dependency change made.
- [ ] 4b. IF affected: identify the minimum fixed Vite version compatible with the
      installed Nuxt version, and add an `overrides`/`resolutions` entry pinning it (or
      document that a Nuxt bump is required if no compatible override exists) (depends
      on 3) — DoD: lockfile updated (or explicit note that remediation depends on a
      Nuxt version bump instead).
- [ ] 5. If task 4b applied a fix: run `nuxt build` and start the dev server locally,
      confirming no build/dev-server errors (depends on 4b) — DoD: clean build output
      and dev server startup with no new errors/warnings.

## Tests
- [ ] T1. `npm ls --all vite` output captured and compared against fixed-version
      thresholds for both CVEs (verification, not a code test).
- [ ] T2. If a fix is applied: attempt to fetch a known-sensitive path (e.g.
      `/@fs/../../.env`) from the running dev server and confirm it is denied
      (non-200), reproducing the CVE-2025-31125 check.
- [ ] T3. If a fix is applied: full `nuxt build` succeeds and prerenders `/`, `/privacy`,
      `/docs` with no errors, confirming no regression from the Vite version change.

## Rollback
Stage 1 (verification) has no rollback concern. If Stage 2's `overrides`/`resolutions`
entry is applied and later found to cause instability in the dev server or build,
revert the lockfile/`package.json` change to remove the override, restoring the Vite
version Nuxt resolves natively. No production deploy or data migration is involved,
since Vite only runs at build/dev time.
