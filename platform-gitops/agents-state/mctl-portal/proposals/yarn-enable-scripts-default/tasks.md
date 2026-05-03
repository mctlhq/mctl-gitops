# Tasks: yarn-enable-scripts-default

- [ ] 1. Audit all postinstall scripts in the current lockfile — DoD: a documented list of
  every package in the monorepo's dependency tree that declares a `preinstall`, `install`,
  or `postinstall` lifecycle script, produced by running an enumeration command (e.g.,
  `yarn info --all --json`) against the current lockfile. List committed as a comment in
  the PR or as a temporary `docs/install-script-audit.md` file (to be deleted post-merge).

- [ ] 2. Decide the `enableScripts` strategy and update `.yarnrc.yml` (depends on 1) —
  DoD: `.yarnrc.yml` contains an explicit `enableScripts` setting (either `true` with a
  justification comment, or `false` plus an `approvedGitRepositories` / per-package
  allowlist). The decision is documented with a rationale comment inline. No implicit
  reliance on Yarn defaults remains.

- [ ] 3. Pin the approved Yarn version via Corepack (depends on 2) — DoD: `package.json`
  `packageManager` field is updated to `yarn@4.14.0` (or `4.14.1` if Node.js v24
  compatibility is needed). `corepack enable` and `corepack prepare` are confirmed to
  install the correct Yarn binary in CI.

- [ ] 4. Upgrade Yarn binary and regenerate lockfile (depends on 3) — DoD: `yarn install`
  completes successfully with the v4.14.0 binary and the updated `.yarnrc.yml`. `yarn.lock`
  is regenerated and committed. No `yarn install` warnings about skipped scripts remain
  unaddressed.

- [ ] 5. Validate CI pipeline (depends on 4) — DoD: the full CI pipeline (lint, type-check,
  unit tests, Docker build) passes on the updated lockfile with the new Yarn version.
  CI logs show no unexpected "script skipped" warnings.

- [ ] 6. Validate Playwright browser availability (depends on 4) — DoD: `yarn playwright
  install` (or the equivalent CI step) successfully downloads browser binaries and
  `yarn playwright --version` reports the expected version. At least one e2e test
  executes without a "browser not found" error.

- [ ] 7. Validate native addon packages (depends on 4, if applicable) — DoD: any native
  Node.js addon in the dependency tree (e.g., `better-sqlite3`, `isolated-vm`) can be
  `require()`d or `import`ed in a Node.js REPL without a `MODULE_NOT_FOUND` or binding
  error. If no native addons are present, task is marked N/A with a comment.

- [ ] 8. Merge and communicate to the team (depends on 5, 6, 7) — DoD: PR merged to main;
  a brief note in the team's Slack channel (or equivalent) describes the change and any
  action developers need to take locally (e.g., run `corepack enable`, re-run
  `yarn install`).

## Tests

- [ ] T1. `yarn install` with Yarn v4.14.0 and the updated `.yarnrc.yml` produces exit
  code 0 and zero "script skipped" warnings for allowlisted packages.
- [ ] T2. `yarn workspaces foreach run test` passes with zero failing test suites on the
  regenerated lockfile.
- [ ] T3. Playwright smoke test: `yarn playwright test --project=chromium` runs at least
  one test file successfully, confirming the browser binary was installed correctly.
- [ ] T4. (If native addons present) Node.js integration test: `node -e "require('<addon>')"
  exits 0 for each native addon identified in the audit.
- [ ] T5. Docker build produces a working image: `docker run --rm <image> node -e
  "require('./packages/backend')"` (or equivalent healthcheck invocation) exits 0.

## Rollback
1. This proposal is purely a build-time change. No production deployments are modified
   until task 8 is merged and a new image is built and promoted by the normal deployment
   pipeline.
2. If the merged change breaks CI, revert the `.yarnrc.yml`, `package.json`
   (`packageManager`), and `yarn.lock` changes in a single revert commit.
3. Corepack will revert to the previously pinned Yarn version automatically after the
   `packageManager` field is reverted.
4. If a production image was promoted before a CI break was detected, roll back via ArgoCD
   to the previous known-good image tag (same process as any other image rollback).
5. Re-open this proposal with additional findings from the failure before re-attempting.
