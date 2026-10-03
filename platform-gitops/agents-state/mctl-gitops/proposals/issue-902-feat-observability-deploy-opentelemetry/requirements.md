# Deploy an OpenTelemetry Collector as the mctl telemetry gateway (traces, phase 1)

## Context

mctl has two production telemetry pipelines today and no third one for traces.
Metrics are scraped by `vmagent` (`selectAllByDefault: true`) and remote-written
into `VMSingle` with 28-day retention
(`platform-gitops/bootstrap/templates/observability/monitoring.yaml:278-288`,
`:35`). Logs are shipped by the `promtail` subchart of `loki-stack` into Loki,
which stores on Cloudflare R2 with 14-day retention
(`platform-gitops/bootstrap/templates/observability/loki.yaml:96-113`, `:79-81`).
There is no trace pipeline and no trace storage of any kind: a repo-wide grep for
`opentelemetry|otlp|4317|4318|tempo|jaeger|traceway` returns zero hits under
`platform-gitops/`, `infrastructure/`, `docs/`, `scripts/` and `cli/` — every hit
is prose in `platform-gitops/agents-state/`. `ROADMAP.md:149` names
"OpenTelemetry/tracing" as an explicitly deferred item, and `ROADMAP.md:35` files
"distributed tracing" under enterprise hardening not yet done. Issue #902 is the
decision to stop deferring it.

Two producer-side issues (`mctlhq/mctl-agent#38`, `mctlhq/mctl-agents#195`) will
emit OTLP spans for agent execution and for the Temporal -> Argo -> agent ->
model/tool -> GitHub chain. Neither can ship until there is somewhere to send
spans. This proposal delivers exactly that: a vendor-neutral OTLP gateway,
deployed through `mctl-gitops`, that receives traces from in-cluster workloads,
enriches them with platform identity, strips sensitive content at the platform
boundary rather than in each producer, buffers across backend outages, and
forwards to whichever trace backend mctl later adopts. The gateway is the thing
that keeps the backend replaceable: swapping Tempo for Traceway or an OTLP SaaS
becomes a values edit in this repo, never a code change in `mctl-agent` or
`mctl-agents`.

## User stories

- AS a platform engineer I WANT an in-cluster OTLP endpoint on gRPC 4317 and
  HTTP 4318 SO THAT instrumented mctl workloads have a single, stable place to
  send execution traces without each one knowing which backend is in use.
- AS a platform engineer I WANT the trace backend configured only in
  `mctl-gitops` SO THAT I can swap Tempo, Traceway or any OTLP-compatible
  backend by editing one Application values block and never touching
  `mctl-agent` or `mctl-agents`.
- AS an SRE debugging a failed agent run I WANT every span annotated with
  cluster, environment, namespace, workload, team and component SO THAT I can
  filter a trace to one tenant and one service without the producer having to
  re-emit platform facts it does not know.
- AS a security owner I WANT prompts, completions, tool payloads, credentials
  and authorization headers stripped at the collector SO THAT no producer bug
  or new attribute name can leak model content or secrets into a trace backend.
- AS a service owner I WANT collector or backend failure to be invisible to my
  workload SO THAT an observability outage never turns into an availability
  incident.
- AS the on-call engineer I WANT the collector to expose its own metrics,
  alerts and a runbook SO THAT a silently dropping telemetry pipeline is
  detected rather than assumed healthy.
- AS a platform engineer I WANT the existing metrics and logs pipelines
  untouched SO THAT introducing traces carries no regression risk for
  VMAgent -> VictoriaMetrics or Promtail -> Loki.

## Acceptance criteria (EARS)

Receiving and reachability

- WHEN an in-cluster workload sends an OTLP/gRPC trace export to
  `otel-collector.monitoring.svc.cluster.local:4317` THE SYSTEM SHALL accept it
  and return a success status.
- WHEN an in-cluster workload sends an OTLP/HTTP trace export to
  `otel-collector.monitoring.svc.cluster.local:4318/v1/traces` THE SYSTEM SHALL
  accept it and return a success status.
- WHILE the collector is deployed THE SYSTEM SHALL expose it only as a
  `ClusterIP` Service with no `Ingress`, no `NodePort` and no entry in any
  Traefik route, so that neither 4317 nor 4318 is reachable from outside the
  cluster.
