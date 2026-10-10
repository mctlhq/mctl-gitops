# Route every critical alert, and every alerting-path alert, directly to Telegram

## Context

The Alertmanager config is set inline in the `monitoring` Argo CD Application
(`platform-gitops/bootstrap/templates/observability/monitoring.yaml`, the
`alertmanager.config` values of `victoria-metrics-k8s-stack` 0.72.5). Its root
route is `receiver: mctl-agent`. Telegram is reached only through an allowlist
of alertname-keyed child routes, and no route looks at `severity`. A
`severity=critical` alert that is not on that allowlist reaches a human only if
mctl-agent is up and decides to escalate it. Of the 25 platform-owned critical
rules under `platform-gitops/infra-components/observability/vm-rules/`, 10
have no Telegram path today: `VictoriaMetricsBackupStale`,
`PublicEndpointDown`, `NodeLowMemoryAvailable`, `VaultSealed`,
`MinioBucketUsageCritical`, `ServiceUnavailable`,
`MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
`ValkeyEventsDown` and `ValkeyEventsAbsent`. The upstream critical rules from
`defaultRules` (for example `KubeAPIDown`, `KubeletDown` and
`AlertmanagerClusterDown`) have none either.

The worst case is the alerting path itself. Alerts that mean "notifications
are broken" (`AlertmanagerFailedToSendAlerts`, `AlertmanagerFailedReload`,
vmalert health alerts, `MctlAgentMetricsAbsent`) go to mctl-agent, so when
mctl-agent is the thing that is broken, nobody hears about it. This proposal
adds a severity-keyed Telegram route and a meta-alert route. Both use
`continue: true`, so mctl-agent still gets every alert it gets today. No alert
may be delivered to Telegram twice. A routing test pins the result.

## User stories

- AS an on-call operator I WANT every `severity=critical` alert delivered to
  Telegram directly SO THAT a critical condition is not hidden behind
  mctl-agent's availability or its escalation decisions.
- AS an on-call operator I WANT alerts about Alertmanager, vmalert and
  mctl-agent's own metrics delivered to Telegram whatever their severity SO
  THAT a broken notification chain is reported over a path that does not
  depend on it.
- AS the mctl-agent maintainer I WANT mctl-agent to keep receiving every alert
  it receives today SO THAT automated triage and incident creation are
  unaffected.
- AS a reviewer of routing changes I WANT a CI test that shows which receivers
  each sample label set reaches SO THAT a later route edit cannot silently drop
  a critical alert or page it twice.

## Acceptance criteria (EARS)

- WHEN an alert with `severity="critical"` is not matched by a `"null"` route
  or by an existing terminal (no `continue`) Telegram route, THE SYSTEM SHALL
  deliver it to the `telegram` receiver exactly once and to the `mctl-agent`
  receiver.
- WHEN an alert with `severity="critical"` is matched by an existing terminal
  Telegram route (for example `VaultBackupStale`, `VaultAudit.*`,
  `NodeDiskSpaceCritical`, `ArgoLocalWorkdirQuotaCritical`), THE SYSTEM SHALL
  keep delivering it to `telegram` only, exactly once, as today.
- WHEN an alert's `alertname` matches `Alertmanager.*`, `VMAlert.*`,
  `vmalert.*` or `MctlAgentMetricsAbsent`, THE SYSTEM SHALL deliver it to
  `telegram` exactly once and to `mctl-agent`, whatever its severity.
- WHEN a `ServiceDown` alert fires for an alerting component (a `job` label
  matching vmalert or (vm)alertmanager), THE SYSTEM SHALL deliver it to
  `telegram` exactly once and to `mctl-agent`, whatever its severity.
- WHEN `KubeAPIDown` fires with `severity="critical"`, THE SYSTEM SHALL route
  it to `telegram` and `mctl-agent`.
- WHEN `PodCrashLooping` fires with `severity="warning"`, THE SYSTEM SHALL
  route it to `mctl-agent` only.
- WHEN `Watchdog` or `InfoInhibitor` fires, THE SYSTEM SHALL route it to
  `"null"` only (unchanged).
- WHEN `KubeControllerManagerDown`, `KubeSchedulerDown` or `KubeProxyDown`
  fires with `severity="critical"`, THE SYSTEM SHALL route it to `"null"` only.
  These are silenced today because k3s does not expose those components.
- WHILE an alert has no `severity="critical"` label and is not a meta-alert as
  defined above, THE SYSTEM SHALL route it to exactly the receivers it reaches
  before this change.
- WHEN the bootstrap chart is rendered, THE SYSTEM SHALL produce an
  Alertmanager config that passes `amtool check-config`.
- IF a future edit makes any critical `vm-rules` alert, or any sample case in
  the routing test, reach `telegram` zero times or more than once, or changes
  the receivers of a non-critical, non-meta sample case, THEN THE SYSTEM SHALL
  fail the `validate-manifests` CI job.

## Out of scope

- The external dead-man's switch for `Watchdog` (#1638).
- Agent-side deduplication and cooldown in mctl-agent
  (`internal/monitor/alerthandler.go`).
- Changing the severity of any rule, including the two
  `MctlTelegramPoolNearCapacity` / `MctlTelegramFloodWaitSpike` critical
  variants that the config comment calls "deliberately agent-only" (see Open
  questions).
- Removing the explicit "two-part shape" alertname list from the mctl-agent
  catch-all route. The new trailing catch-all makes that list redundant, but
  deleting it is a separate clean-up.
- Telegram message templating, chat IDs and new receivers.

## Open questions

- `MctlTelegramPoolNearCapacity` and `MctlTelegramFloodWaitSpike` each have a
  `severity=critical` variant in `vm-rules/mctl-telegram-ops.yaml`. The
  routing comment in `monitoring.yaml` calls them deliberately agent-only.
  The issue asks for "every critical alert" to reach Telegram, so this
  proposal pages them too and updates that comment. If they should stay
  agent-only, the right fix is to lower their severity in a follow-up. An
  exclusion in the router would bring back the allowlist problem this issue
  is removing.
- The issue's problem statement names `KubeNodeNotReady` as part of the
  notification chain, but its "Expected" list leaves it out. Upstream it is
  `warning`. This proposal does not add it to the meta-alert route. It can be
  added to the same regex later if wanted.
- The exact `job` label value of the upstream vm `ServiceDown` rule for vmalert
  and vmalertmanager in chart 0.72.5 must be confirmed from the rendered rules.
  The proposed matcher is `job=~".*(vmalert|alertmanager).*"`.
- Running the routing test in CI needs one new step in
  `.github/workflows/validate-manifests.yml`, because every `tests/*.py` file
  there is wired up by its own step. The issue asks to avoid workflow changes
  "where possible". This proposal keeps the workflow change to a single
  `run:` line. The test downloads a pinned, checksum-verified `amtool` itself
  when it is not on `PATH`.
