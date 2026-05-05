# Tasks: baileys-lockfile-audit

Note: This audit has no tenant promotion order (it is read-only inspection) but it must be completed — and any findings resolved — before other rollouts (`upgrade-to-2026-5-3`, etc.) proceed.

- [ ] 1. Identify the lockfile version embedded in the currently running Docker images for all three tenants — DoD: The `package-lock.json` (or equivalent) from the Docker image layer for each of `labs`, `admins`, and `ovk` has been extracted and confirmed to be identical to (or newer than) the lockfile in the source repository. Method: `docker cp` or image layer inspection. Any discrepancy between the repo lockfile and the image lockfile is documented.
- [ ] 2. Scan all three lockfiles for Baileys-related package entries (depends on 1) — DoD: A complete list of every lockfile entry whose name matches `baileys`, `lotusbail`, or a Baileys-compatible variant has been produced for each tenant. The list includes: package name, declared version, `resolved` URL, and `integrity` hash. Transitive (nested) dependencies are included in the scan, not just top-level entries.
- [ ] 3. Verify resolved URLs against official registry (depends on 2) — DoD: For each entry identified in task 2, the `resolved` URL has been confirmed to start with `https://registry.npmjs.org/@whiskeysockets/baileys/`. Any entry with a different URL is flagged as a finding requiring immediate escalation.
- [ ] 4. Verify integrity hashes against official registry (depends on 2) — DoD: For each entry identified in task 2, the `integrity` sha512 hash has been fetched from `https://registry.npmjs.org/@whiskeysockets/baileys/<version>` and compared to the value in the lockfile. A match is confirmed in writing. Any mismatch is flagged as a finding requiring immediate escalation.
- [ ] 5. Produce and commit the audit record (depends on 3, 4) — DoD: A written audit record exists documenting: date, operator, tenants audited, package name, version, resolved URL, and integrity hash for each Baileys-related entry, and a per-tenant pass/fail result. The record is attached to the relevant task ticket or stored in a location accessible to the security reviewer.
- [ ] 6. Confirm `baileys-registry-lockdown` controls are in place or schedule them (depends on 5) — DoD: Either (a) the `.npmrc` scope pin for `@whiskeysockets` and `npm ci` enforcement are already active and confirmed in the CI pipeline; or (b) a follow-on task to deploy `baileys-registry-lockdown` has been scheduled and its urgency noted in the audit record.
- [ ] 7. Lift rollout hold for other proposals (depends on 5, 6) — DoD: If all tenants passed the audit (no `lotusbail`, no URL mismatch, no hash mismatch), the hold on `upgrade-to-2026-5-3` and other queued rollouts is explicitly lifted and documented. If any finding was raised, this task remains blocked until the incident is resolved.

## Escalation path (if `lotusbail` or a mismatch is found)

- [ ] E1. Raise P0 security incident — DoD: Incident is opened in the incident management system with severity P0; on-call security contact is paged.
- [ ] E2. Halt all active and planned rollouts across all three tenants — DoD: Any open gitops PRs are closed or put on hold; no ArgoCD syncs are triggered until the incident is resolved.
- [ ] E3. Rotate all WhatsApp auth tokens in S3 for all tenants — DoD: All S3-stored WhatsApp session tokens have been invalidated and regenerated; all three tenants have re-authenticated successfully.
- [ ] E4. Remove compromised dependency and regenerate lockfile in a clean environment — DoD: `lotusbail` (or the mismatched package) is removed from `package.json`; `@whiskeysockets/baileys` is reinstalled using `npm install` against `https://registry.npmjs.org/` exclusively; the regenerated `package-lock.json` passes audit tasks 2-4.
- [ ] E5. Rebuild and redeploy all tenant images from the clean lockfile — DoD: New Docker images built from the clean lockfile have been deployed to all three tenants in labs → admins → ovk order; all tenants pass the restore-state probe.

## Tests

- [ ] T1. Name scan completeness test — Confirm the scan in task 2 covers all `packages` entries in the lockfile (including nested), not just the top-level `dependencies` block. Verify by running the scan script against a synthetic lockfile that contains a `lotusbail` entry at nesting depth 2 and confirming it is detected.
- [ ] T2. URL format verification test — For the confirmed clean entry, confirm the `resolved` URL is parseable as `https://registry.npmjs.org/@whiskeysockets/baileys/-/<filename>.tgz` (standard npm tarball URL format). Fail criteria: URL is a GitHub URL, a Git URL, or a private registry URL.
- [ ] T3. Hash match test — Confirm the sha512 `integrity` value in the lockfile matches the value returned by a fresh `curl` to the official registry for the same package version. Fail criteria: values differ by any character.
- [ ] T4. Negative test — Run the scan against a synthetic lockfile containing `lotusbail` as a top-level entry; confirm the scan reports a finding and that the escalation criteria in task 3 would trigger. This is a dry-run validation of the detection logic.

## Rollback

This proposal makes no changes to running systems. There is nothing to roll back.

If the escalation path (tasks E1–E5) has been partially executed (e.g., tokens rotated but clean image not yet deployed), the rollback posture is:
- Tenants remain on their current image (no new image has been deployed).
- Rotated tokens ensure any exfiltrated credentials are invalidated.
- Re-deployment from the clean lockfile (task E5) is the forward path, not a rollback.
