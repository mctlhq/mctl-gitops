# Tasks: issue-2264-feat-observability-deliver-the-gated-off

Precondition: mctlhq/mctl-gitops#2250 is merged, or this branch is based on
it. Do not edit `docs/adr/0002-*` or `scripts/validate-eval-teardown-date.py`.

- [ ] 1. Extend the `logsEval:` block in `platform-gitops/bootstrap/values.yaml`:
  - `candidate.endpoint: ""`, `candidate.port: 9428`,
    `candidate.metricsPortName: http`;
  - `limits` (`default`, `defaultRequest`, `max`, mirroring
    `otelCollector.eval.limits`);
  - `promtailClient: {maxRetries: 2, minPeriod: 500ms, maxPeriod: 5s,
    timeout: 5s}`.

  Every new key gets a comment citing ADR 0002 and the runbook.
  — DoD: `enabled` and `candidate.enabled` stay false; the
  `validate-eval-teardown-date.py` run is unchanged.
- [ ] 2. Add `platform-gitops/bootstrap/templates/observability/_logs-eval.tpl`
  with the helper `logsEval.candidateOpen` (depends on 1):
  - it uses `dig`, so a missing block renders nothing;
  - it returns true only when both flags are true;
  - it calls `fail` when `endpoint` is empty or does not match
    `\.logs-eval\.svc`.

  — DoD: the helper is used by tasks 4-7; it is never re-implemented inline.
- [ ] 3. Add `templates/observability/logs-eval-namespace.yaml`, gated on
  `logsEval.enabled` (depends on 1). It contains:
  - the Namespace with its label and teardown annotation;
  - `default-deny-all`, `allow-intra-namespace` and `allow-dns-egress`;
  - `allow-ingress-from-monitoring` (Promtail, vmagent and Grafana pods,
    `candidate.port` only);
  - the ResourceQuota from `logsEval.quota` and the LimitRange from
    `logsEval.limits`.

  Then edit `templates/projects/project-default.yaml` to append `logs-eval`
  when enabled. — DoD: the default render has no `logs-eval` object, and the
  AppProject is unchanged.
- [ ] 4. Add `templates/observability/logs-eval-candidate.yaml`, the
  Application `logs-eval-victorialogs` (depends on 2, 3):
  - two sources: the chart, and
    `platform-gitops/infra-components/observability/logs-eval`;
  - `prune: true`, no `selfHeal`, and the retry block from
    `eval-candidates.yaml`.

  Also append `candidate.repoURL` in `project-default.yaml` under
  `candidateOpen`. — DoD: renders only when both flags are on.
