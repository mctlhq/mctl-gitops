# Tasks: issue-2245-spike-would-victorialogs-beat-the-curren

Scope of this change is the offline half (design.md "Offline half"). The live
round is a separate owner-gated change that follows the runbook from task 7.

- [ ] 1. Write `docs/adr/0002-log-backend.md` (Status: Proposed): question and
  the issue's boundary, candidates `loki-current` and `victorialogs`, current
  state facts from `bootstrap/templates/observability/loki.yaml`, the weight
  table and decision rule from design.md, consumers that a migration would
  touch (mctl-api `LOKI_URL`, `loki-datasource.yaml`, protected-app lists in
  `wft-create-tenant.yaml` / `wft-delete-tenant-safe.yaml`), and an empty
  verdict record. — DoD: ADR states that no change is recommended from
  ingestion numbers alone and lists every rubric dimension.
- [ ] 2. Write `docs/adr/0002-rubric.yaml` with the eight dimensions, weights
  summing to 100 and every candidate `score: null`, `citation: ""`
  (depends on 1). — DoD: weights match the ADR table exactly.
- [ ] 3. Add `tests/test_adr0002_rubric_frozen.py`, modelled on
  `tests/test_adr_rubric_frozen.py` (depends on 2). — DoD: fails if any score
  is set while the ADR verdict record is empty, if weights disagree with the
  ADR table, or (once scored) if any cell lacks a citation.
- [ ] 4. Add the `logsEval:` block to `platform-gitops/bootstrap/values.yaml`
  (`enabled: false`, `teardownAfter: ""`, quota values, `candidate` with
  `enabled: false` and empty `repoURL`/`chart`/`targetRevision`, `values`
  with 14d retention and the chart ServiceMonitor disabled). — DoD: comments
  cite ADR 0002 and say pins are filled by the live round.
- [ ] 5. Add gated templates (depends on 4):
  `bootstrap/templates/observability/logs-eval-namespace.yaml` (namespace
  `logs-eval`, teardown annotation, ResourceQuota, LimitRange, default-deny,
  intra-namespace, ingress from Promtail/vmagent/Grafana only),
  `bootstrap/templates/observability/logs-eval-candidate.yaml` (Application
  `logs-eval-victorialogs`, selfHeal off, second source
  `infra-components/observability/logs-eval/`),
  `infra-components/observability/logs-eval/servicescrape.yaml`
  (VMServiceScrape), and a gated `victorialogs-eval` Grafana datasource
  ConfigMap. — DoD: `helm template` of `platform-gitops/bootstrap` with
  defaults renders none of them; with both flags on (and dummy pins) all
  render and pass kubeconform in `validate-manifests.yml`.
- [ ] 6. In `bootstrap/templates/observability/loki.yaml`, append a second
  Promtail client only when `logsEval.enabled` and the candidate is enabled:
  VictoriaLogs Loki-compatible push URL, bounded `backoff_config`
  (`max_retries` <= 3, `max_period` <= 10s), placed after the existing Loki
  client (depends on 4). — DoD: default render of the `loki-stack`
  Application is byte-identical to `main`.
- [ ] 7. Generalise `scripts/validate-eval-teardown-date.py` to a list of
  (enabled, teardownAfter) key pairs including `logsEval.*`, extend
  `--selftest` (depends on 4). — DoD: existing `otelCollector.eval` behaviour
  unchanged; new selftest cases pass in `validate-manifests.yml`.
- [ ] 8. Write `docs/runbooks/log-backend-bake-off.md`: pin verification
  steps, capacity check, opening the sandbox, the 7-day soak, the exact
  measurement queries (VictoriaMetrics series and the five-query latency set
  from design.md), the outage test, the retention and tenancy checks, kill
  switch, teardown and rubric filling; link it from `CLAUDE.md`'s runbook
  list. (depends on 1, 5, 6) — DoD: every rubric dimension maps to a named
  measurement step.
- [ ] 9. Add a VMRule (gated with the sandbox) alerting when Loki's ingested
  lines rate drops >50% vs 1h earlier while `logsEval` is open, with a unit
  test under `vm-rules/tests/` (depends on 6). — DoD: `scripts/check-vm-rules.sh`
  passes.

## Tests

- [ ] T1. `tests/test_adr0002_rubric_frozen.py` passes on the committed
  files and fails on a fixture with one score filled and no verdict.
- [ ] T2. `scripts/validate-eval-teardown-date.py --selftest` covers, for
  `logsEval`: closed with empty date (pass), open with empty date (fail),
  past date (fail), > 14 days (fail), within window (pass).
- [ ] T3. Render test: `helm template` of `platform-gitops/bootstrap` with
  default values yields output identical to the base branch for every
  existing object (in particular the `loki-stack` Application and its
  Promtail `clients`), and contains no `logs-eval` objects.
- [ ] T4. Render test with `logsEval.enabled: true` and the candidate
  enabled: namespace, quota, NetworkPolicies, Application, scrape, datasource
  and the second Promtail client render; the Loki client is still first.
- [ ] T5. VMRule unit test for the Loki-ingestion-drop alert (fires on a
  drop, silent on steady rate).

## Rollback

The offline change renders nothing by default, so rollback is a plain
`git revert` of the merge commit. If the sandbox is later open and misbehaves
(Promtail back-pressure, quota pressure, Loki ingestion drop), set
`logsEval.enabled: false` in `platform-gitops/bootstrap/values.yaml` and
merge: ArgoCD prunes `logs-eval` (including the PVC) and Promtail rolls back
to the single Loki client. Production Loki, its R2 data, retention and every
consumer are never modified by this proposal, so no data restore is needed.
