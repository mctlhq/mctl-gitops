# Tasks: nodejs-heap-cap-labs

- [ ] 1. Profile labs heap baseline — DoD: A documented baseline exists with (a) a time-series of
  JS heap usage from the labs pod over at least 24 h of normal operation covering peak channel
  activity, captured via mctl MCP metrics; (b) the observed peak heap value P in MB recorded; (c)
  a recommended cap value N = floor(P / 0.8) stated explicitly; (d) confirmation that N is at
  least 50 MB below the gap between the container memory limit and estimated RSS overhead from
  native/buffer allocations. All four data points are recorded in a comment block at the top of the
  labs overlay file or in the PR description before any code change is merged.

- [ ] 2. Add `--max-heap-size=<N>` to the labs helm overlay (depends on 1) — DoD: The labs-specific
  helm values file in mctl-gitops contains `NODE_OPTIONS: "--max-heap-size=<N>"` (with N from task
  1). The `admins` and `ovk` overlay files are unchanged and do not contain `max-heap-size`. The
  shared `values.yaml` (if one exists) is also unchanged. The PR diff shows only the labs overlay
  modification. A comment in the overlay file references this proposal slug and the profiling
  baseline from task 1.

- [ ] 3. Verify flag is active in the running labs pod (depends on 2) — DoD: After ArgoCD syncs the
  labs overlay, an operator runs `kubectl exec -n labs <pod> -- node -e
  "console.log(process.execArgv)"` (or inspects `/proc/<pid>/cmdline`) and confirms
  `--max-heap-size=<N>` appears in the process arguments. If `NODE_OPTIONS` is not honoured by
  the container entrypoint, fall back to Option B (container command args in the Deployment
  manifest) and re-deploy before marking this task done. Document which injection method was used.

- [ ] 4. Observe labs pod for 48 h post-deployment (depends on 3) — DoD: mctl MCP metrics for the
  labs pod show (a) no heap-OOM-triggered restarts; (b) CPU usage within 10% of the pre-change
  baseline (indicating GC is not thrashing); (c) heap utilisation remaining below N MB under all
  observed load. Any unexpected heap-OOM restart requires raising N by 10%, re-running the profiling
  documentation, and re-deploying before this task can be closed.

- [ ] 5. Update operational runbook (depends on 4) — DoD: The mctl-openclaw runbook (or the
  equivalent on-call document) has a section titled "labs heap cap" that describes: (a) the current
  cap value N and the profiling date; (b) how to detect GC thrashing (CPU spike + high GC pause
  metrics); (c) how to raise or remove the cap; (d) the rollback procedure (identical to the
  Rollback section below).

## Tests

- [ ] T1. Manifest isolation test: run `helm template` (or `argocd app diff`) for all three tenant
  overlays and assert that the string `max-heap-size` appears only in the labs output and is absent
  from the `admins` and `ovk` outputs. This test MUST pass before the PR is merged (task 2 DoD
  gate).

- [ ] T2. Flag presence test: after ArgoCD sync (task 3), inspect the running labs pod's process
  arguments as described in task 3. Assert that `--max-heap-size=<N>` is present with the correct
  numeric value. Record the verification command and output in the PR or task tracker.

- [ ] T3. GC pressure smoke test: while the labs pod is running with the cap applied, simulate a
  moderate allocation spike (e.g., by triggering a bulk skill reload or an unusually large incoming
  message batch if a safe way exists in labs). Observe that (a) V8 GC activates and reclaims memory
  without crashing the pod, and (b) heap returns below 90% of N within a reasonable time window
  (under 60 s). If the pod crashes during this test, the cap is too low — raise N per the formula
  in task 1 and repeat.

- [ ] T4. No-regression baseline check: compare CPU and memory metrics from 24 h before and 48 h
  after the cap is applied (task 4 observation window). Assert no statistically significant CPU
  increase (more than 10% above the pre-change p95) that would indicate GC thrashing under normal
  load.

## Rollback

If the heap cap causes problems (excessive GC, unexpected OOM restarts, or degraded throughput) the
change can be reversed in under five minutes:

1. Open the labs helm overlay in mctl-gitops.
2. Remove or comment out the `NODE_OPTIONS: "--max-heap-size=<N>"` line (or revert the container
   command args if Option B was used in task 3).
3. Commit and push; ArgoCD will automatically sync and restart the labs pod without the flag.
4. Verify the pod comes up healthy and the restore-state probe passes (ADR-0002).
5. If the rollback was triggered by OOM restarts: wait for the pod to stabilise, then re-run the
   profiling from task 1 with a longer observation window before attempting a second deployment.

No S3 state, no schema, and no other tenant is affected by this rollback. The `admins` and `ovk`
tenants are not touched at any point in this proposal and require no rollback action.
