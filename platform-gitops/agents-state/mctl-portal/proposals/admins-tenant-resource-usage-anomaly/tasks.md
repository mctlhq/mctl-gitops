# Tasks: admins-tenant-resource-usage-anomaly

- [ ] 1. Query raw Prometheus/kube-state-metrics data for the `admins` namespace for
      the 2026-09-19 and 2026-09-26 windows and compare against the reported
      tenant-level CPU/mem-limit percentages — DoD: a documented side-by-side
      comparison showing whether raw and reported figures agree or diverge.
- [ ] 2. If step 1 shows divergence, cross-check the query/label path against the
      Loki label-matching check already planned in `portal-log-pipeline-gap` step 4
      (depends on 1) — DoD: a shared conclusion recorded in both proposals on whether
      a common label/scrape/query defect explains both the resource-usage anomaly and
      the empty-log-lines symptom.
- [ ] 3. Inspect per-pod state for all mctl-portal pods in `admins` across the four
      cycles: restart counts, container last-state (OOMKilled/CrashLoopBackOff/etc.),
      and per-pod CPU/mem trend (depends on 1, only if raw metrics confirm the drop
      is real) — DoD: a documented pod-health table for the affected window ruling a
      crash-loop/OOM pattern in or out.
- [ ] 4. Review mctl-gitops commit history and Argo Workflow provisioning activity in
      `admins` between 09-19 and 09-26 for resource-request/limit or HPA changes to
      mctl-portal or any sibling service in the tenant (depends on 1) — DoD: a
      documented list of any relevant changes found, or explicit confirmation that
      none were found.
- [ ] 5. Produce a final root-cause classification (legitimate change / workload
      health issue / metrics-pipeline defect / other) with supporting evidence from
      tasks 1-4 (depends on 2, 3, 4) — DoD: classification recorded in
      `requirements.md`'s acceptance criteria section of this proposal, with a link
      to any follow-on proposal opened for remediation.
- [ ] 6. If task 5 confirms a shared root cause with `portal-log-pipeline-gap`,
      consolidate remediation tracking into a single proposal and mark the other as
      superseded with a cross-reference (depends on 5) — DoD: both proposals'
      documents updated to point at the single active remediation effort, no
      contradictory status between them.

## Tests
- [ ] T1. Verify the raw-metrics query in task 1 is reproducible: running it twice
      against the same window returns consistent figures (rules out query
      flakiness before drawing conclusions from it).
- [ ] T2. If a crash-loop/OOM pattern is found in task 3, verify it correlates in
      time with the CPU/mem-limit usage drop (not just present at some point in the
      window) before citing it as the root cause.
- [ ] T3. If a legitimate workload/deploy change is found in task 4, verify its
      resource-footprint delta is consistent in magnitude with the observed drop
      (e.g., a sibling service scale-down of roughly the right size), not just
      temporally coincident.
- [ ] T4. Confirm no scaling, restart, or configuration change was made against
      `admins` workloads as a side effect of this investigation (per the
      diagnostic-only WHILE-clause in requirements.md).

## Rollback
This proposal is diagnostic-only and makes no production changes, so there is
nothing to roll back for the investigation itself. If a follow-on remediation
proposal is opened as a result of task 5/6, that proposal will carry its own
rollback plan specific to whatever fix it applies.
