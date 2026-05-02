# Tasks: discord-supply-chain-typosquat

- [ ] 1. Audit current `node_modules` for `discord.js-user` on all three tenants — DoD: Run `npm ls discord.js-user 2>/dev/null` (or equivalent) inside the running container on `labs`, `admins`, and `ovk`. Confirm `discord.js-user` is NOT present. If found, immediately trigger Discord bot token rotation for the affected tenant and open an incident before proceeding.

- [ ] 2. Add `discord.js-user` deny-list entry to workspace `.npmrc` — DoD: The workspace-root `.npmrc` (and any tenant-specific overlay `.npmrc` if present) contains the following two lines: `@discord.js-user:registry=null` and `discord.js-user:registry=null`. The change is committed to the mctl-openclaw repo and validated against the npm version used in CI.

- [ ] 3. Pin `discord.js` to an exact verified version in the Discord extension `package.json` — DoD: `extensions/discord/package.json` (or the equivalent openclaw workspace path) specifies `"discord.js": "14.26.4"` (exact pin) or `"discord.js": "^14.26.4"` (patch-range pin, acceptable if CI integrity check from task 4 is in place). The change is committed.

- [ ] 4. Add CI integrity check step — DoD: The CI pipeline for mctl-openclaw includes a step that runs after `npm ci` or `npm install`: `grep -r '"discord.js-user"' node_modules/.package-lock.json && exit 1 || true`. The step is configured to fail the build (non-zero exit) if `discord.js-user` is found. The check is verified on both a clean install and a deliberately corrupted lock file (test-only) to confirm it catches the malicious package.

- [ ] 5. Regenerate `package-lock.json` and verify integrity hashes — DoD: After tasks 2 and 3, `npm install` is run in the Discord extension workspace to regenerate the lock file. The resulting `package-lock.json` contains a SHA-512 `integrity` field for `discord.js@14.26.4` (or the pinned version). The lock file is committed with the updated hashes.

- [ ] 6. Open gitops PR with deny-list and lock-file changes — DoD: A PR is open in the mctl-openclaw repo containing the `.npmrc` deny-list (task 2), the version pin (task 3), the CI check (task 4), and the regenerated lock file (task 5). PR description references this proposal slug and GHSA-69r6-7h4f-9p7q. PR passes CI. (Depends on 2, 3, 4, 5.)

- [ ] 7. Merge PR and verify deployment on `labs` — DoD: PR from task 6 is merged. The `labs` tenant is rebuilt and redeployed with the updated lock file. `npm ci` completes successfully on the new build with the deny-list active. Discord channel connectivity on `labs` is confirmed (test message sent and received). (Depends on 6.)

- [ ] 8. Promote to `admins` and `ovk` — DoD: The same configuration (`.npmrc`, pin, CI check, lock file) is applied to `admins` and then `ovk` per ADR-0001 promotion order. Discord channel connectivity is confirmed on each after deployment. (Depends on 7.)

- [ ] 9. Document lockdown in supply-chain runbook — DoD: The mctl-openclaw supply-chain security runbook (or equivalent ops note) is updated to list `discord.js-user` alongside `lotusbail` (from `baileys-registry-lockdown`) as a permanently deny-listed package. The token-rotation procedure for Discord bot tokens is documented as the incident response action if a future audit finds the package present. (Depends on 8.)

## Tests

- [ ] T1. Deny-list enforcement: In a test environment (not production), attempt `npm install discord.js-user` with the updated `.npmrc` and confirm npm exits with a non-zero status and does not install the package.
- [ ] T2. CI gate: Manually inject `"discord.js-user": "1.0.0"` into a test copy of `package-lock.json` and run the CI integrity check step; confirm the build fails with the expected error message.
- [ ] T3. Legitimate install unaffected: Run `npm ci` in the Discord extension workspace with the deny-list active and confirm `discord.js@14.26.4` installs successfully (deny-list does not block the legitimate package).
- [ ] T4. Discord channel smoke test post-deploy: Send a test message via the Discord channel on `labs`, `admins`, and `ovk` after each deployment; confirm delivery within normal latency.

## Rollback

The deny-list and CI check are build-time changes only; they do not affect the running pod. If the CI check produces a false positive that blocks legitimate builds:
1. Remove or comment out the deny-list entry in `.npmrc` to unblock the build.
2. Investigate whether a transitive dependency legitimately resolves to a package matching the deny-listed name.
3. If the false positive is confirmed, narrow the deny-list pattern and re-add it.

There is no runtime rollback path for this proposal — the deployed Docker image is identical before and after the change. Discord channel functionality is not affected by the deny-list.

If task 1 discovers `discord.js-user` is already installed on a running tenant, treat it as a security incident: immediately rotate the Discord bot token for that tenant, redeploy with a clean image, and follow the incident response procedure in the ops runbook.
