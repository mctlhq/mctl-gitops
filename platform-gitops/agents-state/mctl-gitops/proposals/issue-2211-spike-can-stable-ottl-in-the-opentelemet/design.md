# Design: issue-2211-spike-can-stable-ottl-in-the-opentelemet

## Current state

`platform-gitops/bootstrap/templates/observability/otel-collector.yaml` runs the
OpenTelemetry Collector in gateway mode for **traces only**. The chart is
`opentelemetry-collector` `0.173.0`; the contrib image is pinned to
`otel/opentelemetry-collector-contrib:0.160.0`. The collector has two replicas
in `monitoring`.

Current processor order:

1. `memory_limiter`
2. `k8sattributes` (`mctl.ai/team` -> `mctl.team`,
   `mctl.ai/component` -> `mctl.component`)
3. `resource`
4. `redaction`
5. `filter/health` (already OTTL)
6. `batch`

Exporters are `debug` (`verbosity: normal`) plus `otlp/backend` when
`otelCollector.backendEndpoint` is set. With Tempo configured as the permanent
backend, each span is also printed to collector stdout and shipped by promtail
to Loki.

Logs and metrics do not pass through this collector: logs go promtail -> Loki,
metrics go vmagent -> VMSingle. Therefore this pilot can directly affect traces
only.

Existing coverage includes `tests/test_otel_collector_redaction.py`,
`tests/test_otel_collector_redaction_e2e.py` (real collector binary), and
`tests/test_otel_collector_backends_render.py`.

The previous draft correctly established that the required OTTL functions are
available on `0.160.0`, but it made two incorrect leaps: it treated that as an
answer to a question about **stable OTTL**, and it predeclared `Traces: go`.
The amended design treats `0.160.0` only as a functional baseline. The stable
adoption target is `otel/opentelemetry-collector-contrib:0.164.0`, the first
collector-contrib release carrying the upstream OTTL v1/stability guarantee.
OTTL language stability and the stability level of individual processors are
recorded separately in the final report.

## Proposed solution

The work has three delivery stages and two distinct technical verdicts.

### 1. PR A: baseline, target-version validation and inert mechanism

PR A first records a **0.160.0 baseline**:

- `otelcol_receiver_accepted_spans` and `otelcol_exporter_sent_spans`;
- collector stdout/Loki ingestion bytes for the previous 7 days;
- Tempo ingested bytes;
- validation of both relevant OTTL statement forms and the functions needed by
  the pilot.

That produces only `FUNCTIONAL_FEASIBILITY: GO|NO_GO`.

PR A then bumps the collector image to **`0.164.0`** without enabling any new
OTTL rule. The current trace pipeline and all existing redaction/render e2e
tests must pass against the real `0.164.0` binary. The new OTTL configuration
is also validated on that binary. Only then may the report record
`STABLE_OTTL_SUITABILITY: GO`; any regression or unsupported syntax produces
`NO_GO` and stops the pilot before PR B.

The Helm chart remains at `0.173.0`; only the collector image pin changes.
This keeps the version change minimal and independently reviewable.

### 2. Values-driven OTTL mechanism

New values are inert by default:

```yaml
otelCollector:
  ottl:
    scrub:
      enabled: false
      maxValueLength: 4096
    # attribute: span.name | service.name | mctl.component | http.route | url.path
    # operator:  eq | ne | has_prefix
    # value:     ^[A-Za-z0-9._/:-]{1,128}$
    tenants: []
```

#### Scrub processor

When `ottl.scrub.enabled` is true, render `transform/scrub` after `redaction`
and before `filter/health`. It uses explicit trace contexts and the functions
needed for:

- truncating oversized span attributes;
- replacing email addresses embedded inside attribute values;
- replacing credential-like query/value fragments embedded inside longer
  strings.

The exact syntax is validated with the real `0.164.0` binary before merge.
`error_mode: ignore` keeps evaluation errors fail-open for telemetry retention:
a bad expression does not drop a whole batch or crash the collector.

#### Tenant filters

Tenant values contain **no free-form OTTL**. Each rule is typed:

```yaml
- team: admins
  dropSpans:
    - attribute: mctl.component
      operator: eq
      value: noisy-worker
```

The template maps each attribute to a fixed OTTL path and each operator to a
fixed expression form, then compiles it behind:

```text
resource.attributes["mctl.team"] == "<team>" and <compiled rule>
```

Closed allowlists:

- attributes: `span.name`, `service.name`, `mctl.component`, `http.route`,
  `url.path`;
- operators: `eq`, `ne`, `has_prefix`;
- values: `^[A-Za-z0-9._/:-]{1,128}$` via full-string validation.

Unknown keys, attributes, operators, teams, unsafe values, quotes,
parentheses, whitespace/newlines and template-looking input fail validation.
The template itself also fails on unknown attribute/operator, so safety is not
only a pre-commit convention.

