# Tasks: discordjs-v14264-update

- [ ] 1. Inspect openclaw 2026.4.29 upstream dependency tree for `discord.js` version — DoD: The openclaw upstream repository (`github.com/openclaw/openclaw`) at tag `2026.4.29` is inspected (via `package.json` and `package-lock.json` or `npm ls discord.js` on the published image). The installed `discord.js` version is recorded. If `>= 14.26.4`, proceed to task 2 (Branch A). If `< 14.26.4`, proceed to task 3 (Branch B).

- [ ] 2. [Branch A] Close with verification note — DoD: If task 1 confirms `discord.js >= 14.26.4` is bundled in 2026.4.29, add a comment to `proposals/upgrade-to-2026-4-29/tasks.md` (verification section) noting that discord.js v14.26.4 DM fix is included. Mark this proposal `status: completed-via-upgrade`. No further tasks required. (Depends on 1 — Branch A outcome.)

- [ ] 3. [Branch B] Open patch PR: bump `discord.js` to `14.26.4` in the openclaw fork — DoD: A PR is open in the mctl-openclaw fork targeting `extensions/discord/package.json` (or equivalent), changing the `discord.js` dependency from the current pinned version to `14.26.4`. No other files are changed. PR description explains the DM reception regression and references this proposal slug. (Depends on 1 — Branch B outcome.)

- [ ] 4. [Branch B] Regenerate lock file and verify — DoD: After the version bump, `npm install` is run in the Discord extension workspace. The updated `package-lock.json` contains the correct SHA-512 integrity hash for `discord.js@14.26.4`. No other dependency versions change as a result. (Depends on 3.)

- [ ] 5. [Branch B] Build and deploy patched image to `labs` — DoD: A new Docker image is built from the patched source and deployed to the `labs` tenant. The `labs` Discord channel confirms DM reception (test DM sent immediately after pod restart and received successfully). Pod RSS on `labs` is within 50 MB of the baseline established in the `upgrade-to-2026-4-29` memory check. (Depends on 4.)

- [ ] 6. [Branch B] 24-hour soak on `labs` — DoD: For 24 hours following task 5, no Discord channel errors, no s3-sync canary failures, and no pod restarts on `labs`. DM reception in uncached channels is confirmed via at least one restart-triggered test during the soak window. (Depends on 5.)

- [ ] 7. [Branch B] Promote patch to `admins` and `ovk` — DoD: The patched image is deployed to `admins` and then `ovk` per ADR-0001 promotion order, following the standard s3-sync canary stop/start procedure from ADR-0002. Discord channel connectivity confirmed on each tenant after deployment. (Depends on 6.)

- [ ] 8. [Branch B] Mark proposal complete — DoD: `context/current-version.md` is updated to reflect the patched image tag if it differs from the main 2026.4.29 tag. This proposal is marked `status: completed`. (Depends on 7.)

## Tests

- [ ] T1. DM cold-start test (applies regardless of branch): After the `labs` pod restarts (either via upgrade or Branch B deployment), send a DM to the Discord bot within 10 seconds of the bot reporting `READY`. Confirm the DM is received and a response is sent. Repeat three times to account for timing variability.
- [ ] T2. discord.js version assertion: Run `npm ls discord.js` inside the deployed container and confirm the output shows `discord.js@14.26.4` or higher. Fail if any older version is listed.
- [ ] T3. Existing Discord functionality regression check: Send test messages via each Discord channel feature in use (mentions, slash commands, file attachments) after the deployment; confirm no regressions.
- [ ] T4. Memory check on `labs`: At 1 hour and 6 hours post-deployment, record pod RSS for `labs`. Confirm no increase greater than 50 MB compared to the pre-deployment baseline (critical given `labs` is near its memory limit).

## Rollback

**Branch A (verification only):** No rollback required — no code was changed.

**Branch B (patch applied):**
1. Revert the gitops PR bumping the `discord.js` version in the openclaw fork.
2. Rebuild the Docker image from the reverted source and deploy the reverted image to the affected tenant, following the standard canary stop/restart procedure from ADR-0002.
3. The S3 state is not affected by this change; the restore-state probe will succeed on the reverted pod.
4. DMs will again be silently dropped in the cold-start window on the reverted tenant; document this as a known open issue until the next upgrade opportunity.
