# Investigate silent s3-sync canary and possible pod-down state in `ovk`

## Context
`ovk` is the production, high-SLA tenant for which ADR-0002 explicitly exists to prevent silent auth/session loss. This inbox pass surfaced three anomalies co-occurring for `ovk`/openclaw that did not co-occur on 2026-08-22: (1) zero s3-sync log lines over a 1h window (previously only `labs` showed this), (2) a sharp resource-usage drop (`limits.memory` ~81% → ~17%, pods used 2/5 → 1/5), and (3) ArgoCD reporting `ovk-openclaw` as `OutOfSync` (health still `Healthy`) — with **zero** incidents raised for `ovk` in the same window. Individually each signal could be noise (e.g. a quiet traffic period, a config drift with no functional effect), but together they are consistent with the openclaw pod in `ovk` being down, restarted, or degraded without the alerting we rely on — precisely the blind spot the s3-sync canary and restore-state probe are designed to catch.

This is a read-only diagnostic proposal: confirm or rule out a real pod-health problem in `ovk`, and if confirmed, identify why neither the canary nor an incident fired, before any remediation is attempted.

## User stories
- AS an on-call operator I WANT to know whether the `ovk` openclaw pod is actually down/degraded or just quiet SO THAT I can decide whether customer-facing channels are at risk.
- AS the service owner I WANT to understand why the s3-sync canary and incident system did not flag this state SO THAT the detection gap (not just this one instance) gets fixed.
- AS the on-call operator I WANT a documented, read-only investigation runbook SO THAT this class of signal can be triaged quickly next time without guessing.

## Acceptance criteria (EARS)
- WHEN the investigation starts THE SYSTEM SHALL check the actual pod status (running/ready/restart count) for `ovk`/openclaw via the Kubernetes/ArgoCD state, independent of the mctl log/metrics signals already gathered.
- WHEN pod status is confirmed THE SYSTEM SHALL inspect the s3-sync CronWorkflow execution history for `ovk` to determine whether the canary itself ran and produced no output, versus not running at all.
- WHEN the ArgoCD `OutOfSync` status for `ovk-openclaw` is reviewed THE SYSTEM SHALL diff the live vs. desired manifest to identify what specifically drifted.
- IF the pod is confirmed down or the restore-state probe is failing THEN THE SYSTEM SHALL document the finding and escalate as a new incident, without independently restarting or otherwise mutating the `ovk` deployment as part of this investigation (per architecture guidance: no `ovk` restarts without clear, separately-approved justification).
- IF the pod and canary are confirmed healthy and the empty logs/resource drop are explained by benign causes (e.g., traffic drop, log-retention window) THEN THE SYSTEM SHALL record the explanation and close the investigation with no further action.
- WHILE the investigation is in progress THE SYSTEM SHALL treat all actions as read-only (log/metric/manifest inspection only) and SHALL NOT modify the s3-sync canary schedule, the restore-state probe timeout, or any `ovk` resource beyond diagnostic inspection.
- WHEN the investigation concludes THE SYSTEM SHALL produce a written finding (root cause, evidence, and whether alerting should have fired) to feed a possible follow-up alerting-gap fix.

## Out of scope
- Any code or config change to the s3-sync canary, restore-state probe, or `ovk` deployment itself — this proposal is diagnostic only; a remediation proposal follows if the investigation confirms a real problem.
- Restarting the `ovk` pod.
- The GHSA-2026-09-11 patch rollout (tracked separately in `ghsa-batch-2026-09-11-upgrade-assessment`).
- The `labs` memory quota trend (tracked separately in `labs-memory-quota-trend-review`).