- WHEN a pod outside the allowed source set attempts to connect to the
  collector THE SYSTEM SHALL deny the connection at the NetworkPolicy layer.
- WHILE the collector NetworkPolicy is applied THE SYSTEM SHALL leave every
  other pod in the `monitoring` namespace unaffected by it (the policy selects
  collector pods only).

Enrichment and attribute preservation

- WHEN a span arrives from a pod in the cluster THE SYSTEM SHALL add
  `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name`, `k8s.deployment.name`
  and the pod's `mctl.ai/team` and `mctl.ai/component` labels as resource
  attributes.
- WHEN a span arrives THE SYSTEM SHALL add `k8s.cluster.name` and
  `deployment.environment` resource attributes taken from the collector's
  configuration, not from the producer.
- IF a span already carries a resource attribute that the collector would
  otherwise add THEN THE SYSTEM SHALL keep the producer's value (insert
  semantics, never upsert), so that execution identity emitted by
  `mctl-agent#38` / `mctl-agents#195` is not rewritten.
- WHEN an operator inspects an exported test trace THE SYSTEM SHALL show the
  enrichment attributes above alongside the producer's own span attributes.

Redaction and privacy

- WHEN a span or resource carries an attribute whose key matches the configured
  sensitive-key patterns (authorization, cookie, api key, token, secret,
  password, Vault paths, `gen_ai.prompt*`, `gen_ai.completion*`, message
  content, MCP tool arguments and results, `db.statement`, HTTP request/response
  headers) THE SYSTEM SHALL remove or mask that attribute before export.
- WHEN an attribute *value* matches a known credential shape (for example a
  GitHub token prefix, an `sk-` API key, a Vault `hvs.` service token, a JWT)
  THE SYSTEM SHALL mask the value even when the key is not on the block list.
- WHILE the collector is running THE SYSTEM SHALL NOT export prompt or
  completion content by default.
- WHEN the redaction test payload is sent THE SYSTEM SHALL demonstrate, in the
  exported output, that each configured sensitive attribute is absent or
  masked while the surrounding non-sensitive attributes survive.

Reliability, backpressure and failure isolation

- WHILE the downstream trace backend is unavailable THE SYSTEM SHALL retain
  spans in the exporter sending queue and retry with exponential backoff for
  the configured maximum elapsed time.
- IF the sending queue is full THEN THE SYSTEM SHALL drop the oldest spans and
  increment `otelcol_exporter_enqueue_failed_spans` rather than block the
  receiver indefinitely.
- IF collector memory crosses the configured soft limit THEN THE SYSTEM SHALL
  refuse new OTLP batches with a retryable status via the `memory_limiter`
  processor rather than be OOM-killed.
- WHILE the collector is unreachable, unhealthy or the backend is down THE
  SYSTEM SHALL leave a representative mctl workload serving traffic with its
  readiness probe green and no elevated error rate.
- WHEN the collector Deployment is rolled (config change or image bump) THE
  SYSTEM SHALL keep at least one ready replica so that the OTLP endpoint stays
  resolvable throughout.
- WHILE the collector is running THE SYSTEM SHALL enforce explicit CPU and
  memory requests and limits on its container.

Backend neutrality

- WHEN the trace backend is changed THE SYSTEM SHALL require edits only to the
  collector's exporter configuration in `mctl-gitops`, with no change to
  `mctl-agent` or `mctl-agents` source, images or environment beyond the
  unchanged OTLP endpoint.
- WHILE no trace backend has been selected THE SYSTEM SHALL still run a
  complete, verifiable traces pipeline whose exported output can be inspected.

Self-observability and operations

- WHILE the collector is running THE SYSTEM SHALL serve a health/readiness
  endpoint used by the container's liveness and readiness probes.
- WHILE the collector is running THE SYSTEM SHALL expose its own Prometheus
  metrics on an internal port, scraped exactly once by `vmagent`.
- WHEN spans are refused, dropped, or fail to export above the configured
  thresholds THE SYSTEM SHALL fire a VictoriaMetrics alert carrying
  `mctl_agent_self: "true"` so that the AlertManager route in
  `monitoring.yaml` does not open a ticket against mctl itself.
