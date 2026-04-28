# Tasks: upgrade-to-2026-4-26

- [ ] 1. Bump openclaw to 2026.4.26 in `package.json` and regenerate lockfile —
  DoD: `package.json` specifies `"openclaw": "2026.4.26"`, lockfile is committed,
  no unresolved peer-dependency warnings.

- [ ] 2. Run extension compatibility check in CI (depends on 1) —
  DoD: all packages under `extensions/*` import from `openclaw/plugin-sdk/*`
  without type errors against 2026.4.26; CI pipeline passes green.

- [ ] 3. Build and push Docker image tagged `2026.4.26-mctl-<git-sha>` (depends on 2) —
  DoD: image is present in the container registry and the image digest is recorded
  in the mctl-gitops PR.

- [ ] 4. Update `labs` helm release in mctl-gitops to the new image (depends on 3) —
  DoD: ArgoCD sync is triggered; restore-state readiness probe passes within
  the configured timeout; `labs` pod reports version 2026.4.26.

- [ ] 5. Pause s3-sync canary before `labs` rollout, restart with delay after pod
  is ready (depends on 4) —
  DoD: canary CronWorkflow is suspended at rollout start and resumed (with
  configured delay) after the pod is marked ready; no false alerts fired.

- [ ] 6. Validate `labs` memory metric via mctl MCP (depends on 4, 5) —
  DoD: memory reading from `mcp__mctl__*` for the `labs` tenant is below the
  tenant limit; result is recorded in the PR description.

- [ ] 7. Observe `labs` for the required observation window (depends on 6) —
  DoD: minimum 24 h of healthy operation with no open incidents, no canary
  failures, no restore-state probe failures on `labs`.

- [ ] 8. Promote to `admins` with canary/probe procedure (depends on 7) —
  DoD: ArgoCD rollout for `admins` completes successfully; restore-state probe
  passes; s3-sync canary restarted; `admins` pod reports 2026.4.26.

- [ ] 9. Observe `admins` for stability (depends on 8) —
  DoD: minimum 12 h with no open incidents, no canary failures.

- [ ] 10. Promote to `ovk` with canary/probe procedure (depends on 9) —
  DoD: ArgoCD rollout for `ovk` completes successfully; restore-state probe
  passes; s3-sync canary restarted; `ovk` pod reports 2026.4.26.

- [ ] 11. Update `context/current-version.md` (depends on 10) —
  DoD: file reflects `2026.4.26` for all three tenants; change is committed to
  the repo.

## Tests

- [ ] T1. CVE regression: confirm `chat.send` no longer allows privilege escalation
  (CVE-2026-41371) — send a crafted request from a low-privilege session and verify
  a 403 or equivalent rejection.
- [ ] T2. CVE regression: confirm `config.patch` rejects requests that would bypass
  LLM agentic consent (CVE-2026-41349).
- [ ] T3. CVE regression: confirm remote-onboarding flow requires valid auth
  (CVE-2026-41342).
- [ ] T4. CVE regression: confirm node-pairing endpoint enforces authorization
  (CVE-2026-41352).
- [ ] T5. CVE regression: confirm `allowProfiles` enforces access control
  (CVE-2026-41353).
- [ ] T6. Bearer-token echo: call `device.token.rotate`, confirm the rotated token
  is NOT present in the response body.
- [ ] T7. Memory baseline: record `labs` memory before and after upgrade; delta
  must be within acceptable headroom.
- [ ] T8. Restore-state probe smoke test: restart the `labs` pod manually after
  rollout, confirm it returns ready within the configured timeout.
- [ ] T9. s3-sync canary: after canary restart, confirm it completes at least
  two consecutive successful cycles without false alerts on `labs`.

## Rollback

If the rollout on any tenant fails (restore-state probe timeout, OOM, functional
regression):

1. ArgoCD auto-rollback returns the affected tenant's helm release to the previous
   image (`2026.3.14-mctl-<prev-sha>`). Verify the pod is running 2026.3.14 and
   the restore-state probe passes.
2. Pause the s3-sync canary immediately on the affected tenant to avoid false alerts
   during rollback; restart it with the configured delay.
3. If the `labs` rollback succeeds, do NOT proceed to `admins` or `ovk` until the
   root cause is identified and fixed.
4. Open an incident in the mctl tracking system describing the failure mode,
   memory readings, and the specific task at which rollback was triggered.
5. The previous proposal (`upgrade-to-2026-4-25`) is also superseded and should
   not be retried; prepare a new proposal targeting a patched upstream release if
   2026.4.26 itself carries a regression.
