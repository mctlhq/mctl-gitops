# Design: issue-1593-alert-on-scheduled-dispatch-failures-and

## Current state
- `platform-gitops/infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml`
  is a `VMRule` (`namespace: monitoring`) with two groups:
  - `mctl-agents.queue-saturation` (ADR-008). Four rules with
    `mctl_agent_self: "true"`. These fall through to the root `mctl-agent`
    receiver.
  - `mctl-agents.implementation-admission`. `MctlAgentsImplement*` rules with
    `namespace: admins`, routed to Telegram.

  The header records two facts read off a live worker: durations are in seconds
  (`durations_as_seconds`), and roles are told apart only by `task_queue`,
  because every role reports `service_name="temporal-core-sdk"`.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-agents-worker-monitor.yaml`
  is one `VMServiceScrape` that scrapes `port: http` `/metrics` every 30s on
  `admins-mctl-agents-worker{,-exec,-implement}`.
- `platform-gitops/bootstrap/templates/observability/monitoring.yaml` (around
  lines 584-597) holds the explicit Telegram route
  `alertname =~ "MctlAgentsImplement.*"`. Prefix routes are the documented
  convention ("the next alert must not default to agent-only"). The catch-all
  `mctl-agent` receiver handles everything else.
- `vm-rules/tests/mctl-agents-worker-alerts_test.yaml` holds promtool tests
  against `generated/mctl-agents-worker-alerts.yaml`, which
  `scripts/check-vm-rules.sh` extracts from the VMRule `.spec`. CI runs it in
  `.github/workflows/validate-manifests.yml` (lines 336-337).
- Precedent for "a counter in a long-lived pod is born at 1":
  `LifecycleClaimAbandoned` in `vm-rules/lifecycle-rollout-alerts.yaml` (lines
  150-180) uses `increase(x[1h]) > 0 or (max_over_time(x[1h]) > 0 unless
  max_over_time(x[1h] offset 1h) > 0)`. `increase()` under promtool/Prometheus
  semantics cannot see the first increment of a new series.
- The mctl-agents side, from the agents-state proposals in this repo:
  `ScheduledDispatchWorkflow` is registered on the control plan only, so it runs
  on `task_queue="mctl-dev-loop"` (issue-559 design, section 4 and line 177). A
  terminal failure re-raises, so the execution is Failed and shows up in the SDK
  workflow-failed metric. #561 adds
  `workflow.metric_meter().create_counter("scheduled_dispatch_alert_undelivered")`
  with labels `repo` and `workflow_file`. Because the counter comes from
  `workflow.metric_meter()`, it should also carry the workflow-context labels
  (`namespace`, `task_queue`, `workflow_type`).

## Owner corrections (2026-10-04, before approval)

**C1. Live metric names, read off `admins-mctl-agents-worker` (mctl-agents 1.67.0, includes #561) at 2026-10-04 ~12:55 UTC:**
```
# TYPE temporal_workflow_completed counter
temporal_workflow_completed{namespace="mctl-agents",service_name="temporal-core-sdk",task_queue="mctl-dev-loop",workflow_type="IssuePollWorkflow"} 1
temporal_worker_task_slots_available{namespace="mctl-agents",service_name="temporal-core-sdk",task_queue="mctl-dev-loop",worker_type="WorkflowWorker"} 100
```
So: no `_total` suffix, `temporal_` prefix, and labels `namespace, service_name, task_queue, workflow_type`. `temporal_workflow_failed` follows the same family, but it has no series yet because no workflow has failed since boot. The undelivered counter only appears on its first increment, so its prefix cannot be read yet. **Rule 1 MUST match the name with `{__name__=~"(temporal_)?scheduled_dispatch_alert_undelivered"}`** so it works whether or not the Core exporter prefixes custom metrics. Tests cover both spellings. Task 1 (port-forward) is DONE by the operator: the implementer runs without cluster access and must use these names, not guess.

**C2. The rule-3 worker gate MUST aggregate across series.** Worker pods are replaced on every deploy, often several times a day, and each pod is a new series (new `instance`/`pod` labels). A per-series `count_over_time(...[8d]) > 0.9 × samples` is then almost never true, so the silent-miss alert would be dead in practice. Use `sum(count_over_time(temporal_worker_task_slots_available{task_queue="mctl-dev-loop",worker_type="WorkflowWorker"}[8d]))` against the threshold. Overlap during a rollout only raises the sum, which is harmless. Add a test, T10: the gate series is split across three pods (consecutive, different `instance`) covering the whole 8d, with no completion. The rule FIRES. With a per-series gate this test fails. In the same spirit, arms A and B already `sum(...)` across series. Keep that.

## Proposed solution

### Step 0: confirm names on a live worker (gating)
Run
`kubectl -n admins port-forward deploy/admins-mctl-agents-worker 8080` and then
`curl -s :8080/metrics | grep -E 'workflow_(completed|failed)|scheduled_dispatch'`.
Record the exact names and label sets in the PR description. ADR-008 D5
established the same method. The expressions below use the expected names:
`temporal_workflow_completed`, `temporal_workflow_failed` and
`temporal_scheduled_dispatch_alert_undelivered`. Substitute the confirmed names
everywhere, both rules and tests. If the `failed`/`completed` series have not
appeared yet because no run has happened since the pod started, read them on a
worker that has completed any workflow. The metric family is shared by every
workflow type.

### New group `mctl-agents.scheduled-dispatch`
Add it after the admission group. All rules use the selector
`workflow_type="ScheduledDispatchWorkflow"` (rules 2 and 3) plus
`task_queue="mctl-dev-loop"`, so another team's workflow with the same generic
SDK metric names cannot match. That is the same reasoning as the
`temporal_worker_task_slots_available` guard. Labels are `severity: warning` and
`namespace: admins`, matching the admission group. Alertnames share the prefix
`MctlAgentsScheduledDispatch` so a single route covers them.

1. `MctlAgentsScheduledDispatchAlertUndelivered`. Uses the
   `LifecycleClaimAbandoned` two-arm shape, aggregated `by (repo, workflow_file)`
   so the receiver sees which target failed:
   ```
   sum by (repo, workflow_file) (increase(temporal_scheduled_dispatch_alert_undelivered[1h])) > 0
   or
   (
     sum by (repo, workflow_file) (max_over_time(temporal_scheduled_dispatch_alert_undelivered[1h])) > 0
     unless
     sum by (repo, workflow_file) (max_over_time(temporal_scheduled_dispatch_alert_undelivered[1h] offset 1h)) > 0
   )
   ```
   No `for:`. The event is a discrete, rare, already-confirmed failure. The 1h
   window keeps the alert up for about an hour so Alertmanager delivers it. This
   is the only remaining channel for the failure, so the description names the
   worker log marker to grep and the remedy: check the GitHub App token and
   re-run the dispatch by hand.

2. `MctlAgentsScheduledDispatchFailed`. The same two-arm shape on
   `temporal_workflow_failed{workflow_type="ScheduledDispatchWorkflow",task_queue="mctl-dev-loop"}`,
   aggregated with `sum` (no repo label is available on SDK metrics). It is a
   backstop that also fires when the GitHub issue was filed. The description
   points at the `scheduled-dispatch-failed` issue in the target repo and the
   Temporal UI.

3. `MctlAgentsScheduledDispatchMissed` (silent miss). Window 8d, which is one
   weekly period plus a day of slack. The semantics are stated in a rule comment:
   ```
   (
     absent(
         sum(increase(temporal_workflow_completed{workflow_type="ScheduledDispatchWorkflow",task_queue="mctl-dev-loop"}[8d])) > 0
       or
         sum(last_over_time(temporal_workflow_completed{...}[8d])
             unless temporal_workflow_completed{...} offset 8d) > 0
     )
   )
   and on()
   (
     count_over_time(temporal_worker_task_slots_available{task_queue="mctl-dev-loop",worker_type="WorkflowWorker"}[8d])
       > <8d of 30s scrapes x 0.9>
   )
   ```
   (The implementer picks the concrete `worker_type` and sample count from the
   live scrape. A simpler gate,
   `min_over_time(up{...}[8d])`-style, is acceptable if it gives the same
   behaviour. What matters is that "worker observed for nearly the whole window"
   is required.)
   - Arm A, `increase()`: any existing series grew in the window, so a
     completion was observed.
   - Arm B, `last_over_time ... unless ... offset 8d`: a series that exists in
     the window but did not exist 8 days ago. After a worker restart, the counter
     reappears only when a workflow completes, born at 1. Arm A cannot see that,
     so Arm B counts it as a completion. This is why a restart reads as still-OK.
   - `absent(...)` turns "no evidence of a completion" into 1. That makes the rule
     an observed-absence alert only through the gate.
   - The gate (`and on()` over the worker's own always-exported series) makes a
     scrape gap or a down worker read as unknown, not as a miss. If the worker
     was not observed for most of the window, the rule returns empty, and
     `MctlAgentsWorkerMetricsMissing` covers that state. "Could not observe" is
     never reported as "observed absent".
   - `for: 1h`, so a single rule evaluation over a VM storage hiccup cannot fire
     it.

### Routing
Add a route in `monitoring.yaml` right after the `MctlAgentsImplement.*` route:
`receiver: telegram`, `matchers: [alertname =~ "MctlAgentsScheduledDispatch.*"]`.
Add a comment explaining that the remedy is a human action (fix the App token,
re-create or unpause the schedule, re-run the dispatch), and that a prefix is
used so the next dispatch alert cannot default to agent-only. Leave the ADR-008
and admission routes as they are.

### Tests
Append a section to `vm-rules/tests/mctl-agents-worker-alerts_test.yaml`. Each
rule gets a firing case and a quiet case at minimum. Rule 3 gets the restart
case and the scrape-gap case as well. Long windows are cheap with
`interval: 1h` test blocks: 8d is 192 samples. promtool rejects a test whose
`interval` does not divide the rule window. 1h divides 8d and 1h, so use 1h for
the rule-3 blocks and 1m for rules 1 and 2.

## Alternatives
- **Plain `increase(x[w]) > 0` for rules 1 and 2.** Dropped. Under Prometheus
  and promtool semantics it misses the first increment of a series born at 1,
  and in a long-lived worker that is the only increment that matters. The repo
  already learned this in `LifecycleClaimAbandoned`.
- **`absent_over_time(temporal_workflow_completed{...}[8d])` alone for the miss.**
  Dropped. It cannot tell "never completed" apart from "metrics not scraped". It
  also stays silent on a long-lived pod whose series exists from a run more than
  8 days ago, which is exactly the deleted-schedule case.
- **Alert on the Temporal schedule itself** (schedule info or next action time
  through the Temporal server's metrics, or a probe that lists schedules).
  Dropped for now. The cluster scrapes no Temporal-server metric for schedules,
  and a probe adds a new component. The completed-counter approach uses series
  that are already scraped.
- **Loki rule on the `scheduled_dispatch_alert_undelivered` log line.** Dropped
  as redundant with the counter, and the issue asks for vm-rules.

## Platform impact
- No migration. The change is additive: one VMRule group, one Alertmanager route,
  and tests. Existing rules and routes are unchanged.
- Resource cost is negligible: three rules. The 8d range queries touch one
  low-cardinality series family every evaluation, and VM handles that easily.
  The rule-3 gate scans about 23k samples of one series, which is acceptable.
- Risks:
  - Wrong metric name, so the rule silently never fires. Mitigation: Step 0 is
    gating, and the scraped lines are quoted in the PR.
  - Prometheus (promtool) and VictoriaMetrics `increase()` differ on the first
    sample of a series. VM may count it, Prometheus does not. Mitigation: the
    two-arm shapes are correct under both semantics. Under VM they can at worst
    be redundant, never silent.
  - Rule 3 false positive before the first recorded run, or after more than 8
    days of a deliberately paused schedule. Mitigation: documented in the rule
    description. A deliberate pause should be paired with an Alertmanager
    silence.
  - Rule 1 cannot fire until mctl-agents#561 is deployed. That is acceptable and
    stated in the PR.
