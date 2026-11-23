# Spike: measure client-visible HTTP downtime during Recreate rollouts of tg.mctl.ai

## Context

`labs/mctl-telegram` (public host `tg.mctl.ai`) deploys with `strategy.type: Recreate`
because MTProto auth keys must never be opened by two pods at once
(`platform-gitops/services/labs/mctl-telegram/values.yaml`). Every rollout therefore
has a window in which no pod serves. Today that window is described only by pod
lifecycle numbers from Loki (old pod `shutdown signal received` to new pod
`listening`: 16.77 s, 18.74 s and 12.85 s in production; 10.83-18.81 s in preview).
These are not client-visible outage measurements: a request can still fail after the
app is listening (readiness, endpoint propagation, Traefik, Cloudflare), and it can
fail before shutdown starts. The existing `mctl-telegram-healthz` VMProbe samples every 60 s, so a 10-20 s
gap can fall entirely between two samples. Traefik 400-599 JSON access logs
are **configured enabled** as of 2026-10-29; the older podscrape comment
asserting access logs were off is stale. Actual running flags and Loki
ingestion must still be verified. Ingress logs need traffic; neither they nor
pod lifecycle spans alone prove a continuous client-visible outage.

The issue asks for a bounded research spike, not a monitoring change. It wants a
source-pinned inventory of existing evidence, a comparison of four minimal designs
(A release-scoped probe, B edge/ingress logs, C existing telemetry only, D hybrid),
a time/identity contract, an offline harness that derives outage bounds (and
fail-closed `unknown`) from synthetic attempt records, and a decision record. No live
probe, CI deployment, cluster or Cloudflare change, rollout or strategy change is
authorized. This proposal delivers a spike document and an offline, network-free
estimator with fixtures and tests in `mctl-gitops`. It does not deliver
instrumentation.

## User stories

- AS the mctl-telegram owner I WANT a per-rollout estimate of the real client-path
  outage with explicit lower and upper bounds SO THAT the effect of
  mctl-telegram#1116 can be judged without claiming zero downtime.
- AS a platform operator I WANT a table that says what each existing signal (pod
  lifecycle, Kubernetes readiness, ingress 5xx, external availability) can and cannot
  prove SO THAT pod lifecycle gaps are never reported as HTTP downtime.
- AS a reviewer of the follow-up implementation I WANT an offline harness with
  negative and edge-case fixtures SO THAT the estimator's uncertainty and `unknown`
  behaviour are verified before any live probe exists.
- AS the platform owner I WANT a decision record with cost, failure modes and
  staged rollback SO THAT I can give or withhold an explicit GO for production
  instrumentation.

## Acceptance criteria (EARS) — revision 2

- WHEN the spike document `docs/spikes/2977-rollout-client-downtime.md` is
  reviewed, IT SHALL cite immutable repository blobs and read-only runtime
  evidence for every telemetry source, its cadence, effective retention,
  availability and data sensitivity. Distinguish **configured** from **deployed,
  ingested and actually observed**. If no runtime evidence was collected say
  `not observed`, never `absent`.
- THE inventory SHALL correct the stale October 6 Traefik podscrape comment:
  `infrastructure/k3s-preview/extra-manifests/traefik-helmchartconfig.yaml.tpl`
  configures `accessLog.enabled: true`, JSON, 400-599 filtering and retries
  (commits `74265995863411c72642d420f223b244aa39ad42`,
  `0679c43e4f1eacdaf0148724ca9a70a95fb41545`, Oct 29).
  Read-only inspection SHALL seek running flags and redacted Loki samples
  before describing live telemetry. Existing logged `Cf-Connecting-Ip` and
  `Cf-Ray` values SHALL NOT be exported into public reports, fixtures or GitHub.
- THE signal matrix SHALL separately enumerate pod lifecycle, pod readiness,
  EndpointSlice membership and ingress endpoint propagation, Traefik-origin
  4xx/5xx, Cloudflare edge failures/challenges and synthetic HTTP vantage
  outcomes. `kube_pod_status_ready` SHALL NOT be asserted to prove
  EndpointSlice membership or client-path availability. List what each signal
  proves, cannot prove, and its timestamp resolution/uncertainty.
- THE decision SHALL compare: A release-scoped fine-grained probe; B currently
  configured Traefik 400-599 logs and counters plus possible Cloudflare data;
  C existing blackbox (60s), KSM/Loki and canary; D a hybrid with verified
  ingress telemetry. The matrix SHALL include data availability, cost,
  privacy, failure domain, bias and resolution. External Cloudflare analytics,
  Logpush, UptimeRobot and K8s event retention are `not observed` unless
  accessed via a permitted live read.
- WHEN the stdlib offline estimator reads timestamped subject/control attempts,
  IT SHALL report `old_last_success`, `first_error`, `last_error`,
  `new_first_success`, per-class counts and **two separate** outputs:
  `http_observations` (per-vantage sampled outcomes and a DESCRIPTIVE
  `failure_event_envelope`) and `continuous_blackout` (default `unknown`).
  The failure-event envelope SHALL NEVER be called an unconditional lower
  bound on uninterrupted HTTP downtime.
