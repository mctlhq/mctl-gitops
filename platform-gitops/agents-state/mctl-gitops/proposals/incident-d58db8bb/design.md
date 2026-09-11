# Design: incident-d58db8bb

## Confidence: LOW

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` is a recording rule defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
(group `mctl-telegram-slo-sli`):

```
sum by (job, namespace) (
  rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
)
/
sum by (job, namespace) (
  rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
)
```

Both sides of this division are PromQL vector selectors. If nobody calls
`/oauth/token` or `/oauth/telegram/callback` at all during a given 1h
window, the denominator selector matches zero series, `sum(...)` over an
empty vector is itself empty (not zero), and division of an empty vector
by anything yields an empty result — so the rule genuinely records nothing
for that evaluation, which is what `RecordingRulesNoData` (a default
vmalert self-monitoring alert bundled by the victoria-metrics-k8s-stack
chart, enabled via `defaultRules.enabled: true` in
`platform-gitops/bootstrap/templates/observability/monitoring.yaml`) is
built to catch.

This is consistent with the available evidence: labs/mctl-telegram is a
low-traffic preprod tenant, and nothing in the fetched logs indicates any
OAuth activity in the relevant window. The sibling 28d "compliance" rules in
the same file already handle exactly this empty-vector problem with an
`or 0 * sum(...)` zero-fill — but that pattern is deliberately NOT applied
to the 1h/6h SLI rules used by the burn-rate alerts: zero-filling the
denominator here would make a genuinely-idle window record `0/0` or
`x/0` (NaN/+Inf) instead of "no data", and a stored `+Inf` would incorrectly
trip `MctlTelegramOAuthAvailabilityFastBurn` (`... > 0.01440`) on every quiet
hour. So the recording rule expression itself should NOT be changed to fix
this — that would trade one false positive for a worse one.

The safer, narrower fix is at the alert-routing layer: RecordingRulesNoData
for this one, known-quiet recording rule is not actionable (there is no
config bug to fix — it is an expected consequence of low OAuth traffic on
this tenant) and should not keep consuming an mctl-agent escalation slot.
`monitoring.yaml` already contains several examples of this exact pattern —
a narrowly-matched Alertmanager route to the `"null"` receiver for a
specific, known-benign alert (e.g. the `KubeContainerWaiting`/`namespace =
"vault"` route, or `CPUThrottlingHigh`/`namespace = "monitoring"`).

## Proposed Fix
In `platform-gitops/bootstrap/templates/observability/monitoring.yaml`, add a
new Alertmanager route above the existing catch-all
`RecordingRulesNoData|ScrapePoolHasNoTargets|TooManyScrapeErrors|TooManyLogs`
/ `namespace = "monitoring"` route (around line 633-636), routing this one
specific recording rule to the `"null"` receiver instead of `mctl-agent`:

```yaml
- receiver: "null"
  matchers:
    - alertname = "RecordingRulesNoData"
    - recording = "mctl_telegram:oauth_5xx:ratio_rate1h"
```

IMPORTANT — verify before applying: this proposal infers the label name
`recording` (and the rule-group label, likely `rule_group` or `group`, with
value `mctl-telegram-slo-sli`) from the wording of the default
`RecordingRulesNoData` alert's summary/description template, which is
bundled with the victoria-metrics-k8s-stack chart and not vendored in this
repo, so it could not be read directly. Before merging, confirm the actual
label key/value on a firing instance of this alert (e.g. via the Alertmanager
UI/API, or `vmalert`'s `/api/v1/alerts`) and adjust the matcher accordingly.
If no single label identifies the specific recording rule, matching on
`alertname` plus the `namespace`/`job` labels already present on the
recording rule's `mctl_telegram:oauth_5xx:ratio_rate1h` series may be needed
instead.

## Scope
Minimal: one new Alertmanager route for exactly this recording rule's
RecordingRulesNoData alert. Do not change the recording rule expression
in `mctl-telegram-slo.yaml`, and do not change the existing
`RecordingRulesNoData` catch-all route for other rules.
