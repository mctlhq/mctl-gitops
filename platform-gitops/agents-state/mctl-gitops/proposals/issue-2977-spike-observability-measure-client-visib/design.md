# Design: issue-2977-spike-observability-measure-client-visib

## Current state

### Service under study

- `platform-gitops/services/labs/mctl-telegram/values.yaml`: `strategy.type: Recreate`
  with `rollingUpdate: null` (MTProto keys must not overlap), image `0.145.0` /
  digest `sha256:d256ee26...`, `service.port: 8080`. Readiness probe is `/readyz`,
  `initialDelaySeconds: 2`, `periodSeconds: 2`, `failureThreshold: 3`. A comment
  cites mctl-telegram#1108 as the reason.
- `platform-gitops/services/labs/mctl-telegram-preview/values.yaml`: also
  `strategy.type: Recreate`, host `tg-preview.mctl.ai`. Preview is the only place
  a follow-up may exercise a rollout on purpose.

### Outside-in observation today

- `platform-gitops/infra-components/observability/blackbox/vmprobes.yaml`: VMProbe
  `mctl-telegram-healthz`, `interval: 60s`, `module: http_2xx`, target
  `https://tg.mctl.ai/healthz`, prober
  `blackbox-exporter.monitoring.svc.cluster.local:9115`. The prober is in-cluster.
  Only the target leaves the cluster and comes back through Cloudflare.
- `platform-gitops/infra-components/observability/blackbox/blackbox-exporter.yaml`:
  `replicas: 1`, module `http_2xx` with `timeout: 10s`, `follow_redirects: true`,
  `preferred_ip_protocol: ip4`. One sample per 60 s with a 10 s timeout cannot
  resolve a 10-20 s gap. In a whole-cluster failure the observer dies with the
  observed.
- `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-alerts.yaml`
  (line ~282): `probe_success{job="mctl-telegram-healthz"} == 0`.
  `vm-rules/blackbox-alerts.yaml`: `PublicEndpointDown` with `for: 3m`, plus an
  `absent(...)` guard on the telegram probe. These rules are built for
  multi-minute outages and do not report durations.
- `vm-rules/mctl-telegram-canary.yaml`: the `labs-mctl-telegram-canary` CronJob runs
  every 10 min and pushes `mctl_telegram_canary_*` to Pushgateway. It is an
  end-to-end functional check (OAuth metadata, list_dialogs, get_unread_messages)
  and far too sparse for rollout forensics. It also performs authenticated
  operations, which a rollout probe must not.
