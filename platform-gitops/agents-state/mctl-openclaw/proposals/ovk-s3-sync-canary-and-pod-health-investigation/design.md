# Design: ovk-s3-sync-canary-and-pod-health-investigation

## Current state
Per `context/architecture.md` and ADR-0002, `ovk` relies on the s3-sync canary (periodic Argo CronWorkflow verifying fresh S3 writes) and the restore-state readiness probe (blocks ArgoCD from marking a rollout successful until auth/sessions are restored from S3) to catch silent state-loss — critical for `ovk` because it cannot tolerate auth loss for a live customer. `mctl_get_service_logs` for `ovk`/openclaw returned 0 log lines in a 1h window (previously this empty-logs signal was only seen for `labs`); `ovk` tenant-wide resource usage dropped sharply (`limits.memory` ~81%→~17%, requests.memory ~76%→~17%, pods used 2/5→1/5); and ArgoCD reports `ovk-openclaw` as `OutOfSync` (health `Healthy`). `mctl_list_incidents` for `ovk` returned 0 active incidents in the same window. No rollout is recorded as in progress for `ovk` in this window, so the canary should not be in its expected "paused for rollout" state.

## Proposed solution
A time-boxed, strictly read-only investigation using existing mctl/ArgoCD/Kubernetes introspection, in three parts:
1. **Pod-level ground truth.** Query live pod state for `ovk`/openclaw (phase, ready condition, restart count, last restart reason/timestamp) directly, independent of the aggregated metrics/log signals already in the inbox, to confirm whether the pod is actually down, crash-looping, or simply idle.
2. **Canary execution history.** Inspect the s3-sync CronWorkflow's run history for `ovk` to distinguish "canary ran and found nothing to report" from "canary did not run" — these have very different implications for whether the alerting gap is in the canary itself or in what it's monitoring.
3. **ArgoCD drift diff.** Diff `ovk-openclaw`'s live vs. desired manifest to identify the specific field(s) causing `OutOfSync`, and check whether that drift correlates with the pod/resource changes (e.g., a manually-scaled replica count, an image tag mismatch, a config drift applied outside gitops).

Findings from all three are combined into a single incident-quality report: either "confirmed pod-health problem — escalate as a new incident" or "explained by a benign cause — close out," plus a specific note on why the canary and incident system did not flag the state on their own (a distinct, important sub-finding regardless of which branch applies).

## Alternatives
- **Restart the `ovk` pod immediately to "fix" the symptom.** Rejected: `context/architecture.md` explicitly says not to propose `ovk` restarts without clear justification, and restarting before understanding root cause risks masking a real S3-sync or auth-restore failure rather than fixing it, plus restarts are inherently painful for this high-SLA tenant.
- **Wait for the next scheduled research/analyst pass to see if the signal persists.** Rejected as the sole action: the inbox already shows a meaningful pattern (3 co-occurring anomalies, 0 incidents) that ADR-0002's canary/probe exist specifically to catch; waiting risks an undetected auth-loss window for a production customer.
- **Immediately widen the restore-state probe timeout or canary cycle threshold "to reduce noise."** Rejected: ADR-0002 explicitly forbids disabling/loosening the canary "because it's noisy" without first fixing the underlying cause, and this proposal has not yet established there even is a noise problem versus a real fault.

## Platform impact
- **Migrations:** None — read-only investigation.
- **Backward compatibility:** None — no code, config, or schema change.
- **Resource impact (labs):** None. This proposal touches only `ovk` introspection; no change to `labs` footprint.
- **Risks and mitigations:**
  - Risk: investigation is mistaken for permission to remediate directly → Mitigation: this proposal's scope is explicitly diagnostic only; any fix (e.g., restarting `ovk`, patching the canary alerting logic) requires a separate, explicitly-approved follow-up proposal.
  - Risk: the underlying issue is time-sensitive (active auth loss) and a purely investigative pace is too slow → Mitigation: if pod-level ground truth (step 1) shows a failed readiness/restore-state probe, escalate as an incident immediately rather than waiting for steps 2–3 to complete.
  - Risk: root cause turns out to be outside `ovk`/openclaw (e.g., a platform-wide ArgoCD or logging-pipeline issue also affecting other services) → Mitigation: note this explicitly in the findings so it can be routed to the right owner instead of being treated as an openclaw-specific fix.
