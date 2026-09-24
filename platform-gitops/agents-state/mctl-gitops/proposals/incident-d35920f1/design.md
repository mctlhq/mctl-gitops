# Design: incident-d35920f1

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` (and its `ratio_rate6h` sibling) is
defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
as a bare division:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h]))
```

`mctl-telegram` (team labs) is healthy: ArgoCD reports Healthy/Synced, the
canary probes (`oauth_metadata`, `mcp_init`, `list_dialogs`,
`get_unread_messages`) all report `ok` every ~10 minutes, and the last hour of
logs contains no 5xx of any kind — the only failure is an expected 401 from
an expired JWT. That is: the OAuth token/callback endpoints are receiving
traffic and serving it successfully, with zero matches for
`status_code=~"5.."`.

In PromQL/MetricsQL, a label selector that matches no series yields an EMPTY
vector, not a zero. When the numerator's `status_code=~"5.."` selector
matches nothing, `rate(...)` over it is empty, and dividing by an empty
operand makes the whole expression empty — so the recording rule writes no
series at all. This is exactly the failure mode the file's own comments
already document and guard against for the 28-day compliance rules a few
lines below (`mctl_telegram:oauth_availability:ratio_rate28d` uses an
`or 0 * ...` zero-fill specifically "for the mirror case where every request
5xxs" and to stop the series from "vanish[ing] precisely when OAuth is
perfect"). That same zero-fill was applied to the 28d success-ratio rule but
was never carried over to the 1h/6h `oauth_5xx` ratios that feed the burn-rate
alerts — those two rules have no empty-vector guard, so they alarm with
"no data" during the exact healthy condition they were meant to measure. The
incident is a gap in the recording-rule expression, not a problem in
mctl-telegram itself; the alert should not have fired the way it did.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

Add the same `or 0 * <denominator>` zero-fill to the numerator of
`mctl_telegram:oauth_5xx:ratio_rate1h` (record at line 86) and
`mctl_telegram:oauth_5xx:ratio_rate6h` (record at line 95), matching the
pattern already used at lines 162-176 for
`mctl_telegram:oauth_availability:ratio_rate28d`:

```yaml
        - record: mctl_telegram:oauth_5xx:ratio_rate1h
          expr: |
            (
              sum by (job, namespace) (
                rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
              )
              or
              0 * sum by (job, namespace) (
                rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
              )
            )
            /
            sum by (job, namespace) (
              rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
            )
        - record: mctl_telegram:oauth_5xx:ratio_rate6h
          expr: |
            (
              sum by (job, namespace) (
                rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[6h])
              )
              or
              0 * sum by (job, namespace) (
                rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[6h])
              )
            )
            /
            sum by (job, namespace) (
              rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[6h])
            )
```

Note for the implementer: `mctl_telegram:tool_errors:ratio_rate1h/6h` and
`mctl_telegram:session_borrow_errors:ratio_rate1h/6h` in the same file appear
to share this same empty-numerator gap (their `status="error"` /
`result="error"` selectors can equally go empty when healthy). That is out of
scope for this incident, which is specifically about the `oauth_5xx` series —
flag it rather than fix it here, per the minimal-scope rule below.

## Scope
Minimal. Only the two `expr:` blocks for `mctl_telegram:oauth_5xx:ratio_rate1h`
and `mctl_telegram:oauth_5xx:ratio_rate6h` change. No alert thresholds, no
other recording rules, no unrelated files.

## Confidence: MEDIUM
The root cause is grounded directly in the VMRule source (including its own
comments describing and fixing this exact empty-vector failure mode for a
sibling rule) and in mctl-telegram's healthy logs/ArgoCD status. Marked
MEDIUM rather than HIGH only because the fix was not validated against a live
VictoriaMetrics query engine before writing this proposal — verify the
`or 0 * ...` guard actually zero-fills as expected in this cluster's
MetricsQL evaluation before merging.
