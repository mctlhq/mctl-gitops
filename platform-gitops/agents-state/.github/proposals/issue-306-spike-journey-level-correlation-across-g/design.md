# Design: issue-306-spike-journey-level-correlation-across-g

## Current state

`mctlhq/.github` (read at `e119aaa2ac0fadf222ff22334146f76ce4b8fe95`) holds the roadmap
and the spike reports, not producer code. The spike deliverable follows the existing
pattern: a report under `docs/spikes/`, a `SpikeDefinition` under `roadmap/spikes/` and a
bullet in `AGENTS.md`.

Files read:

- `roadmap/README.md` (section "SpikeDefinition v1alpha1") and
  `roadmap/schemas/spike-definition.schema.json`. Outcomes must be at least two unique
  `UPPER_SNAKE` values. `lifecycle: proposed` needs no timebox. A `decision` is only allowed
  at `decided`.
- `roadmap/spikes/edge-config-kv-instant.yaml` is the manifest template, including the
  "owner records the decision" comment.
- `roadmap/epics/observability.yaml` (`.github#55`) has `lifecycle: completed`. Its success
  criteria are: "One complete DevLoop is visible as a single correlated trace"; "Span
  attributes reuse canonical execution identity and documented mctl conventions"; and
  private prompts, completions and Telegram bodies stay out of traces. Its correlation work
  items are mctl-api#285 (MCP span context), mctl-agent#97 (cross-system correlation),
  mctl-agents#195/#196 and mctl-docs#116 (attribute catalog).
- `roadmap/epics/agent-governance-decision-assurance.yaml` (`.github#181`, active), with
  phases binding, authorization and decision-record (mctl-agents#701/#702, mctl-api#701
  lineage).
- `docs/spikes/agent-governance-decision-assurance.md`:
  - Section 1.4 observed an approve CWFT audit row with `grant_ref=aar_...`,
    `execution_id=we_...`, `agent_run_id=art_...` and a separate trace id `9706d41d...`
    (source `submit-annotation`).
  - S1: the trace id is not bound into the approval. "the grant's intent hash covers
    execution id, kind, target, args digest, policy rule/version, artifact hash and work
    item id (`workitems#IntentHash`)".
  - S6: "There is no single record joining request, intent, policy, approval, tool result
    and outcome; the join is by id across the audit table, the work-item execution, Argo and
    the `.status.yaml` approval block."
  - Section 8: the D4 field map (`intent.traceId` partial, not stored on the grant;
    `execution.executionId` exists; `actor.tenantId` via `work_item_id`).
  - G8 assigns joined-trace correlation to observability `#55` and the audit record to
    mctl-api.
- `docs/spikes/agent-ui-ag-ui.md` (D1 table and D4) lists the WorkItem store
  (`GET /work-items`, `/executions`, ids `wi_`, `state_version`, `cs_`, `xr_`) and the
  correlation set "`we_`, `wi_`, `aar_`, `trace_id` as references".
- `docs/spikes/security-finding-lifecycle.md` uses one WorkItem reference per canonical
  finding key. This is a precedent for the WorkItem as the long-lived unit of work.
- The `issue-182` proposal design under `agents-state/.github/proposals/`. It pins
  `mctl-api@5dd4e73` `internal/workitems/action_approvals.go`: `IntentHash` covers
  `policy_version`, `artifact_hash`, `work_item_id`.

Contract evidence from the mctl MCP tool descriptions available in this run (`[DOC]`):

- WorkItem: `mctl_create_work_item` creates a canonical `wi_` in a tenant and records
  `origin surface` and an optional `external_key`. `mctl_append_work_item_intent` appends
  "what was asked" as free text; the description says "An intent is provenance, not
  approval". `mctl_request_work_item_execution` records `start` or `resume` requests that
  the platform claims and attaches to the same WorkItem. `mctl_list_work_item_snapshots`
  says "A resumed execution seals a NEW snapshot that names the one it resumed from".
- DevLoop: the workflow id is deterministic, `dev-loop-mctlhq-{repo}-{issue}`. A restart
  after an abandon keeps the workflow id and gets a new run id (`previous_run_id`).
