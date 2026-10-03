# Design: incident-58bb178b

## Diagnosis
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
defines `mctl_telegram:oauth_5xx:ratio_rate1h` as a bare division: the count of
5xx responses on `/oauth/token` and `/oauth/telegram/callback` over 1h,
divided by the count of all requests on those routes over 1h. In Prometheus/
VictoriaMetrics, a label selector that matches zero series (here,
`status_code=~"5.."` when there have been no 5xx responses in the window)
yields an EMPTY vector, not a vector of zeros. Dividing an empty numerator by
a non-empty denominator produces an empty result, so the recorded series is
simply absent for that evaluation — which is exactly what `RecordingRulesNoData`
fired on. Service logs confirm the OAuth token/callback path is healthy right
now (client registrations accepted, an authorize request served, a token
grant issued, zero 5xx lines), so this is the expected "no errors happened"
case, not an outage.

The file's own comments show the authors already hit this exact failure mode
once, in the neighboring `mctl-telegram-slo-compliance` group: both
`mctl_telegram:tool_availability:ratio_rate28d` and
`mctl_telegram:oauth_availability:ratio_rate28d` zero-fill their numerator
with an `or 0 * <denominator>` term specifically so a "nothing bad happened"
window still records a real 0 instead of vanishing. That zero-fill pattern
was never applied to `mctl_telegram:oauth_5xx:ratio_rate1h` /
`...ratio_rate6h` in the `mctl-telegram-slo-sli` group above it, even though
those two rules have the identical shape (a `status_code=~"5.."` numerator
that legitimately goes empty whenever OAuth is fully healthy) and directly
feed the `MctlTelegramOAuthAvailabilityFastBurn` / `...SlowBurn` alerts. The
skill gap the escalation named ("no diagnostic rule for this signal") is
accurate — this is a recording-rule authoring bug, not a runtime incident,
and no existing skill covers reading VMRule definitions.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
Rule: `mctl_telegram:oauth_5xx:ratio_rate1h` (the rule named in the incident)

Current `expr`:
```
sum by (job, namespace) (
  rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
)
/
sum by (job, namespace) (
  rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
)
```

New `expr` (zero-fill the numerator with the same `or 0 * <denominator>`
pattern already used by `mctl_telegram:oauth_availability:ratio_rate28d` a
few lines below, so a series with no 5xx still carries a `(job, namespace)`
labeled 0 instead of going empty):
```
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

This only changes behavior when the numerator selector matches nothing: the
result is then `0 / denominator = 0` (still empty if there is zero traffic at
all, which is the honest "unmeasured" case and outside this incident's
scope). When 5xx responses exist, `0 * denominator` is irrelevant because the
`or` only falls back if the left side is empty.

## Scope
Minimal: only the `mctl_telegram:oauth_5xx:ratio_rate1h` rule's `expr` changes.

`mctl_telegram:oauth_5xx:ratio_rate6h` has the identical structural defect
(same numerator shape, same missing zero-fill) and feeds
`MctlTelegramOAuthAvailabilitySlowBurn`, so it will very likely produce its
own `RecordingRulesNoData` incident under the same healthy-OAuth conditions.
It is left untouched here to keep this change to the single rule named in
the incident; it is a good candidate for a fast follow using the same fix.

## Confidence: HIGH
The failure mechanism (empty-vector selector collapsing a division) is
directly documented by the file's own comments for the sibling
`ratio_rate28d` rules, and the service logs independently confirm OAuth is
currently healthy with zero 5xx, matching the "no data" symptom rather than
an outage.