- [ ] 5. Add `platform-gitops/infra-components/observability/logs-eval/servicescrape.yaml`
  (depends on 4). It is a VMServiceScrape in `logs-eval` that selects
  `app.kubernetes.io/instance: logs-eval-victorialogs`, on port `http`, path
  `/metrics`. Its header comment explains the single-scrape rule (#1159) and
  that the pin step verifies the labels and port. — DoD: kubeconform passes
  with the CRD schemas.
- [ ] 6. Grafana (depends on 2):
  - add `templates/observability/victorialogs-eval-datasource.yaml`
    (ConfigMap `victorialogs-eval-grafana-datasource`, uid
    `victorialogs-eval`, type `victoriametrics-logs-datasource`, url
    `candidate.endpoint`);
  - in `monitoring.yaml`, append `,victoriametrics-logs-datasource` to
    `GF_INSTALL_PLUGINS` only under `candidateOpen`;
  - in `monitoring.yaml`, add the `alertname =~ "LogsEval.*"` route to
    `telegram`, only when `logsEval.enabled`.

  — DoD: the default `monitoring` Application render is byte-identical to
  `main`.
- [ ] 7. In `templates/observability/loki.yaml`, add the second Promtail
  client after the Loki client, under `candidateOpen`:
  - URL `<endpoint>/insert/loki/api/v1/push`;
  - `timeout`, and `backoff_config` (`min_period`, `max_period`,
    `max_retries`) from `logsEval.promtailClient`;
  - `external_labels: {}`;
  - a comment on the fan-out delay bound.

  (depends on 2) — DoD: the default `loki-stack` render is byte-identical to
  `main`; nothing else in `loki.yaml` changes.
- [ ] 8. Add `platform-gitops/infra-components/observability/vm-rules/logs-eval-alerts.yaml`
  (VMRule `logs-eval-alerts`, group `logs-eval.shipper`):
  - `LogsEvalLokiIngestionDrop`;
  - `LogsEvalLokiDroppedEntries`.

  Both are ANDed with the `promtail_sent_entries_total{host=~".+\\.logs-eval\\.svc.*"}`
  gate, and their annotations name the kill switch and the runbook. The
  header explains the data gate (Tempo bake-off precedent). — DoD:
  `scripts/check-vm-rules.sh --selftest` and `scripts/check-vm-rules.sh` pass.
- [ ] 9. Add `tests/fixtures/logs-eval.example-values.yaml`, a fixture-only
  overlay with dummy pins and an in-namespace endpoint (depends on 1).
  — DoD: its header states it is never applied.
- [ ] 10. Add `tests/test_logs_eval_render.py`, covering the off, on and
  guard cases from design.md section 8 (depends on 3-7, 9). — DoD:
  `python3 tests/test_logs_eval_render.py` exits 0, and it fails if the
  second Promtail client is moved before the Loki client or its
  `max_retries` is set to 10.
- [ ] 11. Edit `.github/workflows/validate-manifests.yml` (depends on 9, 10):
  - add a step that renders the overlay and runs kubeconform;
  - add the overlay render to the "Argo CD Applications stay inside their
    AppProjects" step;
  - add a step that runs `tests/test_logs_eval_render.py`.

  — DoD: the workflow is green on the PR.
- [ ] 12. Write `docs/runbooks/log-backend-bake-off.md`:
  - pre-open checks: the `host` label, the ingestion baseline and the
    headroom;
  - pin verification and opening;
  - the soak;
  - measurement steps per rubric key: `ingest_resources`, `storage_cost`,
    `query_latency`, `retention`, `tenant_isolation`, `ha_recovery`,
    `consumer_compat`, `migration_cost`;
  - the kill switch, teardown and rubric filling.

  Link it from the runbook list in `CLAUDE.md`. (depends on 1-8) — DoD:
  every key in `docs/adr/0002-rubric.yaml` is named in at least one
  measurement step, and every alert annotation links to the runbook.
- [ ] 13. Check the render diff (depends on all above): run `helm template
  root platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml`
  on the branch and on `main`, and diff them. — DoD: the diff is empty,
  stated in the PR body.

## Tests

- [ ] T1. Off render (`tests/test_logs_eval_render.py`):
  - no `logs-eval` objects;
  - Promtail clients equal exactly the Loki URL;
  - `GF_INSTALL_PLUGINS` is unchanged;
  - no `LogsEval` route;
  - no VictoriaLogs datasource;
  - AppProject destinations without `logs-eval`.
- [ ] T2. On render with the overlay:
  - namespace, quota, LimitRange and four NetworkPolicies, with ingress only
    from `monitoring` on 9428;
  - the Application with `prune: true`, no `selfHeal` and two sources;
  - the datasource and plugin;
  - Promtail clients of length 2, Loki first, candidate bounded
    (`max_retries` <= 3, `max_period` <= 10s, `timeout` <= 10s);
  - the AppProject includes `logs-eval` and the candidate repo.
- [ ] T3. Guard: `helm template` fails when the candidate is on with an empty
  `endpoint`, and when the `endpoint` is outside `logs-eval`.
- [ ] T4. kubeconform of the on render with the CRD schema location, and the
  AppProject scope check on it.
- [ ] T5. `vm-rules/tests/logs-eval-alerts_test.yaml`:
  - `LogsEvalLokiIngestionDrop` fires on a 60% drop with the candidate
    series present;
  - it is silent on a steady rate, on a 30% drop, and on a 60% drop with no
    candidate series;
  - `LogsEvalLokiDroppedEntries` fires on dropped Loki entries with the
    candidate present, and is silent without the candidate or with zero
    drops.
- [ ] T6. `tests/test_adr0002_rubric_frozen.py` and
  `scripts/validate-eval-teardown-date.py --selftest` still pass, unchanged.

## Rollback

With the committed defaults, nothing new renders except a silent VMRule. A
`git revert` of the merge commit is therefore a complete rollback, with no
data or cluster state to restore. If the sandbox is later opened and Promtail
back-pressure, quota pressure or a `LogsEval*` alert appears, set
`logsEval.enabled: false` in `platform-gitops/bootstrap/values.yaml` and
merge. Argo CD then:
- prunes `logs-eval-victorialogs`, its PVC and the namespace;
- returns Promtail to its single Loki client;
- removes the datasource and plugin (one Grafana restart).

Production Loki, R2 bucket `loki`, retention and every consumer are never
modified by this change.
