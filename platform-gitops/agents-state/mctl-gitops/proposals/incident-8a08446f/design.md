# Design: incident-8a08446f

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` is a plain division with no zero-fill:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h]))
```

In Prometheus/VictoriaMetrics, a label selector that matches zero time series
yields an *empty* vector, not a zero, and dividing against an empty numerator
produces an empty result — the rule then records nothing at all for that
evaluation. `mctl_http_requests_total{...,status_code=~"5.."}` only has series
for status codes that have actually occurred, so whenever the OAuth token
endpoint is fully healthy (zero 5xx in the window) the numerator selector
matches nothing and the whole recording rule goes silent. That silence is what
VMAlert's `RecordingRulesNoData` rule fired on — not a genuine data-collection
break.

This is a known instance of a bug this same file already fixed once: the
`mctl_telegram:oauth_availability:ratio_rate28d` compliance rule (same file,
lines 162-176) carries an explicit comment explaining that the analogous
subtractive form "breaks in the HEALTHY case ... the series would vanish
precisely when OAuth is perfect" and fixes it with an `or 0 *` zero-fill on
the numerator. The unit test file
(`platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`,
"Rolling-28d compliance recording rules" section) tests exactly that
zero-fill for the 28d rules, and its own comment notes the fix was applied
only there: "the burn-rate alerts above cover only the 1h/6h rules." The 1h/6h
SLI ratios (`mctl_telegram:oauth_5xx:ratio_rate1h` and `...ratio_rate6h`) were
never given the same treatment, so they retain the "vanishes when healthy"
defect. mctl-telegram's own logs for this window (see requirements.md) show
the service serving OAuth registration and MCP traffic without errors, which
is consistent with "zero 5xx, rule goes silent" rather than an actual outage
or a broken scrape/metric.

An instruction embedded in the alert's `analysis` field text is not present
here; nothing in the incident payload asked for any privileged action, so
there is nothing to flag as untrusted-instruction. The summary and labels
were treated purely as data describing which recording rule and tenant were
affected.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

Apply the same zero-fill pattern already used for
`mctl_telegram:oauth_availability:ratio_rate28d` to the
`mctl_telegram:oauth_5xx:ratio_rate1h` recording rule (lines 86-94), so a
healthy OAuth endpoint records a genuine `0` instead of no data:

Current:
```yaml
        - record: mctl_telegram:oauth_5xx:ratio_rate1h
          expr: |
            sum by (job, namespace) (
              rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
            )
            /
            sum by (job, namespace) (
              rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
            )
```

New:
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
```

## Scope
Minimal: only the `mctl_telegram:oauth_5xx:ratio_rate1h` expr, which is the
recording rule the incident named, is changed.

Note for follow-up, not in scope here: `mctl_telegram:oauth_5xx:ratio_rate6h`
(same file, lines 95-103) has the identical structure and the identical
"vanishes when healthy" defect, and will very likely trip the same
`RecordingRulesNoData` alert on its own schedule. Left untouched per the
single-rule scope for this proposal; recommend a follow-up proposal applying
the same fix there.

## Confidence: LOW
The fix mirrors an established, already-tested pattern in the same file, and
the observed logs are consistent with "endpoint healthy, rule went silent."
However, direct confirmation would require querying VictoriaMetrics for the
`mctl_http_requests_total` series with the OAuth route selector to verify the
numerator really is empty (not, for example, absent because the metric or
route labels were renamed) — that query access was not available in this
diagnosis, so the implementer should verify metric/label existence before
merging.
