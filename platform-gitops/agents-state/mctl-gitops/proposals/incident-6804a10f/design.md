# Design: incident-6804a10f

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` is defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
(group `mctl-telegram-slo-sli`) as a bare division:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"...",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"..."}[1h]))
```

VictoriaMetrics/PromQL selectors that match zero series return an *empty* vector, not a
vector of zero. When `/oauth/token` and `/oauth/telegram/callback` serve no 5xx responses at
all in the 1h window (the healthy case — corroborated by the canary probes and the absence of
any 5xx-shaped log line in the mctl-telegram evidence gathered for this incident), the
`status_code=~"5.."` numerator selector matches nothing, the division has an empty operand,
and the whole expression evaluates to no data. That is exactly the alertmanager symptom:
"Recording rule ... produces no data", not "ratio is high" — the service is fine, the rule
recording it is not.

This is a known, already-documented gap in the same file: the `mctl-telegram-slo-compliance`
group (rules `mctl_telegram:tool_availability:ratio_rate28d`,
`mctl_telegram:oauth_availability:ratio_rate28d`,
`mctl_telegram:session_borrow_success:ratio_rate28d`) explicitly guards every numerator with
an `or 0 * <denominator-shaped query>` zero-fill, with a comment explaining precisely this
failure mode ("A selector that matches no series yields an EMPTY vector, not zero, and an
empty operand makes the whole division empty"). That guard was applied to the 28d compliance
rules but never back-ported to the 1h/6h SLI rules in the `mctl-telegram-slo-sli` group, which
is why this alert — scoped to `ratio_rate1h` specifically — fires on the SLI rule and not on
the compliance rule.

No skill matched this ticket because it is a generic "recording rule has no data" alert with
no service-specific diagnostic rule in mctl-agent; the actual defect is a gitops/config
authoring gap, not a service outage, so no code or service change is needed.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

Change the `mctl_telegram:oauth_5xx:ratio_rate1h` recording rule's `expr` field (the rule
named in this alert only — the sibling `ratio_rate6h` rule has the same latent gap but is out
of scope per the minimal-change rule below) from:

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

This mirrors, verbatim in pattern, the zero-fill already used and explained in this same file
for `mctl_telegram:oauth_availability:ratio_rate28d` (lines ~162-176). No new technique is
introduced.

## Scope
Minimal. Only the `expr` of the single recording rule `mctl_telegram:oauth_5xx:ratio_rate1h`
is touched. The sibling rules (`ratio_rate6h`, `tool_errors:*`, `session_borrow_errors:*`)
appear to share the same structural gap, but this incident and alert name only this one rule
— fixing the others is a separate, deliberate decision left to a future proposal, not bundled
here.

## Confidence: MEDIUM
The zero-fill defect and fix pattern are directly evidenced in-file (the same gitops repo
already documents and applies this exact fix elsewhere for the same metric family). What is
not independently verifiable from here is live confirmation that /oauth/token currently has
zero 5xx traffic rather than zero traffic entirely — either produces "no data" today, and
both are consistent with all evidence gathered (healthy canary, no 5xx-shaped log lines). The
fix is correct for both cases, since it converts "no data" into a genuine `0` for the
zero-5xx case and leaves a genuinely-firing rule alone if 5xx traffic ever exists.
