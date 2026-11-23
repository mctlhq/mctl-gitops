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

### Ingress and edge — P1-1 corrected

- `traefik-podscrape.yaml` scrapes Traefik counters every 30 s and
  drops `traefik_service_request_duration_seconds_bucket`. Its October 6
  comment that access logs were off is historical and **stale**.
- `infrastructure/k3s-preview/extra-manifests/traefik-helmchartconfig.yaml.tpl`
  currently configures **`accessLog.enabled: true`**, JSON,
  `filters.statusCodes: "400-599"`, `retryAttempts: true`, and
  `queryParameters.defaultMode: drop`. Commits `74265995863411c72642d420f223b244aa39ad42`
  and `0679c43e4f1eacdaf0148724ca9a70a95fb41545`
  established this on 2026-10-29. Configuration is **not evidence** of
  running flags or ingested Loki data: those remain `not observed` until
  verified read-only. The old comment must not override the current manifest.
- The log filter captures 400–599 **requests reaching Traefik**, not
  successful 2xx requests or Cloudflare-side failures, and does not prove
  availability during zero traffic. Counters sampled every 30 s cannot
  resolve 10–20 s blackouts; runtime-verified 5xx access log events could
  give more accurate error-event timestamps (still not a continuous outage).
- The configured log fields retain `Cf-Connecting-Ip`, `Cf-Ray` and
  User-Agent while dropping Authorization/Cookie, RequestLine and query
  parameters. Protect these identifiers: never paste raw IPs, full ray IDs,
  headers or correlated user agents into test fixtures, GitHub issues or
  spike output. Aggregate/redact before public evidence.
- `firewall.tf` skips Cloudflare SBFM/BIC for traffic from Hetzner
  ASN24940 to `tg.mctl.ai`/`tg-preview.mctl.ai`. An in-cluster
  probe exercises the public route but a **privileged trusted-ASN path**,
  not a representative external client. Healthy control-target traffic
  cannot rule out subject-specific WAF challenges.
- No `logpush` Terraform resource found under the mctl-ai Cloudflare
  zone; actual analytics/Logpush entitlements and external monitors
  remain **not observed**, not proven absent.

### Retention

- VictoriaMetrics: `retentionPeriod: "28d"`
  (`platform-gitops/bootstrap/templates/observability/monitoring.yaml`).
- Loki: `retention_period: 336h` (14 d)
  (`platform-gitops/bootstrap/templates/observability/loki.yaml`). Configured 14-day retention does not explain the unobserved 0.143.0
  window **on the same day of deployment**. The sampled 1000-line Loki query
  returned only newer records starting ~09:30Z: `query_truncated_or_unverified`,
  not `retention_expired`. Check an earlier bounded UTC/pod query if permitted;
  otherwise keep it `not observed`.
- kube-state-metrics is **configured enabled** (`monitoring.yaml`,
  `kube-state-metrics` / `kubeStateMetrics`); the actual
  `kube_pod_status_ready` series and sampling history were **not observed**
  at runtime. No event exporter was found in the searched GitOps paths,
  but live event-retention behavior remains unverified. Pod Ready does not
  prove EndpointSlice or Traefik backend propagation.

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

### What each signal proves — revised inventory

| Signal | Source / evidence | Proves | Does NOT prove | Cadence and gaps |
|---|---|---|---|---|
| Pod lifecycle | Loki SIGTERM and `listening` | Process transition timestamps | HTTP 503 duration | Millisecond log time; not request evidence |
| Pod readiness | KSM `kube_pod_status_ready` | Pod readiness at sampled instants | EndpointSlice propagation or client reachability | Scrape sampled |
| EndpointSlice / ingress endpoint | K8s watch, Traefik dynamic backend state (if readable) | Actual routing membership when inspected | Cloudflare or real user response | **Not observed**; cannot infer from pod readiness |
| Traefik 4xx/5xx | JSON 400–599 access logs configured enabled; 30s counters | Errors for traffic that reaches Traefik | 2xx brackets, absent-traffic health, edge-side errors | Loki runtime not observed; 30s counters |
| Cloudflare 52x / WAF | Edge records or probe headers | Per-request edge failure/challenge | Continuous/global failure | Analytics not observed |
| Synthetic outside-in | Bounded public probe | Per-vantage outcome at sampled times | Between-sample availability, other ASNs, colos, MCP/OAuth | Interval, timeout, clock and trusted-ASN bias |

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