This fixes the earlier design flaw where a free-form condition was merely
wrapped in `mctl.team guard and (...)`; input such as `true) or (true` could
rewrite the boolean expression without containing a quote.

Pipeline order remains:

```text
memory_limiter, k8sattributes, resource, redaction,
[transform/scrub], filter/health, [filter/tenant-*...], batch
```

### 3. Debug exporter cost cut

When `otelCollector.backendEndpoint` is set, render `debug.verbosity: basic`;
when the backend is unset, render `normal` as the rollback/debugging state.

The real **0.164.0** binary must prove that `basic` does not print span
attributes/body: send a sentinel attribute and assert it is absent from
stdout. A mutation at `normal` or `detailed` must make the sentinel appear.

### 4. PR B: explicit pilot enablement

PR B is a separate owner-approved values-only change setting:

```yaml
otelCollector:
  ottl:
    scrub:
      enabled: true
```

No tenant drop rule is enabled by default. Tenant rules require their own
explicit owner decision because they intentionally discard telemetry.

PR B is not allowed unless PR A has produced
`STABLE_OTTL_SUITABILITY: GO` on `0.164.0`.

### 5. PR C: seven-day measurement and final verdict

After seven days, PR C records:

- collector accepted vs exported spans;
- collector stdout/Loki ingestion bytes before/after;
- Tempo ingested bytes before/after;
- CPU/memory impact on the collector;
- final per-signal recommendation.

The report uses explicit verdicts:

```text
FUNCTIONAL_FEASIBILITY: GO|NO_GO
STABLE_OTTL_SUITABILITY: GO|NO_GO
TRACES_PILOT: GO|NO_GO
LOGS: FOLLOW_UP|NO_CHANGE
METRICS: NO_CHANGE|FOLLOW_UP
```

No `Traces: go` is predeclared before the target-version validation and pilot
results exist.

PR A and PR B say `Refs mctlhq/mctl-gitops#2211`; only PR C may close the
issue.

## Runbook

Update `docs/runbooks/otel-collector.md` with:

- the collector image pin and why `0.164.0` is the stable-OTTL floor for this
  spike;
- OTTL scrub and tenant-rule configuration;
- the structural tenant guard and closed allowlists;
- debug exporter behaviour and rollback;
- how to read OTTL/filter counters;
- correction of the existing `summary: info` documentation drift.

## Alternatives

1. **Stay on 0.160.0 because the functions work.** Rejected: that answers
   functional feasibility but not the issue's stable-OTTL question.
2. **Bump the Helm chart as well.** Rejected for this pilot: it widens the
   change surface without being required to validate OTTL v1. The image-only
   move to 0.164.0 is the minimal target.
3. **Extend the `redaction` processor only.** Rejected: it cannot express
   tenant-conditioned filtering, substring-preserving replacement and the
   same size-control behaviour.
4. **Move logs through the collector now.** Rejected: it replaces the current
   promtail path and its audit-related stages; assess separately.
5. **Free-form per-tenant OTTL.** Rejected because it weakens structural
   tenant isolation.
6. **Tail sampling now.** Rejected from this pilot; it changes trace-routing
   and availability semantics and deserves a separate proposal.

## Platform impact

- **Version change:** PR A changes collector-contrib `0.160.0 -> 0.164.0` and
  rolls the two collector replicas. The Helm chart does not change.
- **Default config:** with `scrub.enabled: false` and `tenants: []`, no new
  transform/tenant filter executes. The only intentional steady-state config
  change besides the image pin is `debug.verbosity: normal -> basic` while
  Tempo is configured.
- **Compatibility gate:** all current collector/redaction/render tests are
  rerun on the target binary. Unknown or failing target-version behaviour is
  `NO_GO`, never silently accepted.
- **Resources:** OTTL transform/filter evaluation adds CPU per span only after
  PR B or later tenant-rule enablement. PR A is effectively an image upgrade
  plus debug-output reduction.
- **Rollback:** revert PR B to disable scrub; revert PR A to restore the
  0.160.0 image and previous exporter behaviour. Argo CD rolls the two
  replicas back.
- **Security:** no author-supplied OTTL reaches tenant filter config. The
  template-added `mctl.team` guard plus typed schema and mutation tests protect
  cross-tenant isolation.

## Open questions resolved by implementation

- Exact compatibility of the existing pipeline with `0.164.0`.
- Whether the target transform processor's component-stability level changes
  the final adoption recommendation even though the OTTL language is v1.
- Whether `debug: basic` at the target version is sufficiently quiet for Loki
  cost reduction while remaining useful for batch-level debugging.
- Which, if any, tenant-specific drop rules are worth enabling after the scrub
  pilot; none are enabled by this proposal.
