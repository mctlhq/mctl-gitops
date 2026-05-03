# Tasks — wrangler-node22-ci-upgrade

## Checklist

- [ ] 1. Update `node-version` in `deploy.yml` to `'22'` for every job
  that invokes wrangler, and for the Nuxt build job if it is in the same
  file.
  DoD: `deploy.yml` contains no `node-version` value below `'22'`; the
  change is committed to the feature branch.

- [ ] 2. Bump wrangler in `package.json` to `^4.87.0` (depends on 1, can
  be done in the same commit).
  DoD: `package.json` declares `"wrangler": "^4.87.0"` (or higher);
  `package-lock.json` is regenerated via `npm install` and committed
  alongside.

- [ ] 3. Open a pull request containing tasks 1 and 2; confirm CI passes
  on the PR branch (depends on 1 and 2).
  DoD: the `deploy.yml` workflow run on the PR branch exits with code 0;
  the wrangler startup log shows no Node.js version error; the Worker is
  deployed (or `--dry-run` succeeds on a staging environment).

- [ ] 4. Optionally add `.nvmrc` with content `22` to the repository root
  so local `wrangler dev` sessions also use Node 22 (independent of 1-3,
  low-effort bonus).
  DoD: file exists at repo root; `node --version` inside the project
  directory returns `v22.x.x` when using nvm or a compatible tool.

- [ ] 5. Merge the PR and verify the first post-merge deploy workflow run
  succeeds (depends on 3).
  DoD: the merged `main` branch CI run completes successfully; the Worker
  revision timestamp in the Cloudflare Dashboard is newer than the merge
  time.

## Tests

- T1. On the PR branch, inspect the GitHub Actions run log for the deploy
  job and confirm the "Set up Node.js" step reports `v22.x.x`.
- T2. Confirm the wrangler startup output contains no line matching
  "requires Node.js" or similar fatal version-check messages.
- T3. Run `npm ci && npx wrangler --version` in a local Node 22
  environment; confirm the wrangler version reported is 4.87.0 or higher.
- T4. After merge, retrieve the latest Worker deployment from the
  Cloudflare Dashboard (or via `wrangler deployments list`) and confirm
  the deploy timestamp post-dates the merge.
- T5. Trigger a full Nuxt build (`npm run build`) in a Node 22 environment
  and confirm it completes without errors or changed output artifacts
  compared to the pre-change baseline.

## Rollback

1. Revert the merge commit (`git revert <merge-sha>`) on `main`. This
   restores `deploy.yml` and `package.json` / `package-lock.json` to their
   pre-upgrade state in a single atomic commit.
2. Push the revert commit; the CI pipeline will pick it up automatically
   and deploy the previous wrangler version.
3. Note: rolling back to wrangler < 4.87.0 re-introduces the old version
   with potentially unpatched issues. The rollback should only be used if
   the Node 22 / wrangler 4.87.0 combination itself causes a runtime
   regression, and it should be treated as a temporary measure while the
   underlying issue is diagnosed.
4. No Cloudflare secret rotation, Kubernetes changes, or database
   migrations are needed to complete the rollback.
