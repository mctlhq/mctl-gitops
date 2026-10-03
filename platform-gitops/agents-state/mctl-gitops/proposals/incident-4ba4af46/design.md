# Design: incident-4ba4af46

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` (and its `ratio_rate6h` sibling) is
recorded in platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml
as a bare `errors / total` division:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"...",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"..."}[1h]))
```

In Prometheus/VictoriaMetrics, a counter series with a given label set (here
`status_code="5.."`) only exists once at least one sample with that exact
label combination has been recorded. Whenever the OAuth token/callback routes
are healthy for a full window (zero 5xx responses), the `status_code=~"5.."`
selector matches no series at all, so `rate(...)` and the outer `sum(...)`
both evaluate to an EMPTY vector — not zero. Dividing by an empty numerator
still divides fine, but VictoriaMetrics' recording-rule evaluator writes no
sample at all when either operand of `/` is empty at that timestep with no
match, so the whole recorded series intermittently disappears exactly when
the service is healthy. RecordingRulesNoData then fires on the resulting gap.

This is not a hypothesis — it is the same failure mode this same file's
`mctl-telegram-slo-compliance` group was deliberately rewritten to avoid. Its
28d rules (`mctl_telegram:oauth_availability:ratio_rate28d` etc.) carry an
explicit `or 0 * sum(...)` zero-fill and a code comment that says exactly
this: "the subtractive form breaks in the HEALTHY case ... the series would
vanish precisely when OAuth is perfect." The corresponding regression test
(`tests/mctl-telegram-slo_test.yaml`, "oauth availability compliance records
1 when there is no 5xx series at all") pins that fix for the 28d rules only.
The 1h/6h burn-rate SLI rules in the `mctl-telegram-slo-sli` group
(`mctl_telegram:oauth_5xx:ratio_rate1h`/`ratio_rate6h`, and by the same
construction `tool_errors` and `session_borrow_errors`) were never given the
equivalent guard, so they carry the same bug the 28d rules were fixed for.

mctl-telegram's own traffic supports this: the log snippet in requirements.md
shows the canary CronJob and live MCP tool calls all healthy in the run
immediately preceding the incident, and the canary's synthetic probes never
call `/oauth/token` or `/oauth/telegram/callback` at all (it probes
`oauth_metadata`, `mcp_init`, `list_dialogs`, `get_unread_messages`). So the
only traffic that could populate this SLI is real user OAuth activity, which
on a low-traffic beta service can easily produce zero 5xx responses for a
full 1h window while still producing 2xx/4xx traffic on those routes — the
exact condition that makes the numerator vanish.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
Group: `mctl-telegram-slo-sli`

Apply the same `or 0 * sum(...)` zero-fill already used in the
`mctl-telegram-slo-compliance` group to the numerator of both OAuth SLI
recording rules, so the numerator degrades to a real 0 instead of vanishing
whenever there is denominator traffic but no 5xx:

`mctl_telegram:oauth_5xx:ratio_rate1h` — change:
```
expr: |
  sum by (job, namespace) (
    rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
  )
  /
  sum by (job, namespace) (
    rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
  )
```
to:
```
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

Apply the identical transform to `mctl_telegram:oauth_5xx:ratio_rate6h`
(same expression, `[6h]` windows).

## Scope
Minimal. Only the two OAuth SLI recording-rule expressions
(`ratio_rate1h`, `ratio_rate6h`) in the `mctl-telegram-slo-sli` group are
touched — the exact pair the firing alert (`mctl_telegram:oauth_5xx:ratio_rate1h`)
belongs to, plus its `6h` sibling built the same way. No thresholds, alert
definitions, or the other SLI families (`tool_errors`, `session_borrow_errors`)
are changed, even though they share the same underlying construction and are
plausibly exposed to the same bug — that is a separate decision for a
follow-up, out of scope for this specific alert.

This does not fully eliminate every "no data" case: if there is truly zero
traffic to `/oauth/token` and `/oauth/telegram/callback` for the whole window
(denominator also empty), the zero-fill numerator is empty too and the series
still will not record. The zero-fill only fixes the healthy-with-traffic
case, which the evidence above indicates is what happened here. Flagging this
residual gap explicitly rather than silently under-scoping the fix.

## Confidence: MEDIUM
High confidence in the mechanism (it is proven elsewhere in the same file,
with a comment and a regression test) and that it explains "no data" for
this specific rule. Medium rather than high because it was not possible to
directly query the raw `mctl_http_requests_total` series to confirm traffic
was present-but-error-free during the incident window (no metrics-query tool
available here) — the diagnosis is corroborated by the surrounding evidence
(canary never touches these routes; service otherwise healthy) rather than a
direct read of the numerator/denominator series.
