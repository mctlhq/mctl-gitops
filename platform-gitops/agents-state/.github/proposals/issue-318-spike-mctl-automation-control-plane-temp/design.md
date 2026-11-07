# Design: issue-318-spike-mctl-automation-control-plane-temp

## Current state

This repository (`mctlhq/.github`) holds the cross-repo roadmap, spike
reports, event contracts and reference models. It deploys no runtime. The
parts relevant to #318:

- Spike conventions. Reports live in `docs/spikes/<name>.md` and are indexed in
  `AGENTS.md` under `# Spikes`. Manifests live in `roadmap/spikes/<name>.yaml`
  and are validated by `roadmap/scripts/validate.py` against
  `roadmap/schemas/spike-definition.schema.json` (required: `title`,
  `question`, `lifecycle`, `github.issue`, `outcomes` matching
  `^[A-Z][A-Z0-9_]*$`; optional `timebox`, `execution.devloop`, `evidence.report`,
  `epic`, `decision`). `roadmap/scripts/lifecycle_guard.py` runs in
  `.github/workflows/roadmap-validate.yml`. The recent precedent
  `roadmap/spikes/journey-intent-correlation.yaml` keeps `lifecycle: proposed`
  with no `decision` block, because "an agent does not record its own approval".
- Reference-model precedent. `docs/spikes/mcp-gateway-g0/` is a stdlib-only Go
  module (`go.mod`: `module mctl.ai/spikes/mcpgatewayg0`, `go 1.22`) with
  `model/`, `fixtures/*.json`, `harness_test.go`, `bench_test.go`. CI runs it
  in `.github/workflows/workflow-tests.yml` ("Set up Go for the MCP gateway G0
  reference model", `go vet ./... && go test ./...`). Python reference models
  (`security-finding-lifecycle`, `cve-advisory-impact`) run there via
  `unittest discover`.
- Related spike and its overlap. `roadmap/spikes/mcp-tasks-durable-execution.yaml`
  (#41) asks for the thinnest MCP Tasks adapter over Temporal/Argo executions,
  with outcomes `GO_ADAPTER_IN_MCTL_API | GO_UPSTREAM_ONLY | NO_GO` and
  `decisionBy: 2026-12-15`. Its pilot is mctl-api#284. An automation run is
  modelled as an execution that a Task could expose, so these two must not both
  define one execution store.
- Identity precedent. `docs/spikes/journey-intent-correlation.md` (#306)
  proposes `REUSE_WORK_ITEM_ID`. mctl-api mints `wi_` (WorkItem), `we_`
  (execution), `xr_` (execution request) and `cs_` (snapshot). Its D6 notes
  that `we_` phase is not whole-journey completion, and that
  `MCTL_SUBMIT_CREATES_EXECUTION` was unobservable. The automation design
  should reuse `wi_`/`we_` for runs rather than mint a parallel execution id.
- Events contract. `events/README.md` plus `events/schemas/event-envelope.v1.schema.json`
  define a closed envelope of 4096 bytes or less: `id` is a stable dedupe key
  from the source (`X-GitHub-Delivery`, Telegram `event_id`), plus `type`,
  `source`, `occurred_at`, `correlation_id` and `subject`. There are three
  producer streams (`mctl:events:telegram`, `mctl:events:github`,
  `mctl:events:synthetic`) with ACL'd producers on Valkey Streams. Delivery is
  at-least-once with a durable outbox, and "the event is disposable; the
  source is canonical". This is the only verified ingress an `event` trigger
  may subscribe to.
- Epics that own adjacent pieces: `roadmap/epics/surfaces.yaml` (completed;
  WorkItem REST mctl-api#349, delegated surface identity #350,
  surface-originated execution requests #368);
  `roadmap/epics/unified-identity.yaml` (completed; canonical principals
  mctl-api#373, agent and on-behalf-of identity #376, membership by canonical
  principal #377); `roadmap/epics/agent-finops.yaml` (completed; usage ledger
  mctl-api#266); `roadmap/epics/telegram-managed-runtime.yaml` (active; root
  mctl-telegram#1088, reservation-based caps #1092);
  `roadmap/epics/tenant-support-agent.yaml` (active; root #243, A2A task store
  mctl-support#2, budgets #4, MCP wrapper in mctl-api); and
  `roadmap/epics/agent-platform.yaml` (AgentDefinition/ExecutionProfile).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image
  `ghcr.io/mctlhq/mctl-agents:1.117.0`, command
  `python -m orchestrator.temporal.worker --role control`,
  `TEMPORAL_ADDRESS: temporal-frontend.temporal.svc.cluster.local:7233`,
  `TEMPORAL_NAMESPACE: mctl-agents`, and the queue split (ADR-008):
  `mctl-dev-loop` for control and `mctl-dev-loop-exec` for exec. A comment
  says this role "owns the schedules" (issue-poll moved from an Argo cron into
  this worker), and `EXECUTION_REQUEST_DISPATCHER: "true"` claims mctl-api
  execution requests and delivers them with Update-with-Start
  (mctl-agents#461/#487). `[CONFIG]`
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/` and
  `mctl-agents-worker-implement/`: present and referencing Temporal. `[CONFIG]`
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`: tag `0.4.1`,
  host `support.mctl.ai`, Postgres task store shared by two replicas,
  `SUPPORT_ALLOWED_TENANTS: namax66,karabu`, `SUPPORT_TASKS_PER_DAY: "200"`,
  spend caps at service defaults (task 0.50, tenant 10, workspace 50 USD per
  UTC month). Containment comes from the run token (scope support, one tenant,
  read-only routes), not from a NetworkPolicy. `[CONFIG]`
- `mctl_list_services(team=admins)`: ArgoCD complete. Eight catalogue services,
  all Synced: the three mctl-agents workers at 1.117.0, mctl-support 0.4.1,
  mctl-design, mctl-docs, mctl-web and umami. mctl-api and mctl-telegram are
  not in the `admins` catalogue. Their deployed config and the
  Temporal-client, MCP-tool and flag state of mctl-api are **unknown (not
  observed)**, not absent. `[LIVE]`
- The Temporal Schedules actually registered in namespace `mctl-agents`, and
  any Temporal namespace or authorization config: not observable with the
  read-only tools in this run. **Unknown (not observed).**
- mctl-agents, mctl-api and mctl-telegram source code was not cloned in this
  run, so `orchestrator/temporal/worker.py` and the mctl-api Temporal client
  are cited from the issue and prior reports, not read. Task 1 pins and reads
  them.

## Proposed solution

Deliver the spike as research artifacts in this repo only. Nothing runs in
production.

1. `docs/spikes/automation-control-plane.md`, the report, structured like
   `journey-intent-correlation.md`: non-claims and evidence tags, an
   evidence-pins table, D1 to D5, limitations.
2. `roadmap/spikes/automation-control-plane.yaml`, a `SpikeDefinition`:
   `metadata.owner: mctlhq/.github`, `lifecycle: proposed`, `github.issue:
   mctlhq/.github#318`, outcomes `COMPOSE_EXISTING_ONLY`, `EXTEND_MCTL_API`,
   `DEDICATED_AUTOMATION_SERVICE`, `DEFER_WITH_GAPS`, `timebox.decisionBy:
   2026-12-15`, `execution.devloop: true`, `evidence.report`. There is no
   `epic` or `decision` block.
3. `docs/spikes/automation-control-plane/`, a stdlib-only Go reference model
   (`module mctl.ai/spikes/automationcp`, `go 1.22`), plus a CI step in
   `.github/workflows/workflow-tests.yml` and an `AGENTS.md` index entry.
4. `docs/spikes/automation-control-plane/temporal-integration/`, an **isolated real Temporal dev-server integration harness** with a pinned Temporal CLI/server and pinned SDK, a dedicated CI job/check that fails on skip/unavailability, synthetic workflows, loopback-only network binding and cleanup. No production namespace, tokens or credentials.

### Architecture the spike tests (hypothesis B, to be confirmed or refuted)

```
Claude / ChatGPT --MCP--> mctl-api  (identity, tenant, policy, idempotency,
Telegram assistant --A2A/REST relay-->   AutomationDefinition store,
mctl-support (tenant-bound) --MCP-->      template registry)
                                   |  Temporal Go client (Schedule / Start /
                                   |  Signal / Update-with-Start), namespace TBD
                                   v
                       Temporal  --> mctl-agents worker: AgentAutomationWorkflow
                                   |   fire-time checkpoint -> budget reserve ->
                                   |   per-fire WorkItem (wi_) -> xr_ -> we_ -> agent run ->
                                   |   settle -> delivery adapter (Telegram first)
events/ ingress (Valkey Streams, verified producers) --> mctl-api event router
          (allowlist type+subject, dedupe by envelope id) --> Start or Signal
```

Key decisions to evidence:

- **Definition vs run — WorkItem conflict resolved.** `AutomationDefinition`
  (`au_`, versioned, lifecycle `enabled|paused|deleted`) is the standing
  intent. **Every occurrence gets its own WorkItem (`wi_`)**, correlated via
  `automation_id` and a deterministic external/idempotency key derived from
  `(au_, occurrence_id)` or `(au_, verified_event_id)`. Use existing `xr_`
  execution requests and `we_` executions; `AutomationRun` is a query/view
  across those records, **not** a second execution store. `workitem/v1`
  permits at most one non-terminal `we_` per `wi_`; different occurrences
  have different `wi_` and may overlap without violating that invariant.
  Re-delivery of one occurrence resolves to the same `wi_` and at most one
  budget reservation. MCP Tasks (#41) can expose a specific `we_`; the
  standing automation itself is never a Task.
- **Templates, not raw Temporal.** The contract accepts `template:
  {name, version}` from a registry (for example `reminder.v1`,
  `agent.investigate-ci-failure.v1`, `support.diagnostic-followup.v1`). The
  Temporal workflow type, task queue, namespace and signal names are
  server-side mappings. A request carrying a `workflow_type`, `task_queue`,
  `namespace` or `signal` field is refused with `raw_temporal_forbidden`.
- **Triggers.** `at` maps to a Schedule with one action and a fixed calendar
  spec plus `remaining_actions = 1`, or to a delayed start. The spike compares
  both. **Do not assume a DST normalization rule:** probe the real Temporal
  server for gap/overlap behavior and either expose the observed semantics
  or explicitly implement/test a product-layer policy. `schedule` maps to a
  Temporal Schedule with timezone, start/end, a catch-up window and an overlap
  policy (default skip). `event` and `dependency` never create Temporal
  Schedules. The router dedupes by `(automation_id, envelope.id)` and uses
  Update-with-Start keyed on the workflow id `au-<id>-ev-<dedupe>`, so a
  duplicate delivery reuses the same run. The rule for Signal versus a new
  workflow: Signal only when the template declares a long-running "await
  dependency" workflow, otherwise start a new run.
- **Fire-time and action-time checkpoints.** On every fire, before any spend,
  the workflow re-reads owner principal, tenant membership, install revision
  (not revoked, matches the pin or resolution policy) and policy snapshot.
  **Every external action** (including Telegram send) must independently
  re-evaluate current authorization at the existing server-side policy
  checkpoint; revocation during a run blocks future side effects. A failure
  records `refused:<reason>` and may auto-pause after N consecutive refusals.
  Never treat a stale approval or the original fire-time grant as ongoing
  authority.
- **Budget.** Reserve per run before the agent activity, idempotent on
  `we_`; settle on completion or release on failure. This follows the
  reservation-cap pattern of mctl-telegram#1092 and the agent-finops ledger.
  Ceilings apply per run, per owner per day, and per tenant per month, with
  max concurrent runs per definition and per tenant, and an event fanout cap.
- **Support follow-ups.** mctl-support may create only the
  `support.diagnostic-followup.v1` template. Its token is tenant-bound and
  read-only, with TTL of 24h or less, at most 3 fires, a small per-run budget,
  and an explicit tenant-owner authorization reference. Mutating templates
  are refused for this actor.
- **Delete and revoke.** These stop future fires (delete or pause the
  Schedule, unsubscribe from events) and mark the definition. In-flight runs
  are not silently terminated; they may complete read-only computation, but
  **must be denied further external side effects after revocation**, unless
  re-authorized at action time. Explicit `cancel_in_flight: true` requests
  cancellation and preserves an audit trail.
- **Delivery.** Telegram is the first adapter. Delivery failure retries with
  backoff and then records `delivered: failed`, while the result stays
  readable from any surface through `mctl_get_automation` run history.
  ChatGPT same-chat push is `unknown`, see #300.

- **Dual-store reconciliation.** Persist a desired automation state and
  version before touching Temporal, then apply an idempotent Schedule operation
  keyed by a deterministic schedule ID and version. Reconcile observed
  Temporal Schedules against desired state after crashes, timeouts, partial
  creates, pauses, updates and deletes; never run a schedule whose owner or
  definition cannot pass authorization. Inject the failure after Temporal
  accepted `create_schedule` but before MCTL committed success, then prove
  recovery without a duplicate fire. Explicitly model bounded drift alarms,
  orphan cleanup rules and distinction between unknown/unobserved state and
  observed absence.
- **Events are not all CI signals.** The current `events/README.md` covers
  Telegram message and GitHub PR/review streams, not GitHub check/run failure
  events. A CI-failure trigger requires an authenticated ingress producer,
  canonical subject hydration, dedupe, tenant scoping and producer coverage.
  No claim of CI event support before that proof.
- **Cross-surface identity.** A Telegram user id and an MCP OAuth subject
  are only the same principal when the `SurfaceIdentityLink` possession proof
  resolves them. Unknown/revoked links deny automation lookup and mutation.

### Reference model (D4)

The model is plain Go with a `Clock` interface and fake clock, an in-memory
definition store, a `Scheduler` interface whose semantics are modelled on
Temporal Schedules (overlap policies, catch-up window, timezone via
`time.LoadLocation`), an HMAC-SHA256 webhook verifier with a replay window, an
event router, a budget ledger and a mocked agent and delivery adapter.
Fixtures sit in `fixtures/*.json` (principals, tenants, installs, templates,
events). `harness_test.go` covers the four positive demos. `negative_test.go`
covers each negative fixture listed in requirements. `bench_test.go` covers
schedule-storm and fanout throughput with the fake clock. The report presents
the measured numbers as model evidence only. **A separate required real-server
integration suite** launches a pinned Temporal dev-server, connects through a
pinned official SDK, runs an inert registered Worker, creates and describes a
real Schedule, observes the workflow execution, and verifies the result and
Schedule state. A skipped/unavailable check is a failure, not a success;
record the real CLI/server and SDK versions and keep this evidence distinct
from simulated results. The Temporal integration check runs only against
localhost with disposable state; never against the production cluster.

## Alternatives

- **A: `COMPOSE_EXISTING_ONLY`.** Use WorkItem plus MCP Tasks plus
  surface-relayed execution requests (`xr_`) and let each surface hold its own
  timer. This was dropped as the default hypothesis because none of these has
  a standing-intent record, a recurrence or an event subscription. Timers in
  surfaces would create several schedulers, which the issue forbids. It stays
  a scored option in D5.
- **C: `DEDICATED_AUTOMATION_SERVICE`.** A new service with its own store and
  Temporal client. It is held back unless D4 or the threat model show that
  isolation or throughput needs cannot be met by a separate namespace and task
  queue inside the current topology. It adds a fourth identity-aware ingress
  next to mctl-api, mctl-telegram and mctl-support.
- **Raw Temporal MCP (official read-only temporalio temporal-mcp, community
  Python or TypeScript MCPs).** Dropped as a user-facing surface. These expose
  namespace-level operations without tenant, principal or budget semantics,
  and giving agents cluster-admin Temporal tools is explicitly out of scope.
  The read-only official server may be noted as an operator-only diagnostic.
- **D: `DEFER_WITH_GAPS`.** The verdict if D1 shows that the fire-time
  identity re-check (canonical principal across Telegram and MCP) or
  install-revision fencing is not yet available.

## Platform impact

- Migrations: none. No runtime, schema-store or GitOps change. The repo gains
  one report, one manifest, one Go module and one CI step.
- Backward compatibility: the new `SpikeDefinition` must pass
  `roadmap/scripts/validate.py` and `lifecycle_guard.py`. Publication
  (`roadmap-publish.yml`) will list a new proposed spike, which is benign.
- Resource impact: one extra fast Go model-test step plus a distinct CI job
  for a real Temporal dev-server and SDK integration test. The real-server
  job may need pinned binary acquisition and takes longer; its result must be
  required for completion of the research PR, never silently skipped.
- Risks and mitigations:
  - The model diverges from real Temporal Schedule semantics (catch-up,
    overlap, DST). Mitigation: label model results distinctly and run the
    mandatory real `temporal server start-dev` integration check; if CI
    cannot run it, D4 stays blocked until an equivalent reproducible,
    evidence-backed non-production test is a required check.
  - The spike is mistaken for approval. Mitigation: `lifecycle: proposed`, no
    `decision` and no `epic` block, follow-ups listed unfiled, and an explicit
    non-claims section.
  - The spike overlaps #41 and #306. Mitigation: D1 overlap map, and runs
    reuse `wi_`/`we_`.
  - Claims about mctl-api, mctl-telegram or Temporal runtime are stated
    without observation. Mitigation: evidence pins plus `unknown (not
    observed)` tagging, as in this design's "Deployed state checked".
  - Secret leakage in fixtures. Mitigation: synthetic HMAC keys only, marked
    as test material, and no real tokens.
