# Investigate zero s3-sync log output for `labs`/openclaw

## Context
The most recent metrics pass (`mctl_get_service_logs`) returned zero log lines for the
`labs` tenant's openclaw s3-sync sidecar across both a 1-hour and a 6-hour sampling
window, while the same query against `admins` and `ovk` returned normal sync activity
(regular successful writes of workspace skill dirs and `update-check.json` every
1-2 minutes) in the same window. No active incident is currently open for any tenant
(`mctl_list_incidents` returns `count: 0` for all three).

Per ADR-0002, the s3-sync canary exists specifically to catch a broken S3 write path
*before* it causes silent auth/session loss on the next pod restart — the restore-state
probe only checks that data can be *read back* from S3 on startup, so a canary that has
stopped reporting (rather than reporting failures) is a blind spot: we cannot currently
tell whether `labs` (a) genuinely has no sync activity, (b) has a renamed
pod/container that the log query is missing, or (c) has a broken canary/log pipeline.
Per ADR-0001, `labs` is also the designated canary *tenant* for changes ahead of `ovk`;
if its own s3-sync signal is unreliable, that safety net is degraded for every future
rollout that passes through `labs` first, including the plugin-SDK migration and any
Baileys upgrade proposed alongside this finding.

## User stories
- AS the mctl-openclaw service owner I WANT to know why the `labs` s3-sync container
  produced zero log lines over a 6-hour window SO THAT I can confirm whether `labs`
  state persistence is actually healthy or silently broken.
- AS the mctl-openclaw service owner I WANT a documented, repeatable way to verify
  s3-sync canary health per tenant SO THAT a future silent gap is caught quickly
  instead of discovered only after a `labs` restart loses auth.

## Acceptance criteria (EARS)
- WHEN the investigation task runs THE SYSTEM SHALL produce a written determination
  of the root cause of the zero-log-line result for `labs`/openclaw s3-sync (one of:
  container/pod naming mismatch, log query/tooling issue, genuinely stalled sync
  workflow, or canary CronWorkflow not scheduled/running in `labs`).
- WHEN the s3-sync CronWorkflow status is checked for `labs` THE SYSTEM SHALL record
  its last successful run timestamp and compare it against the `admins`/`ovk`
  equivalents sampled in the same window.
- IF the investigation confirms `labs` s3-sync is genuinely not writing to S3 THEN
  THE SYSTEM SHALL raise this as a follow-up incident/action item (not silently
  close the finding) so it can be triaged with appropriate urgency, per ADR-0002's
  guidance that canary failures must be alerted, not ignored.
- IF the investigation finds only a logging/observability gap (sync is actually
  healthy) THEN THE SYSTEM SHALL document the correct log query/container name so
  future metrics passes do not re-raise a false positive.
- WHILE this investigation is in progress THE SYSTEM SHALL NOT modify the `labs`
  s3-sync canary configuration, the S3 bucket, or the restore-state probe timeout
  (per ADR-0002's "what NOT to propose").
- WHILE this investigation is in progress THE SYSTEM SHALL NOT add any new
  long-running process, sidecar, or memory footprint to the `labs` deployment.

## Out of scope
- Any code change to the s3-sync canary implementation, the openclaw sync client,
  or the S3 bucket/backup-region configuration.
- Disabling or reconfiguring the canary's alert thresholds.
- Reducing or changing the restore-state probe timeout.
- Investigating `admins`/`ovk` s3-sync — both already show healthy activity in the
  sampled window and are not in scope for this finding.
- A full audit of `labs`' overall memory/resource posture (tracked separately if
  needed; this proposal only asserts the investigation itself must add zero footprint).
