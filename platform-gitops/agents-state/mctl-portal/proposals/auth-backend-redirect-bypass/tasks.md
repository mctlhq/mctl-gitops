# Tasks: auth-backend-redirect-bypass

Note: Tasks 1-2 are shared with the `auth-backend-metadata-ssrf` proposal. Both proposals are delivered in a single PR. The task numbering below reflects the combined PR sequence; see `auth-backend-metadata-ssrf/tasks.md` for its additional tasks.

- [ ] 1. Bump `@backstage/plugin-auth-backend` to `^0.27.1` in `packages/backend/package.json` — DoD: entry reads `"@backstage/plugin-auth-backend": "^0.27.1"` or higher; applies to both redirect-bypass (this proposal) and metadata-ssrf (Proposal 3) simultaneously.

- [ ] 2. Run `yarn install && yarn dedupe` and commit updated `yarn.lock` (depends on 1) — DoD: `yarn install --frozen-lockfile` passes in CI; lock-file resolves `@backstage/plugin-auth-backend` to 0.27.1 or higher with no lower-version copies remaining.

- [ ] 3. Write a security test for redirect-URI bypass (depends on 1) — DoD: a test issues a login request to `/api/auth/oidc/handler/frame?redirect_uri=https%3A%2F%2Fattacker.example%2Fcb` (percent-encoded bypass attempt); the backend responds with HTTP 400; the log contains `WARNING` referencing the disallowed URI; no authorization code appears in the response body.

- [ ] 4. Run full Dex SSO login flow in staging (depends on 2) — DoD: an end-to-end login via Dex completes successfully in the staging environment; the resulting session token grants access to the catalog home page; no errors in the auth-backend logs during the flow.

- [ ] 5. Deploy to production via ArgoCD (depends on 3, 4, and `auth-backend-metadata-ssrf` task 3) — DoD: ArgoCD sync completes for `admins` tenant; `@backstage/plugin-auth-backend` confirmed at 0.27.1+ in the running pod; no auth error rate spike in Grafana for 30 minutes post-deploy; incident ticket linked to CVE-2026-32235 marked resolved.

## Tests

- [ ] T1. Security test: crafted `redirect_uri` with percent-encoded host — server returns HTTP 400, no code leaked.
- [ ] T2. Security test: `redirect_uri` with an extra path segment appended to the allowlisted URL (e.g., `/callback/evil`) — server returns HTTP 400.
- [ ] T3. Happy-path test: `redirect_uri` exactly matching configured `callbackUrl` — authorization flow proceeds, session cookie issued.
- [ ] T4. Playwright e2e: full browser-based login via Dex SSO — user lands on catalog home page, session valid.
- [ ] T5. Regression test: after login, access to `/api/catalog/entities` returns 200 with a valid entity list.

## Rollback
1. Revert the `packages/backend/package.json` and `yarn.lock` changes via a Git revert PR (this also rolls back the `auth-backend-metadata-ssrf` fix since they share the same bump).
2. ArgoCD re-syncs automatically on the new commit.
3. Previous image is available in the registry for direct tag override in ArgoCD if an immediate rollback is needed before the revert PR merges.
4. After rollback, treat both CVE-2026-32235 and CVE-2026-32236 as active; open a P1 incident and apply the temporary mitigations: restrict the Dex callback URL at the ingress level and disable `auth.experimentalClientIdMetadataDocuments.enabled` manually in the ConfigMap until the fix is reapplied.
