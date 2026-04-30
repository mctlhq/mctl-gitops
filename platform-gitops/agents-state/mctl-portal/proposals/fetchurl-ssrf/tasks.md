# Tasks: fetchurl-ssrf

- [ ] 1. Identify the exact Backstage package(s) containing the patched `FetchUrlReader` and the minimum patched version for the deployed Backstage release line — DoD: package name(s) and patched version(s) recorded in the PR description; CVE advisory cross-referenced to confirm.
- [ ] 2. Bump the identified package(s) to the patched version in `packages/backend/package.json` and the root resolutions block (depends on 1) — DoD: `package.json` diff shows only the target package(s) changed; `yarn install --immutable` succeeds in CI.
- [ ] 3. Run `yarn dedupe` and commit the updated `yarn.lock` (depends on 2) — DoD: lockfile committed with no unexpected version changes; `yarn install --immutable` passes.
- [ ] 4. Audit `app-config.yaml` and `app-config.production.yaml` for all `backend.reading.allow` entries (depends on 1, can be done in parallel with 2) — DoD: a table listing each entry, its purpose, the plugin that requires it, and whether it is retained or removed; reviewed and approved by a platform engineer.
- [ ] 5. Apply the narrowed `backend.reading.allow` configuration from the audit (depends on 4) — DoD: configuration change committed with one comment per entry explaining its purpose; no previously-required entry silently removed.
- [ ] 6. Build backend image with upgraded package and updated configuration (depends on 3, 5) — DoD: image pushed to registry with tag `fetchurl-ssrf-<sha>`; `docker sbom` confirms patched package version.
- [ ] 7. Deploy to `admins` tenant via ArgoCD sync (depends on 6) — DoD: ArgoCD shows `Synced / Healthy`; `/healthcheck` returns 200; catalog refresh completes without new fetch errors in backend logs within 10 minutes of deployment.
- [ ] 8. Update `context/current-version.md` to record the upgraded package version and date — DoD: file reflects the patched package version and `2026-04-30`.

## Tests

- [ ] T1. Package version assertion: run `yarn why <patched-package>` in CI and assert the resolved version is equal to or greater than the patched minimum.
- [ ] T2. SSRF regression test: stand up a local HTTP server that responds with a 302 redirect to `http://169.254.169.254/latest/meta-data/` (or equivalent internal address not in the allowlist); call `FetchUrlReader.readUrl` with the initial URL (which is in the allowlist); assert the call fails with an allowlist rejection error, not a successful fetch of the redirect target.
- [ ] T3. Legitimate redirect test: configure a test URL in the allowlist that redirects to another URL also in the allowlist; assert `FetchUrlReader.readUrl` successfully returns the content from the redirect target.
- [ ] T4. Catalog integration test: trigger a catalog refresh in a staging environment with the patched backend; assert all previously-registered entities are still discovered without errors, and backend logs contain no new `FetchUrlReader` failures.
- [ ] T5. Configuration completeness check: run a grep over all plugin source files in `packages/backend` for `readUrl` and `FetchUrlReader` usages; assert every origin domain used in those calls is covered by an entry in the audited `backend.reading.allow` list.
- [ ] T6. Full backend unit test suite: `yarn test` across all workspace packages; zero failures.
- [ ] T7. Post-deploy smoke test: navigate to the Catalog in the portal, trigger a manual entity refresh on a GitHub-hosted `catalog-info.yaml`, and assert it imports successfully.

## Rollback
1. Revert the package bump and configuration change commits in git; merge the revert PR.
2. Trigger an ArgoCD sync to restore the previous image tag and configuration.
3. Verify `/healthcheck` returns 200 and catalog refresh completes successfully.
4. If the rollback is due to a legitimate redirect being blocked, add the required destination to `backend.reading.allow` with justification, then re-attempt the upgrade in a new branch.
5. If the rollback is due to a package regression, open an issue against the upstream Backstage repository and monitor for a follow-up patch release.