- Two failed samples SHALL NOT establish continuous unavailability between
  them. Only with an **explicit, independently justified**
  `single_contiguous_blackout_assumption` may the estimator compute
  *conditional* lower/upper durations and a model-resolution flag. Without
  this assumption `continuous_blackout.status: unknown` and
  `precision_target_met: null`. Any success between first and last failure
  SHALL force `continuous_blackout: unknown/intermittent_success` even when
  the sample envelope is measurable. One fixture SHALL disprove the former
  false inference using 503@t0, 200@t5, 503@t10.
- IF coverage is incomplete, bracketing success missing, control fails, local
  probe fails, clock is untrusted, the response is cached or redirects, THEN
  IT SHALL fail closed with a machine-readable reason. All-success synthetic
  attempts with sufficient coverage SHALL be `no_outage_observed`, meaning
  **no failed sample**, not proven zero outage between probes or on MCP/OAuth.
- THE outcome taxonomy SHALL distinguish `ok`, `origin_5xx` only where
  origin evidence exists, `http_5xx_unattributed` for ambiguous 502/503/504,
  `edge_52x` (520-527), `http_403`, `http_429`, `edge_challenge`
  only with Cloudflare mitigation evidence, `timeout`, `connect_error`,
  `tls_error`, `dns_error`, `probe_local_error`, `other`. A WAF
  challenge does not prove origin unavailability. Distinguish regular
  external ASNs/regions from the privileged in-cluster ASN24940 vantage:
  Cloudflare's SBFM skip means the latter cannot prove global client reachability.
  A healthy control target cannot exclude subject-specific WAF errors.
- THE estimator SHALL perform no network I/O. AST forbidden-import checks
  SHALL be a defense in depth, supplemented by a test-scoped fail-fast socket
  guard and a test asserting no external communications on CLI execution.
- WHEN `python3 tests/test_rollout_outage_estimator.py` runs, IT SHALL cover
  T1-T18 from tasks.md: 200/503/200, 10s timeout, all-success probes with
  zero real-client traffic, gaps, 521/522 vs unattributed 5xx, intermittent
  colos, t0/t5/t10 false lower bound, clock skew, cache HIT, redirects,
  probe-local failure, ASN/WAF challenges and a same-day truncated Loki query.
- THE report SHALL keep `lifecycle` independent of `http_observations`;
  never infer HTTP 503 duration from SIGTERM-to-listening.
  A +/-1–2s precision target SHALL be described only as **conditional-model
  sampling resolution**, not a guaranteed client downtime bound.
- THE output SHALL contain a provisional, justified decision, owner (or
  `owner: pending`), a *draft-only* follow-up issue, preview-only
  acceptance, cost estimate and staged rollback.
- WHILE this spike remains proposed, IT SHALL NOT change running probes,
  VMProbe/VMRule, blackbox modules, Traefik config, Cloudflare, service values,
  rollouts, secrets or PA flags. A reviewed proposal still requires
  a separate owner decision to run the implementer and any live test.

## Out of scope

- Running any live probe, including a 1 Hz probe against preview or production,
  during the spike.
- Enabling Traefik access logs, Cloudflare Logpush, new VMProbes, new alerts or a new
  dashboard.
- Changing `strategy.type: Recreate`, replica counts or readiness probe settings of
  mctl-telegram or mctl-telegram-preview.
- MTProto session ownership/fencing (mctl-telegram#1115), DB retry/readiness and
  graceful shutdown (mctl-telegram#1116), and symptom ownership (mctl-telegram#1108).
- Generic monitoring of additional public sites (mctl-gitops#1773) and any SLO
  redesign.
- Filing the follow-up implementation issue. The spike only drafts it; filing needs
  the owner's design selection.

## Open questions

- Traefik deployment: access logs are configured enabled, but running flags,
  Loki 400-599 records/retention and request coverage have not been independently
  queried. Do not confuse this with an absent pipeline; the runtime check
  must redact raw user IP, full Cf-Ray and request metadata.
- Earlier 0.143.0 Loki reconstruction: the 1000-line service-log query returned
  only newer records starting at ~09:30Z **on the same day as the release**.
  The 14-day retention cannot explain that gap. Seek bounded earlier queries
  if possible, otherwise mark `query_truncated_or_unverified`.
- Cloudflare analytics: is a GraphQL Analytics token with `Zone Analytics:Read` for
  `mctl.ai` available, and at what granularity and retention does the plan expose
  `httpRequestsAdaptiveGroups` per host and status? No Logpush job exists in
  `infrastructure/cloudflare/zones/mctl-ai/*.tf`. Whether one exists outside
  Terraform was not observed.
- Is there an external monitor (UptimeRobot or similar) for `tg.mctl.ai`? Nothing in
  the repo references one. Absence outside the repo was not observed.
- Are any Cloudflare rate-limiting rules applied to `tg.mctl.ai`? A 1 Hz probe from a
  GitHub-hosted runner (not AS24940) is not covered by the SBFM skip rule in
  `infrastructure/cloudflare/zones/mctl-ai/firewall.tf` and may be challenged. This
  must be checked before any follow-up chooses a runner-based vantage point.
- Owner of the decision record: the issue names none. The proposal assumes the
  issue author / mctl-telegram owner decides, and records "owner: pending" until then.
- Kubernetes event retention: `mctl_list_namespace_events` documents a default 1 h
  cluster retention. No event exporter to Loki was found in
  `platform-gitops/bootstrap/templates/observability/`, so readiness transitions of
  past rollouts are likely unrecoverable except via kube-state-metrics samples. Not
  verified live.
