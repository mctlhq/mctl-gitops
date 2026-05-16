# Tasks: techdocs-path-traversal-fix-v2

- [ ] 1. Confirm the current installed version of `@backstage/plugin-techdocs-node` — DoD: `yarn why @backstage/plugin-techdocs-node` output is documented in the PR description, showing the current version and its resolution path.
- [ ] 2. Audit existing `docs/` directories in catalog-registered repositories for out-of-tree symlinks (depends on 1) — DoD: a list of any repositories containing symlinks that resolve outside their `docs/` root is produced; each is either remediated or accepted as in-scope for monitoring.
- [ ] 3. Bump `@backstage/plugin-techdocs-node` to the patched version in `package.json` (depends on 1) — DoD: `package.json` references version 1.14.1 (or 1.13.11 on the 1.13.x line); `yarn install` completes without errors.
- [ ] 4. Run `yarn dedupe` and review `yarn.lock` diff (depends on 3) — DoD: `yarn.lock` diff is scoped to `@backstage/plugin-techdocs-node` and its direct dependency tree; no unrelated packages are silently upgraded.
- [ ] 5. Run `yarn audit --level moderate` and confirm CVE-2026-25152 is resolved (depends on 4) — DoD: `yarn audit` exits 0 with no findings attributable to CVE-2026-25152.
- [ ] 6. Build Docker image locally and verify startup (depends on 5) — DoD: `docker build` succeeds; the container starts and `GET /healthcheck` returns HTTP 200 within 60 s.
- [ ] 7. Deploy to staging and verify TechDocs renders correctly (depends on 6) — DoD: at least two existing catalog entities with TechDocs render their documentation pages without errors; no new errors appear in the backend logs related to the TechDocs generator.
- [ ] 8. Test symlink rejection in staging (depends on 7) — DoD: a test `docs/` directory containing a symlink pointing to `../../etc/passwd` is processed; the TechDocs build for that entity fails with an explicit error log entry; the `/etc/passwd` content does not appear in any generated HTML.
- [ ] 9. Push the patched image to the registry and update the image tag in mctl-gitops Helm values for `admins` (depends on 7, 8) — DoD: PR to mctl-gitops is merged; ArgoCD reports `mctl-portal` as `Synced` and `Healthy`.
- [ ] 10. Confirm production TechDocs health post-deployment (depends on 9) — DoD: a spot-check of three catalog entities with TechDocs confirms documentation renders correctly; no symlink-related errors appear in backend logs within 10 minutes of rollout completing.

## Tests

- [ ] T1. `yarn audit --level moderate` — exits 0, no findings for CVE-2026-25152.
- [ ] T2. Health endpoint — `GET /healthcheck` returns HTTP 200 within 60 s of container start.
- [ ] T3. TechDocs render test — navigate to a catalog entity with TechDocs in staging; the documentation page loads without errors.
- [ ] T4. Symlink rejection test — provide a `docs/` directory with an out-of-tree symlink; the TechDocs generator must log an error for that entity and not embed the linked file content in any HTML output.
- [ ] T5. `yarn.lock` diff review — the diff touches only `@backstage/plugin-techdocs-node` and its declared dependencies; no other packages are inadvertently upgraded.
- [ ] T6. ArgoCD health gate — `mctl-portal` in `admins` reports `Healthy` after sync; no unexpected pod restarts.

## Rollback
1. Revert the image tag in the mctl-gitops Helm values to the previous tag.
2. Commit and push to mctl-gitops; ArgoCD re-syncs and restores the previous pod.
3. The previous image (with the unpatched `@backstage/plugin-techdocs-node`) will be running again — CVE-2026-25152 will be re-open. Escalate to the security team and consider temporarily restricting access to TechDocs entities whose `docs/` directories contain untrusted content.
4. Preserve the failed image tag and logs for post-mortem analysis.
