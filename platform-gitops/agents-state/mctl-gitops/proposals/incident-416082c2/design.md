# Design: incident-416082c2

## Diagnosis
The recording rule `mctl_telegram:oauth_5xx:ratio_rate1h` lives in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
group `mctl-telegram-slo-sli`. Its expression divides a 5xx-filtered
sub-selector of `mctl_http_requests_total` (route in `/oauth/token` or
`/oauth/telegram/callback`) by the unfiltered selector for those same routes,
both wrapped in `sum by (job, namespace) (rate(...)[1h])`, with no fallback.
In PromQL, a label selector that matches zero series yields an EMPTY vector,
not zero — so when the OAuth token/callback routes receive literally no
requests in a given 1h window (a realistic case: per the file's own comment,
this is a comparatively low-traffic, login-flow-only endpoint), BOTH the
numerator and the denominator are empty, the division has nothing to
divide, and the recording rule emits no series for that evaluation. vmalert's
`RecordingRulesNoData` meta-alert then fires on the missing series.

The same file already documents and fixes this exact class of bug for the
rolling-28d compliance rules two groups down (`mctl-telegram-slo-compliance`,
e.g. `mctl_telegram:oauth_availability:ratio_rate28d`), using an
`or (0 * <always-present-selector>)` fallback specifically because "a
selector that matches no series yields an EMPTY vector, not zero". That
fallback was never applied to the three 1h/6h SLI recording rules in the
`mctl-telegram-slo-sli` group (`tool_errors`, `oauth_5xx`,
`session_borrow_errors`), which is why this alert is on `oauth_5xx:ratio_rate1h`
specifically: it is the lowest-traffic of the three, so it is the first to hit
an all-empty window.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
Record: `mctl_telegram:oauth_5xx:ratio_rate1h` (group `mctl-telegram-slo-sli`)

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

New `expr` (adds a zero-fill fallback keyed on the unfiltered
`mctl_http_requests_total` metric, which the service emits for every route it
serves and so is present even in a window with zero OAuth-route traffic —
mirroring the fallback idiom already used for the 28d compliance rules in the
same file):
```
(
  sum by (job, namespace) (
    rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h])
  )
  /
  sum by (job, namespace) (
    rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])
  )
)
or
(
  0 * sum by (job, namespace) (rate(mctl_http_requests_total[1h]))
)
```

This records 0 (no OAuth errors) for any (job, namespace) that is emitting
any HTTP traffic at all but had zero OAuth-route requests in the window,
instead of recording nothing. It does not change behavior for any window
where OAuth-route traffic exists.

## Confidence: LOW
The root-cause mechanism (empty-vector division on a selector with no
matching series) is directly grounded in this file's own documented reasoning
for the equivalent 28d-rule bug, so that part is confident. The exact
zero-fill expression above is a proposed mirror of the existing idiom but has
not been evaluated against `promtool`/`generated/mctl-telegram-slo.yaml` — the
implementer should validate it with the repo's existing unit-test harness
(`platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`)
before merging, adding a case analogous to the existing 28d
"records 0/1 at the extremes" tests but for a window with zero matching
traffic at all.

## Scope
Minimal. Only the `expr` field of the single recording rule
`mctl_telegram:oauth_5xx:ratio_rate1h` is changed. The sibling
`ratio_rate6h` record and the `tool_errors`/`session_borrow_errors` SLI
records share the same latent gap but are out of scope for this specific
alert; flagged as a follow-up in tasks.md.
