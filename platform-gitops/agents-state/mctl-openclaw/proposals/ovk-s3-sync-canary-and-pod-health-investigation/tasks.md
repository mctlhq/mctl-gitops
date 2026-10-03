# Tasks: ovk-s3-sync-canary-and-pod-health-investigation

- [ ] 1. Query live pod state for `ovk`/openclaw (phase, ready condition, restart count, last restart reason/timestamp) — DoD: a factual pod-status snapshot is recorded, independent of the aggregated metrics already in the inbox.
- [ ] 2. If step 1 shows a failed or not-ready pod, escalate immediately as a new incident (depends on 1) — DoD: incident created with the pod-status evidence, before proceeding to steps 3–4 (time-sensitive branch).
- [ ] 3. Inspect the s3-sync CronWorkflow run history for `ovk` over the same window as the 0-log-lines observation (depends on 1) — DoD: determined whether the canary ran and reported nothing, or did not run at all, with timestamps.
- [ ] 4. Diff `ovk-openclaw`'s live vs. desired ArgoCD manifest to identify the specific drifted field(s) (depends on 1) — DoD: exact field-level diff recorded, with an assessment of whether it correlates with the pod/resource changes.
- [ ] 5. Correlate findings from steps 1, 3, 4 against the 2026-08-22 baseline to determine root cause (benign vs. real fault) (depends on 2, 3, 4) — DoD: single written conclusion: "confirmed problem, escalated as incident #___" or "explained by benign cause: ___".
- [ ] 6. Regardless of root cause, document specifically why the s3-sync canary and incident system did not flag this state on their own (depends on 5) — DoD: a distinct sub-finding exists describing the detection gap, to seed a possible follow-up alerting-fix proposal.

## Tests
- [ ] T1. Re-run `mctl_get_service_logs` for `ovk`/openclaw with a wider window (e.g., 24h) to confirm whether the 0-log-lines result is a real gap or a windowing artifact.
- [ ] T2. Re-run `mctl_get_service_status`/resource metrics for `ovk` at investigation time to confirm the resource drop (limits.memory ~81%→~17%) is still present or has since changed.
- [ ] T3. Confirm no incident was silently created-and-auto-resolved for `ovk` in the window (distinguish "no incident fired" from "incident fired and cleared").

## Rollback
This proposal is entirely read-only (log, metric, and manifest inspection); there is no system state to roll back. If step 2's escalation creates an incident that later turns out to be a false positive, close the incident with the corrected finding — no infrastructure change needs to be reverted. No canary, probe, or `ovk` deployment configuration is touched by this investigation itself.
