# Tasks: ovk-empty-logs-pod-health-investigation

- [ ] 1. Check status/findings of sibling proposal `ovk-s3-sync-canary-and-pod-health-investigation` — DoD: documented whether it was executed and whether its finding is still current.
- [ ] 2. IF sibling finding is stale or investigation still open: confirm actual `ovk`/openclaw pod running/ready/restart-count state via Kubernetes/ArgoCD (depends on 1) — DoD: pod state recorded independent of mctl log/metric proxies.
- [ ] 3. Inspect the s3-sync CronWorkflow execution history for `ovk` (depends on 1) — DoD: determined whether the canary ran with no output vs. did not run at all.
- [ ] 4. Diff ArgoCD live vs. desired manifest for `ovk-openclaw` (depends on 1) — DoD: any drift identified and explained, or confirmed no drift.
- [ ] 5. Write consolidated finding covering both this week's and the sibling's open questions (depends on 2, 3, 4) — DoD: written finding with root cause (or "confirmed benign"), evidence, and an explicit statement on whether alerting should have fired.
- [ ] 6. IF a real problem is confirmed: escalate as a new incident (depends on 5) — DoD: incident created/updated, no `ovk` restart or mutation performed as part of this investigation.
- [ ] 7. IF confirmed benign: close this proposal and the sibling investigation (depends on 5) — DoD: both marked closed with the shared finding referenced.

## Tests
- [ ] T1. Pod status check reproducible from raw Kubernetes/ArgoCD state (not solely mctl log tail).
- [ ] T2. s3-sync CronWorkflow history query returns a clear ran/did-not-run determination.
- [ ] T3. ArgoCD manifest diff for `ovk-openclaw` reviewed for drift.

## Rollback
Not applicable — this proposal is read-only and diagnostic only; no
production change is made, so there is nothing to roll back. If step 6
results in an incident, its own remediation plan (a separate, future
proposal) will define any rollback procedure for whatever fix it proposes.
