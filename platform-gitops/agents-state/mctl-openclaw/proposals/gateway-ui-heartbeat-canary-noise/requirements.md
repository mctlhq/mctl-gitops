# Mitigate upstream #73836 heartbeat poll noise to prevent false s3-sync canary alerts

## Context

Upstream GitHub issue **#73836** (filed April 28, 2026) describes a regression in openclaw's gateway/UI layer that causes: (1) UI reconnect stalls, (2) Telegram typing indicator gaps in `ovk`, and (3) — most critically for our platform — **excessive heartbeat poll noise** that fires at an elevated rate and can exceed the threshold monitored by our s3-sync canary Argo CronWorkflow.

ADR-0002 ("S3-backed state + canary + restore-state probe") explicitly documents that **canary noise must be fixed at its source, not silenced**. A noisy canary that pages falsely conditions engineers to ignore alerts, which is precisely when a real S3-sync failure can go undetected — leading to auth loss on the next pod restart. This is especially dangerous for `ovk` (high SLA, production customer) where losing channel auth causes visible downtime.

The fix is either: (a) cherry-pick the upstream patch once merged, or (b) apply a targeted configuration workaround to reduce heartbeat poll frequency below the canary threshold until the upstream fix lands. This proposal covers both paths and can be executed independently of the full version upgrade.

## User stories

- AS an on-call engineer I WANT the s3-sync canary to fire only on genuine S3-sync failures SO THAT I do not become desensitized to canary alerts and miss a real failure.
- AS a platform engineer I WANT Telegram typing indicators and UI reconnect behaviour in `ovk` to be stable SO THAT production customers do not experience visible degradation.
- AS a developer I WANT a documented workaround available while the upstream fix is pending SO THAT we are not blocked on upstream merge timelines.

## Acceptance criteria (EARS)

- WHEN the mitigation is applied THE SYSTEM SHALL produce heartbeat poll events at a rate no higher than the pre-regression baseline, as measured over a 24-hour observation window per tenant.
- WHILE the heartbeat noise mitigation is active THE SYSTEM SHALL NOT trigger s3-sync canary alerts in the absence of a genuine S3-sync failure across all three tenants.
- WHEN upstream issue #73836 is resolved and a patch version is released THE SYSTEM SHALL cherry-pick or upgrade to include that fix within one business day of the release.
- IF a genuine S3-sync failure occurs (pod fails to write a fresh timestamp within N canary cycles) THE SYSTEM SHALL still fire the canary alert within the configured threshold, confirming the mitigation has not blinded the canary.
- WHEN Telegram typing indicators are monitored in `ovk` after the mitigation THE SYSTEM SHALL show no user-visible typing gaps compared to the pre-regression baseline.
- WHILE the configuration workaround is in place (pending upstream fix) THE SYSTEM SHALL log a warning on startup noting that heartbeat poll frequency has been manually overridden, ensuring the workaround does not silently persist post-upgrade.

## Out of scope

- Raising or lowering the s3-sync canary cycle threshold as a permanent change (ADR-0002 prohibits silencing the canary without fixing the root cause).
- Fixing unrelated UI responsiveness regressions from #73836 (stall during reconnect) — those are addressed by the upstream upgrade proposal.
- Changes to the `restore-state` readiness probe timeout.
