# Tasks: slack-socket-mode-update

- [ ] 1. Bump `@slack/socket-mode` to `2.0.7` in `package.json` and regenerate `package-lock.json` — DoD: `package.json` lists `"@slack/socket-mode": "2.0.7"` (or equivalent exact pin); `npm install` completes without errors; `package-lock.json` diff is reviewed and contains no unexpected transitive dependency changes.

- [ ] 2. Build and push Docker image (depends on 1) — DoD: Docker image built successfully with the updated dependency; pushed to the mctl registry with a distinct tag; image scan shows no new high/critical CVEs introduced by this bump.

- [ ] 3. Roll out to `labs` with canary pause/resume (depends on 2) — DoD: s3-sync canary suspended before apply; ArgoCD applies the new image to the `labs` namespace; restore-state readiness probe passes within the existing timeout; canary resumed and passing; Slack channel on `labs` shows no stale-connection warning logs.

- [ ] 4. Observe `labs` Slack channel health (depends on 3) — DoD: No stale-connection warnings in `labs` Slack channel logs for at least a few hours post-deploy; Slack messages routed correctly; reconnection events (if any) complete promptly with no extended latency.

- [ ] 5. Roll out to `admins` with canary pause/resume (depends on 4) — DoD: Same procedure as task 3 applied to `admins`; restore-state probe passes; canary resumed and passing; Slack channel healthy on `admins`.

- [ ] 6. Roll out to `ovk` with canary pause/resume (depends on 5) — DoD: Same procedure as task 3 applied to `ovk`; restore-state probe passes; canary resumed and passing; Slack channel healthy on `ovk`; no customer-visible Slack delivery interruption.

## Tests

- [ ] T1. Confirm `@slack/socket-mode` version in the running `labs` pod is 2.0.7 (e.g., via `npm ls @slack/socket-mode` in the container or image inspection).
- [ ] T2. Monitor `labs` Slack channel logs for 2 hours post-deploy and confirm zero occurrences of the stale-closing-connection warning message.
- [ ] T3. Confirm the restore-state readiness probe passes on all three tenants after rollout (ArgoCD sync status = Healthy for each namespace).
- [ ] T4. Confirm the s3-sync canary passes at least two consecutive cycles on each tenant after the post-rollout resume.
- [ ] T5. Send a test Slack message through the `labs` tenant after rollout and confirm it is delivered correctly end-to-end.

## Rollback
If any rollout step fails (probe does not pass, canary fires, Slack channel errors):

1. ArgoCD: revert the failing tenant's helm release to the previous image tag (which used the pre-2.0.7 version of `@slack/socket-mode`).
2. Wait for the restore-state probe to pass on the reverted pod.
3. Resume the s3-sync canary.
4. Verify Slack channel health on the reverted tenant.
5. Do NOT roll back tenants that have already been confirmed healthy.
6. Investigate the failure, then re-evaluate whether a further patch version or a code-level workaround is needed before retrying.

The previous image tag must be retained in the mctl registry until all three tenants are confirmed stable on the new version.
