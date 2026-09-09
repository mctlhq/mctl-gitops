# Design: incident-5b1eed1e

## Diagnosis
`mctl_telegram:oauth_5xx:ratio_rate1h` and its `ratio_rate6h` sibling, defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
compute a plain division of two PromQL vector selectors:

```
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"...",status_code=~"5.."}[1h]))
/
sum by (job, namespace) (rate(mctl_http_requests_total{route=~"...",}[1h]))
```

A `status_code=~"5.."` selector that matches zero time series (i.e. the OAuth
token/callback routes served no 5xx responses in the window — the expected,
healthy case) yields an EMPTY vector, not a zero. An empty numerator makes the
whole division empty, so the recording rule itself emits no sample for that
evaluation — which is indistinguishable from "never measured" and is exactly
what trips vmalert's RecordingRulesNoData check.

This is not a guess: the same file already documents and fixes this precise
failure mode for the neighboring 28d compliance rule,
`mctl_telegram:oauth_availability:ratio_rate28d` (lines 155-161), with a
`... or 0 * sum(...)` zero-fill on the numerator, and the comment there states
outright: "with traffic served and no 5xx at all, the status_code=~"5.." selector
matches nothing, the numerator is empty, and `1 - empty` is empty — so the
series would vanish precisely when OAuth is perfect." The 1h/6h SLI rules that
feed the burn-rate alerts (`mctl_telegram:oauth_5xx:ratio_rate1h` /
`ratio_rate6h`) were never given the same treatment, so they hit the identical
bug on every fully-healthy evaluation window. The log evidence shows steady
OAuth-adjacent traffic (client_registration, oauth_metadata probes) and no
visible 5xx, consistent with a healthy-but-briefly-empty numerator rather than
a scrape or service outage — vmalert itself logged nothing (Loki returned zero
lines for it), and mctl-telegram's ArgoCD health is Healthy/Synced.

## Proposed Fix
File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`

Apply the same zero-fill pattern used for `mctl_telegram:oauth_availability:ratio_rate28d`
to the two 1h/6h SLI rules, so a healthy window (traffic present, zero 5xx)
records a genuine `0` instead of emitting nothing:

Current (`mctl_telegram:oauth_5xx:ratio_rate1h`, lines 86-94):
```
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
```
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

Apply the identical change to `mctl_telegram:oauth_5xx:ratio_rate6h` (lines
95-103), substituting `[6h]` for `[1h]` in all three range vectors, mirroring
the existing rate1h/rate6h pairing already used throughout this file.

## Scope
Minimal: only the two recording rule expressions
(`mctl_telegram:oauth_5xx:ratio_rate1h`, `mctl_telegram:oauth_5xx:ratio_rate6h`)
gain a numerator zero-fill, copied verbatim in structure from the already-shipped
`mctl_telegram:oauth_availability:ratio_rate28d` pattern in the same file. No
alert thresholds, no other SLIs, no unrelated rules are touched.

Residual gap, out of scope here: if the OAuth token/callback routes see
literally zero requests in the whole window (denominator also empty), the fix
above cannot manufacture a value — `0 * empty` is still empty. That case would
need a `mctl_http_requests_total` count guard or a longer window and is a
separate, larger design decision (possibly touching the alert semantics), not
a one-line fix. Flagging it here for the implementer/reviewer rather than
bundling it into this change.

## Confidence: LOW
The diagnosis is grounded in the file's own comments describing an identical,
already-fixed bug in a neighboring rule, and in log evidence of steady
OAuth-adjacent traffic with no visible errors. However, this responder does not
have direct query access to VictoriaMetrics/vmalert (no PromQL execution
tool), so it cannot directly confirm whether the numerator or the denominator
(or both) were empty at alert time. If the residual "true zero traffic" case
above turns out to be the actual cause, this fix alone will not fully resolve
recurrence and the implementer should verify against actual metric data before
or after applying.
