# Design: issue-261-experiment-agent-ui-prove-bounded-ag-ui

## Current state

Repository role. `mctlhq/.github` holds plans, spike reports, roadmap manifests and
contracts, not service code. `AGENTS.md` lists active spikes. The latest commit
(`e7cf8e8`, "record AG-UI Phase A verdict and Phase B follow-up") added:

- `docs/spikes/agent-ui-ag-ui.md` is the Phase A report. It pins `@ag-ui/core@1.0.3`
  (`a1131c90...`) and the 1.0.3 `EventType` enum. In the report:
  - D1 inventories durable facts: `we_` executions, `wi_` WorkItems with
    `state_version`, `aar_` approvals, human-input `request_id`, the abandon signal,
    the usage ledger with three cost fields, and evidence/audit refs.
  - D1 also finds no streaming surface at the pins: no `text/event-stream` or
    `http.Flusher` in mctl-api non-test Go, and no token stream. MCP invocation
    recording is "unknown (not observed)".
  - D2 classifies each mapping as exact, lossy or none.
  - D3 holds the refusal table. Stale, replay and wrong-actor cases are refused by
    existing mctl-api checks (`prepareApprovalGrant`, single-use consume, `isHumanAdmin`
    in `handlers_action_approvals.go:87`, `canSeeActionApproval`). Three adapter checks
    are new: subscribe/run tenant authz, unknown `interruptId`, and injected event.
  - D4 places the adapter in mctl-api. D5 names the ten Phase B tests. D6 gives the
    verdict, D8 the disposition `KEEP_AS_AGENT_PLATFORM_FOLLOWUP`.
- `roadmap/spikes/agent-ui-ag-ui.yaml` binds `.github#258`, `lifecycle: decided`,
  `decision.verdict: ADOPT_LIMITED_EVENT_SUBSET`, `followUps: [.github#261]`.

Spike machinery.
- `roadmap/schemas/spike-definition.schema.json` defines lifecycles
  `proposed|parked|active|decided|archived`. `active` requires `timebox`. Only
  `decided` may carry `decision`.
- `roadmap/scripts/validate.py` (`spike_semantic_errors`, `_spike_corpus_errors`)
  enforces unique spike names and spike issue bindings, and that a spike issue is not
  an epic root. `followUps` are not bindings, so a new spike may bind `.github#261`.
  `roadmap/epics/human-input.yaml:53` binds `mctlhq/mctl-api#261`, a different issue.
- `roadmap-validate.yml` runs `validate.py roadmap/epics roadmap/spikes`.

Reference-model precedent.
- `docs/spikes/mcp-gateway-g0/` is a "NON-NORMATIVE, deterministic, stdlib-only Go
  model" (module `mctl.ai/spikes/mcpgatewayg0`, `go 1.22`, no `go.sum`). It has
  `model/`, `fixtures/`, `model_test.go` (T1-T13) and `bench_test.go`. Its results
  are tagged `[REF]`.
- `.github/workflows/workflow-tests.yml` runs it (`setup-go` with `go-version-file`,
  then `go vet ./... && go test ./...`), triggered by path filters on PR and push.
  Python models (`security-finding-lifecycle`, `cve-advisory-impact`) follow the same
  pattern.

Event principle. `events/README.md`: "The event is disposable; the source is
canonical". Envelopes carry references, not content. Phase A D4 applies this rule to
AG-UI replay.

Deployed state checked:
- `mctl_list_services(team=admins)` (complete=true) lists `mctl-agents-worker`,
  `-exec` and `-implement` at 1.106.0, plus mctl-design, mctl-docs, mctl-support,
  mctl-web and umami. mctl-api and mctl-portal are not catalogue services in `admins`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `ingress.enabled:
  false` ("pure asyncio process with no HTTP server"). This confirms mctl-agents must
  get no public ingress.
- `$MCTL_GITOPS_ROOT/infra-components/mctl-platform/mctl-api/` and `.../mctl-portal/`
  contain only `oidc-zitadel.yaml` (plus `zitadel-hook.yaml` for mctl-api), i.e.
  Zitadel OIDC wiring. mctl-api/mctl-portal deployment values (replicas, env, flags)
  were not found in this checkout: unknown (not observed).
- A grep for `AG_UI|ag-ui|AGUI` under `infra-components/mctl-platform` found nothing.
  Read as: no AG-UI deployment config is visible in this checkout. This is not proof of
  absence elsewhere.
- Not checked live: mctl-api execution, approval or tool-invocation records. The
  investigate scope is read-only, and Phase A recorded these tools as refused. Gap
  recorded under Open questions.

## Proposed solution

Deliver the `.github` half of Phase B as four artifacts. Live S1/S2/S3 code stays in
mctl-api / mctl-portal and is specified, not built, here.

### 1. Spike manifest `roadmap/spikes/agent-ui-ag-ui-phase-b.yaml`

