# Design: incident-b02e37d3

## Confidence: LOW

## Diagnosis
MctlTelegramSessionBorrowSlowBurn is a warning-severity, non-paging SLO
burn-rate alert defined in
platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml:
it fires when `mctl_telegram:session_borrow_errors:ratio_rate6h` (the
Pool.Borrow() error ratio, excluding expected `expired_idle` /
`expired_absolute` TTL results) exceeds 6% over a trailing 6h window — 6x
the 99% session-borrow-success objective's error budget. It escalated to
this responder because mctl-agent has no skill wired to the
`mctl_sessions_borrow_total{result="error"}` signal (type=generic), not
because the situation is necessarily severe: the alert's own severity is
"file a reliability ticket; no page".

Service logs for labs/mctl-telegram covering roughly the last 30-70
minutes of the 6h alert window show no ERROR-level entries and no
explicit session-borrow failures — only expected INFO-level connection
teardown ("idle telegram client, closing", recurring roughly every 10
minutes for user_id 9980, consistent with an idle-connection reaper) and
healthy canary/tool-call traffic (status=ok throughout). This agent has no
shell and could not page further back into the 6h window within its
context budget, so the specific error(s) that actually crossed the
threshold were not directly observed.

Critically, the SLO rule file itself documents this as a known, accepted
limitation rather than a bug: "on a low-traffic service a 1h window holds
few invocations, so a couple of errors can cross a burn threshold... no
minimum-volume guard [is] invented here." mctl-telegram is a low-traffic
service (the visible tail shows on the order of one real user plus the
10-minute canary). It is therefore plausible — though not confirmed, hence
LOW confidence — that this occurrence is exactly that documented
low-volume edge case rather than a new regression, and that a human
skimming the raw sample size would resolve the ticket in seconds if that's
the case.

## Proposed Fix
Minimal, observability-only change to
platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml.
Does not change the alert threshold, severity, or routing — only makes the
sample size behind the ratio visible in the alert description, which is
exactly the missing piece for triaging this specific alert class.

1. In the `mctl-telegram-slo-sli` rule group, add two new recording rules
   immediately after the existing `mctl_telegram:session_borrow_errors:ratio_rate6h`
   rule:

   ```yaml
   - record: mctl_telegram:session_borrow_errors:count_rate6h
     expr: |
       sum by (job, namespace) (increase(mctl_sessions_borrow_total{result="error"}[6h]))
   - record: mctl_telegram:session_borrow_attempts:count_rate6h
     expr: |
       sum by (job, namespace) (increase(mctl_sessions_borrow_total{result=~"ok|error"}[6h]))
   ```

2. In the `mctl-telegram-slo-burn` group, update the
   `MctlTelegramSessionBorrowSlowBurn` alert's `annotations.description`
   (current value below) to append the raw sample counts using
   VictoriaMetrics/Prometheus template `query`:

   Current:
   ```yaml
   description: >-
     The Pool.Borrow() error rate over the last 6h, excluding expected
     TTL expirations, is {{ $value | humanizePercentage }} — above the
     6.0% slow-burn threshold (6x the 99% objective's budget). File a
     reliability ticket; no page.
     SLO and error-budget policy:
     https://github.com/mctlhq/mctl-telegram/blob/main/docs/slo.md
   ```

   New:
   ```yaml
   description: >-
     The Pool.Borrow() error rate over the last 6h, excluding expected
     TTL expirations, is {{ $value | humanizePercentage }} — above the
     6.0% slow-burn threshold (6x the 99% objective's budget). Sample:
     {{ with query "mctl_telegram:session_borrow_errors:count_rate6h" }}{{ . | first | value | humanize }}{{ end }} errors /
     {{ with query "mctl_telegram:session_borrow_attempts:count_rate6h" }}{{ . | first | value | humanize }}{{ end }} attempts
     in 6h — on a low-traffic tenant this ratio can cross threshold on very
     few events; check the sample size before treating this as a
     regression. File a reliability ticket; no page.
     SLO and error-budget policy:
     https://github.com/mctlhq/mctl-telegram/blob/main/docs/slo.md
   ```

Verify the `query` template function is supported by this cluster's
VictoriaMetrics alerting template engine before merging (it is standard in
vmalert/Prometheus alert templates, but confirm against the deployed
vmalert version); if unsupported, fall back to exposing the two new
recording rules on the existing Grafana dashboard
(mctl-telegram-overview-dashboard-configmap.yaml) instead of inline in the
alert text.

## Scope
Minimal. Only touches the session-borrow SLI/alert block in
mctl-telegram-slo.yaml (two new recording rules + one alert annotation).
Does not touch MctlTelegramSessionBorrowFastBurn, the other SLO alerts in
this file, the objective, the threshold, or any application code/config
outside this VMRule. Does not resolve or speculate on the underlying
Pool.Borrow() error cause — that remains unknown at LOW confidence and
should be reassessed once the sample-size context is visible on the next
occurrence.
