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
fail before shutdown starts. The only outside-in observer, the
`mctl-telegram-healthz` VMProbe, samples every 60 s, so a 10-20 s gap can fall
entirely between two samples.

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

## Acceptance criteria (EARS)

- WHEN the spike document `docs/spikes/2977-rollout-client-downtime.md` is merged THE
  SYSTEM SHALL contain an evidence inventory in which every source has a repo path
  or a read-only tool call as its source, plus its sampling interval and retention.
  Every source not observed in this run (Cloudflare analytics/Logpush, UptimeRobot or
  other external monitors, live Kubernetes event retention) SHALL be listed as
  "not observed", never as "absent".
- THE SYSTEM SHALL include a table with the rows *pod lifecycle gap*, *Kubernetes
  unready / endpoint removed*, *ingress (Traefik) 5xx*, *edge (Cloudflare) 5xx/52x*
  and *external client availability*. For each row it SHALL give the source, what
  the row proves, what it cannot prove, and its time resolution and uncertainty.
- THE SYSTEM SHALL include a design matrix for options A, B, C and D. It SHALL cover
  cost, operational risk, bias, failure domain and resulting precision.
- WHEN the offline estimator is given an ordered set of probe-attempt records for one
  rollout window THE SYSTEM SHALL output `old_last_success`, `first_error`,
  `last_error`, `new_first_success`, the observed failing span (lower bound), the
  bracketing span (upper bound), the per-class error counts and a status of
  `measured`, `no_outage_observed` or `unknown`.
- IF two consecutive subject attempts between `old_last_success` and
  `new_first_success` are further apart than the configured maximum sample gap (or
  anywhere in the window when no failure was observed), OR no success exists before
  or after the span, OR
  the control target also failed during the span, OR the declared clock offset
  exceeds the tolerance, OR any attempt in the window reported a probe-local failure
  (DNS resolution of the probe itself, runner abort) THEN THE SYSTEM SHALL return
  `unknown` with a machine-readable reason and SHALL NOT return a duration.
- IF an attempt carries `cf-cache-status` `HIT`, `STALE` or `UPDATING` THEN THE SYSTEM
  SHALL treat the window as `unknown` (`reason: edge_cache_served`). A cached answer
  does not prove the origin was available.
- THE SYSTEM SHALL classify each attempt as one of `ok`, `origin_5xx` (Traefik or app
  502/503/504 without a Cloudflare error page), `edge_52x` (520-527), `timeout`,
  `connect_error`, `tls_error`, `dns_error`, `probe_local_error` or `other`, and
  report counts per class.
- THE SYSTEM SHALL report lifecycle (`shutdown -> listening`) and HTTP outage under
  separate keys, and SHALL never derive one from the other.
- WHILE the estimator or its tests run THE SYSTEM SHALL perform no network I/O. A
  test SHALL fail if the estimator module imports `socket`, `urllib`, `http.client`,
  `requests`, `httpx` or `subprocess`.
- WHEN `python3 tests/test_rollout_outage_estimator.py` runs THE SYSTEM SHALL pass
  every fixture case listed in tasks.md (200->503->200, no traffic, missed probes,
  timeouts, Cloudflare 521, concurrent edge paths, clock drift, no response, probe
  self-failure, cache hit).
- THE SYSTEM SHALL record in the spike document a decision from the issue's
  enumeration and a named owner (or "owner: pending" with whose decision it is). It
  SHALL record one bounded follow-up implementation issue as a draft text, plus
  preview acceptance criteria. The precision target of +/-1-2 s SHALL be stated only
  as proven by the harness for the stated sampling parameters.
- WHILE this spike is in scope THE SYSTEM SHALL NOT change any VMProbe, VMRule,
  blackbox module, Traefik HelmChartConfig, Cloudflare Terraform, service values,
  workflow that deploys, or rollout strategy.

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
