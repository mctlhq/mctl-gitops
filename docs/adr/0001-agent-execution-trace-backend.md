# ADR 0001: Agent execution trace backend

**Status:** Proposed

**Numbering note.** `docs/adr/` does not exist anywhere else in
`mctlhq/mctl-gitops` before this proposal. ADR-007, ADR-008 and ADR-010 are
referenced throughout this repository's agent-platform docs
(`platform-gitops/agent-platform/README.md:4`,
`platform-gitops/argo-workflows/cluster-templates/wft-lifecycle-bootstrap.yaml:8`)
but live in `mctlhq/mctl-agents`, a different repository. Whether
`mctlhq/.github#55` intends one org-wide ADR sequence (which would make this
ADR-011) or a per-repo sequence starting at 0001 is not stated anywhere this
investigation could find. This ADR uses the per-repo filename
`docs/adr/0001-agent-execution-trace-backend.md` and records the ambiguity
here so a renumber, if the org-wide sequence is intended instead, is a
`git mv` and a link fix rather than a rewrite. A reviewer who wants the
org-wide sequence should say so on the pull request.

## Context

`mctlhq/mctl-gitops#902` shipped the vendor-neutral producer boundary:

```text
mctl workloads -> OTLP -> OpenTelemetry Collector -> one or more replaceable backends
```

A gateway-mode OpenTelemetry Collector runs in `monitoring`
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`),
accepts OTLP on `otel-collector.monitoring.svc.cluster.local:4317/4318`,
enriches spans with `mctl.team` / `mctl.component` / `k8s.*` /
`deployment.environment.name`, redacts credential-shaped and prompt-shaped
attributes, and exports to exactly one sink today: the `debug` exporter,
whose stdout lands in Loki via promtail.
`platform-gitops/bootstrap/values.yaml` holds `otelCollector.backendEndpoint:
""` with the comment "Empty until a trace backend is chosen".

Issue #903 asks which self-hostable backend, if any, fills that key in,
comparing five candidates against real mctl execution requirements:

- **Traceway** -- MIT, self-hostable, native OTLP, unified
  traces/metrics/logs/AI tracing. Younger ecosystem; this investigation
  could not verify its identity, chart or license -- it appears nowhere in
  this clone.
- **Grafana Tempo** -- OTLP-native general distributed trace backend, strong
  fit with the existing Grafana/Loki stack. Limited AI-specific cost/session
  UX compared with a specialist product.
- **Langfuse** -- self-hostable open-core, MIT core, OpenTelemetry
  ingestion, strong AI-specific trace/session UX and token/cost tracking.
  Heavier production stack: ClickHouse/Postgres/Redis/blob storage.
  Enterprise governance features are commercially licensed.
- **Arize Phoenix** -- self-hostable, OpenTelemetry/OpenInference-oriented
  tracing, strong evals/experiments UX. ELv2 source-available license
  rather than permissive OSS; better suited as an AI eval/trace specialist
  than a general platform tracing backend.
- **SigNoz** -- OpenTelemetry-native and self-hostable, explicit LLM
  observability for token/cost spans, investing in agent-native/MCP access.
  ClickHouse-backed; overlaps more with the existing
  Loki/VictoriaMetrics/Grafana stack than a pure trace store.

The issue names three possible architectural outcomes: a single backend
covers both ordinary distributed tracing and AI/agent observability; a
general trace store paired with an AI specialist; or the existing
mctl-native dashboards plus Tempo are sufficient and no specialist backend
earns its operational cost. No candidate-specific SDK may be added to
`mctl-agent` or `mctl-agents` -- OTLP/OpenTelemetry remains the only
application contract, which is exactly what `#902`'s Collector boundary
exists to guarantee regardless of which candidate wins.

**DevLoop implementation boundary (2026-09-19).** The issue's own boundary
note splits this work in two. This ADR, its frozen rubric
(`docs/adr/0001-rubric.yaml`), the Stage A paper screen below, the
representative DevLoop trace fixtures
(`tests/fixtures/devloop-trace{,-redaction}.json`), the generalized exporter
list and the gated evaluation manifests are the `mctlhq/mctl-gitops`
implementation half, completable in one pull request that changes zero
cluster state. Everything that requires a live cluster -- creating
`observability-eval`, deploying candidates, turning the fan-out on, the
soak, filling the rubric cells from measurements, choosing and recording the
verdict, and tearing down -- is `mctlhq/mctl-gitops#1280` and is deliberately
not part of this PR's done-ness.

