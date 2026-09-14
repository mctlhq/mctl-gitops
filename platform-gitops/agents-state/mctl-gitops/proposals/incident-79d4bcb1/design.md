# Design: incident-79d4bcb1

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` (and its `ratio_rate6h` sibling) in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
is a bare division:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h]))
```

`/oauth/token` and `/oauth/telegram/callback` are only hit when a client
actually completes (or refreshes) the Telegram OAuth exchange — a rare event
compared to the constant MCP tool traffic (`list_dialogs`, `get_messages`,
`get_unread_messages`, ...) visible in mctl-telegram's own logs. When zero
requests land on either route within the 1h (or 6h) lookback, BOTH the
numerator and the denominator selectors match no series at all, so the
division has no operand to attach a value to and the recording rule emits
NO series for that evaluation — not a zero, an absence. VictoriaMetrics'
recording-rule-health check (`RecordingRulesNoData`) then fires on that
absence, exactly as seen here.

This is not the same failure the file already patched: the
`mctl-telegram-slo-compliance` group's `_ratio_rate28d` rules use an
`or 0 * <unfiltered-selector>` zero-fill specifically because the
numerator (e.g. `status_code="5.."`) can be empty while the denominator
(all requests to those routes) still has samples over 28 days. That fix
does nothing when the *denominator's own selector* is empty too, which is
exactly the sparse-traffic case the 1h/6h OAuth SLI rules hit. The
`mctl-telegram:oauth_availability:ratio_rate28d` and
`tool_availability:ratio_rate28d` rules are not immune to this in
principle, but a 28-day window realistically always has at least one
request; a 1h window on a rarely-hit route routinely does not.

The incident's own text ("Recording rule ... produces no data") is a
factual metric-health description, not an instruction, and nothing in it
asked for any privileged action — there is nothing to flag as untrusted
here beyond noting it per policy.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

Zero-fill both the numerator and the denominator of the two SLI rules
(`mctl_telegram:oauth_5xx:ratio_rate1h` at line 86-94, and
`mctl_telegram:oauth_5xx:ratio_rate6h` at line 95-103) by falling back to
the service's overall (route-unfiltered) request rate for the same
`(job, namespace)` whenever the OAuth-route-specific selector is empty.
mctl-telegram serves constant non-OAuth traffic (see requirements.md log
evidence), so `mctl_http_requests_total` without a route filter is a safe
"the service is alive and being scraped" anchor to hang a zero on:

Current (`ratio_rate1h`):
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
              0 * sum by (job, namespace) (rate(mctl_http_requests_total[1h]))
            )
            /
            (
              sum by (job, namespace) (
                rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
              )
              or
              sum by (job, namespace) (rate(mctl_http_requests_total[1h]))
            )
```

Apply the same pattern to `ratio_rate6h` with `[6h]` windows throughout.

When OAuth-route traffic is present, both fallbacks are shadowed by the
`or`'s left-hand side (PromQL `or` keeps the left operand's series and
only adds right-hand series for label sets missing on the left), so the
ratio is computed exactly as before. When OAuth-route traffic is absent
for the window, the numerator zero-fills to 0 and the denominator falls
back to overall request rate (nonzero, since the service is serving other
traffic), so the rule records 0 (no burn) instead of nothing — matching
the same reasoning already written for the 28d compliance rules just
above this block in the same file.

## Scope
Minimal. Only the `expr` of `mctl_telegram:oauth_5xx:ratio_rate1h` and
`mctl_telegram:oauth_5xx:ratio_rate6h` in this one file changes. No other
recording rule, alert threshold, label, or unrelated file is touched.
