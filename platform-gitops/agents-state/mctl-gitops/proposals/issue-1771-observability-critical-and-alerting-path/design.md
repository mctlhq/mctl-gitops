# Design: issue-1771-observability-critical-and-alerting-path

## Current state

- `platform-gitops/bootstrap/templates/observability/monitoring.yaml` is an
  Argo CD `Application` (`monitoring`) for `victoria-metrics-k8s-stack`
  `0.72.5`. Its `helm.values` block contains `alertmanager.config` (around
  lines 500-865):
  - `route.receiver: mctl-agent`, `group_by: ["alertname", "namespace"]`,
    `group_wait: 30s`, `group_interval: 5m`, `repeat_interval: 4h`.
    There are no `inhibit_rules`.
  - About 30 child routes, all keyed on `alertname` (sometimes also
    `namespace` or `project`). None reads `severity`.
  - There are three kinds of child routes:
    1. `"null"` routes. `InfoInhibitor|Watchdog` is first. The rest are spread
       further down: `KubeContainerWaiting`+`vault`, `KubeJobFailed`+`labs`,
       `CPUThrottlingHigh`+`monitoring`,
       `KubeControllerManagerDown|KubeSchedulerDown|KubeProxyDown` (upstream
       critical, but meaningless on k3s), and
       `KubePodNotReady|PodNotReady`+`argo-workflows`.
    2. Terminal Telegram routes (no `continue`). These deliver to Telegram
       only, with no mctl-agent ticket: `KubeJobFailed`+`vault`,
       `VaultBackup*`, `VaultAudit.*`, `MctlAgentsPipelineStale`,
       `SeerrSense.*`, `ErpactMariadbMemory.*`, `ErpactBackup.*`,
       `Lifecycle.*`, `MctlAgentsImplement.*`,
       `MctlAgentsScheduledDispatch.*`, `TempoEval.*`,
       `ArgoCDGitPollingStalled`, `NodeCordoned|K3sUpgradeJobFailed`, and
       `ArgoLocalWorkdir*|NodeDiskSpaceCritical|NodeFilesystemCollectorFailed`.
    3. "Two-part shape" Telegram routes with `continue: true`. Each of these
       also has its alertnames repeated in the final `mctl-agent` route, so
       the agent still gets a ticket: `MctlTelegramCanary.*`,
       `AccessLogin.*`, `ArgoCDApplicationDegraded|...OutOfSyncLong` for
       projects `default|platform`, the three `*FastBurn` alerts,
       `MctlAgentDeadLetter|MctlAgentActionsExecutingStuck|MctlAgentClaudeUsageLimit`,
       and `MctlApi.*`. The comments explain why the repetition is needed: the
       root default receiver fires only when no child route matched at all.
       Once a `continue: true` child has matched, an alert that matches
       nothing else is never delivered to mctl-agent.
  - Two explicit `mctl-agent` routes close the list. The first covers
    monitoring-namespace scrape alerts. The second is the "catch-all"
    alertname allowlist.
  - Receivers: `"null"`, `mctl-agent` (webhook to
    `admins-mctl-agent-base-service.admins.svc...:8080/api/v1/alerts`), and
    `telegram` (`telegram_configs`, `chat_id` from
    `.Values.alertmanager.telegramChatId` in
    `platform-gitops/bootstrap/values.yaml`).
