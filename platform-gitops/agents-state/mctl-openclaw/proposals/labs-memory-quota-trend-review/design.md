# Design: labs-memory-quota-trend-review

## Current state
Per `context/architecture.md`, `labs` is explicitly called out as "close to the memory limit — any footprint increase requires justification" and serves as the mandatory canary tenant per ADR-0001 (every change rolls out `labs` → `admins` → `ovk`, with an observation window in `labs` first). Tenant-wide metrics (17 services, not openclaw-specific) show `limits.memory` usage rising from ~60% (2026-08-22) to ~83% (this pass), `requests.memory` from ~62% to ~76%, and `limits.cpu` at ~94%, with 16/25 pods in use. There is currently no per-service breakdown of what is driving this growth, and no alert threshold below 100% that would give advance warning before quota exhaustion blocks a rollout.

## Proposed solution
A monitoring-only proposal with two parts, neither of which adds workload to `labs`:
1. **Attribution.** Pull per-service memory/CPU metrics for all 17 services in `labs` via `mctl` and rank contributors to the delta between the 2026-08-22 and 2026-09-19 snapshots, to determine whether the growth is concentrated (one or two services) or diffuse, and whether openclaw itself is a contributor.
2. **Early-warning alerting.** Define and configure an alert threshold (e.g., a percentage of `limits.memory`/`limits.cpu` comfortably below 100%, informed by the historical rollout footprint needed for an openclaw canary pass) in the existing mctl monitoring/alerting layer, so the team is notified before quota exhaustion rather than discovering it mid-rollout. The alert is a platform-level monitoring rule, not a new in-namespace workload.

The output feeds directly into the `ghsa-batch-2026-09-11-upgrade-assessment` proposal: before that proposal's `labs` rollout step runs, this review's findings should confirm `labs` has enough headroom to safely absorb a canary rollout (transient pod overlap during rollout, canary/probe cycling, etc.).

## Alternatives
- **Immediately increase `labs`' memory/CPU quota allocation.** Rejected for this proposal: a capacity increase is a legitimate possible outcome, but it requires platform-level budget/sign-off and should follow attribution (part 1), not precede it — jumping straight to "more quota" without knowing the driver risks masking a leak or misconfiguration.
- **Reduce footprint by removing or downsizing services in `labs` immediately.** Rejected for this proposal: `labs` intentionally hosts experimental/beta workloads per ADR-0001 and `context/architecture.md`; removing something without knowing if it's the actual driver (and without the service owner's input) is premature and out of this proposal's read-only/monitoring scope.
- **Do nothing and rely on the existing incident system to catch quota exhaustion when it happens.** Rejected: `mctl_list_incidents` shows 0 active incidents for `labs` despite the trend already reaching ~83%/~94%, i.e., the existing incident system is not currently configured to catch this proactively — which is the exact gap this proposal closes.

## Platform impact
- **Migrations:** None.
- **Backward compatibility:** None — no code or schema change.
- **Resource impact (labs):** None by design — this proposal explicitly adds no new pod, sidecar, or resource request/limit inside the `labs` namespace; the alerting rule lives in the existing mctl monitoring/alerting layer outside the tenant's own quota. This is called out because `labs` is flagged in `context/architecture.md` as requiring justification for any footprint increase, and the answer here is "zero footprint increase."
- **Risks and mitigations:**
  - Risk: attribution reveals openclaw itself is a significant driver of the growth, which would need its own fix (potentially conflicting with the "no footprint increase" constraint) → Mitigation: treat that as a distinct, separately-scoped follow-up proposal, not something this monitoring task attempts to fix directly.
  - Risk: the alert threshold is set too high (near 100%) and still doesn't give enough lead time to react before a rollout is blocked → Mitigation: set the threshold using the historical peak footprint of a `labs` openclaw rollout as a buffer reference, and revisit after the `ghsa-batch-2026-09-11-upgrade-assessment` rollout provides a real data point.
  - Risk: alert threshold set too low and becomes noisy → Mitigation: start conservative (e.g., informational-only notification) and tune after observing one or two cycles, consistent with the "fix the cause, don't silence the alert" principle in ADR-0002 applied here by analogy.
