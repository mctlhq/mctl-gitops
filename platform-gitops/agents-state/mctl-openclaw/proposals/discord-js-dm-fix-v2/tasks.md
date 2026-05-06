# Tasks: discord-js-dm-fix-v2

- [ ] 1. Identify current discord.js version — Run `npm ls discord.js` in the
  repository root and inside a running pod for each tenant; record the exact
  installed version in a comment on this task. — DoD: The current version is
  confirmed in writing and differs from v14.26.4 (if it is already v14.26.4 or
  higher, close this proposal as already satisfied and stop).

- [ ] 2. Bump discord.js to v14.26.4 in `extensions/discord/package.json`
  (depends on 1) — DoD: The `discord.js` entry in `extensions/discord/package.json`
  reads `"discord.js": "14.26.4"` (exact pin); the change is committed on a
  dedicated branch referencing this proposal and upstream PR #11495.

- [ ] 3. Regenerate the lockfile (depends on 2) — DoD: `npm install` has been
  run in a clean environment inside `extensions/discord/`; `package-lock.json`
  reflects `discord.js@14.26.4` with a valid `resolved` URL and `integrity`
  hash from the public npm registry; `npm ls discord.js` shows exactly one
  entry at v14.26.4 (no duplicate versions).

- [ ] 4. Build and verify the patched Docker image (depends on 3) — DoD: The
  Docker image builds successfully; `npm ls discord.js` run inside the image
  confirms `discord.js@14.26.4`; the image tag is documented.

- [ ] 5. Deploy to `labs` and run validation tests (depends on 4) — DoD: The
  `labs` tenant `values.yaml` references the patched image tag; ArgoCD reports
  `Healthy`/`Synced`; the restore-state readiness probe passes within its
  configured timeout; tests T1, T2, T3, and T4 all pass (see Tests section
  below); no restore-state probe failures and no s3-sync canary failures are
  observed during a 24-hour soak.

- [ ] 6. Deploy to `admins` (depends on 5) — DoD: The `admins` tenant
  `values.yaml` references the patched image tag; ArgoCD reports
  `Healthy`/`Synced`; the restore-state probe passes; test T1 (DM in uncached
  channel) passes; s3-sync canary remains healthy for 4 hours post-rollout.

- [ ] 7. Deploy to `ovk` (depends on 6) — DoD: The `ovk` tenant `values.yaml`
  references the patched image tag; ArgoCD reports `Healthy`/`Synced`; the
  restore-state probe passes; test T1 passes; s3-sync canary remains healthy
  for 4 hours post-rollout; `ovk` SLA monitoring shows no DM-drop events.

## Tests

- [ ] T1. DM received in uncached channel — Immediately after a pod restart
  (before the channel cache is warm), send a Discord DM to the bot from a test
  account that has not previously messaged this bot instance in the current
  session. Confirm the DM is received and the skill runtime processes it within
  10 seconds. Fail criteria: the DM is silently dropped or not processed within
  the timeout.

- [ ] T2. Existing guild-message handling unaffected — Send a standard guild
  (server) message to the bot from a test account in a known channel. Confirm
  the message is received and handled with the same latency as before the
  upgrade. Fail criteria: previously working guild-message delivery breaks after
  the upgrade.

- [ ] T3. Bot restarts without regression — Restart the bot pod and immediately
  send both a DM and a guild message. Confirm both are received and processed
  correctly. Fail criteria: either message type is dropped or produces an
  unhandled error after restart.

- [ ] T4. Memory baseline for `labs` — Record pod RSS (from Kubernetes metrics)
  in `labs` immediately before and 1 hour after the patched image is deployed.
  Confirm the delta is under 5 MB. Fail criteria: RSS increase exceeds 5 MB,
  which would be unexpected for a patch-level bump and would require
  investigation before promoting to `admins`.

## Rollback

If any step in the rollout fails — restore-state probe does not pass, s3-sync
canary fails, a DM-receipt test fails, or an unexpected memory regression is
observed:

1. Immediately revert the affected tenant's `values.yaml` to the pre-patch
   image tag via a gitops PR; merge and allow ArgoCD to sync.
2. Stop the s3-sync canary for the affected tenant before the revert pod
   starts (to avoid a spurious canary failure mid-restart).
3. Wait for the restore-state readiness probe to pass on the reverted pod.
4. Restart the s3-sync canary with the standard post-rollout delay.
5. Do not promote to the next tenant until the regression is identified and
   resolved.

Because this change involves only a discord.js patch-version bump — no S3
schema changes, no Kubernetes manifest changes beyond the image tag, and no
skill YAML changes — reverting the image tag fully restores the prior state.
No data migration or manual session reconstruction is required.