- WHILE the collector is deployed THE SYSTEM SHALL be described by a runbook in
  `docs/runbooks/` covering the redaction list, the batching/retry settings, the
  backend-swap procedure and the verification steps.

GitOps and non-regression

- WHILE this change is in effect THE SYSTEM SHALL leave
  `vmagent -> VMSingle` and `promtail -> Loki` configuration byte-identical, so
  that no metrics or logs behaviour changes.
- WHEN the change is merged THE SYSTEM SHALL be reconciled entirely by ArgoCD
  from `mctl-gitops`, with no imperative `kubectl apply` step.
- WHEN CI runs on the pull request THE SYSTEM SHALL pass `helm lint` and
  `kubeconform -strict` on the rendered bootstrap chart, the
  `infra-components` sweep, `scripts/check-vm-rules.sh` including its
  promtool unit tests, and `yamllint`.

## Out of scope

- Producer-side instrumentation. `mctlhq/mctl-agent#38` and
  `mctlhq/mctl-agents#195` own SDK setup, span creation, context propagation and
  token-usage attributes. This proposal only provides the sink.
- Selecting, deploying or operating a trace backend (Tempo, Traceway, Jaeger, a
  SaaS). Phase 1 ships a working pipeline whose export target is a single
  configuration key; backend selection is a follow-up issue.
- Trace retention policy, trace storage sizing and trace-backed dashboards or
  Grafana trace-to-logs correlation. All depend on the backend decision.
- Migrating metrics or logs through the collector. `vmagent`, `VMSingle`,
  `promtail` and `loki-stack` are untouched. The collector config may be shaped
  so metric/log pipelines can be added later, but none are enabled.
- Tail-based or head-based sampling. Phase 1 accepts everything producers send.
- Turning tracing on for every deployed service by default. The
  `base-service` chart gains an **opt-in, default-off** way to point a service
  at the collector; no existing `platform-gitops/services/*/*/values.yaml` is
  flipped on by this proposal.
- mTLS or authentication on the OTLP receiver. Phase 1 relies on in-cluster
  network isolation, consistent with how `pushgateway`, `blackbox-exporter` and
  Loki are reached inside `monitoring` today.
- The broader governance chain (`mctl-agents#196` to `#199`): execution
  identity, runtime policy checkpoints, human approvals and auditable evidence.

## Open questions

- **Which trace backend, and when?** The issue names Traceway and Tempo as
  candidates. Nothing in the repo references either (the only `Tempo` string is
  a CVE note in `agents-state/mctl-gitops/inbox/2026-07-18.md:43`). Proceeding
  with a backend-neutral exporter block that is inert until an endpoint is set,
  plus an always-on `debug` exporter so the pipeline is verifiable in phase 1.
  Recording the choice is a follow-up issue, not a blocker here.
- **Sampling with more than one replica.** Tail sampling requires all spans of a
  trace to land on one collector instance, which a stateless two-replica
  Deployment cannot guarantee without a `loadbalancing` exporter tier.
  Proceeding with no sampling; if volume forces sampling later it should be
  designed together with the replica topology.
- **Persistent sending queue.** A `file_storage`-backed queue survives collector
  restarts but needs per-replica storage, i.e. a StatefulSet. Proceeding with an
  in-memory queue and documenting that an in-flight batch is lost on restart.
- **Environment value.** `deployment.environment` is set from bootstrap values.
  The repo has a preprod cluster under `infrastructure/k3s-preview/`, so the
  value is parameterised rather than hard-coded `prod`; which literal each
  cluster uses needs an operator decision.
- **Who may send.** Phase 1 allows platform namespaces (`admins`, `mctl-api`,
  `argo-workflows`, `temporal`) and tenant namespaces (those labelled
  `mctl.me/tenant`), since tenant workloads are mctl workloads. If traces should
  be platform-only, the NetworkPolicy `from:` list is the single place to
  narrow it.
- **Namespace-wide policy for `monitoring`.** The namespace deliberately has no
  NetworkPolicy at all
  (`infra-components/observability/blackbox/blackbox-exporter.yaml:19-26` calls
  this out as a known gap and a separate decision). This proposal adds a
  pod-scoped policy for the collector only and does not resolve that gap.
