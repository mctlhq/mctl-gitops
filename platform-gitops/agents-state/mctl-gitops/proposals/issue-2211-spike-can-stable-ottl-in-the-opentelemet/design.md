# Design: issue-2211-spike-can-stable-ottl-in-the-opentelemet

## Current state

**Collector.** `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
is an Argo CD Application for chart `opentelemetry-collector` `0.173.0`. It
uses the contrib image `otel/opentelemetry-collector-contrib:0.160.0`
(`otelcol-contrib`) and runs a 2-replica Deployment in `monitoring`
(requests 100m/384Mi, limits 500m/512Mi). Only a `traces` pipeline exists
(`logs: null`, `metrics: null`). The processor order is:

1. `memory_limiter`
2. `k8sattributes`: extracts pod labels `mctl.ai/team` -> `mctl.team` and
   `mctl.ai/component` -> `mctl.component`, plus namespace, pod, node and
   deployment
3. `resource`: `insert` of `k8s.cluster.name` and `deployment.environment.name`
4. `redaction`: `allow_all_keys: true`, `blocked_key_patterns`,
   `blocked_values`, `ignored_key_patterns` for `gen_ai.usage.*_tokens`,
   `summary: info`
5. `filter/health`: already OTTL, in the old context-less form
   `traces: span: ['attributes["url.path"] == "/healthz"', ...]`, with
   `error_mode: ignore`
6. `batch`

The exporters are `debug` (`verbosity: normal`, always on) plus
`otlp/backend` when `otelCollector.backendEndpoint` is set. Optional
`otlp/<name>` exporters come from `otelCollector.backends[]`, and
`otlp/eval-<name>` exporters come from `otelCollector.eval.candidates[]`.
Every optional block is values-driven and renders byte-identical when empty.
`tests/test_otel_collector_backends_render.py` pins that pattern.

**Values.** `platform-gitops/bootstrap/values.yaml` sets `otelCollector.backendEndpoint:
"tempo.tracing.svc.cluster.local:4317"` with `backendInsecure: true`. Tempo is
the permanent backend (`docs/plans/tempo-adoption.md`, ADR 0001). As a result,
every span goes to Tempo **and** is printed to the collector's stdout by
`debug`, and promtail ships that stdout to Loki. Each span is stored twice.

**Logs.** `platform-gitops/bootstrap/templates/observability/loki.yaml` runs
`loki-stack` `2.10.2` with Loki `2.9.17`. Its settings are
`limits_config.ingestion_rate_mb: 4`, `ingestion_burst_size_mb: 8`,
`retention_period: 336h`, and a 720h `retention_stream` for Vault audit.
Promtail's pipeline is `cri: {}` plus regex/metrics `match` blocks. Tenant
identity comes from `extraRelabelConfigs` (`mctl.ai/team` -> `team`,
`mctl.ai/component` -> `component`). Logs never pass through the collector,
so OTTL cannot filter or redact them today.

**Metrics.** These go vmagent -> VMSingle (`monitoring.yaml`), outside the
collector.

**Tests and CI.** `tests/test_otel_collector_redaction.py` covers key
classification. `tests/test_otel_collector_redaction_e2e.py` runs the real
`0.160.0` binary in docker with processors lifted from the rendered config,
reads spans back from a file exporter, and supports a `--without-ignore`
mutation proof. `tests/test_otel_collector_backends_render.py` is the render
test. All three run in `.github/workflows/validate-manifests.yml`
(lines ~788-884).

**Docs.** `docs/runbooks/otel-collector.md` documents redaction, volume
control and the backend swap. It says `summary` is "deliberately left unset",
but the template sets `summary: info`, so the runbook has drifted.

**Deployed state checked:**
- `mctl_list_services(team=admins)`: 8 services, all Synced, including
  `mctl-agents-worker`, `mctl-agents-worker-exec`,
  `mctl-agents-worker-implement` and `mctl-support`.
- `$MCTL_GITOPS_ROOT/services/*/*/values.yaml`: `otel.enabled: true` on
  `admins/mctl-agents-worker`, `admins/mctl-agents-worker-exec`,
  `admins/mctl-agents-worker-implement` and `admins/mctl-support`. No other
  tenant (`karabu`, `labs`, `namax66`) has opted in, so all live trace volume
  today has `mctl.team="admins"`.
- `mctl_get_service_logs(team=monitoring, service=otel-collector)`: returned
  0 lines. This tool scopes to catalogue services in tenant namespaces, and
  the collector is a platform Application in `monitoring`. This is a gap,
  **not** evidence of zero output. I did not observe span volume, debug-log
  volume or the collector's refused/dropped counters.
- The deployed collector ConfigMap was not read directly (no read-only tool
  exposes it). The template plus `bootstrap/values.yaml` is taken as the
  intended state.

## Proposed solution

The work has two parts: a written spike verdict and a values-driven pilot on
the traces pipeline. All of it is config in this repo. No image changes.

### 1. Spike document: `docs/spikes/ottl-telemetry-pipeline.md`

The document gives a verdict for each signal:

- **Traces:** go. The collector is already in path and already
  tenant-stamped. OTTL's `filter` and `transform` processors (both in contrib
  `0.160.0`) cover per-tenant drop rules, substring scrubbing
  (`replace_all_patterns`, `replace_pattern`), size caps (`truncate_all`,
  `limit`) and attribute deletion (`delete_matching_keys`). They complement
  `redaction`, which matches whole values and whole keys only.
- **Logs:** OTTL is not reachable while promtail ships directly to Loki. The
  document records the option of a filelog-receiver collector DaemonSet, or a
  promtail -> collector `loki` receiver hop, with a rough cost estimate.
  Today's equivalent levers are promtail `drop`/`replace` stages and Loki
  `retention_stream`. Recommendation: separate follow-up, not this pilot.
- **Metrics:** no change. vmagent relabeling already covers cardinality
  control.
- **Syntax:** the document records the result of running `otelcol-contrib
  validate` against the pilot config at `0.160.0` for both statement forms:
  context-inferred `statements:` with `span.`/`resource.` prefixes, and the
  explicit `trace_statements` contexts. It also records what "OTTL v1"
  guarantees in terms of grammar and function stability, and whether a pin
  bump is needed. This is where the open question in requirements.md is
  resolved.
- **Measurement:** the before/after numbers from the 7-day pilot.

### 2. Pilot: values-driven OTTL processors in `otel-collector.yaml`

New values in `platform-gitops/bootstrap/values.yaml`, empty by default:

```yaml
otelCollector:
  ottl:
    scrub:
      enabled: false
      maxValueLength: 4096
    # Each entry: {team, dropSpanConditions: [<OTTL bool expr over span>]}
    tenants: []
