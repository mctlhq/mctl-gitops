# Tasks: issue-1771-observability-critical-and-alerting-path

- [ ] 1. Capture a baseline routing table. Render today's config from `main`
  and run `amtool config routes test` for every alert in `vm-rules/*.yaml`
  (its own labels) plus the sample cases in design.md. Save the results as
  `tests/fixtures/alertmanager-routes-baseline.txt` for reference in the PR
  description. — DoD: the baseline table exists and shows the 10 critical
  vm-rules alerts that currently reach `mctl-agent` only.
- [ ] 2. In `platform-gitops/bootstrap/templates/observability/monitoring.yaml`,
  move every `receiver: "null"` child route to the top of `route.routes`,
  keeping their relative order and comments (depends on 1). — DoD: re-running
  task 1's table gives identical receivers for every case.
- [ ] 3. Add the matcher `severity != "critical"` to each existing
  `continue: true` Telegram route: `MctlTelegramCanary.*`, `AccessLogin.*`,
  `ArgoCDApplicationDegraded|ArgoCDApplicationOutOfSyncLong` (project
  `default|platform`), the three `*FastBurn` routes,
  `MctlAgentDeadLetter|MctlAgentActionsExecutingStuck|MctlAgentClaudeUsageLimit`,
  and `MctlApi.*` (depends on 2). — DoD: each route carries the matcher, with
  a one-line comment saying critical variants are paged by the severity route.
- [ ] 4. Confirm the upstream vm `ServiceDown` rule's `job` label values for
  vmalert and vmalertmanager in chart `victoria-metrics-k8s-stack` 0.72.5 (for
  example with `helm template` of the chart and a grep of the VMRule). —
  DoD: the `job` regex used in task 5 is backed by the rendered rule and
  quoted in the PR description.
- [ ] 5. Insert the two meta-alert routes (telegram, `continue: true`,
  `severity != "critical"`; matchers from design.md) and then the severity
  route (`receiver: telegram`, `continue: true`, `severity = "critical"`).
  Place them after the last terminal Telegram route
  (`ArgoLocalWorkdirPodPending|...`) and before the two existing
  `mctl-agent` routes (depends on 3, 4). — DoD: the routes are present with
  comments explaining the circularity and why null routes must come first.
- [ ] 6. Append a final matcher-less `- receiver: mctl-agent` route after the
  existing catch-all, with a comment that it restores the root default for
  alerts matched by a `continue: true` route. Update the
  `PoolNearCapacity`/`FloodWaitSpike` "deliberately agent-only" comment to
  say their critical variants now also page Telegram (depends on 5). — DoD:
  `KubeAPIDown` severity=critical routes to `telegram,mctl-agent`.
- [ ] 7. Add `tests/test_alertmanager_routing.py` as described in design.md:
  helm render, config extraction with secret-file placeholders,
  `amtool check-config`, a case table, the generated "every critical vm-rules
  alert reaches telegram exactly once" check, `amtool` from PATH or a pinned
  download verified by sha256, and `--selftest` (depends on 6). — DoD:
  `python3 tests/test_alertmanager_routing.py --selftest && python3
  tests/test_alertmanager_routing.py` exits 0 locally. The self-test fails a
  config with the severity route removed.
- [ ] 8. Add one step to `.github/workflows/validate-manifests.yml` after
  "Check and unit-test alerting rules" that runs the two commands from task
  7 (depends on 7). — DoD: the `validate-manifests` job is green on the PR,
  and this step is the only workflow change.

## Tests

- [ ] T1. `amtool check-config` passes on the rendered Alertmanager config.
- [ ] T2. `KubeAPIDown` with `severity=critical` routes to `telegram,mctl-agent`.
- [ ] T3. `PodCrashLooping` with `severity=warning` routes to `mctl-agent`.
- [ ] T4. `Watchdog` routes to `null`. `InfoInhibitor` routes to `null`.
- [ ] T5. `KubeSchedulerDown`, `KubeControllerManagerDown` and `KubeProxyDown`
  with `severity=critical` route to `null`.
- [ ] T6. `VaultBackupStale` with `severity=critical` routes to `telegram`
  only, exactly once.
- [ ] T7. `MctlApiDown` with `severity=critical` routes to
  `telegram,mctl-agent`, with exactly one `telegram`.
- [ ] T8. `MctlAgentMetricsAbsent` with `severity=warning` routes to
  `telegram,mctl-agent`.
- [ ] T9. `AlertmanagerFailedReload` and `AlertmanagerFailedToSendAlerts` with
  `severity=critical` route to `telegram,mctl-agent`, with exactly one
  `telegram`.
- [ ] T10. `ServiceDown` with the vmalert `job` label, at both `warning` and
  `critical`, routes to `telegram,mctl-agent`, with exactly one `telegram`.
- [ ] T11. Every `severity: critical` alert parsed from `vm-rules/*.yaml`
  (with its static labels) reaches `telegram` exactly once.
- [ ] T12. Non-critical regression cases route as before:
  - `MctlTelegramPoolNearCapacity` at warning goes to `mctl-agent`.
  - `ArgoCDApplicationDegraded` with project=platform at warning goes to
    `telegram,mctl-agent`.
  - `SeerrSense*` goes to `telegram`.
  - `KubeJobFailed` in namespace=labs goes to `null`.
- [ ] T13. `--selftest`: with the severity route removed from the config, the
  test fails.

## Rollback

Revert the PR. The route changes live in one file, `monitoring.yaml`, and
Argo CD resyncs the `monitoring` Application. The VM operator then reloads
vmalertmanager with the previous config, and no state is migrated. Do not just delete the
`severity = "critical"` route on its own. Task 3's `severity != "critical"`
matchers depend on it, so deleting it alone would take Telegram away from
the critical canary, MctlApi and FastBurn alerts. A partial rollback has to
remove the severity route and task 3's matchers together, and the test's
case table has to be updated to match.
