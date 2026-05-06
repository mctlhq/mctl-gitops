# Tasks: baileys-supply-chain-audit

- [ ] 1. Audit the current lockfile on all tenants — DoD: `package-lock.json` (and `yarn.lock` if present) is inspected for each tenant overlay; confirmed that `@whiskeysockets/baileys` at version `2026.3.14` is the only Baileys-adjacent entry; no entry matching `lotusbail`, `lotus-bail`, or similar aliases is present; findings documented in a short audit note committed alongside the lockfile.

- [ ] 2. Pin `@whiskeysockets/baileys` to exact version and integrity hash (depends on 1) — DoD: `package.json` specifies `"@whiskeysockets/baileys": "2026.3.14"` (no `^` or `~`); `package-lock.json` is regenerated with `npm ci` and the `integrity` field is populated and non-empty; the committed lockfile passes a manual diff review confirming no unexpected new or removed packages appeared during the re-lock.

- [ ] 3. Create `config/expected-integrity.json` (depends on 2) — DoD: file exists at `config/expected-integrity.json` in the repository root; it contains the SHA-512 integrity hash for `@whiskeysockets/baileys@2026.3.14` exactly as it appears in the lockfile; format is `{ "@whiskeysockets/baileys": "<sha512-...>" }`; the file is reviewed and approved in the same PR as task 2.

- [ ] 4. Write `scripts/audit-baileys-lockfile.sh` (depends on 3) — DoD: script is executable and checked into the repository; it reads `package-lock.json`, asserts the resolved Baileys package name equals `@whiskeysockets/baileys`, asserts no alias entry matches the known-bad pattern, and compares the integrity hash against `config/expected-integrity.json`; script exits 0 on success and non-zero with a descriptive message on any failure; manual smoke-test run on the current lockfile exits 0.

- [ ] 5. Add `supply-chain-guard` CI job (depends on 4) — DoD: a new required CI job is defined in the pipeline configuration; it runs `npm ci --ignore-scripts` followed by `scripts/audit-baileys-lockfile.sh` and `npx lockfile-lint` on every push to `main`, every pull request targeting `main`, and on a nightly schedule; the job is marked as a required status check blocking merges; pipeline run in a feature branch confirms the job passes on the current lockfile.

- [ ] 6. Write revocation runbook `ops/runbooks/baileys-compromise-revocation.md` (no dependency) — DoD: file exists at the specified path; it covers all six steps defined in `design.md` (identify affected tenant, revoke linked devices, restart pod, re-pair via QR, rotate S3 credentials, file incident); runbook is reviewed and approved by at least one ops engineer and one security engineer; it is linked from the main `README.md`.

- [ ] 7. Update `CONTRIBUTING.md` with Baileys pinning policy (depends on 2) — DoD: a new section "Baileys Dependency Policy" is added explaining that the package must remain exactly pinned, that any version bump requires verifying the upstream git tag signature, updating `config/expected-integrity.json`, and following the `labs` → `admins` → `ovk` rollout order per ADR-0001.

- [ ] 8. Validate lockfile change in `labs` (depends on 2, 5) — DoD: the updated lockfile is deployed to the `labs` tenant; the WhatsApp channel connects successfully and processes at least one test message end-to-end; no memory-limit alerts are triggered; `supply-chain-guard` CI job passes.

- [ ] 9. Promote to `admins` (depends on 8) — DoD: the updated lockfile is deployed to the `admins` tenant; WhatsApp channel is verified operational; no incidents opened within 30 minutes of rollout.

- [ ] 10. Promote to `ovk` (depends on 9) — DoD: the updated lockfile is deployed to the `ovk` tenant; WhatsApp channel is verified operational; no incidents opened within 30 minutes of rollout; post-deployment note added to the ADR-0001 changelog.

## Tests

- [ ] T1. CI fails when `lotusbail` is in the lockfile — inject a synthetic lockfile entry for `lotusbail` in a test branch; confirm the `supply-chain-guard` job exits non-zero and reports the offending package name in the job log.

- [ ] T2. CI fails when `@whiskeysockets/baileys` is unpinned — change the version specifier in `package.json` to `^2026.3.14` and commit to a test branch without regenerating the lockfile; confirm the `supply-chain-guard` job rejects the open range.

- [ ] T3. CI fails when integrity hash is tampered — modify the `integrity` field for `@whiskeysockets/baileys` in `package-lock.json` on a test branch; confirm `scripts/audit-baileys-lockfile.sh` exits non-zero and prints a message referencing `config/expected-integrity.json`.

- [ ] T4. CI passes on clean lockfile — run the full `supply-chain-guard` job against the production lockfile after task 2 is complete; confirm exit 0 and a passing status check in the PR.

- [ ] T5. Revocation runbook dry-run — ops engineer and security engineer walk through the runbook against the `labs` tenant using a test WhatsApp number; confirm each step can be completed within one business hour and that the runbook contains no gaps or ambiguous instructions.

## Rollback

If a lockfile change introduced in tasks 2 or 8–10 breaks the WhatsApp channel (connection failures, auth errors, or message processing halting):

1. Revert the `package-lock.json` to the previous committed version via `git revert` or by restoring the file from the previous release tag.
2. Rebuild and redeploy the affected tenant's Docker image using the reverted lockfile.
3. If the WhatsApp session is in an inconsistent state after the rollback, execute the revocation runbook (`ops/runbooks/baileys-compromise-revocation.md`) to force a clean QR re-pairing.
4. Open an incident ticket describing the failure mode so that the root cause can be identified before re-attempting the rollout.

Note: the CI guard itself (`supply-chain-guard` job) carries no rollback risk — disabling it is possible by removing the required-check designation in repository settings, but this must be treated as a temporary emergency measure and re-enabled within one business day.
