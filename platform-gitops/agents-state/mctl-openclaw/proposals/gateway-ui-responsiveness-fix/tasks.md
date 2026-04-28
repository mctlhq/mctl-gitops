# Tasks: gateway-ui-responsiveness-fix

- [ ] 1. Open a tracking issue linked to upstream #73836 —
  DoD: an issue exists in the mctl-openclaw tracker with a link to the upstream
  bug, the known symptoms documented, and the assigned engineer subscribed to
  upstream notifications.

- [ ] 2. Establish a heartbeat poll frequency baseline on `labs` (depends on 1) —
  DoD: a 30-minute sample of pod logs is captured and the average heartbeat poll
  events per minute is recorded as the pre-fix baseline.

- [ ] 3. Monitor upstream #73836 for a fix commit (depends on 1, ongoing) —
  DoD: the tracking issue is updated within one business day of a fix commit or PR
  appearing upstream; the fix commit SHA is recorded.

- [ ] 4. Cherry-pick the upstream fix onto the mctl-openclaw fork (depends on 3) —
  DoD: `git cherry-pick <fix-sha>` applies (with any conflicts resolved and
  documented in the PR body); the feature branch is pushed and a PR is opened.

- [ ] 5. Run CI on the cherry-picked branch (depends on 4) —
  DoD: CI pipeline passes green, including unit tests and extension compatibility
  checks; no new test failures.

- [ ] 6. Deploy cherry-pick to `labs` with canary/probe procedure (depends on 5) —
  DoD: ArgoCD sync completes for `labs`; restore-state probe passes; s3-sync
  canary is paused before rollout and restarted with configured delay after pod
  is ready; `labs` pod shows the cherry-picked commit in its version/build info.

- [ ] 7. Validate heartbeat poll noise reduction on `labs` (depends on 6) —
  DoD: a 30-minute post-fix pod-log sample shows a measurable reduction in
  heartbeat poll events per minute compared to the baseline from task 2;
  result is recorded in the PR.

- [ ] 8. Observe `labs` for false canary positives (depends on 6) —
  DoD: 24 h of `labs` operation with no s3-sync canary alerts attributable to
  heartbeat poll noise.

- [ ] 9. Promote cherry-pick to `admins` (depends on 7, 8) —
  DoD: ArgoCD rollout for `admins` completes; restore-state probe passes; s3-sync
  canary restarted.

- [ ] 10. Promote cherry-pick to `ovk` (depends on 9 after stability observation) —
  DoD: ArgoCD rollout for `ovk` completes; restore-state probe passes; s3-sync
  canary restarted; no Telegram typing-indicator gaps reported.

- [ ] 11. Close tracking issue (depends on 10) —
  DoD: the tracking issue is closed with a summary of the fix SHA, affected
  tenants, and the measured improvement in heartbeat poll frequency; PR is merged.

## Tests

- [ ] T1. Heartbeat frequency comparison: pod-log poll rate after cherry-pick (task 7)
  is lower than the baseline captured in task 2.
- [ ] T2. Canary clean run: s3-sync canary completes at least 3 consecutive
  successful cycles on `labs` without a false alert after the fix is deployed.
- [ ] T3. Telegram typing indicator: send a message on the `labs` Telegram channel
  and confirm the typing indicator appears without gaps during the reply.
- [ ] T4. UI reconnect: simulate a brief network interruption on `labs` and confirm
  the Control UI reconnects within the expected timeout without stalling.
- [ ] T5. Restore-state probe: restart the `labs` pod after the cherry-pick
  deployment and confirm it returns ready within the configured timeout (ensuring
  the cherry-pick does not slow down S3 session restoration).
- [ ] T6. Extension compatibility: confirm that no extension under `extensions/*`
  emits new errors or warnings in logs after the cherry-pick is applied.

## Rollback

If the cherry-pick introduces a regression or the CI validation fails:

1. Revert the cherry-pick commit from the feature branch (`git revert <cherry-pick-sha>`).
2. Open a PR with the revert; merge to restore the fork to the pre-cherry-pick state.
3. ArgoCD will re-sync `labs` to the reverted state; verify restore-state probe
   passes and heartbeat poll frequency returns to the pre-fix baseline.
4. Do NOT promote to `admins` or `ovk` until the issue is resolved.
5. Update the tracking issue with the observed failure mode and re-engage upstream
   to obtain a corrected fix.
6. If upstream is unresponsive after two weeks, escalate to an internal workaround
   patch (document as a new ADR before merging).