- `vm-rules/mctl-telegram-slo.yaml`: the SLIs are app-scoped (recorded from the
  app's own metrics). A request that never reaches a pod is invisible to them.

### Ingress and edge

- `platform-gitops/bootstrap/templates/observability/traefik-podscrape.yaml`: Traefik
  metrics are scraped per pod every 30 s. `traefik_service_request_duration_seconds_bucket`
  is dropped. `traefik_service_requests_total` (by service and code) and the
  entrypoint histogram are kept. The file's own comment records that Traefik
  **access logs are off** (2026-10-06). The Traefik HelmChartConfig
  (`infrastructure/k3s-preview/extra-manifests/traefik-helmchartconfig.yaml.tpl`)
  has no `accessLog` key, so they are still off. A 30 s counter delta can show that
  503s happened for the backend in a window. It cannot show when, and it shows
  nothing if no client sent a request.
- The Traefik websecure entrypoint carries the `traefik-cloudflare-origin`
  middleware (same file). Only traffic that arrived through Cloudflare reaches a
  router, so any probe must use the public hostname, not the origin IP.
- `infrastructure/cloudflare/zones/mctl-ai/firewall.tf`: SBFM/BIC is skipped for
  `ip.src.asnum eq 24940` (Hetzner) on `tg.mctl.ai` and `tg-preview.mctl.ai`. A
  probe that egresses from the cluster is therefore not bot-challenged. A probe
  from a GitHub-hosted runner is not covered by this rule.
- No `logpush` resource exists under `infrastructure/cloudflare/zones/mctl-ai/`.
  Cloudflare analytics access for this run was not observed.

### Retention

- VictoriaMetrics: `retentionPeriod: "28d"`
  (`platform-gitops/bootstrap/templates/observability/monitoring.yaml`).
- Loki: `retention_period: 336h` (14 d)
  (`platform-gitops/bootstrap/templates/observability/loki.yaml`). Pod
  lifecycle lines older than 14 d are gone, which is why the 0.143.0 rollout cannot
  be reconstructed from application logs.
- kube-state-metrics is enabled (`monitoring.yaml`, `kube-state-metrics` /
  `kubeStateMetrics`), so `kube_pod_status_ready` samples exist at scrape
  resolution. No Kubernetes event exporter was found, so events live only for the
  cluster's event TTL.

### Deployed state checked:

- `mctl_get_service_status labs/mctl-telegram`: Argo app `labs-mctl-telegram`,
  project `apps`, Healthy/Synced, updatedAt 2026-11-23T18:24:04Z, image tag
  `0.145.0`, host `tg.mctl.ai`, port 8080, base-service, has database. This matches
  the repo values.
- `mctl_get_service_logs labs/mctl-telegram since=2h lines=20`: the app emits JSON
  logs with `edge_request_id` (Cloudflare ray id, colo suffix such as `-DFW` or
  `-FRA`) and `edge_route`. Loki labels carry `pod` and a `filename` that contains
  the pod UID (`labs_<pod>_<uid>/...`). The pod runs on node
  `mctl-preprod-worker-cx43-fsn1-*`, so production `labs` runs on the cluster
  defined in `infrastructure/k3s-preview/`. This gives a join key between a probe's
  `cf-ray` response header and app logs, when the app logs the probed route.
  Whether `/readyz` requests are logged was not observed.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: same Recreate and
  readiness settings as the clone.
- Not observed: Cloudflare analytics/Logpush, any external monitor
  (UptimeRobot etc.), live Kubernetes event retention, the Grafana dashboards in
  use, and the actual `probe_success` history for past rollouts (no VM query tool in
  this run). All are recorded under Open questions in requirements.md.

### What each signal proves (the table the spike document must carry)

| Observation | Source | Proves | Cannot prove | Resolution / uncertainty |
|---|---|---|---|---|
| Pod lifecycle gap | Loki `shutdown signal received` -> `listening` | No new process was listening during the span | That clients failed, or for how long (readiness, endpoints, Traefik and edge add or remove time) | Log timestamp ms. The meaning is wrong for downtime. 14 d retention |
| Kubernetes unready / endpoint absent | kube-state-metrics `kube_pod_status_ready`, events | The Service had no ready endpoint at sampled instants | Edge behaviour, or what a client got | Scrape interval (+/- one interval). Events expire after about 1 h |
| Ingress 5xx | `traefik_service_requests_total{code=~"5.."}` | At least N 5xx left Traefik for the backend within a 30 s bucket | Timing inside the bucket. Zero 5xx with zero traffic means nothing | 30 s, counter resets on Traefik restart. Access logs off |
| Edge 5xx/52x | Cloudflare analytics or Logpush | Clients hit edge errors (52x = origin unreachable) | Unknown availability. Not observed in this run | Plan-dependent (not observed) |
| External client availability | Outside-in probe through the public hostname | The full path failed or succeeded at each attempt | Behaviour between attempts, at other colos/regions, or on the MCP/OAuth paths | Interval + timeout + clock offset (see the contract below) |

## Proposed solution

The spike delivers documents and an offline harness only. It changes no deployed
object.

### 1. Spike document `docs/spikes/2977-rollout-client-downtime.md`

It follows the shape of `docs/spikes/2286-obi-evaluation.md` (STATUS line,
"not observed never means absent" rule) and contains:

1. The evidence inventory and the table above, each row source-pinned. It includes
   the baseline numbers from the issue, labelled as lifecycle observations and not
   as downtime, and the historical 5-8 s claim from #1108 labelled as a historical
   estimate.
2. A design matrix for A-D (below).
3. The time/identity contract and the estimator algorithm (below).
4. A safety checklist for a future probe. It must be unauthenticated, use GET of
   `/readyz` only, send no cookies or Authorization header, record no response body,
   and log no client IP. It must check `cf-cache-status` (expected `DYNAMIC` or
   `BYPASS`). It must use no query string, because a cache-buster changes the
   request class and is unnecessary if the status is `DYNAMIC`. It must stay at or
   below 1 request/s per target per vantage point and use a hard window cap.
5. The decision record and a draft of one follow-up issue.

### 2. Offline estimator `scripts/rollout-outage/estimate.py`

A stdlib-only Python 3 module with a CLI (`estimate.py <attempts.jsonl> --window
<meta.json>`) that reads attempt records and prints one JSON report. It does no
network I/O, and a test enforces that (requirements.md).

**Attempt record (JSONL, one per probe attempt):**

```
schema: "rollout-probe-attempt/v1"
run_id, vantage {id, kind: in-cluster|runner|external, asn, region}
target: "https://tg-preview.mctl.ai/readyz" | control target
role: "subject" | "control"
seq, scheduled_at, sent_at, received_at   (RFC3339 UTC, ms; received_at null on timeout)
timeout_ms
outcome: ok|origin_5xx|edge_52x|timeout|connect_error|tls_error|dns_error|probe_local_error|other
http_status (nullable), cf_ray (header only), cf_cache_status, redirect_count (must be 0)
```

**Window metadata (one per rollout):** release tag, source SHA, image digest, GitOps
commit, Argo application, Argo sync revision and start/finish, old and new pod
name/UID, Loki lifecycle timestamps (shutdown, listening), clock offset estimate and
its source (`ntp`/`http-date`/`unknown`), interval_ms, max_gap_ms and
clock_tolerance_ms.

**Algorithm (subject attempts, sorted by `sent_at`):**

- `first_error` F is the first non-ok attempt. `last_error` E is the last non-ok
  attempt. `old_last_success` L is the last ok attempt before F. `new_first_success`
  N is the first ok attempt after E.
- For an attempt's observation instant, use `[sent_at, received_at]`. On a timeout,
  use `[sent_at, sent_at + timeout_ms]`.
- Lower bound = `max(0, E.sent_at - F.end) - 2*|clock_offset_uncertainty|`, floored
  at 0. The path was certainly failing at some instant in F's interval and in E's.
- Upper bound = `N.received_at - L.sent_at + 2*|clock_offset_uncertainty|`.
- Report the midpoint +/- half-width, and `precision_target_met = half_width <= 2000 ms`.
- If successes occur between F and E, set `pattern: intermittent` (for example
  concurrent edge paths or colos) and report the envelope plus a transition count.
- Lifecycle duration (`listening - shutdown`) is reported under `lifecycle` and is
  never used in the HTTP bounds.

**Fail-closed `unknown` reasons:** `no_success_before` (L missing),
`no_success_after` (N missing), `coverage_gap` (a gap > max_gap between
consecutive attempts anywhere in `[L, N]`, or anywhere in the window when no failure
was seen, which is why `no_outage_observed` needs full coverage),
`control_failed` (a control-target attempt failed between L and N, so the vantage
point or network failed, not the subject), `probe_local_error`,
`clock_untrusted` (offset unknown or > tolerance), `edge_cache_served`,
`redirect_followed`.

With 1 Hz attempts, a 2 s timeout, ~100 ms latency and a clock offset known to
50 ms, the width is about 2.3 s (half-width about 1.2 s). That is the only
configuration in which the issue's +/-1-2 s target is claimed. The harness fixtures
must show it, and must also show that a 10 s timeout breaks it.

### 3. Fixtures and tests

`tests/fixtures/rollout-outage/<case>.jsonl` + `<case>.meta.json`, and
`tests/test_rollout_outage_estimator.py` (stdlib `unittest`, same style as other
`tests/test_*.py`). It is run explicitly by one new step in
`.github/workflows/validate-manifests.yml`, which is how other tests are wired. The
step runs a Python unit test only and deploys nothing.

### 4. Decision record (provisional, to be confirmed by the owner)

Design matrix summary:

| Option | Precision for a 10-20 s gap | Cost | Bias / risk | Failure domain |
|---|---|---|---|---|
| A Release-scoped 1 Hz probe | about +/-1-2 s (proven only by harness parameters) | ~2 req/s for ~6 min per rollout (subject + control), under 1 MB of records | One vantage/colo, synthetic path only (`/readyz`, not MCP/OAuth) | In-cluster vantage shares the cluster. Control target detects that |
| B Traefik counters + Cloudflare 5xx | 30 s buckets at best. Cannot separate "no traffic" from "available" | Logs: enabling access logs or Logpush is a new pipeline (excluded here) | Traffic-dependent. Absent requests look like availability | Traefik counters in-cluster. Cloudflare off-cluster (not observed) |
| C Existing 60 s probe + lifecycle + KSM | Cannot bound a sub-60 s outage (may see 0 or 1 failed sample) | Zero | Systematic under-reporting. Lifecycle gap misread as downtime | In-cluster |
| D Hybrid A + B + C correlation | A's precision plus attribution (edge 52x vs origin 503) | A + reading existing counters. Cloudflare part depends on access not yet verified | As A, with better attribution | Mixed |

Provisional decision: **`RELEASE_SCOPED_PROBE`**, with existing-telemetry
correlation (Loki lifecycle, kube-state-metrics readiness, Traefik 5xx counters,
`cf-ray` to `edge_request_id`) as attribution only. Upgrade to
`HYBRID_EDGE_AND_PROBE` only if the open question on Cloudflare analytics access is
answered positively. `REUSE_CURRENT_TELEMETRY` is rejected by option C's row.
`EXTERNAL_MONITOR_REQUIRED` is not warranted: the failure under study is pod-scoped,
not cluster-scoped.

Draft follow-up issue (text only, filed after owner GO): "Run the release-scoped
probe for one `mctl-telegram-preview` rollout". Scope: a one-shot Argo Workflow in
`monitoring` that probes `https://tg-preview.mctl.ai/readyz` plus control
`https://mctl.ai/` at 1 Hz with a 2 s timeout from T-60 s to T+180 s around a
preview sync, at most 10 minutes total. It writes JSONL to the workflow log archive
and a summary to Pushgateway, and runs `estimate.py`. It adds no VMProbe, alert or
dashboard. Preview acceptance: five preview rollouts produce `status: measured` or
an explained `unknown`, the half-width is <= 2 s in at least 4 of 5, and there are
zero challenged (403/429) attempts. Production use needs a separate GO.

## Alternatives

- **Raise the existing VMProbe to 1-5 s permanently.** Dropped because it changes a
  deployed probe (not authorized), multiplies samples for every minute of the day
  to serve a few minutes per release, and shares the blackbox 10 s module timeout,
  which by itself breaks the precision target.
- **Enable Traefik access logs or Cloudflare Logpush now (option B as primary).**
  Dropped because it is a new log pipeline (explicitly excluded), it is
  traffic-dependent so it cannot separate absence of traffic from availability, and
  its Cloudflare side was not observable in this run.
- **Infer downtime from lifecycle + readiness only (option C).** Dropped because
  the #1108 record already shows `/readyz` 503 beyond `listening`. Lifecycle is a
  lower-level proxy and would misreport.
- **External SaaS monitor.** Dropped for now: SaaS checks run at 30-60 s at best on
  common plans, they add a vendor, and the failure is pod-scoped. Reconsider only
  if a cluster-wide failure becomes the question.

## Platform impact

- Migrations: none. Backward compatibility: no existing file's behaviour changes.
  The only edit to an existing file is one CI step in `validate-manifests.yml` that
  runs a unit test.
- Resource impact: none at runtime. CI adds well under a second of Python.
- Risks and mitigations:
  - The estimator is mistaken for a probe. Mitigation: no-network import guard test,
    and the spike doc states STATUS: NO LIVE PROBE.
  - Overclaimed precision. Mitigation: `precision_target_met` is computed, fixtures
    show the 10 s-timeout case failing it, and the doc forbids reporting lifecycle
    as downtime.
  - A future runner-based probe gets bot-challenged. Mitigation: recorded as an open
    question. The draft follow-up uses an in-cluster vantage covered by the AS24940
    skip rule, with a control target.
  - Adding a CI step to a required workflow. Mitigation: if the queue's required
    `validate` check is a concern, the step can instead go into an existing shard
    job. Either way it is a pure unit test with no secrets.
