# Tasks: integration-credential-leak-fix

- [ ] 1. Verify current `@backstage/integration` version and confirm
       vulnerability — DoD: version string logged and cross-checked against
       CVE-2026-29185 advisory; a local proof-of-concept encoded-traversal
       URL test demonstrates credential misdirection on the current build.

- [ ] 2. Coordinate with `techdocs-path-traversal-fix` — confirm both CVEs
       are addressed by the same Backstage v1.50.3 bump (depends on 1)
       — DoD: single `yarn backstage-cli versions:bump --release 1.50.3`
       execution covers both `@backstage/integration` >=1.20.1 and
       `@backstage/plugin-techdocs-node` >=1.13.11; confirmed with diff.

- [ ] 3. Build and smoke-test the Docker image locally (depends on 2) — DoD:
       `docker build` succeeds; `@backstage/integration` version in the
       image is >=1.20.1; the local PoC encoded-traversal URL test from
       task 1 now returns an error and does not attach credentials.

- [ ] 4. Run scaffolder e2e tests and manually review the three most-used
       scaffolder templates in staging (depends on 3) — DoD: all scaffolder
       tests pass; each template can commit to its target repository without
       errors.

- [ ] 5. Run full Playwright e2e suite in staging (depends on 4) — DoD: all
       existing tests pass with zero regressions; GitHub PR/issue widgets
       load correctly.

- [ ] 6. Update image tag in `mctl-gitops` and open PR (depends on 5) — DoD:
       PR opened (may be the same PR as `techdocs-path-traversal-fix` task 5
       if both bumps are combined); CI passes; approved by at least one
       reviewer; commit message references CVE-2026-29185.

- [ ] 7. Merge PR and verify ArgoCD sync to `admins` namespace (depends on 6)
       — DoD: ArgoCD reports `Synced / Healthy`; new pod running the updated
       image; no error spike in logs or Prometheus alerts within 15 minutes
       post-deploy.

- [ ] 8. Notify security team and close vulnerability tracker finding (depends
       on 7) — DoD: CVE-2026-29185 marked remediated; commit SHA recorded;
       security team informed of option to rotate GitHub PAT as a
       precautionary measure.

## Tests

- [ ] T1. Encoded path-traversal URL test: submit a crafted URL containing
       `%2F..%2F` sequences to the integration resolver; assert that the
       resolver returns an error and that no `Authorization` header is attached
       to any outbound request to a non-configured host.

- [ ] T2. Legitimate GitHub URL test: resolve `https://github.com/<org>/<repo>`
       via the integration library; assert that the correct credential is
       attached and the request succeeds.

- [ ] T3. Scaffolder commit test: run the three most-used scaffolder templates
       in staging end-to-end; assert each template completes and the expected
       commit appears in the target repository.

- [ ] T4. GitHub widget test: open the catalog page for a component that has
       GitHub PR/issue widgets; assert widgets load without authentication
       errors.

- [ ] T5. Playwright e2e full run in staging: all existing test cases pass with
       zero regressions.

## Rollback
1. Revert the image-tag commit in `mctl-gitops` and push under the
   emergency-commit policy.
2. ArgoCD detects the revert and re-syncs the previous image within ~2 minutes.
3. Confirm the previous pod is `Running`.
4. If the GitHub PAT was rotated during the upgrade window, the old token is
   no longer valid; the security team must issue a new token and update the
   ExternalSecret in Vault before reverting, or accept a brief scaffolder
   outage.
5. Re-open the CVE finding and schedule a follow-up investigation.
