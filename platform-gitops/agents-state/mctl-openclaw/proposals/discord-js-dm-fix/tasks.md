# Tasks: discord-js-dm-fix

## Verification

- [ ] 1. Verify discord.js version in openclaw v2026.5.3 upstream bundle — DoD: The upstream openclaw v2026.5.3 source tree or Docker image has been inspected with `npm ls discord.js`; the result is recorded in writing. If the result shows `discord.js@14.26.4` or higher, proceed to task 2 (Branch A). If the result shows a lower version, proceed to task 3 (Branch B).

## Branch A: fix is already in openclaw v2026.5.3

- [ ] 2. Close proposal as satisfied by upstream upgrade (depends on 1, Branch A) — DoD: A note is added to this proposal and to `upgrade-to-2026-5-3/tasks.md` confirming that discord.js >= v14.26.4 is included in v2026.5.3 and that Discord DM receipt in uncached DMChannels must be validated during the `labs` soak (append to task T10 in `upgrade-to-2026-5-3/tasks.md`). This proposal is marked complete. No further tasks required.

## Branch B: fix is NOT in openclaw v2026.5.3

- [ ] 3. Open PR to bump discord.js to v14.26.4 in `extensions/discord/package.json` (depends on 1, Branch B) — DoD: A PR exists in the openclaw fork that changes the `discord.js` version constraint in `extensions/discord/package.json` to `14.26.4`; the PR description references upstream discord.js PR #11495.
- [ ] 4. Regenerate `package-lock.json` for the Discord extension workspace (depends on 3) — DoD: `npm install` has been run in a clean environment in `extensions/discord/`; the updated `package-lock.json` reflects `discord.js@14.26.4` with the correct `resolved` URL (`https://registry.npmjs.org/discord.js/`) and sha512 `integrity` hash; no duplicate `discord.js` entries appear in `npm ls discord.js`.
- [ ] 5. Build patched Docker image (depends on 4) — DoD: A Docker image has been built from the updated source tree; the image tag is documented; `npm ls discord.js` inside the image confirms `discord.js@14.26.4`.

### labs rollout (Branch B)

- [ ] 6. Stop s3-sync canary for `labs` (depends on 5) — DoD: The Argo CronWorkflow for the `labs` s3-sync canary has `.spec.suspend: true` applied.
- [ ] 7. Open and merge gitops PR for `labs` with patched image (depends on 6) — DoD: The `labs` tenant `values.yaml` references the patched image tag; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 8. Confirm `labs` restore-state probe passes (depends on 7) — DoD: ArgoCD marks the `labs` rollout as `Healthy`/`Synced`; the `restore-state` readiness probe has passed within the configured timeout.
- [ ] 9. Restart s3-sync canary for `labs` with post-rollout delay (depends on 8) — DoD: The `labs` s3-sync canary CronWorkflow has `.spec.suspend: false` applied after the ADR-0002 delay; the first canary cycle completes successfully.
- [ ] 10. `labs` 24-hour soak (depends on 9) — DoD: s3-sync canary has had zero consecutive failures exceeding two cycles; pod RSS memory has not increased above the pre-upgrade baseline; Discord DM receipt test (T2) has passed; no Discord API `429` (rate limit) errors have been observed in logs; no restore-state probe failures observed.

### admins rollout (Branch B)

- [ ] 11. Stop s3-sync canary for `admins` (depends on 10) — DoD: The Argo CronWorkflow for the `admins` s3-sync canary has `.spec.suspend: true` applied.
- [ ] 12. Open and merge gitops PR for `admins` with patched image (depends on 11) — DoD: The `admins` tenant `values.yaml` references the patched image tag; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 13. Confirm `admins` restore-state probe passes (depends on 12) — DoD: ArgoCD marks the `admins` rollout as `Healthy`/`Synced`.
- [ ] 14. Restart s3-sync canary for `admins` (depends on 13) — DoD: The `admins` s3-sync canary CronWorkflow has `.spec.suspend: false` applied; first canary cycle completes successfully.
- [ ] 15. `admins` verification (depends on 14) — DoD: Discord DM receipt test (T2) passes; s3-sync canary is healthy; no restore-state probe failures observed for 4 hours post-rollout.

### ovk rollout (Branch B)

- [ ] 16. Stop s3-sync canary for `ovk` (depends on 15) — DoD: The Argo CronWorkflow for the `ovk` s3-sync canary has `.spec.suspend: true` applied.
- [ ] 17. Open and merge gitops PR for `ovk` with patched image (depends on 16) — DoD: The `ovk` tenant `values.yaml` references the patched image tag; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 18. Confirm `ovk` restore-state probe passes (depends on 17) — DoD: ArgoCD marks the `ovk` rollout as `Healthy`/`Synced`.
- [ ] 19. Restart s3-sync canary for `ovk` (depends on 18) — DoD: The `ovk` s3-sync canary CronWorkflow has `.spec.suspend: false` applied; first canary cycle completes successfully.
- [ ] 20. `ovk` post-rollout verification (depends on 19) — DoD: Discord DM receipt test (T2) passes; s3-sync canary is healthy; no restore-state probe failures observed for 4 hours post-rollout.

## Tests

- [ ] T1. discord.js version confirmation test — Run `npm ls discord.js` inside the running pod (or during image build) for each tenant after the patched image is deployed; confirm output shows `discord.js@14.26.4`. Fail criteria: any tenant shows a lower version.
- [ ] T2. DM receipt in uncached DMChannel test — Immediately after a pod restart (before the channel cache is warm), send a Discord DM to the bot from a test account that has not previously DM'd this bot instance; confirm the DM is received and the skill runtime processes it within 10 seconds. Fail criteria: DM is silently dropped or not processed within the timeout.
- [ ] T3. Cached channel regression test — Send a Discord DM from a test account that has already exchanged messages with the bot in the current session (channel is cached); confirm the DM is received and processed normally. Fail criteria: previously working DM delivery breaks after the upgrade.
- [ ] T4. Memory baseline test for `labs` — Record pod RSS before and after the discord.js bump in `labs`; confirm the delta is under 5 MB. Fail criteria: RSS increase exceeds 5 MB (which would be unexpected for a patch-level dependency bump).
- [ ] T5. Rate limit check — During the `labs` soak, inspect Discord API logs for any `429` HTTP responses in the `DMChannel` fetch code path. Fail criteria: `429` errors observed at a rate higher than zero per hour during steady-state operation.

## Rollback

**Branch A:** No deployment changes were made; there is nothing to roll back.

**Branch B:** If any step in the rollout fails (restore-state probe does not pass, s3-sync canary fails, DM receipt test T2 fails, or unexpected memory regression):

1. **Immediately revert the image tag** in the affected tenant's `values.yaml` to the pre-patch image (the previous discord.js v14.26.3 image) via a gitops PR; merge and allow ArgoCD to sync.
2. **Stop the s3-sync canary** for the affected tenant before the revert pod starts.
3. **Wait for the `restore-state` probe** to pass on the reverted pod.
4. **Restart the s3-sync canary** with the post-rollout delay.
5. **Do not promote** to the next tenant until the regression is identified and resolved.

Since this change involves only a discord.js patch-version bump (no S3 schema changes, no Kubernetes manifest changes beyond the image tag), reverting the image tag fully restores the prior state. No data migration or manual session reconstruction is required.

If Branch B is being executed concurrently with `upgrade-to-2026-5-3`, coordinate rollback decisions: rolling back the discord.js bump independently is safe and does not affect the openclaw version rollout.
