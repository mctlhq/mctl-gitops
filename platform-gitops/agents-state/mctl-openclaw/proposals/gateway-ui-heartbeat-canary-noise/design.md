# Design: gateway-ui-heartbeat-canary-noise

## Current state

The s3-sync canary (Argo CronWorkflow, per ADR-0002) fires every N minutes and checks that the openclaw pod has written a fresh S3 timestamp within the expected window. If the canary misses more than N consecutive cycles, it pages the on-call engineer. This is the primary early-warning system for silent S3-sync failures.

Upstream issue **#73836** (filed April 28, 2026) introduces a regression in the gateway/UI layer:
- The `heartbeat` poll fires at a significantly higher rate than intended (noise).
- The elevated polling rate generates spurious write activity on the internal event bus.
- This causes the s3-sync worker to queue more operations than usual, occasionally causing it to miss its write-timestamp window — which the canary interprets as a sync failure.

In practice: the canary fires a spurious alert even though S3 is healthy and writing. Per ADR-0002 §"Recurring footguns", the correct response is to **fix the noise source, not raise the canary threshold or silence alerts**.

The Telegram typing indicator gap (also part of #73836) causes user-visible UX degradation in `ovk` (production tenant) but is not a safety issue.

See `context/architecture.md` §"s3-sync canary" and `context/decisions/0002-s3-state-with-canary-and-probe.md`.

## Proposed solution

**Two-track approach: immediate workaround + upstream fix tracking.**

### Track A: Configuration workaround (immediate — while upstream fix is pending)

openclaw exposes a `heartbeat.intervalMs` configuration parameter (confirmed in the 2026.x config schema). Setting this to the pre-regression value prevents the excessive poll rate without disabling heartbeat functionality.

Change in the Helm values (each tenant):
```yaml
openclaw:
  config:
    heartbeat:
      intervalMs: 30000  # restore to pre-regression default; upstream regression raised this to ~5000
```

Apply via a gitops PR for each tenant (labs→admins→ovk). This is a hot-config change: openclaw reloads config without a pod restart.

Add a **startup warning log** (via the YAML skill layer or a thin wrapper) that prints a notice when `heartbeat.intervalMs` is explicitly overridden, so the workaround cannot silently persist after an upstream fix is applied.

### Track B: Upstream fix tracking

Watch upstream issue #73836 and the associated PR. When the fix is merged and released:
1. The researcher cycle will detect the new release.
2. The gitops config override (`heartbeat.intervalMs`) is removed in the same PR that bumps the image tag.
3. End-to-end canary and Telegram typing tests are run to confirm the noise is gone.

This decouples the workaround from the full version upgrade (`upgrade-to-2026-4-27` proposal), allowing both to proceed independently.

## Alternatives

**A. Raise the canary cycle threshold to absorb the noise** — Explicitly rejected by ADR-0002 §"What NOT to propose": "Disabling the canary 'because it's noisy' — the cause of the noise must be fixed." Raising the threshold would mask genuine S3-sync failures.

**B. Silence canary alerts temporarily** — Also rejected by ADR-0002 for the same reason. Temporary silencing has a history of becoming permanent.

**C. Wait for the full upstream upgrade and do nothing now** — Rejected. The `upgrade-to-2026-4-27` rollout is a multi-day operation (sequential tenant soak periods). In the meantime, false canary alerts in `ovk` erode on-call trust in the alert system — the most dangerous pre-condition for missing a real incident.

## Platform impact

### Migrations
No migration required. The `heartbeat.intervalMs` override is a Helm values addition; it is removed once the upstream fix is applied.

### Backward compatibility
`heartbeat.intervalMs` is an existing config parameter. Setting it explicitly overrides the upstream default; it will be removed (not left at the old value) when the upstream fix lands, restoring normal behavior.

### Resource impact (especially for `labs`)
Reducing heartbeat poll frequency from the regression-elevated rate (~5 s) back to the intended interval (~30 s) **decreases** CPU and event-bus load. This is a memory/CPU improvement for all tenants, including `labs`.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Heartbeat interval is reduced too much, masking real connectivity loss | Set to the documented pre-regression default (30 s), not an arbitrary low value; confirm with upstream issue comments |
| Startup warning log is noisy in production | Log at `WARN` level, once at startup, with a structured field `workaround: heartbeat-interval-override`; suppress after upstream fix is removed |
| Telegram typing gap persists after config change | The typing gap is a UI rendering artifact of the reconnect stall (separate from heartbeat); document as a known cosmetic issue pending upstream fix; not blocking |
| Config override silently persists after upstream upgrade | The startup warning log and removal task in the upstream-fix PR prevent this |
