# Design: incident-9feab4cd

## Diagnosis
The recording rules `mctl_telegram:oauth_5xx:ratio_rate1h` and
`mctl_telegram:oauth_5xx:ratio_rate6h`, defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
(group `mctl-telegram-slo-sli`), compute a 5xx ratio as:

```
sum(rate(mctl_http_requests_total{route=~"...",status_code=~"5.."}[1h]))
/
sum(rate(mctl_http_requests_total{route=~"...",status_code=~"5.."}[1h]))
```

(numerator filtered to `status_code=~"5.."`, denominator unfiltered by status).
When there have been zero 5xx responses on `/oauth/token` and
`/oauth/telegram/callback` in the window — the healthy, expected case, and what
the logs for labs/mctl-telegram confirm for the incident window (all OAuth
probes and client-registration calls succeeded, no error-level or 5xx log
lines) — no time series exists for
`status_code=~"5.."`, so the numerator's `rate(...)` selector matches nothing
and returns an EMPTY vector, not zero. Dividing produces an empty result, so
the recording rule emits no sample at all, which VMRule surfaces as
"recording rule produces no data" (RecordingRulesNoData).

This is the exact failure mode the same file already documents and guards
against in the `mctl-telegram-slo-compliance` group, one section down: the
`mctl_telegram:oauth_availability:ratio_rate28d` rule (and its siblings) use
an explicit `or 0 * <unfiltered-rate>` zero-fill specifically because "a
selector that matches no series yields an EMPTY vector, not zero... the naive
form silently stops recording exactly at the extremes" (see comment at
mctl-telegram-slo.yaml:136-145). The `mctl-telegram-slo-sli` group's
`oauth_5xx` rules (ratio_rate1h and ratio_rate6h, lines 86-103) were never
given the equivalent guard, so they hit the identical empty-vector case on
every quiet 1h/6h window with no OAuth errors — i.e. most of the time.

No skill matched this because it is a PromQL/recording-rule authoring gap in
the vm-rules config, not a service, resource, or infra outage; mctl-agent has
no diagnostic rule for "recording rule produces no data" in general.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

In the `mctl-telegram-slo-sli` group, change the `mctl_telegram:oauth_5xx:ratio_rate1h`
and `mctl_telegram:oauth_5xx:ratio_rate6h` rule expressions to zero-fill the
numerator the same way `mctl_telegram:oauth_availability:ratio_rate28d`
already does, e.g. for the 1h rule:

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

Apply the same pattern to `ratio_rate6h`, substituting `[6h]` for `[1h]`. The
denominator is left as-is (unfiltered by status_code); only the numerator gets
the `or 0 * <unfiltered-rate>` zero-fill, matching the existing 28d rules
exactly.

## Scope
Minimal. Only the two `expr:` blocks for `mctl_telegram:oauth_5xx:ratio_rate1h`
and `mctl_telegram:oauth_5xx:ratio_rate6h` in
`infra-components/observability/vm-rules/mctl-telegram-slo.yaml` change. No
other recording rules, alerts, thresholds, or files are touched. The two
`MctlTelegramOAuthAvailability{Fast,Slow}Burn` alerts that read these series
are unaffected in behavior — they still fire the same way when there IS a
5xx ratio above threshold; they simply now also correctly evaluate to 0
(rather than absent) when there are no 5xx responses.
