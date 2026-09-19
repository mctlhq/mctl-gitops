# Review and alert on `labs` tenant-wide memory quota trend before it blocks rollouts

## Context
Tenant-wide memory usage in `labs` (across its 17 services) rose from ~60% to ~83% of `limits.memory` and from ~62% to ~76% of `requests.memory` between 2026-08-22 and this pass, with `limits.cpu` now at ~94%. `labs` is already flagged in `context/architecture.md` as close to its memory limit, and per ADR-0001 it is the mandatory canary tenant that every change (including openclaw itself) must pass through, with an observation window, before promotion to `admins`/`ovk`. If `labs` runs out of headroom, it stops being a usable canary and becomes a bottleneck for every other proposal in flight, including the GHSA patch rollout.

This proposal is a monitoring and investigation task: identify which of the 17 services in `labs` is driving the growth, and add an early-warning alert threshold so the team is notified before the quota is exhausted rather than discovering it during a blocked rollout. It intentionally does not add any new footprint to `labs`.

## User stories
- AS the service owner I WANT to know which service(s) in `labs` are driving the memory growth SO THAT I can distinguish a one-off spike from a real leak or genuine capacity need.
- AS an on-call operator I WANT an early-warning alert before `labs` memory/CPU quota is exhausted SO THAT rollouts are not blocked or destabilized without notice.
- AS the service owner I WANT confirmation that this review itself adds no memory footprint to `labs` SO THAT it does not violate the tenant's "no footprint increase" constraint.

## Acceptance criteria (EARS)
- WHEN the review starts THE SYSTEM SHALL break down `labs` tenant-wide `limits.memory`/`requests.memory`/`limits.cpu` usage by service (using `mctl` per-service metrics) to identify the top contributor(s) to the increase from ~60%→~83% (memory) and to ~94% (CPU).
- WHEN the top contributor(s) are identified THE SYSTEM SHALL determine whether the growth is openclaw-specific or driven by other services sharing the `labs` namespace/quota.
- WHEN an early-warning alert threshold is proposed THE SYSTEM SHALL set it below the point at which `labs` would be unable to safely absorb a canary rollout of a new openclaw version (i.e., before hitting effective capacity, not at 100%).
- IF the alert threshold is crossed THEN THE SYSTEM SHALL notify the on-call/service-owner channel with the current usage percentage and the top-contributing service(s), without automatically throttling or scaling anything.
- WHILE this review is being implemented THE SYSTEM SHALL NOT add any new persistent workload, sidecar, or resource request/limit to `labs` — the alerting mechanism SHALL live in the existing mctl monitoring/alerting layer, not as new footprint inside the `labs` namespace.
- WHEN the review concludes THE SYSTEM SHALL record findings and the chosen alert threshold, and SHALL flag to the `ghsa-batch-2026-09-11-upgrade-assessment` proposal owner whether `labs` currently has safe headroom to run that rollout's canary phase.

## Out of scope
- Reducing or optimizing the memory footprint of any specific `labs` service — this proposal only measures and alerts; a follow-up proposal would be needed for any actual footprint reduction.
- Increasing `labs` quota/allocation — a capacity decision that would need separate platform-level sign-off.
- The GHSA-2026-09-11 patch rollout itself (tracked separately in `ghsa-batch-2026-09-11-upgrade-assessment`), beyond flagging headroom status to it.
- The `ovk` pod-health investigation (tracked separately in `ovk-s3-sync-canary-and-pod-health-investigation`).
