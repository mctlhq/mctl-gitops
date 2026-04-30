# Tasks: wrangler-upgrade-security

- [ ] 1. Audit `deploy.yml` and `package.json` to determine the exact current wrangler version or install method — DoD: documented finding in the PR description.
- [ ] 2. Pin wrangler to `4.87.0` in `package.json` devDependencies (add if absent) and update `package-lock.json` via `npm install` — DoD: `package.json` shows `"wrangler": "4.87.0"` and lockfile is committed.
- [ ] 3. Update `deploy.yml` to use `npm ci` (or `npx wrangler@4.87.0`) instead of any floating wrangler install — DoD: no `latest` tag reference for wrangler in CI.
- [ ] 4. Review wrangler 4.59-4.87 changelogs for breaking changes in CLI flags used in `deploy.yml` — DoD: no breaking flags identified, or workflow updated to match new flags.
- [ ] 5. Open a PR, trigger the deploy workflow in a staging environment or dry-run — DoD: `wrangler pages deploy` completes without error; deployed Worker responds to health-check requests.

## Tests
- [ ] T1. CI run shows wrangler version `4.87.0` in the deploy step logs.
- [ ] T2. Deployed Worker on `mctl.ai/api/github/login` returns a valid redirect (OAuth flow starts), confirming runtime is healthy.
- [ ] T3. `npm audit` (or `wrangler`-specific advisory check) reports no known CVEs for wrangler@4.87.0.

## Rollback
Revert `package.json` and `deploy.yml` to the previous wrangler version and re-run the deploy workflow. The Pages deployment will roll back to the previous build automatically via Cloudflare's deployment history if needed.