```

Template additions in `otel-collector.yaml`, following the
`{{- range .Values.otelCollector.backends }}` style already used there.

**`transform/scrub`** renders when `ottl.scrub.enabled` is true:

```yaml
transform/scrub:
  error_mode: ignore
  trace_statements:
    - context: span
      statements:
        - truncate_all(attributes, {{ maxValueLength }})
        - replace_all_patterns(attributes, "value", "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "<email>")
        - replace_all_patterns(attributes, "value", "(?i)(token|key|secret|password)=[^&\\s]+", "$$1=****")
```

The pilot uses the explicit-context form because it is known to load at
`0.160.0`. Task 1 decides whether to switch to the context-inferred form.
`$$` escapes the collector's `${...}` env expansion. The block is
`trace_statements` only: there is no logs or metrics pipeline.

**`filter/tenant-<team>`** renders one processor per `ottl.tenants[]` entry:

```yaml
filter/tenant-{{ .team }}:
  error_mode: ignore
  traces:
    span:
      - 'resource.attributes["mctl.team"] == "{{ .team }}" and ({{ cond }})'
```

The team guard is added by the template, not by the author. That is what
makes per-tenant isolation structural rather than a review convention.

Pipeline order:
`memory_limiter, k8sattributes, resource, redaction, [transform/scrub],
filter/health, [filter/tenant-*...], batch`.
Tenant filters must run after `k8sattributes`, because the guard needs
`mctl.team`. Scrubbing runs after `redaction`, so key-level masking still
happens first and the summary counts stay meaningful.

**Debug exporter cost cut.** Render `verbosity: basic` when
`otelCollector.backendEndpoint` is set, and `normal` otherwise. This keeps
the documented "set backendEndpoint to empty" rollback fully observable
through stdout, while removing per-span bodies from Loki in steady state. A
single change in this direction also avoids adding a new values key.

**Validation.** Add a new `scripts/validate-otel-ottl-tenants.py`, or extend
the render test, to assert that each `ottl.tenants[].team` matches
`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` and exists as
`platform-gitops/tenants/<team>/`, and that `dropSpanConditions` contains no
`"` that could break out of the guard's quoting.

**Pilot enablement** is a separate, later values-only PR: `ottl.scrub.enabled:
true`. No tenant rules are enabled by default (see Open questions). The
runbook gets a worked example for `admins`, for instance dropping
`span.kind == SPAN_KIND_INTERNAL` spans with duration under 1ms from one
noisy component, but it stays commented.

### 3. Runbook

Update `docs/runbooks/otel-collector.md` with:
- a new "OTTL rules" section covering the scrub, tenant filter and how to
  add a rule safely;
- a fix for the `summary` drift;
- the new debug verbosity behaviour in the backend-swap section;
- a section on how to read the drop counters
  (`otelcol_processor_filter_spans_filtered`) for the 7-day measurement.

## Alternatives

1. **Extend the `redaction` processor only (more `blocked_values`).** It
   masks a whole value on match. It cannot keep the rest of a URL or message,
   cannot truncate, and cannot condition on tenant. Dropped as insufficient
   for the "per-tenant" and "cost" halves of the question.
2. **Move logs to the collector now (filelog receiver DaemonSet) and apply
   OTTL to all signals.** This would answer the question for logs too, but it
   replaces a working promtail pipeline. Every regex/metrics stage in
   `loki.yaml`, including the Vault audit counters SOC 2 relies on, would need
   porting, and it adds a per-node DaemonSet on a cluster with tight
   headroom. Dropped from the pilot and assessed in the spike document as a
   follow-up.
3. **Tail sampling for cost.** This gives the largest potential reduction,
   but it needs trace-ID-aware routing across the 2 replicas
   (`loadbalancing` exporter, or a single replica). That changes the
   availability model, and sampling also hides agent-execution traces that
   ADR 0001 relies on. Recorded in the spike as a later option.
4. **Free-form per-tenant OTTL statements without a template-added guard.**
   This is more flexible, but one wrong rule can drop or rewrite other
   tenants' spans. Dropped in favour of the template-enforced
   `mctl.team` guard.

## Platform impact

- **Migrations / compatibility:** none. With default values, the only
  rendered change is `debug.verbosity: normal -> basic` while a backend is
  set. Producers and Tempo are unaffected. Span content changes only when
  scrub or tenant rules are enabled.
- **Resources:** OTTL transform and filter evaluation adds CPU per span. The
  regexes are small and current volume comes from one tenant, so this is not
  expected to approach the 500m limit. Task 6 checks the collector CPU and
  memory panels after enablement. Loki ingestion from `monitoring` drops by
  roughly the debug exporter's span bodies. That saving is unmeasured until
  task 1, see Open questions.
- **Risks and mitigations:**
  - *A bad OTTL statement crashlooping the collector.* Config is unmarshalled
    strictly at startup. Mitigation: the e2e test runs the real `0.160.0`
    binary against the rendered config, and Argo CD rolls the 2 replicas one
    at a time.
  - *A runtime evaluation error dropping data.* `error_mode: ignore` on every
    new processor.
  - *Over-broad scrub regex destroying useful attributes such as span names
    and IDs.* `replace_all_patterns` is applied to attribute values only, and
    T3 asserts that a non-matching attribute survives byte-identical.
  - *Cross-tenant drops.* The guard is template-enforced, quoting is
    validated, and the `mctl.team` guard is checked by T4.
  - *Losing debug visibility.* `basic` still logs batch counts. Setting
    `backendEndpoint: ""` restores `normal`.
- **Open questions:** see requirements.md. In particular, OTTL v1 syntax at
  the pinned `0.160.0`, which tenant rules to enable, and the unobserved
  collector volume (`mctl_get_service_logs` returned nothing for
  `monitoring/otel-collector`).
