# Tasks: auth-backend-metadata-ssrf

Note: Tasks 1-2 are shared with `auth-backend-redirect-bypass`. Both proposals are delivered in a single PR. Complete `auth-backend-redirect-bypass` tasks 1-2 first; they satisfy the package bump requirement for this proposal as well.

- [ ] 1. (Shared with auth-backend-redirect-bypass) Bump `@backstage/plugin-auth-backend` to `^0.27.1` in `packages/backend/package.json` — DoD: same as auth-backend-redirect-bypass task 1.

- [ ] 2. (Shared with auth-backend-redirect-bypass) Run `yarn install && yarn dedupe` and commit `yarn.lock` — DoD: same as auth-backend-redirect-bypass task 2.

- [ ] 3. Audit current value of `auth.experimentalClientIdMetadataDocuments.enabled` in all `app-config*.yaml` files (depends on none — can run in parallel with 1) — DoD: a written finding is recorded in the PR description: either "flag was absent" or "flag was set to X"; any integration dependency on the feature is confirmed to not exist.

- [ ] 4. Set `auth.experimentalClientIdMetadataDocuments.enabled: false` explicitly in `app-config.yaml` (depends on 3) — DoD: the key exists and is `false` in `app-config.yaml`; if a production-specific override file exists (`app-config.production.yaml`), the key is also set to `false` there.

- [ ] 5. Add CI configuration drift check (depends on 4) — DoD: a CI step using a structured YAML parser asserts that `auth.experimentalClientIdMetadataDocuments.enabled` is not `true` in any `app-config*.yaml` file; the step fails the build if the assertion is violated; the check is enforced on every PR targeting `main`.

- [ ] 6. Write a security test for the SSRF vector (depends on 1) — DoD: a test starts the backend with `experimentalClientIdMetadataDocuments.enabled: false` and issues an auth request that would normally trigger the metadata fetch; no outbound HTTP request to an external URL is observed (verified via a mock HTTP recorder); the test fails if any redirect-following occurs.

- [ ] 7. Deploy to production via ArgoCD (depends on 5, 6, and `auth-backend-redirect-bypass` task 4) — DoD: ArgoCD sync completes; `@backstage/plugin-auth-backend` is 0.27.1+ in the running pod; `app-config.yaml` in the deployed ConfigMap contains `enabled: false`; no SSRF-related error entries in the auth-backend logs; incident ticket linked to CVE-2026-32236 marked resolved.

## Tests

- [ ] T1. Config test: the backend starts successfully with `experimentalClientIdMetadataDocuments.enabled: false`; startup log contains `INFO` confirming the feature is disabled.
- [ ] T2. Security test: with the feature disabled, an auth request that would trigger the CIMD fetch completes without any outbound HTTP call to a metadata URL (mock recorder confirms zero calls).
- [ ] T3. Security test (package-level, requires enabled: true in test env only): a CIMD metadata URL that redirects to an internal address (e.g., `http://169.254.169.254/`) is rejected; the backend logs an ERROR and does not follow the redirect.
- [ ] T4. CI drift check test: temporarily set `enabled: true` in a test config file; confirm the CI drift-check step fails; revert.
- [ ] T5. Integration test: full Dex SSO login succeeds with the flag disabled — confirms the flag does not interfere with the primary auth flow.

## Rollback
1. Rolling back this proposal also rolls back `auth-backend-redirect-bypass` because they share the same `plugin-auth-backend` version bump. Follow the rollback procedure in `auth-backend-redirect-bypass/tasks.md`.
2. Additionally, revert the `app-config.yaml` change to restore the previous state of `auth.experimentalClientIdMetadataDocuments.enabled` (typically removing the key, which restores the implicit default).
3. After rollback, both CVE-2026-32235 and CVE-2026-32236 are active again. Open a P1 incident. As a temporary mitigation, manually patch the running ConfigMap to set `enabled: false` via `kubectl edit configmap` in the `admins` namespace and restart the pod — this closes the SSRF vector without resolving the redirect-bypass CVE, buying time for the fix to be re-applied properly.