- Critical rule inventory, parsed from every `VMRule` under
  `platform-gitops/infra-components/observability/vm-rules/`. There are 25
  `severity: critical` alerts:
  - 10 of them reach mctl-agent only: `VictoriaMetricsBackupStale`,
    `PublicEndpointDown`, `NodeLowMemoryAvailable`, `VaultSealed`,
    `MinioBucketUsageCritical`, `ServiceUnavailable`,
    `MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
    `ValkeyEventsDown` and `ValkeyEventsAbsent`.
  - `MctlAgentMetricsAbsent` (`vm-rules/mctl-agent-cleanup-alerts.yaml`) is
    `warning` and is routed to mctl-agent only.
  - Upstream rules come from `defaultRules.enabled: true`, with the
    etcd/scheduler/controller-manager groups turned off. All of them
    (`KubeAPIDown`, `KubeletDown`, `Alertmanager*`, vm `ServiceDown`, ...)
    fall to the root default receiver.
- Testing hooks: `scripts/check-vm-rules.sh` runs `promtool` on the vm-rules.
  Nothing in the repo runs `amtool`. The comment in `monitoring.yaml` says
  `amtool config routes test` was run by hand once. The convention for render
  tests is plain `python3 tests/test_*.py` (no pytest) driving
  `helm template test platform-gitops/bootstrap`. Examples are
  `tests/test_otel_collector_backends_render.py` and
  `tests/test_otel_collector_alert_windows.py`. Each test has its own step in
  `.github/workflows/validate-manifests.yml`, which already installs helm and
  promtool.

## Proposed solution

All changes are in `monitoring.yaml`'s `route.routes`, plus a new test. The
new route order is:

1. **Hoist every `"null"` route to the top**, in their current relative order.
   This is behavior-neutral. No earlier route matches the same label sets
   today: `KubeJobFailed`+`vault` and `KubeJobFailed`+`labs` are disjoint, and
   nothing earlier matches `CPUThrottlingHigh`, `KubeControllerManagerDown`,
   or `KubePodNotReady` in `argo-workflows`. The hoist is required so the
   silenced k3s-irrelevant critical alerts
   (`KubeControllerManagerDown|KubeSchedulerDown|KubeProxyDown`) are never
   reached by the severity route. Comment: "null routes first: a silence must
   win over the severity page below".
2. **The existing terminal Telegram routes stay where they are**, unchanged.
   A critical alert matched by one of them (`VaultBackupStale`,
   `VaultAudit*`, `NodeDiskSpaceCritical`, `NodeFilesystemCollectorFailed`,
   `ArgoLocalWorkdirQuotaCritical`) still stops there. It reaches Telegram
   once and, as today, gets no agent ticket.
3. **The existing `continue: true` Telegram routes gain one matcher,
   `severity != "critical"`.** Their critical alerts (`AccessLoginBroken`,
   `AccessLoginProbeStale`, `MctlTelegramCanaryFailing`, the three
   `*FastBurn`, `MctlAgentActionsExecutingStuck`, `MctlApiDown`,
   `MctlApiNoReadyReplicas`) then reach Telegram through the severity route
   in step 5 instead. Non-critical alerts keep their current route. This is
   the dedupe: Alertmanager treats two matching routes to the same receiver
   as two aggregation groups and sends twice.
4. **New meta-alert route**, inserted directly before the severity route:
   ```yaml
   - receiver: telegram
     continue: true
     matchers:
       - alertname =~ "Alertmanager.*|VMAlert.*|vmalert.*|MctlAgentMetricsAbsent"
       - severity != "critical"
   - receiver: telegram
     continue: true
     matchers:
       - alertname = "ServiceDown"
       - job =~ ".*(vmalert|alertmanager).*"
       - severity != "critical"
   ```
   The `severity != "critical"` matcher keeps critical meta-alerts (for
   example `AlertmanagerClusterDown`, `AlertmanagerFailedToSendAlerts`) on
   the severity route alone, so they are never sent twice. The comment
   states the circularity: "alerts about the notification path must not be
   delivered only through it".
5. **New severity route**, after all terminal Telegram routes and before the
   two existing `mctl-agent` routes:
   ```yaml
   - receiver: telegram
     continue: true
     matchers:
       - severity = "critical"
   ```
6. The existing `mctl-agent` monitoring-scrape route and the catch-all
   allowlist route stay unchanged. Critical alerts on that list (for example
   `VaultSealed`, `MinioBucketUsageCritical`, `NodeLowMemoryAvailable`) reach
   it after step 5.
7. **New final matcher-less route `- receiver: mctl-agent`.** Any alert that
   gets this far has either matched nothing so far (it would have reached the
   root default `mctl-agent` anyway, with the same grouping inherited from
   the root) or has been passed on by a `continue: true` route from step 4 or
   5. This restores the root default for those alerts. Without it,
   `KubeAPIDown` would go to Telegram only. The comment says this makes the
   alertname list in the catch-all route redundant, and that removing the
   list is a later clean-up.

Resulting behavior for the cases in the issue:

| Alert / labels | Today | After |
|---|---|---|
| `KubeAPIDown` severity=critical | mctl-agent | telegram, mctl-agent |
| `PodCrashLooping` severity=warning | mctl-agent | mctl-agent |
| `Watchdog` | null | null |
| `KubeSchedulerDown` severity=critical | null | null |
| `VaultBackupStale` severity=critical | telegram | telegram |
| `MctlApiDown` severity=critical | telegram, mctl-agent | telegram, mctl-agent (one telegram) |
| `VaultSealed` severity=critical | mctl-agent | telegram, mctl-agent |
| `MctlAgentMetricsAbsent` severity=warning | mctl-agent | telegram, mctl-agent |
| `AlertmanagerFailedReload` severity=critical | mctl-agent | telegram, mctl-agent |
| `ServiceDown` job=vmalert... (any severity) | mctl-agent | telegram, mctl-agent |
| `MctlTelegramPoolNearCapacity` severity=warning | mctl-agent | mctl-agent |

The comment above the `PoolNearCapacity`/`FloodWaitSpike` explanation is
updated to say that their `critical` variants now also page Telegram through
the severity route.

**Test: `tests/test_alertmanager_routing.py`** (plain python3, no pytest,
following the existing `tests/` convention):

- Run `helm template test platform-gitops/bootstrap -f
  platform-gitops/bootstrap/values.yaml`, select the `Application` named
  `monitoring`, parse `spec.sources[0].helm.values` as YAML, and take
  `alertmanager.config`.
- Rewrite `bot_token_file` and `credentials_file` to point at placeholder
  files in a temp directory, then write `alertmanager.yml`.
- Run `amtool check-config`.
- Run `amtool config routes test --config.file=... <labels>` for a case
  table. The table covers the eleven rows above, plus every `severity:
  critical` alert parsed from `vm-rules/*.yaml`, which is generated at test
  time so a new critical rule is covered automatically. Assertions:
  - The exact receiver list matches the case table.
  - For every critical vm-rules alert, `telegram` appears exactly once.
- `amtool` resolution: use it from `PATH` if present. Otherwise download a
  pinned `alertmanager-<ver>.linux-amd64.tar.gz` (the version vmalertmanager
  runs in chart 0.72.5) into a temp dir and verify its sha256 before use.
- A `--selftest` flag feeds a config with the severity route removed and
  asserts that the test then fails. This matches the "a guard never seen to
  fail is not known to work" practice in `validate-manifests.yml`.
- Wiring: one step in `.github/workflows/validate-manifests.yml` after the
  promtool step, running `python3 tests/test_alertmanager_routing.py
  --selftest && python3 tests/test_alertmanager_routing.py`. This is the
  only workflow change.

## Alternatives

1. **Severity route as the first child route (as the issue literally
   says).** Dropped. It would page Telegram for the null-routed
   `KubeControllerManagerDown|KubeSchedulerDown|KubeProxyDown`. It would also
   send a second Telegram message for every critical alert on a terminal
   Telegram route, and avoiding that would need `severity != "critical"` on
   those routes. That in turn would push them past their terminal stop and
   give them agent tickets that operators deliberately removed. Hoisting the
   nulls and placing the severity route after the terminal Telegram routes
   meets the same intent: every critical alert reaches Telegram before the
   agent catch-all.
2. **Make `telegram` the root receiver for critical alerts with a nested
   sub-tree, or swap the root receiver to telegram and route non-critical
   alerts to mctl-agent.** Dropped. It inverts the whole tree and touches
   every route and its comments, and the large diff hides a subtle change in
   what operators get paged for.
3. **Extend the alertname allowlist with the 10 missing platform critical
   rules and the upstream names.** Dropped. This is the allowlist-drift
   failure the issue (and the prefix-match comments throughout the file)
   warns against: the next critical rule would silently default to
   agent-only again.
4. **Test by reimplementing routing in Python.** Dropped. A homemade router
   can disagree with Alertmanager about `continue` and default-receiver
   semantics, which is exactly the subtlety this change depends on.
   `amtool config routes test` uses the real implementation.

## Platform impact

- **Migrations:** none. This is a config-only change. The VM operator reloads
  vmalertmanager when Argo CD syncs `monitoring`.
- **Backward compatibility:** non-critical, non-meta alerts keep their exact
  receivers, and the test asserts this. mctl-agent keeps receiving every
  alert it receives today. It additionally receives nothing new, because
  every alert that newly reaches the final catch-all reached the root default
  before.
- **Telegram volume:** up by the critical alerts that were agent-only (10
  platform rules plus upstream critical rules) and by the warning-level meta
  alerts. Mitigations: existing grouping by `alertname,namespace` and the
  `repeat_interval: 4h` throttle repeats. The `null` routes still silence
  known-noisy rules.
- **Risks:**
  - A routing mistake could drop alerts. Mitigation: `amtool check-config`
    plus the routing table in CI, and the generated "every critical
    vm-rules alert reaches telegram exactly once" assertion.
  - The two "deliberately agent-only" critical variants
    (`MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`) will page.
    This is flagged in requirements Open questions.
  - The `ServiceDown` `job` label may differ from the guessed pattern. The
    implementer confirms it from the rendered upstream rules. The test covers
    a realistic label set.
- **Resource impact:** negligible.