## Frozen rubric

Weights sum to 100. See `docs/adr/0001-rubric.yaml` for the full
machine-readable rubric (cell-level definitions, per-candidate score cells,
all null in this PR) -- `tests/test_adr_rubric_frozen.py` asserts this table
and that file agree dimension-for-dimension.

| Dimension | Weight |
|---|---|
| Trace reconstruction | 25 |
| AI/agent observability | 25 |
| Data ownership / portability | 20 |
| Operations | 15 |
| Security / privacy | 10 |
| Evals / quality loop | 5 |

Each cell is scored 0-5 against a written definition per level (see the
rubric's `cell_scale`); weighted total out of 500; **tie margin 25 points**,
broken in favour of the smaller new operational dependency surface on this
cluster (no ClickHouse runs anywhere in
`platform-gitops/infra-components/data/` today, which makes this a decidable
criterion rather than a taste judgement).

### Decision rule

1. One candidate wins outright on both trace reconstruction and AI/agent
   observability and is not last on operations -> **single backend**.
2. Else the best general trace store and the best AI specialist each win
   their own axis by more than the tie margin and their combined measured
   footprint fits the cluster -> **general trace store + AI specialist**,
   the specialist explicitly not the FinOps source of truth.
3. Else no candidate's AI/agent score exceeds by more than one point what
   the existing `openclaw-llm-usage` dashboard pattern
   (`infra-components/observability/grafana-dashboards/openclaw-llm-usage-dashboard-configmap.yaml`)
   already delivers -> **ADOPT TEMPO / mctl-native only**. This is the
   deliberate default when the spike is inconclusive: one values key, one
   Grafana datasource ConfigMap, one bucket, trivially reversible.
4. Else **CONTINUE COMPARISON** with one named blocker.

No score exists yet in this PR, so this rule cannot be evaluated today; it
is frozen so that when scores do exist under #1280, the rule that consumes
them was fixed first.

## Stage A paper screen

A *paper* screen only -- it ranks nothing and scores nothing. Every claim
that rests only on the text of issue #903 is recorded with
`evidence: issue-903-body` and, where that claim is load-bearing for the
deployment path, the candidate is marked `UNVERIFIED` rather than
`SURVIVES`. A screened-out candidate would keep its row with the reason;
none is screened out at this stage of this investigation. See
`docs/adr/0001-rubric.yaml`'s `stage_a` block for the full row detail
(license, deploy path, dependencies, OTLP ingestion, raw export, footprint
claim, evidence, verdict). Summary:

| Candidate | License | Verdict | Why |
|---|---|---|---|
| Traceway | MIT (asserted) | UNVERIFIED | Appears nowhere in this clone; issue text is the only source. |
| Tempo | AGPL-3.0 | SURVIVES | Verified against upstream Grafana Tempo documentation and this repo's existing chart-pin conventions. |
| Langfuse | MIT core (asserted) | UNVERIFIED | Dependency list and OTLP ingestion claim not independently confirmed. |
| Phoenix | ELv2 (asserted) | UNVERIFIED | Plain-OTLP-only ingestion (the Stage A portability gate) is not confirmed; the issue describes it as OpenInference-oriented. |
| SigNoz | MIT/Apache-2.0 core (asserted) | UNVERIFIED | ClickHouse dependency and OTLP-native LLM observability claim not independently confirmed. |

**Stage A portability gate.** A candidate that cannot ingest plain OTLP
without a vendor SDK or vendor-specific instrumentation in producer code
fails this gate, because that would violate the no-candidate-SDK constraint
issue #903 places on `mctl-agent` / `mctl-agents`. Phoenix's OpenInference
orientation is the one candidate where this gate's answer is not yet known;
#1280 resolves it before treating Phoenix as a live candidate.

## FinOps boundary

Per `mctlhq/.github#48`: **the selected observability backend is not
automatically the financial source of truth.** `mctlhq/.github#48` defines a
backend-neutral usage/cost contract tied to execution identity; a backend
selected here may visualize and aggregate that data, but mctl must be able
to reconstruct per-DevLoop spend without depending on a proprietary
backend's pricing model or retention policy. This ADR does not define that
contract -- it only records the boundary and, via the correlation attributes
in the trace fixtures below, makes it testable once #48 lands.

## Representative trace fixtures

`tests/fixtures/devloop-trace.json` and
`tests/fixtures/devloop-trace-redaction.json` are the fixed input every
candidate is judged against once #1280 runs the comparison: two executions
(one success, one error) covering the Temporal, Argo, model, MCP/tool,
GitHub, artifact and outcome spans issue #903 calls out, plus a deliberately
poisoned variant that exercises the collector's redaction block lists.

**Fixture-fidelity caveat.** `mctlhq/mctl-agent#38` and
`mctlhq/mctl-agents#195` -- the real span producers -- have not shipped as of
this writing, so every correlation attribute name in the fixtures (
`mctl.execution_id`, `mctl.temporal.workflow_id`, `gen_ai.request.model`,
etc.) is this proposal's invention, not a verified contract. If those issues
land with different attribute names, the fixture is wrong in its strings but
the comparison it drives is not: candidate ranking does not depend on the
exact attribute name, only on the shape of the trace tree. Re-running the
comparison against a real execution once the producers land is an explicit
follow-up under #1280, not a blocker to merging this ADR skeleton.

## Permitted verdicts

Verbatim from issue #903's "Deliverable" section -- the later decision
selects exactly one of these seven, not an eighth option invented at
decision time:

- ADOPT TRACEWAY
- ADOPT TEMPO + AI SPECIALIST
- ADOPT LANGFUSE
- ADOPT PHOENIX for eval specialization
- ADOPT SIGNOZ
- ADOPT TEMPO / mctl-native only
- CONTINUE COMPARISON with an explicit unresolved blocker

## Exit procedure

1. `mctlhq/mctl-gitops#1280` sets `otelCollector.eval.enabled: true` and
   populates `otelCollector.eval.candidates` with the Stage A survivors'
   verified chart/image pins.
2. The same `#1280` sets `otelCollector.backends` to fan the representative
   trace fixtures out to every live candidate via the
   `otel-trace-fixture` `ClusterWorkflowTemplate`
   (`platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`).
3. `#1280` runs the soak, measures the operations dimension from existing
   VictoriaMetrics series (never from vendor documentation), and fills every
   score cell in `docs/adr/0001-rubric.yaml` with a one-line evidence
   citation.
4. `#1280` evaluates the decision rule above against the filled rubric,
   selects exactly one of the seven permitted verdicts, and replaces this
   ADR's Decision section with that verdict and the evidence for it. This
   ADR's status moves from `Proposed` to `Accepted` at the same time.
5. `#1280` tears down `observability-eval` (or, for a `single backend` /
   `general trace store + AI specialist` outcome, migrates the winning
   candidate(s) out of the disposable evaluation namespace into their
   permanent home) using the `mctl.ai/teardown-after` date recorded on the
   namespace as the trigger.
6. If the spike is abandoned rather than concluded, this ADR is amended with
   an `Abandoned` status and the reason -- never deleted -- so the next
   attempt starts from this screen rather than from zero.

## Bake-off scope amendment (#1280, 2026-10-10)

Recorded before any measurement, as the exit procedure above requires.

**Scope: Tempo only.** The owner narrowed this round to a single candidate,
Grafana Tempo, deployed monolithic (single binary, one replica) from the
community chart `tempo` `2.4.0` (Tempo `2.10.8`) into `observability-eval`.
Langfuse, SigNoz, Phoenix and Traceway are not deployed and their rubric
cells stay null. Steps 1 and 2 of the exit procedure therefore apply to one
candidate rather than to every Stage A survivor. A verdict that adopts an
unmeasured candidate cannot be supported by this round's evidence; whether
the remaining candidates get a later round is the owner's call on #1280.

**Storage.** Tempo writes blocks to the Cloudflare R2 bucket `tempo-traces`
through a bucket-scoped token read from Vault by an ExternalSecret; the WAL
is on a 2Gi `emptyDir`, and no persistent volume is used. Retention is 14
days (`block_retention: 336h`, enforced by the compactor), with the bucket's
own 30-day lifecycle rule as a backstop.

**Soak window and declared volume.** Declared here, before the first
measurement:

- Window: from the synthetic span proof (collector → Tempo → Grafana,
  `docs/runbooks/tracing-bake-off.md` step 4.3, timestamp recorded on #1280)
  until 2026-10-23 23:59 UTC, one day before the sandbox's `teardownAfter`
  date of 2026-10-24.
- Volume: synthetic only. The `otel-trace-fixture` workflow with default
  parameters (about 240 spans per submission), submitted once for the proof
  and then at most once a day: under 5,000 spans for the whole window. No
  producer emits OTLP to the collector today (verified 2026-10-10), so real
  producer traffic is declared as none. Instrumenting a producer during the
  window is an amendment recorded here, with a reason, before it lands.

**Accepted risks, for the bake-off only.** Spans not yet flushed are lost
when the pod is deleted or rescheduled, because the WAL is on an
`emptyDir` (a container restart keeps it). An R2 outage that lasts longer
than the 2Gi WAL can absorb loses spans as well. Both are acceptable for an
evaluation with synthetic traffic and would have to be revisited for any
permanent deployment. The runbook lists the remaining, smaller ones.

**Teardown.** If Tempo is not selected, the teardown commit removes the
deployment, its alerts and its datasource (runbook step 9), and the
`tempo-traces` bucket is emptied. If it is selected, nothing is promoted in
place: a permanent tracing backend, and turning tracing on across
production workloads, are each a separate owner gate after this ADR's
verdict.

## Producer amendment: DevLoop traces (#1280, mctl-agents#195, 2026-10-10)

Recorded before any producer emits, as the soak declaration above requires.
It changes only the "real producer traffic" line. The window, the synthetic
volume, storage, retention and the teardown date stay as declared.

**Reason.** `mctlhq/mctl-agents#195` closes only on a real DevLoop rendered
end to end, and this issue's preconditions say final scoring must use
correctly exported live telemetry. A synthetic-only soak cannot fill the AI/agent
observability cells from real data.

**Producer, and only this producer.** The `mctl-agents` DevLoop:

- the worker Deployments that run DevLoop activities, with
  `MCTL_TRACE_WORKFLOW_TYPES=DevLoopWorkflow`. A run of any other workflow
  type (reconcile, incidents, sweep, poller, schedules) gets an unsampled
  root, and nothing under it is recorded;
- the `mctl-agents-investigate` and `mctl-agents-implement` pods, with
  `MCTL_TRACE_REQUIRE_PARENT=true`. A pod that a traced DevLoop did not
  submit stays inert.

`mctl-agent`, `mctl-api` and every other `base-service` release stay
uninstrumented. Each of them would need its own amendment here.

**Declared volume.**
- **Rate:** 101 issue investigations in the 14 days to 2026-10-10 (about 7 a
  day), with at most as many implementations.
- **Spans per run:** an upper estimate of 1,000 for an investigation and
  2,000 for an implementation. That is one span per model message plus one
  per tool call, within the $8 budget.
- **Bound:** about 21,000 spans a day, or about 300,000 over the rest of the
  window.
- **Cap:** 500,000 producer spans for the whole window, measured as
  `tempo_distributor_spans_received_total` minus the fixture's
  submissions. The synthetic declaration (under 5,000 spans) is unchanged
  and counted separately.

**Stop rule.** Any one of the following turns the producer off. The switch is
a one-line revert of the workers' `otel.enabled`, and the pods then go inert
because they no longer receive a sampled `traceparent`.
- the cap is reached;
- `tempo_discarded_spans_total` increases;
- either collector exporter alert for the Tempo exporter fires;
- Tempo's working set passes 80% of its 1Gi limit;
- the leak check finds a single hit. That check is #195 checklist item 11:
  grep the first exported trace for the issue body, proposal text,
  credential shapes and the prompt.

**Privacy.** Two layers redact on the way out: the producer's export guard
(`mctl-agents/docs/observability/execution-traces.md`, "Redaction rules")
and then the Collector's `redaction` processor. No prompt, completion, tool
argument or result, body or command line is recorded. The Collector's
`debug` exporter also writes up to one log line per span to Loki. That line
carries span names, never attributes.

**What this is not.** It is not an adoption of Tempo. It does not turn on
tracing beyond the DevLoop path. It does not extend the window. The
teardown commit (runbook step 9) also removes the producer's OTLP env and
`otel.enabled`, so nothing keeps emitting into a Collector that has no trace
backend.

## Decision

<!-- VERDICT: UNFILLED -->

Not yet decided. The live evaluation that produces the scores for the
matrix above is tracked as mctlhq/mctl-gitops#1280. This section is filled
by that issue with exactly one of the seven verdicts listed under
"Permitted verdicts", and this ADR's status moves from Proposed to Accepted
at the same time.
