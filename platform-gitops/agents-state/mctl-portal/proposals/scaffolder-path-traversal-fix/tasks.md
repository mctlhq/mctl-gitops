# Tasks: scaffolder-path-traversal-fix

- [ ] 1. Identify current installed versions of the three affected packages — DoD: a table in the PR description lists current vs. target version for `@backstage/backend-defaults`, `@backstage/plugin-scaffolder-backend`, and `@backstage/plugin-scaffolder-node`, confirmed by `yarn why <package>`.
- [ ] 2. Bump package versions to fixed minimums in `package.json` (depends on 1) — DoD: `package.json` entries for all three packages reference the patched version; `yarn install` completes without errors.
- [ ] 3. Run `yarn dedupe` and review `yarn.lock` diff (depends on 2) — DoD: `yarn.lock` diff is scoped to the three target packages and their direct dependency tree; no unrelated packages are silently upgraded.
- [ ] 4. Run `yarn audit` and confirm CVE-2026-24046 is resolved (depends on 3) — DoD: `yarn audit --level high` exits 0 with no findings attributable to CVE-2026-24046 in any of the three patched packages.
- [ ] 5. Build Docker image locally and verify startup (depends on 4) — DoD: `docker build` succeeds; container starts and the Backstage backend health endpoint (`/healthcheck`) returns 200 within 60 s.
- [ ] 6. Deploy to staging environment and run Playwright e2e suite (depends on 5) — DoD: all existing Playwright tests pass; Scaffolder smoke test (create a minimal service via a test template) completes without error.
- [ ] 7. Push patched Docker image to registry and update image tag in mctl-gitops Helm values for `admins` (depends on 6) — DoD: PR to mctl-gitops is merged; ArgoCD reports the `mctl-portal` application as `Synced` and `Healthy`.
- [ ] 8. Verify in production that Scaffolder is functional post-deployment (depends on 7) — DoD: a manual smoke test (navigate to Scaffolder in the portal, verify templates load, verify a dry-run or low-risk template execution succeeds) passes; no errors in backend logs related to the patched packages.

## Tests

- [ ] T1. `yarn audit --level high` — exits 0, no High/Critical findings for the three CVE-2026-24046 packages.
- [ ] T2. Backstage backend health check — `GET /healthcheck` returns HTTP 200 after pod restart.
- [ ] T3. Playwright Scaffolder smoke test — navigate to `/create`, select a template, complete all required fields, submit; the task completes successfully or fails with a known non-security error (e.g., mctl-gitops auth in staging).
- [ ] T4. Path traversal regression test — if a test fixture exists or can be added: attempt to pass a tar archive containing a symlink pointing to `../../etc/passwd` through a Scaffolder template action; the backend must return a task failure without exposing file contents.
- [ ] T5. ArgoCD health gate — `mctl-portal` application in `admins` reports `Healthy` after sync; no pod restarts beyond the planned rollout.

## Rollback
1. Revert the image tag change in the mctl-gitops Helm values to the previous tag.
2. Commit and push to mctl-gitops; ArgoCD will re-sync and roll back the pod.
3. The previous image (with the unpatched packages) will be restored; the CVE will be re-open — escalate to security team and do not re-expose the Scaffolder to untrusted template authors until a new fix is prepared.
4. Preserve logs and the failing image tag for post-mortem analysis.
