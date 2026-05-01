# Tasks: wrangler-ci-injection-audit

- [ ] 1. Read `deploy.yml` in full and map every variable and expression that contributes to the `--commit-hash` argument — DoD: a list of all contributing expressions is recorded in the PR description, each tagged as `github-controlled`, `repo-owner-controlled`, or `pr-author-controllable`.

- [ ] 2. Verify workflow `permissions:` scope for `pull_request` triggered runs — DoD: the `permissions:` block is present in `deploy.yml`; fork-triggered runs have at most `contents: read`; no secrets are exposed to the `pull_request` event. If absent, add the block as a fix.

- [ ] 3. Replace any use of `github.event.pull_request.head.sha` (or any PR-author-controllable expression) in the `--commit-hash` argument with `github.sha` — DoD: `--commit-hash` is sourced exclusively from GitHub-controlled context variables; the change is committed and noted in the PR.

- [ ] 4. Add a SHA format validation step to `deploy.yml` immediately before the wrangler invocation (depends on 1, 2, 3) — DoD: the step runs `[[ "$COMMIT_HASH" =~ ^[0-9a-f]{40}$|^[0-9a-f]{64}$ ]]` (or equivalent) and exits non-zero on mismatch; the step is visible in CI logs.

- [ ] 5. Add an inline comment block in `deploy.yml` near the `--commit-hash` line citing CVE-2026-0933, the audit date (2026-05-01), and the reason `github.sha` is preferred — DoD: comment is present and legible in the merged file.

- [ ] 6. Write ADR `context/decisions/0003-wrangler-ci-injection-audit.md` documenting the audit findings, any mitigations applied, and a clean/issue verdict (depends on 1–5) — DoD: ADR is merged to `context/decisions/`; the tracking ticket for CVE-2026-0933 is linked.

- [ ] 7. Open a PR with all changes; request review from at least one platform security engineer — DoD: PR is open, at least one reviewer assigned, all CI checks pass.

- [ ] 8. Merge PR and confirm `deploy.yml` runs successfully in the next triggered deploy (depends on 7) — DoD: the next deploy log shows the SHA validation step passing and the wrangler invocation completing with exit code 0.

## Tests
- [ ] T1. Dry-run: trigger the `deploy.yml` workflow on a branch where `github.sha` is a valid 40-character hex string — validation step exits 0.
- [ ] T2. Negative test: temporarily modify the validation regex to fail on a valid SHA (simulate a bad input) — CI step exits non-zero and the deploy is blocked before wrangler is invoked.
- [ ] T3. Confirm fork PR simulation: open a draft PR from a fork and verify that no secrets are accessible in the workflow run (check `${{ secrets.CLOUDFLARE_API_TOKEN }}` resolves to empty).
- [ ] T4. End-to-end: a successful `wrangler pages deploy` run completes post-merge; the Cloudflare deployment dashboard shows the correct commit hash in the metadata.

## Rollback
The changes are confined to `deploy.yml`. If the validation step causes an unexpected failure in production CI:
1. Revert the commit that added the validation step (keep the `permissions:` fix and source-variable fixes in place).
2. Re-run `deploy.yml` manually to confirm the revert unblocks deploys.
3. Investigate the failure in a branch before re-applying.
The Cloudflare Worker itself is not affected by any change in this proposal — rollback requires no Worker redeploy.