**Attempt schema** (JSONL): `run_id`, `target`, `role`
(subject/control), `vantage` (kind, ASN, region), `seq`, UTC
`scheduled_at`/`sent_at`/`received_at`, timeout, HTTP status,
cache status, redirect count, sanitized colo suffix, outcome.
Outcomes: `ok`, `origin_5xx` (ONLY with independently verified
origin attribution), `http_5xx_unattributed` (502/503/504 without
attribution), `edge_52x` (520-527), `http_403`, `http_429`,
`edge_challenge` (only with CF mitigation evidence), `timeout`,
`connect_error`, `tls_error`, `dns_error`,
`probe_local_error`, `other`. Challenge/403/429 never silently
count as proven origin 503. Store no raw client IP or full Cf-Ray.

**Window metadata**: source tag/SHA, image digest, GitOps commit, Argo
revision, old/new pod UID, UTC lifecycle timestamps, probe vantage
and ASN (trusted or untrusted), interval, maximum gap, timeout,
clock offset + evidence/uncertainty, and optional separately evidenced
`single_contiguous_blackout_assumption`.

**Estimator contract — P1-2 corrected:**

1. `http_observations`: sort subject attempts by `sent_at`; L is
   last successful attempt before first failure F, E last failure,
   N first success after E. Each result is observed during
   `[sent_at,received_at]` or `[sent_at,sent_at+timeout]`.
   Report per-class counts and **descriptive**
   `failure_event_envelope` (F.sent through E.end). It is **NOT
   a lower bound on continuous downtime**. `status: measured`
   means sufficient sampled event coverage, **not** a proved blackout.
   With all-success samples and adequate coverage, report
   `no_outage_observed` = *no failed sample*, not zero true downtime.
2. `continuous_blackout`: default `status: unknown`.
   Even adjacent errors can hide a brief recovery, so discrete
   failures cannot prove uninterrupted outage. Conditional
   single-incident onset/recovery intervals are allowed ONLY if a
   separately justified `single_contiguous_blackout_assumption`
   is provided and no intervening success exists:
   `conditional_lower=max(0,E.sent-F.end-2*clock_uncertainty)`;
   `conditional_upper=max(0,N.end-L.sent+2*clock_uncertainty)`.
   This is **model-dependent**, NOT a guaranteed bound on real
   downtime. `precision_target_met` is null without justification,
   otherwise is a model-resolution check, not an accuracy guarantee.
3. If any success occurs between F and E (even another colo),
   `pattern: intermittent`, count transitions, keep only the
   descriptive failure envelope, and `continuous_blackout:
   unknown/intermittent_success`. Fixture: 503 t=0, success t=5,
   503 t=10 must **never** claim 10s continuous failure.
4. Fail closed to machine-readable `unknown`: missing L or N,
   coverage gaps (including all-success windows), control failure,
   probe-local failures, untrusted clocks, cache HIT/STALE/UPDATING
   or ambiguous route cache policy, redirect, and unsupported
   continuity assumption. A healthy control target does not prove
   target-specific WAF is absent.
5. `lifecycle` is a separate object; never derive `http_outage`
   from SIGTERM → listening. +/-1–2s is a possible **conditional
   sampling resolution** for a specific 1Hz/2s-timeout model, not
   a real-world continuous-blackout guarantee. No high-frequency
   live probe is authorized by this spike.

