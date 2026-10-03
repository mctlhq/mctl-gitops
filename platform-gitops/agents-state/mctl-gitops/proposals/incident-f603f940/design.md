# Design: incident-f603f940

## Confidence: LOW

## Diagnosis
`TooHighChurnRate24h` is one of the default alert rules bundled by the
`victoria-metrics-k8s-stack` Helm chart (`defaultRules.enabled: true` in
`platform-gitops/bootstrap/templates/observability/monitoring.yaml`), not a
custom rule from this repo's own `vm-rules/` directory (confirmed: no match
for "ChurnRate" anywhere under `platform-gitops/infra-components/observability`).
It fires when vmsingle (10.42.6.245:8428, the ingest/query endpoint for the
`monitoring` namespace's single-node VictoriaMetrics) creates too many new
time series over a 24h window — i.e. label-cardinality churn on the metrics
backend itself, not a symptom of any single tenant service.

mctl-agent correctly escalated this: its `analysis` field states no skill
matched (type=generic, alert=TooHighChurnRate24h) and nothing was analysed.
This is consistent with `monitoring.yaml`'s AlertManager `route` block: the
alert is not named in any child route (`null`, `telegram`, or the `mctl-agent`
catch-all's explicit alertname list at the bottom of the route tree), so it
falls through to the top-level default receiver, `mctl-agent` — the same
generic path every unrouted alert takes.

Root-causing the actual cardinality source (e.g. per-pod-name label churn
from Argo Workflow step pods and CronJob pods being scraped with
`vmagent.spec.selectAllByDefault: true`, or a similar per-invocation label
shape) requires ad hoc PromQL investigation against vmsingle
(e.g. `topk(10, count by (__name__)(increase(scrape_series_added[24h])))`),
which this responder cannot run — there is no tenant service or log stream
to query, and mctl-agent has no skill for this class of signal either. That
is why this proposal is LOW confidence and scoped to routing, not to a
cardinality fix: without knowing which metric/job is churning, any relabel
config written here would be a guess that risks silently dropping wanted
series.

## Proposed Fix
Route `TooHighChurnRate24h` directly to a human via Telegram, the same
pattern already used in this file for other alerts mctl-agent has no
actionable skill for (e.g. `NodeCordoned`, `K3sUpgradeJobFailed`,
`ArgoLocalWorkdirPodPending`). This stops a repeat firing from becoming
another dead-end generic ticket while a human investigates the churn source
directly against vmsingle.

File: `platform-gitops/bootstrap/templates/observability/monitoring.yaml`
In the `alertmanager.config.route.routes` list, add a new route entry
before the final catch-all `receiver: mctl-agent` entry (the one matching
`alertname =~ "RecordingRulesNoData|ScrapePoolHasNoTargets|..."`):

```yaml
                  # TooHighChurnRate24h is a bundled VM-health default rule
                  # about vmsingle's own time-series churn, not a tenant
                  # service signal. mctl-agent has no skill for cardinality
                  # diagnosis (needs ad hoc PromQL against vmsingle), so route
                  # straight to a human instead of a dead-end generic ticket.
                  - receiver: telegram
                    matchers:
                      - alertname = "TooHighChurnRate24h"
```

## Scope
Minimal. Only adds one AlertManager route matcher for this exact alertname.
Does not touch vmagent scrape config, retention, or any relabeling — the
underlying churn source is undiagnosed and any change there would be a
guess. Does not modify the existing `mctl-agent` catch-all route.