- `mctl_trigger_issue` says: "Only when the server runs with
  MCTL_SUBMIT_CREATES_EXECUTION=on (off by default): the server first records the run as an
  execution of the issue's work item (opening the item if the issue has none)".
- Usage ledger (`mctl_get_usage_summary`) groups by `temporal_workflow_id`,
  `work_item_id`, `execution_id`, `run_id`.
- Incidents expose `trace_id` derived from the workflow's submit audit record.

Naming collision. "intent" already means two things in MCTL:

1. The WorkItem intent entry, which has an integer id and stores provenance text.
2. The approval `intent_hash`, which is the `mctl-action-intent/v1` canonical
   action-binding hash.

A third meaning, `mctl.intent.id`, would make "intent" ambiguous in every query and
record.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `otel.enabled: true`,
  `MCTL_TRACE_WORKFLOW_TYPES: DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"`. The comment
  reads "Bounded DevLoop rollout; other workflow types remain unsampled", with export to
  Tempo through the Collector.
- `services/admins/mctl-agents-worker-exec/values.yaml` sets the same two env vars. Its
  comment says other workflow types (reconcile, incidents, sweep) get an "unsampled root"
  and that the traceparent is sent as the Argo parameter declared by mctl-api (#538) and
  the CWFTs (#1789).
- `services/admins/mctl-agents-worker-implement/values.yaml` sets the same
  `MCTL_TRACE_WORKFLOW_TYPES: DevLoopWorkflow` block.
- `services/admins/mctl-support/values.yaml` has `otel.enabled: true`.
- A grep of the gitops checkout for `MCTL_SUBMIT_CREATES_EXECUTION` found no match. mctl-api
  has no `services/*/mctl-api` entry in this checkout, so the setting is **unknown (not
  observed)**, not "off".
- `mctl_list_agent_executions` and `mctl_get_dev_loop(dev-loop-mctlhq-.github-306)` were
  both refused with "outside the investigate scope of this agent run". No execution or
  DevLoop records were observed.
- mctl-docs (attribute catalog #116), mctl-api, mctl-agents and mctl-telegram source were
  not available in this clone. Their behaviour is cited from the reports above, or is
  unknown.

## Proposed solution

Run the spike as a documentation-only change in `mctlhq/.github`. It produces three
artifacts.

### 1. Report `docs/spikes/journey-intent-correlation.md`

The report follows the structure of `docs/spikes/agent-ui-ag-ui.md`: an evidence pins
table, then sections D1-D6, a verdict, follow-ups and limitations.

**Pins.** Record the 40-hex commits of mctl-api, mctl-agents, mctl-gitops, mctl-docs and
mctl-telegram that were read. Tag every claim `[CODE]`, `[DOC]`, `[DEPLOYED]` or
`unknown (not observed)`.

**D1 identity map.** One row per candidate with these columns: minter, trust (asserted vs
propagated), lifetime, cardinality, spans multiple traces?, survives retry/resume/
`continue_as_new`?, present on paths P1-P5 (the path names from `.github#182`), reason it
can or cannot be the journey key. Expected rows and the current reading:

| Candidate | Current reading (to confirm) |
|---|---|
| `trace_id` | One trace. A DevLoop is designed as one trace, but the approve CWFT was observed under its own trace id, and cron runs are separate roots. Cannot be the journey key. |
| request correlation id (`mctl-telegram#617`, audit `request_id`) | One ingress request. Shorter than the journey. Becomes a child reference. |
| `execution_id` (`we_`) and attempt | One execution. A resume or retry creates another `we_`. Child. |
| Temporal workflow id / run id | The workflow id is stable per issue, including across a restart after abandon. It is not tenant-generic and exists only for DevLoop. The run id changes. A useful secondary key, not the canonical one. |
| `aar_` | One approval request. An authorization record, never a correlation key. |
| `intent_hash`, `artifact_hash`, proposal digest | Exact-content binding. Changes when the proposal is amended. Not stable by design. |
| WorkItem intent entry (integer) | One "what was asked" entry inside a WorkItem. Provenance, child of the WorkItem. |
| `mctl-api#701` decision record | One decision. Many per journey. Child. |
| `work_item_id` (`wi_`) | Minted by mctl-api, tenant scoped, holds intents, executions, requests and snapshots across resumes, and is bound into `intent_hash`. **Candidate journey key.** |

**D2 lifecycle (reuse framing).** The journey is the WorkItem.

- Minting event: WorkItem creation, by the surface that accepts the delegation. For an
  issue, this is the create-or-open that `mctl_trigger_issue` performs when
  `MCTL_SUBMIT_CREATES_EXECUTION` is on.
- Authoritative minter: mctl-api.
- Boundary: one delegated objective.
- Retry, resume and `continue_as_new` keep the `wi_`. Each one adds a `we_` and a `cs_`.
- A material amendment to the same objective appends a WorkItem intent entry and makes the
  existing grant stale (mctl-agents#701 supersede). A different objective means a new
  WorkItem. Content hashes stay the exact-binding layer.
- One WorkItem can hold many decisions and executions. These are represented by the
  existing child records, not by a new id.
- The report must test this framing against the counterexamples in Open questions. If a
  journey that needs one key across several WorkItems is proven, the verdict becomes
  `ADOPT_INTENT_ID`, the name changes (for example `mctl.journey.id`), and D2-D4 are filled
  in for the new id.

**D3 propagation matrix.** For each boundary on ingress/MCP -> mctl-api -> decision/approval
-> Temporal -> Argo -> runtime -> MCP/tool -> GitHub/platform mutation -> evidence, record
whether the `wi_` is asserted, propagated, absent or unknown. Known gaps to verify:

- The issue-to-WorkItem link is gated by `MCTL_SUBMIT_CREATES_EXECUTION`.
- P2 direct approve and P3 incident responder have no WorkItem (`.github#182` 9.1).
- The ingress request id is not recorded on the WorkItem intent or execution request.
- The trace id is not stored on the grant (`.github#182` section 8).

Trust rule: the `wi_` is asserted only by mctl-api. Downstream it is propagated as an
opaque attribute and never trusted for authorization. The binding that matters for
authorization already lives in `intent_hash`.

**D4 OTel contract.**

- `mctl.work_item.id` as a span attribute on root and boundary spans only: ingress
  request, DevLoop root, each CWFT root, approval decision event and mutation span. It is
  not put on every span.
- It is not a resource attribute, because one process serves many WorkItems.
- It is not W3C baggage on external calls, because baggage can leak to third parties. It
  may be internal baggage between mctl components only, if the report finds a boundary
  that needs it.
- Cardinality: one value per WorkItem. Fine as a span attribute and searchable in Tempo
  TraceQL. Never a metric label.
- Catalog owner: mctl-docs#116. Retention follows Tempo retention. The durable join lives
  in mctl-api.

**D5 sampling.** The baseline is workflow-type head sampling. DevLoop is always sampled,
other types are unsampled, and the traceparent crosses Argo through
`MCTL_TRACE_ARGO_PARAM`. Proposed: **DEFER** coordinated journey sampling.

- The baseline already keeps every DevLoop trace, so a journey-level decision adds nothing
  for the governed path.
- Deterministic sampling from a hash of the `wi_` would couple identity to the sampler and
  needs a custom sampler in every producer.
- Debug and incident overrides should be a per-WorkItem force-sample flag, read at the
  next root span. This is a candidate follow-up, not part of the spike.
- Cost bound: no added spans. Only one attribute on a bounded set of spans.

**D6 operator queries.** Each of the four questions is answered as a durable join first,
with an optional trace lookup:

1. "Everything because of this delegation": `GET /work-items/{wi}` with intents,
   executions, snapshots and requests, plus approvals with that `work_item_id`, plus audit
   by `we_`, plus Tempo search on `mctl.work_item.id`.
2. "Which decision authorized this side effect": side-effect audit row -> `we_` /
   `aar_` -> `intent_hash` -> policy rule/version, using durable records only.
3. "Which traces, executions and retries": WorkItem executions, then trace ids from the
   submit annotations and audit, then Tempo.
4. "Did it finish": WorkItem state and latest execution phase. The answer must note the
   #702 misprojection caveat.

**Worked journey.** Use issue `.github#306` itself, labelled illustrative where not
observed:

- trace A: `mctl_trigger_issue` -> DevLoop investigate.
- Proposal digest D1.
- `aar_` created, human decision.
- trace B: approve CWFT (separate trace, as observed in `.github#182` 1.4).
- trace C: implement.
- Optional: a reinvestigate rewrites to digest D2, which supersedes the grant. Or a restart
  after abandon creates a new run id.

All of these share one `wi_`.

**Verdict rule.** `REUSE_WORK_ITEM_ID`, which is a NO-GO on `mctl.intent.id`, applies
unless D1/D3 find a journey that needs one key across more than one WorkItem, or that
starts where no WorkItem can be created. In that case the verdict is `ADOPT_INTENT_ID`.
`NO_CHANGE` applies only if `mctl.work_item.id` is already emitted on root spans and every
P1-P5 path already has a WorkItem.

### 2. Manifest `roadmap/spikes/journey-intent-correlation.yaml`

`SpikeDefinition` with:

- owner `mctlhq/.github`
- issue `mctlhq/.github#306`
- outcomes `REUSE_WORK_ITEM_ID`, `ADOPT_INTENT_ID`, `NO_CHANGE`
- `lifecycle: proposed`
- `execution.devloop: true`
- `evidence.report: docs/spikes/journey-intent-correlation.md`
- no `decision`

### 3. `AGENTS.md`

One bullet under `# Spikes` that links the report.

Follow-ups are listed in the report as candidates with owners only. Expected candidates:

- mctl-docs: catalog entry `mctl.work_item.id`.
- mctl-api: enable or verify `MCTL_SUBMIT_CREATES_EXECUTION`; record the ingress request
  id and trace id on the intent or execution request.
- mctl-agents: emit the attribute on DevLoop and CWFT roots.
- mctl-telegram: attach `wi_` to the request-level correlation in #617.

Each candidate is checked against mctl-api#285, mctl-agent#97, mctl-agents#195/#196,
mctl-telegram#617, mctl-docs#116 and mctl-api#701 before it is filed. Nothing is filed
before the owner decides.

## Alternatives

- **Mint a new `mctl.intent.id` now, as the issue hypothesizes.** Dropped as the default.
  - The WorkItem already has the required lifetime, minter, tenant scoping and child
    model.
  - A second id would need its own minting, storage and propagation, which is the "second
    correlation scheme" that `.github#55` forbids.
  - "intent" collides with WorkItem intents and `intent_hash`.
  - It stays a valid outcome if the evidence demands it.
- **Use the Temporal DevLoop workflow id as the journey key.** It is stable per issue and
  deterministic. Dropped as canonical because it exists only for DevLoop (not for Telegram,
  MCP-only or incident paths), it is keyed by GitHub issue rather than by tenant, and
  Temporal is not the governance store. It stays a secondary join key.
- **Rely on trace links and one long-lived trace per journey.** Dropped. Long traces across
  human approval waits of hours or days are fragile. Separate roots (CWFT, cron, shepherd)
  already exist. Sampled telemetry cannot be the governance record (`mctl-api#701`).

## Platform impact

- Migrations: none. The change is documentation plus one roadmap manifest in
  `mctlhq/.github`. No producer, schema or gitops change.
- Backward compatibility: the new manifest must pass the existing validator, and spike
  issue bindings must be unique (no other manifest binds `.github#306`; checked by grep).
  Spikes are not part of the RoadmapPublication, so no publication changes.
- Resource impact: none in this spike. The recommended direction adds no spans and one
  low-cardinality attribute on root spans.
- Risks and mitigations:
  - Risk: the report asserts deployed behaviour it could not read, such as the
    `MCTL_SUBMIT_CREATES_EXECUTION` value. Mitigation: evidence tags, and
    `unknown (not observed)` is mandatory.
  - Risk: the report treats a trace join as governance proof. Mitigation: every D6 query
    starts from durable records.
  - Risk: the agent records its own decision. Mitigation: the manifest stays `proposed`
    with no `decision`, and the owner records the verdict.
  - Risk: follow-ups duplicate closed `.github#55` work. Mitigation: a duplicate check
    against the listed issues is required before any follow-up is filed.