```yaml
apiVersion: roadmap.mctl.ai/v1alpha1
kind: SpikeDefinition
metadata:
  name: agent-ui-ag-ui-phase-b
  owner: mctlhq/.github
spec:
  title: AG-UI Phase B - bounded DevLoop Run Inspector
  question: >-
    Does a read-only AG-UI 1.0.x projection over canonical MCTL records, with
    resume forwarded only to existing governed handlers, give enough real event
    sources and fail-closed semantics to justify an AG-UI northbound adapter?
  lifecycle: active
  github: {issue: {repository: mctlhq/.github, number: 261}}
  outcomes: [PROMOTE_AG_UI_ADAPTER, KEEP_LIMITED_OPERATOR_ADAPTER, STOP_AG_UI_EXPERIMENT]
  timebox: {decisionBy: "2026-12-15"}
  execution: {devloop: true}
  evidence: {report: docs/spikes/agent-ui-ag-ui-phase-b.md}
```

There is no `decision` block. The owner moves it to `decided` later, as was done for
#258. The roadmap disposition has no schema field, so it lives in the report, as Phase
A D8 does.

### 2. Reference model `docs/spikes/agent-ui-ag-ui-phase-b/`

Module `mctl.ai/spikes/aguiphaseb`, `go 1.22`, stdlib only. Layout mirrors G0:

- `model/events.go`: a closed Go enum of the adopted subset, with string values copied
  from the pinned 1.0.3 enum. Also event structs (`threadId`, `runId`,
  `protocolVersion: "1.0.x"` pinned to `1.0.3`), `Interrupt{id, reason, toolCallId?,
  responseSchema}` and the RUN_FINISHED `interrupt` outcome.
  `ResumeEntry{interruptId, status resolved|cancelled, payload}`.
- `model/records.go`: canonical record types standing in for mctl-api:
  - `Execution{ID we_, WorkflowID, AgentVersion, Profile, Status, Result}`
  - `Stage{Name, StartedSeq, FinishedSeq}`
  - `ToolInvocation{ID, CapabilityID, ArgsDigest, ResultRef, TraceID}`
  - `WorkItem{ID wi_, StateVersion, SnapshotID cs_}`
  - `ApprovalRequest{ID aar_, IntentHash, ArtifactDigest, State, Tenant}`
  - `HumanInput{RequestID, Revision}`
  - `UsageRecord{ProviderReported, Calculated, InvoiceReconciled *Money}`

  A `Store` interface plus a fixture-backed implementation with a monotonic record
  sequence.
- `model/projector.go`: `Project(store, execID) []Event` is a pure, deterministic
  function. Event id = `<we_>:<seq>`, where seq is the canonical record sequence.
  - RUN_STARTED comes from the execution start.
  - STEP pairs come from stage records.
  - TOOL_CALL_START/ARGS(digest)/END/RESULT(ref) come only from `ToolInvocation`
    records.
  - STATE_SNAPSHOT/DELTA come from WorkItem `state_version`, as a reference-only
    projection.
  - CUSTOM `mctl.refs` / `mctl.usage` / `mctl.trace` carry ids, capped at N fields.
  - RUN_FINISHED/RUN_ERROR come from the recorded result. RUN_FINISHED with outcome
    `interrupt` comes from a pending `aar_` / human-input.
- `model/sse.go`: an SSE encoder (`id:`, `event:`, `data:`) with
  `Stream(w, lastEventID, bounds)`. It parses `Last-Event-ID` and re-projects from the
  store, emitting only after that id. An unknown, malformed or out-of-retention id
  gives a STATE_SNAPSHOT followed by the head. Count and byte caps produce a
  STATE_SNAPSHOT fallback. A writer that exceeds the write budget is dropped
  (simulated clock). There is no buffer field on the adapter type, and a test asserts
  this through the type's shape.
- `model/resume.go`: the `Adapter.Resume(actor, tenant, input)` / `Cancel(...)`
  forwarder. Adapter-owned checks, from Phase A D3 "required new":
  - strict closed-schema decode (`DisallowUnknownFields`, allowed event types only);
  - actor/tenant authorization before lookup (the same refusal for unknown and
    forbidden);
  - known `interruptId`.

  It then calls the `CanonicalHandlers` interface: `DecideActionApproval`,
  `RespondHumanInput`, `Abandon`. A fake handler implements the existing semantics
  (digest/intent-hash match, single-use transition `WHERE state='approved'`, human-
  admin only, no self-decision, no service credential) and records every call. The
  adapter contains no decision branch, and tests assert decisions happen only in the
  handler.
- `fixtures/`: one bounded DevLoop run (JSON) with stages, one recorded tool
  invocation (for example capability `mctl_get_service_logs`, matching the Phase A Q8
  scenario), one `aar_`, one human-input request, usage records, two tenants and actors
  (human admin, other-tenant human, service credential).
- `model_test.go`: the 10 named tests plus `TestCancelRecordedTerminal`,
  `TestToolIdentityNoGrant`, `TestBoundedReplaySnapshot`, `TestSlowConsumerDropped`,
  `TestAdapterRemovable` (canonical scenario run with a nil adapter gives an identical
  handler call log and final records), `TestClosedSubset` and `TestMctlCustomClosed`.
- `bench_test.go`: projection/encode time per event and allocations, plus
  time-to-first-event on the fixture. These are reported as reference overhead
  estimates only.