**Offline safety:** stdlib-only estimator, no network I/O. AST
forbidden-import scan is defense-in-depth; test with a fail-fast
network/socket guard too (not an AST-only isolation claim).

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
| A Release-scoped 1 Hz probe | +/-1–2s **conditional model sampling resolution**, not true downtime guarantee | ~2 req/s for ~6min per rollout | Trusted ASN24940 one-colo synthetic path; hidden recoveries | Shares cluster failure domain; control cannot rule out WAF |
| B **Existing configured Traefik JSON 400–599 logs** + counters + optional CF data | Individual error events IF runtime verified, 30s counters, no success brackets | Reuse configured access logs, Cloudflare read access not observed | Traffic dependent, absent traffic != availability, sensitive IP/ray | Traefik in-cluster; CF availability unknown |
| C Existing 60 s probe + lifecycle + KSM | Cannot bound a sub-60 s outage (may see 0 or 1 failed sample) | Zero | Systematic under-reporting. Lifecycle gap misread as downtime | In-cluster |
| D Hybrid A + **verified** B logs + lifecycle | A's conditional sampling plus ingress attribution | Bounded probes + existing configured logs | Still no continuous/global availability proof | Mixed failure domains |

Provisional decision: **`RELEASE_SCOPED_PROBE`**, potentially
**`HYBRID_EDGE_AND_PROBE`** once the already-configured Traefik
400–599 JSON access logs have been verified live in redacted Loki.
A hybrid does not require Cloudflare Analytics, but any optional
Cloudflare edge evidence needs separate verified entitlements and
granularity. Existing 60s probes alone cannot establish short outages.
Neither probe nor ingress logs alone prove continuous real-client
availability; record model assumptions and vantage limitations.

Draft follow-up issue (text only, filed after owner GO): "Run the release-scoped
probe for one `mctl-telegram-preview` rollout". Scope: a one-shot Argo Workflow in
`monitoring` that probes `https://tg-preview.mctl.ai/readyz` plus control
`https://mctl.ai/` at 1 Hz with a 2 s timeout from T-60 s to T+180 s around a
preview sync, at most 10 minutes total. It writes JSONL to the workflow log archive
and a summary to Pushgateway, and runs `estimate.py`. It adds no VMProbe, alert or
dashboard. Preview acceptance: five bounded preview rollouts have
documented sampled outcomes (`measured`, `no_outage_observed` or
specific `unknown`); stable probe cadence, cache bypass and 403/429
classification; no real client writes. +/-2s is tested as a
**conditional sampling-resolution goal**, not presumed true blackout
accuracy. Do not infer continuous downtime from sample failures
without independent evidence. Production use requires a separate GO.

## Alternatives

- **Raise the existing VMProbe to 1-5 s permanently.** Dropped because it changes a
  deployed probe (not authorized), multiplies samples for every minute of the day
  to serve a few minutes per release, and shares the blackbox 10 s module timeout,
  which by itself breaks the precision target.
- **Enable a new Traefik logging pipeline or Cloudflare Logpush now.**
  Traefik access logs are already **configured on**, so verify that
  runtime ingestion first. New logging/Logpush is out of research scope;
  even existing 400–599 lines lack 2xx success brackets and say nothing
  about availability in an idle window.
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
  - The estimator is mistaken for a probe. Mitigation: static AST check plus test-scoped fail-fast network guard,
    and spike doc STATUS: NO LIVE PROBE.
  - Overclaimed precision. Mitigation: keep the observed failure
    envelope descriptive, model-bound duration explicitly conditional
    on an independent continuity hypothesis; test t0/t5/t10 and
    hidden-recovery counterexamples. Lifecycle is separate.
  - A runner may be WAF-challenged, while in-cluster ASN24940 is
    a privileged path. Mitigation: classify 403/429 and challenges,
    note target-specific WAF cannot be ruled out by a healthy control,
    and forbid extrapolation to ordinary external users without
    independent vantage evidence.
  - Adding a CI step to a required workflow. Mitigation: if the queue's required
    `validate` check is a concern, the step can instead go into an existing shard
    job. Either way it is a pure unit test with no secrets.
