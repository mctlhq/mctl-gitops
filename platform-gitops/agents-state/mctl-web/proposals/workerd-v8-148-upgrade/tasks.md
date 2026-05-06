# Tasks: workerd-v8-148-upgrade

- [ ] 1. Pin wrangler to 4.88.0 in `cloudflare-worker/package.json` —
  DoD: `"wrangler": "4.88.0"` (exact, not a range) appears in `devDependencies`;
  `npm ci` inside `cloudflare-worker/` completes without errors and
  `npx wrangler --version` outputs `4.88.0`.

- [ ] 2. Regenerate the lockfile (depends on 1) —
  DoD: `cloudflare-worker/package-lock.json` is updated to reflect wrangler
  4.88.0 and its transitive dependencies; the file is committed alongside the
  `package.json` change in the same PR.

- [ ] 3. Verify local `wrangler dev` uses workerd v1.20260506.1 (depends on 2) —
  DoD: running `wrangler dev` in `cloudflare-worker/` prints a log line
  referencing workerd `v1.20260506.1` (or V8 `14.8`) during startup; confirmed
  by at least one developer on the team.

- [ ] 4. Open and merge the PR containing tasks 1-3 (depends on 3) —
  DoD: PR is approved, CI passes (lint + type-check in `cloudflare-worker/`),
  and the branch is merged to the deploy branch without conflicts.

- [ ] 5. Confirm production deployment via `deploy.yml` (depends on 4) —
  DoD: the GitHub Actions workflow completes with status "success"; Cloudflare
  dashboard shows the newly deployed Worker version; no error spike observed in
  Cloudflare Worker analytics within 15 minutes of deployment.

## Tests

- [ ] T1. Smoke test — POST `/api/contact` with a valid payload after deployment
  returns HTTP 200 and the expected JSON body.
- [ ] T2. Smoke test — GET `/api/github/login` returns HTTP 302 redirect to
  `github.com/login/oauth/authorize`.
- [ ] T3. Rate-limit regression — send 4 rapid requests to `/api/contact` from
  the same IP; the 4th request must return HTTP 429.
- [ ] T4. Local dev parity — run `wrangler dev` and execute T1 and T2 against
  `localhost`; results must match production responses.
- [ ] T5. Lockfile integrity — `npm ci --dry-run` inside `cloudflare-worker/`
  must exit 0 on a clean CI runner (no network), confirming the committed
  lockfile is self-consistent.

## Rollback
If any smoke test (T1-T3) fails in production after deployment:

1. Revert the `package.json` and `package-lock.json` changes to restore the
   previous wrangler version (e.g., 4.86.0 / workerd v1.20260430.1).
2. Merge the revert PR; `deploy.yml` will re-deploy the previous Worker version
   automatically.
3. Confirm the revert deployment completes successfully via the Cloudflare
   dashboard and re-run T1-T3.
4. Open a post-mortem issue referencing the failing test output and the workerd
   release notes before attempting the upgrade again.

Rollback is low-risk because the change is limited to a version pin with no
data or schema side-effects.
