# Deliver the gated offline half of the ADR 0002 log-backend bake-off (issue-2245 slice 2)

## Context

Issue #2245 asked whether VictoriaLogs would beat the current log backend
(`loki-stack`, Loki 2.9.17 on R2) on the real MCTL workload. Its accepted
proposal (`platform-gitops/agents-state/mctl-gitops/proposals/issue-2245-spike-would-victorialogs-beat-the-curren/`)
splits the work into an offline half, which commits gated, default-off
manifests, and a separate owner-gated live round that flips one flag and
follows a runbook. Implementer PR #2250 delivers slice 1 of the offline half:
`docs/adr/0002-log-backend.md`, the frozen `docs/adr/0002-rubric.yaml` with
`tests/test_adr0002_rubric_frozen.py` in CI, the `logsEval:` values block in
`platform-gitops/bootstrap/values.yaml` (disabled), and the generalised
`scripts/validate-eval-teardown-date.py`. As of 2026-10-29, #2250 is still
open and not merged to `main` (checked with `gh pr view 2250`).

This issue delivers the rest of the accepted offline scope:
- the gated `logs-eval` sandbox (namespace, candidate Application,
  VMServiceScrape, Grafana datasource);
- a default-off second Promtail client with bounded retries;
- the bake-off runbook;
- a gated alert on a Loki ingestion drop, with a unit test;
- render and CI coverage for both flag states.

The live 7-day round is NOT started. Production Loki, its R2 data, its
retention and its single Promtail client stay unchanged in the default
render.

## User stories

- AS the platform owner I WANT every sandbox manifest for the log-backend
  bake-off reviewed and merged ahead of time SO THAT opening the live round is
  a values edit, not a new design review under time pressure.
- AS the platform owner I WANT the Promtail dual-write to the candidate to be
  bounded and alerting SO THAT a candidate outage cannot silently degrade log
  delivery to Loki, including the Vault audit stream.
- AS an operator running the live round I WANT a runbook that maps every ADR
  0002 rubric dimension to a named measurement step SO THAT the rubric can be
  filled with cited evidence, not impressions.
- AS a reviewer I WANT CI to render both `logsEval.enabled=false` and
  `logsEval.enabled=true` SO THAT "nothing changes by default" is a check,
  not a claim.

## Acceptance criteria (EARS)

- WHILE `logsEval.enabled` is false (the committed default) THE SYSTEM SHALL
  render no object in namespace `logs-eval`, no `logs-eval-victorialogs`
  Application, no VictoriaLogs Grafana datasource and no `LogsEval.*`
  Alertmanager route from `platform-gitops/bootstrap`.
- WHILE `logsEval.enabled` is false THE SYSTEM SHALL render the `loki-stack`
  Application with exactly one Promtail client,
  `http://loki-stack:3100/loki/api/v1/push`. The `loki-stack`,
  `monitoring` and `default` AppProject objects shall be byte-identical to
  their render on `main` before this change.
- WHEN `logsEval.enabled` is true THE SYSTEM SHALL render namespace
  `logs-eval` with the `mctl.ai/teardown-after` annotation, a ResourceQuota
  from `logsEval.quota`, a LimitRange, NetworkPolicies (default-deny,
  intra-namespace, DNS egress, and ingress on the candidate port only from
  the Promtail, vmagent and Grafana pods in `monitoring`), and add `logs-eval`
  to the `default` AppProject destinations.
- WHEN `logsEval.enabled` and `logsEval.candidate.enabled` are both true THE
  SYSTEM SHALL render:
  - the Application `logs-eval-victorialogs`, with `prune: true`, no
    `selfHeal`, and a second source
    `platform-gitops/infra-components/observability/logs-eval/` that carries
    the VMServiceScrape;
  - the Grafana datasource ConfigMap `victorialogs-eval-grafana-datasource`;
  - the `victoriametrics-logs-datasource` Grafana plugin;
  - a second Promtail client placed after the Loki client.
