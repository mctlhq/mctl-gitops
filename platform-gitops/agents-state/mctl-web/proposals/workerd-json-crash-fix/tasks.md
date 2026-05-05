# Tasks: workerd-json-crash-fix

- [ ] 1. Upgrade wrangler pin in `cloudflare-worker/package.json` to the latest available
  version at merge time (≥ 4.87.0) — DoD: `package.json` updated, `package-lock.json`
  regenerated with `npm install`, diff shows wrangler version bump.

- [ ] 2. Verify resolved workerd version in lockfile (depends on 1) — DoD: run
  `node -e "console.log(require('./node_modules/workerd/package.json').version)"` inside
  `cloudflare-worker/` and confirm the printed version is ≥ `1.20260505.1`.

- [ ] 3. Add workerd version assertion step to `deploy.yml` (depends on 2) — DoD: a `run`
  step after `npm ci` parses the resolved workerd version from the lockfile and exits
  non-zero if it is below `1.20260505.1`; the step name is `Verify workerd version`.

- [ ] 4. Run full local integration smoke-test (depends on 1) — DoD: `wrangler dev` starts
  without errors; manually hitting `/api/contact` and `/api/submit` (with test data) returns
  expected responses and no runtime panics appear in the wrangler log.

- [ ] 5. Open PR and pass CI (depends on 3, 4) — DoD: GitHub Actions run completes green
  (build, type-check, and the new version-assertion step all pass); PR description references
  workerd v1.20260505.1 crash fix and links to the workerd release page.

## Tests
- [ ] T1. `wrangler dev` cold-start: confirm no `[error]` lines in the first 10 seconds of
  output when starting the Worker locally with the new wrangler version.
- [ ] T2. JSON module path: if any Worker code imports a `.json` file as a module, confirm
  that it loads without error under the new workerd version.
- [ ] T3. CI assertion gate: temporarily set `MIN_VERSION` to a future date (e.g.
  `99991231.1`) in a test branch and confirm the CI step exits non-zero and blocks deployment.

## Rollback
1. Revert the `cloudflare-worker/package.json` change (restore previous wrangler pin) via
   `git revert` on the merge commit.
2. Run `npm install` in `cloudflare-worker/` to restore the lockfile.
3. Trigger `deploy.yml` manually (workflow_dispatch) on the reverted commit to redeploy
   the previous Worker version.
4. Confirm the Worker is healthy via the Cloudflare Dashboard → Workers → mctl-web → Logs.