- `README.md`: NON-NORMATIVE banner, run commands, layout and the `[REF]` meaning.

### 3. CI

In `.github/workflows/workflow-tests.yml`, add `docs/spikes/agent-ui-ag-ui-phase-b/**`
to both path lists. Add a `setup-go` step (`go-version-file:
docs/spikes/agent-ui-ag-ui-phase-b/go.mod`) and a step "AG-UI Phase B reference model
(mctlhq/.github#261)" running `go vet ./... && go test ./...` in that directory.

### 4. Report `docs/spikes/agent-ui-ag-ui-phase-b.md` + `AGENTS.md` entry

Sections:
1. Non-claims and evidence tags. Adds `[REF]` to the Phase A tags; `[REF]` is never
   production proof.
2. Evidence pins: `.github` commit, `@ag-ui/core@1.0.3`, and mctl-api/mctl-portal pins
   once live slices exist.
3. Normative S1/S2/S3 contract:
   - routes under mctl-api `/api/v1/agents/...`;
   - auth reuses the existing session/bearer and `PrincipalAuthz`;
   - `protocolVersion` plus a response header;
   - the id scheme and bounds (defaults: 512 events, 256 KiB, 24 h, 5 s);
   - the closed resume schema and the refusal table mapping each case to the canonical
     check;
   - the `mctl.*` field list, each field justified by a Phase A D1 row;
   - the adapter feature flag. Off means the routes return 404 and nothing else
     changes.
   - The portal Run Inspector view and its read-only rendering rules: escaped text, no
     control parsing, `[Approve]/[Edit]/[Reject]/[Cancel]` only build a resume/cancel.
     `[Edit]` links to the governed edit path that supersedes the grant; the UI never
     edits it inline.
4. Proof checklist: the ten required proofs, each with a `[REF]` result (test name)
   and a live result (link, or `unknown (not observed)`).
5. Mapping table: exact / lossy / unsupported for every 1.0.3 event type.
6. Measurements: every item in the issue. REF-measured values for LOC/files/deps of
   the model, event count/bytes, time-to-first-event, reconnect recovery and
   duplicate/lost result, `mctl.*` field count, and adapter-side auth code lines. Live
   values otherwise `unknown (not observed)`.
7. Semantic duplication with REST/MCP/Temporal.
8. Exit: exactly one of the three exit decisions and exactly one roadmap disposition,
   with evidence and flip conditions. Decision rule:
   - PROMOTE requires a live token/message source and durable event-granular tool
     records. Phase A found neither, so it is unreachable on `[REF]` alone.
   - STOP applies if any S2 negative case can only be closed by adapter-side decision
     logic.
   - Otherwise KEEP_LIMITED_OPERATOR_ADAPTER.

   Disposition is `KEEP_AS_AGENT_PLATFORM_FOLLOWUP` unless independently owned durable
   product surfaces are proven. The section is labelled a recommendation, and the
   owner records `decision` on the manifest.

`AGENTS.md`: add a Spikes bullet for the Phase B report pointing at the model directory.

## Alternatives

- **Report-only (no reference model).** Cheapest, but the issue's named tests would
  have no executable form until mctl-api exists. The fail-closed resume claims would
  stay prose. Dropped: G0 set the precedent that a `.github` spike proves its boundary
  with a runnable `[REF]` model.
- **Build S1/S2/S3 from this proposal.** Not possible: a `.github` DevLoop cannot
  change mctl-api/mctl-portal. Phase A D4 also places the adapter and its ingress in
  mctl-api. Those slices go to their own repositories against the contract here.
- **TypeScript model using `@ag-ui/core` directly.** It would validate event shapes
  against the real package. But it adds an npm dependency, a lockfile and Dependabot
  surface to `.github`, and mctl-api is Go. Dropped in favour of a stdlib Go model with
  enum strings copied from the pinned schema. A later live S3 test in mctl-portal
  checks against the real package.
- **Amend `roadmap/spikes/agent-ui-ag-ui.yaml` instead of a new manifest.** It is
  `decided` with a different outcome set. Reopening it would rewrite a recorded
  decision. Dropped.

## Platform impact

- Migrations: none. No runtime, schema or deployment change. `validate.py` already
  accepts the new manifest shape.
- Backward compatibility: purely additive files, plus one CI step and two path filters.
- Resources: one extra Go vet/test step in `workflow-tests.yml`, run only when its
  paths change. Seconds of CI.
- Risk: `[REF]` results get read as production proof. Mitigation: a NON-NORMATIVE
  banner, the `[REF]` tag on every model claim, separate live columns defaulting to
  `unknown (not observed)`, and an exit rule that forbids PROMOTE on `[REF]` alone.
- Risk: enum drift from AG-UI upstream. Mitigation: pin to 1.0.3 by commit in the
  report. `TestClosedSubset` fails if an unpinned type is emitted.
- Risk: the contract diverges from the real mctl-api handlers. Mitigation: the
  refusal table cites the existing checks by name from Phase A. Live slices must
  re-verify at their own pins.
- Risk: the timebox lapses without live slices. Mitigation: the report states which
  verdict the `[REF]` evidence alone supports.