- WHEN the second Promtail client is rendered THE SYSTEM SHALL configure it
  with `backoff_config.max_retries` <= 3, `backoff_config.max_period` <= 10s
  and a client `timeout` <= 10s. Its URL shall be derived from
  `logsEval.candidate.endpoint` and point inside the `logs-eval` namespace.
- IF `logsEval.candidate.enabled` is true and `logsEval.candidate.endpoint`
  is empty or not a `*.logs-eval.svc*` URL THEN THE SYSTEM SHALL fail the
  Helm render with a message naming the key.
- WHILE Promtail has a client whose `host` is in `logs-eval`, and Promtail's
  sent-entries rate to `loki-stack:3100` over 15m is below 50% of the same
  rate 1h earlier for 10m, THE SYSTEM SHALL fire
  `LogsEvalLokiIngestionDrop`.
- WHILE no Promtail client points into `logs-eval` THE SYSTEM SHALL keep
  every `LogsEval*` alert silent, however Loki's ingestion rate moves.
- WHEN `scripts/check-vm-rules.sh` runs in CI THE SYSTEM SHALL unit-test
  each `LogsEval*` rule both ways (fires on the failure shape, silent on
  steady rate and silent with the sandbox closed).
- WHEN `validate-manifests.yml` runs THE SYSTEM SHALL do all of the
  following, and fail on any assertion:
  - render `platform-gitops/bootstrap` with the committed values and with
    the overlay `tests/fixtures/logs-eval.example-values.yaml`;
  - kubeconform the enabled render;
  - run the AppProject scope check on it;
  - run `tests/test_logs_eval_render.py`.
- THE SYSTEM SHALL provide `docs/runbooks/log-backend-bake-off.md`, which
  maps every ADR 0002 rubric dimension key to at least one named measurement
  step and gives the kill switch and teardown. `CLAUDE.md` shall link it.
- WHILE this change is merged THE SYSTEM SHALL leave `docs/adr/0002-rubric.yaml`
  and `docs/adr/0002-log-backend.md` unmodified, so that
  `tests/test_adr0002_rubric_frozen.py` keeps passing.

## Out of scope

- Opening the sandbox, filling the candidate pins (`repoURL`, `chart`,
  `targetRevision`) with real values, or starting the 7-day soak. This is the
  owner-gated live round.
- Any change to production Loki: image, chart version, R2 bucket `loki`,
  `retention_period`, `retention_stream`, `limits_config`, mctl-api
  `LOKI_URL`, `loki-datasource.yaml`.
- Editing ADR 0002 or its rubric, and filling the verdict.
- The teardown-date validator: #2250 already generalises it to `logsEval.*`.
- A separate shipper (vlagent, Vector) for VictoriaLogs.
- Scraping Loki's own `/metrics`. The alert uses the Promtail-side counters
  that are already scraped by `promtail-podscrape.yaml`.

## Open questions

- Hard dependency on #2250: the `logsEval:` values block, ADR 0002 and the
  teardown validator exist only on #2250's branch. This change must be built
  on `main` after #2250 merges, or rebased onto it. If #2250's values block
  changes before merge, task 1 adapts to the merged shape.
- `logsEval.candidate.endpoint` and `logsEval.candidate.port` are not in
  #2250's values block. This proposal adds them, empty or with the VictoriaLogs
  default port 9428. The owner may prefer different key names.
- The candidate chart's Service labels and metrics port name cannot be
  verified offline, because no chart pin exists yet. The VMServiceScrape
  selects on `app.kubernetes.io/instance: logs-eval-victorialogs`, the label
  Helm sets from the Argo CD release name, and on the port name from values.
  The runbook's pin-verification step must confirm both.
- The `host` label value on `promtail_sent_entries_total` was not observed
  live: no read-only tool in this run queries VictoriaMetrics. The rule
  assumes Promtail's documented `host` = URL `host:port` (so
  `loki-stack:3100` for the existing client). The runbook's first step is to
  confirm this before the sandbox opens.
- Severity and routing of `LogsEval*` alerts: the proposal routes them to
  Telegram only (like `Tempo.*`), with the route rendered only while the
  sandbox is open. The owner may want a ticket as well.
