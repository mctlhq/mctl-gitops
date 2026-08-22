# Tasks: wrangler-bump

- [ ] 1. Update the wrangler version pin used by `deploy.yml` (in `package.json`
      devDependencies or equivalent) from the current version to 4.125.0 (or the
      latest patch release at execution time) — DoD: dependency manifest and lockfile
      updated; `wrangler --version` in CI reports >= 4.125.0.
- [ ] 2. Review `wrangler.toml` and any CLI flags/scripts in `deploy.yml` for
      compatibility with wrangler 4.125.0, updating as needed (depends on 1) — DoD:
      no deprecated/removed flags remain; config reviewed against the wrangler
      4.125.0 changelog.
- [ ] 3. Run the deploy pipeline against a non-production target or dry-run mode to
      validate the bump before touching production (depends on 1, 2) — DoD: a
      successful non-production/dry-run deploy completes with no errors introduced
      by the version bump.
- [ ] 4. Deploy to production via the normal `deploy.yml` flow (depends on 3) — DoD:
      Worker deploy succeeds; `deploy.yml` run is green.
- [ ] 5. Verify the deployed Worker's endpoints function correctly post-deploy
      (depends on 4) — DoD: `/api/github/login`, `/api/github/callback`,
      `/api/submit`, `/api/contact`, and the domain redirects all respond as expected.

## Tests
- [ ] T1. CI pipeline test: `deploy.yml` completes successfully in a non-production/
      dry-run pass after the version bump.
- [ ] T2. Manual smoke test: GitHub OAuth login/callback flow works end-to-end after
      production deploy.
- [ ] T3. Manual smoke test: tenant provisioning submit form and contact form still
      trigger correctly (Backstage call, Telegram notification, Resend email where
      applicable) and rate limits still apply as configured.
- [ ] T4. Manual check: any KV-backed state (if used by this Worker) reads/writes
      correctly post-bump, specifically exercising binary values if applicable, to
      confirm the corruption fix is in effect and nothing else regressed.

## Rollback
If the pipeline fails or the deployed Worker misbehaves after the bump: revert the
wrangler version pin in the dependency manifest/lockfile to the prior known-good
version, re-run `deploy.yml` to redeploy the Worker using the previous wrangler
version, and confirm endpoints recover. Because wrangler is a build-time tool, rolling
back the pin and redeploying fully reverts any pipeline-level risk introduced by this
change; no data migration or cleanup is needed.
