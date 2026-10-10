# Tasks: issue-1773-observability-probe-portal-docs-ops-graf

- [ ] 1. Hand-check every target (read-only) from inside the cluster's egress path,
  for example `kubectl -n monitoring run curl --rm -it --image=curlimages/curl -- curl -s -o /dev/null -w '%{http_code}\n' <url>`,
  or through blackbox-exporter `/probe?module=http_2xx&target=<url>&debug=true`.
  Targets: `https://app.mctl.ai/.backstage/health/v1/readiness`, `https://docs.mctl.ai/`,
  `https://ops.mctl.ai/healthz`, `https://grafana.mctl.ai/api/health`,
  `https://agent.mctl.ai/healthz`, and `https://<host>/api/method/ping` for every host of
  `kubectl -n erpact get ingress -o jsonpath='{..host}'`. — DoD: every target answers
  a stable 2xx (or a replacement path is chosen and the reason recorded), and a table
  of target and status code is ready for the PR body.
- [ ] 2. Add VMProbe `platform-consoles` to
  `platform-gitops/infra-components/observability/blackbox/vmprobes.yaml` (jobName
  `platform-consoles`, `http_2xx`, `60s`, five static targets), with a comment that
  explains each path, in the file's style (depends on 1). — DoD: kubeconform passes in
  `validate-manifests.yml`, and after sync vmagent `/targets` shows 5 up targets for
  job `platform-consoles`.
- [ ] 3. Add `platform-gitops/infra-components/observability/vm-rules/platform-console-alerts.yaml`
  (VMRule `mctl-platform-console-alerts`, rules `PlatformConsoleDown` for 5m warning and
  `PlatformConsoleProbeAbsent` for 15m warning) and
  `vm-rules/tests/platform-console-alerts_test.yaml`. — DoD: `scripts/check-vm-rules.sh`
  passes locally and in CI.
- [ ] 4. Add the Telegram-only route `alertname =~ "PlatformConsole.*"` in
  `platform-gitops/bootstrap/templates/observability/monitoring.yaml`, above the
  mctl-agent catch-all routes, with a comment (why Telegram-only: agent.mctl.ai is
  mctl-agent itself) (depends on 3). — DoD: `helm template` of the bootstrap chart renders.
  `amtool config routes test --config.file=<rendered alertmanager config> alertname=PlatformConsoleDown`
  prints `telegram`.
- [ ] 5. Switch VMProbe `erpact-sites` from `targets.staticConfig` to
  `targets.ingress` (namespaceSelector `erpact`, one target per host,
  `__param_target`/`instance` = `https://<host>/api/method/ping`), and update its
  comment (depends on 1). Confirm vmagent RBAC for ingresses in `erpact`. If
  it is missing, add a read-only Role/RoleBinding under
  `platform-gitops/bootstrap/templates/erpact/`. — DoD: vmagent `/targets` for job
  `erpact-sites` lists every Ingress host from task 1 exactly once, all up. Instance
  strings for the five old sites are byte-identical to the old ones.
- [ ] 6. Add `ErpactSiteUnprobed` (Ingress host in `erpact` with no matching
  `probe_success{job="erpact-sites"}` instance for 15m, warning) to
  `vm-rules/erpact-alerts.yaml` group `erpact.availability`, with test cases in
  `vm-rules/tests/erpact-alerts_test.yaml` (an unprobed host fires; a probed host
  stays quiet) (depends on 5). — DoD: `scripts/check-vm-rules.sh` passes. A live query
  returns empty after the sync.
- [ ] 7. Route `ErpactSite.*` to Telegram with `continue: true`, and append
  `ErpactSite.*` to the mctl-agent catch-all regex in `monitoring.yaml` (independent; drop it
  if the reviewer rejects it). — DoD: `amtool config routes test` for `ErpactSiteDown`
  prints both `telegram` and `mctl-agent`.
- [ ] 8. Open the PR with the status-code table from task 1, the discovered ERPact site
  list, and screenshots or excerpts of vmagent `/targets` (depends on 2-7). — DoD:
  the PR body meets acceptance criterion "PR lists observed status code per target",
  and CI (`validate-manifests.yml`, `yamllint.yml`) is green.

## Tests

- [ ] T1. promtool `PlatformConsoleDown`: a healthy series stays quiet, 4 failed probes in a row
  stay quiet, 6 failed probes in a row fire with `severity=warning`,
  `service=platform` and the instance in the summary.
- [ ] T2. promtool `PlatformConsoleProbeAbsent`: no series for 15m fires. A present series
  stays quiet.
- [ ] T3. promtool `ErpactSiteUnprobed`: `kube_ingress_path{namespace="erpact",host="erpact-new.mctl.ai"}`
  with no matching probe series fires after 15m. The same host with
  `probe_success{job="erpact-sites",instance="https://erpact-new.mctl.ai/api/method/ping"}`
  stays quiet.
- [ ] T4. Existing `erpact-alerts_test.yaml` and `blackbox-alerts_test.yaml` pass unchanged.
- [ ] T5. Live check after the Argo CD sync: `probe_success{job="platform-consoles"}`
  has 5 series equal to 1. `count(probe_success{job="erpact-sites"})` equals the number
  of distinct Ingress hosts in `erpact` (8 expected per the audit).
- [ ] T6. Routing check with `amtool config routes test` on the rendered Alertmanager
  config for `PlatformConsoleDown` (telegram) and `ErpactSiteDown` (telegram plus
  mctl-agent).

## Rollback

Revert the PR. Argo CD restores the static `erpact-sites` target list and removes
the `platform-consoles` VMProbe, the new VMRule and the routes on the next sync. The
VMRule and VMProbe are removed together, so no absence alert is left pointing at a
missing job. If only the ERPact discovery misbehaves (wrong or zero targets), revert
just the `erpact-sites` hunk and the `ErpactSiteUnprobed` rule. The console probes
are independent of it. No data migration or state is involved.
