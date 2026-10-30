# Phase B carrier: bounded AG-UI DevLoop Run Inspector experiment (reference model, contract, report and spike manifest)

## Context

mctlhq/.github#258 (Phase A, report `docs/spikes/agent-ui-ag-ui.md`, manifest
`roadmap/spikes/agent-ui-ag-ui.yaml`) ended with the owner decision
`ADOPT_LIMITED_EVENT_SUBSET` and named #261 as its only follow-up. #261 authorizes a
bounded Phase B experiment: a read-only AG-UI 1.0.x SSE projection in mctl-api over
canonical execution / WorkItem / approval / usage records (S1), interrupt/resume that
only forwards to existing governed handlers (S2), and a minimal mctl-portal Run
Inspector on plain `@ag-ui/client` (S3). The issue ends with exactly one exit decision
and exactly one roadmap disposition.

This repository is the schema pin and spike-record owner (Phase A D4: "schema pin
`mctlhq/.github`"), not the runtime. S1/S2 code lives in mctl-api and S3 in
mctl-portal; neither can be changed from a `.github` proposal. This proposal therefore
delivers the `.github` half of Phase B, following the precedent of
`docs/spikes/mcp-gateway-g0/`: (a) a deterministic, stdlib-only, non-normative Go
reference model of the projection and resume forwarder. It implements the ten named
tests plus cancel, tool-identity, bounded-state and removability proofs as `[REF]`
evidence. (b) The normative cross-repo contract S1/S2/S3 must implement. (c) A
`SpikeDefinition` that binds #261 with the three exit outcomes. (d) A Phase B report
that keeps `[REF]` evidence strictly apart from live evidence, which stays
`unknown (not observed)` until the mctl-api/mctl-portal slices land.

## User stories

- AS the platform owner I WANT Phase B tracked as a timeboxed SpikeDefinition with the three allowed exit outcomes SO THAT the verdict is recorded in Git before the result is known.
- AS an mctl-api implementer I WANT a precise AG-UI 1.0.x projection contract (event subset, id scheme, bounds, resume schema, refusal table) and an executable reference model SO THAT S1/S2 can be built and checked against known-good behaviour.
- AS an mctl-portal implementer I WANT the Run Inspector's data contract (which events and `mctl.*` references it renders) SO THAT S3 stays a plain `@ag-ui/client` view with no authority.
- AS a security reviewer I WANT resume/control negative cases proven to fail closed, with all decisions made only by the canonical handler, SO THAT AG-UI never becomes a second approval or auth path.
- AS a reader of the report I WANT every claim tagged `[REF]`, `[CODE]`, `[DEPLOYED]`, `[DOC]` or `unknown (not observed)` SO THAT reference-model results are never mistaken for production proof.

## Acceptance criteria (EARS)

Spike record
- WHEN the change lands THE SYSTEM SHALL contain `roadmap/spikes/agent-ui-ag-ui-phase-b.yaml` (kind `SpikeDefinition`, owner `mctlhq/.github`) binding `mctlhq/.github#261`, with `outcomes` exactly `PROMOTE_AG_UI_ADAPTER`, `KEEP_LIMITED_OPERATOR_ADAPTER`, `STOP_AG_UI_EXPERIMENT`, `lifecycle: active`, `timebox.decisionBy`, `execution.devloop: true`, `evidence.report: docs/spikes/agent-ui-ag-ui-phase-b.md`, and no `decision` block.
- WHEN `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` runs THE SYSTEM SHALL pass, including the cross-kind spike invariants.

Reference model (`docs/spikes/agent-ui-ag-ui-phase-b/`)
- THE SYSTEM SHALL be a Go module with no third-party dependencies and no `go.sum`, runnable offline with `go vet ./... && go test ./...`.
- WHEN canonical fixture records (one `we_` execution with stage records, one `wi_` WorkItem with `state_version`, at least one recorded tool invocation, one `aar_` approval, one human-input request, usage records) are projected THE SYSTEM SHALL emit only event types in the adopted subset, using the names of the pinned `@ag-ui/core@1.0.3` `EventType` enum: RUN_STARTED, RUN_FINISHED, RUN_ERROR, STEP_STARTED, STEP_FINISHED, STATE_SNAPSHOT, STATE_DELTA, TOOL_CALL_START/ARGS/END/RESULT, CUSTOM.
- THE SYSTEM SHALL never emit TEXT_MESSAGE_*, SUBAGENT_*, REASONING_*, RAW, MESSAGES_SNAPSHOT or ACTIVITY_*.
- IF a stage or tool invocation has no canonical record THEN THE SYSTEM SHALL emit no event for it. Missing calls are never fabricated.
- THE SYSTEM SHALL derive every event id as `<execution id>:<sequence>`, where the sequence is a pure function of the canonical records. Projecting the same records twice SHALL yield byte-identical event streams.
- WHEN a client reconnects with `Last-Event-ID` THE SYSTEM SHALL rebuild the stream from the canonical records and resume strictly after that id, with no duplicates or gaps, and SHALL hold no adapter-side event buffer.
- IF `Last-Event-ID` is unknown, malformed, or older than the retention bound THEN THE SYSTEM SHALL send a fresh STATE_SNAPSHOT and continue from the current head.
- WHILE streaming THE SYSTEM SHALL enforce a per-run cap on event count and bytes. On reaching either cap it SHALL send a STATE_SNAPSHOT instead of further history.
- IF a consumer does not drain within its write budget THEN THE SYSTEM SHALL drop that connection, and a reconnect SHALL recover the same consequential state.
- THE SYSTEM SHALL carry custom data only under a closed `mctl.*` set (`mctl.refs`, `mctl.usage`, `mctl.trace`), with a capped field count. Every field SHALL be an identifier reference (`we_`, `wi_`, `cs_`, `aar_`, human-input request id, `trace_id`, evidence ref, tool/capability id), never a body or a control.
- WHEN usage is projected THE SYSTEM SHALL keep `provider_reported_cost`, `calculated_cost` and `invoice_reconciled_cost` as separate references and never sum them.
- WHEN a TOOL_CALL_* event is emitted THE SYSTEM SHALL identify the canonical MCP tool or capability id. TOOL_CALL_ARGS/RESULT SHALL carry a digest or record reference, never raw arguments or results, and no event SHALL grant the tool.
- WHEN a pending `aar_` or human-input request exists THE SYSTEM SHALL end the run with RUN_FINISHED outcome `interrupt` whose `Interrupt.id` equals the canonical id and whose `responseSchema` is closed (approve | reject | edit-reference, plus the digest/revision shown).

Resume and control
- WHEN a resume (`resume[{interruptId, status, payload}]`) or cancel arrives THE SYSTEM SHALL authenticate the actor and authorize the tenant before any lookup that could reveal existence, then forward to the canonical handler stand-in (DecideActionApproval / RespondHumanInput / dev-loop abandon) as the authenticated caller.
- THE SYSTEM SHALL let only the canonical handler decide, and the adapter SHALL hold no decision logic.
- IF the digest or revision is stale THEN THE SYSTEM SHALL refuse via the canonical handler and change no state.
- IF the same resume is replayed (same or new connection) THEN THE SYSTEM SHALL execute at most once and report the original outcome.
- IF the actor is wrong, the tenant is wrong, or the credential is a service/relayed one THEN THE SYSTEM SHALL refuse with no state change and no existence disclosure.
- IF the `interruptId` is unknown THEN THE SYSTEM SHALL refuse without forwarding.
- IF a frontend sends any field, event type or tool call outside the closed resume/cancel schema THEN THE SYSTEM SHALL refuse it and change no state.
- WHEN cancel is accepted THE SYSTEM SHALL emit the terminal RUN_FINISHED/RUN_ERROR only from the recorded canonical result, never an optimistic one.
- WHEN the adapter is disabled THE SYSTEM SHALL leave canonical execution, approval and human-input behaviour unchanged (proved by running the same canonical scenario with and without the adapter).

Tests and CI
- THE SYSTEM SHALL implement the named tests `TestRunLifecycleProjection`, `TestStageSteps`, `TestUsageRefOnly`, `TestInterruptFromApproval`, `TestResumeForwards`, `TestResumeStaleDigest`, `TestResumeReplay`, `TestResumeWrongActorTenant`, `TestInjectedEventRefused` and `TestLastEventIDReplay`, plus `TestCancelRecordedTerminal`, `TestToolIdentityNoGrant`, `TestBoundedReplaySnapshot`, `TestSlowConsumerDropped`, `TestAdapterRemovable`, `TestClosedSubset` and `TestMctlCustomClosed`.
- WHEN a PR or a push to main touches `docs/spikes/agent-ui-ag-ui-phase-b/**` THE SYSTEM SHALL run `go vet ./... && go test ./...` for the model in `.github/workflows/workflow-tests.yml`.

Report and contract
- THE SYSTEM SHALL add `docs/spikes/agent-ui-ag-ui-phase-b.md` containing: evidence tags and pins; the normative S1/S2/S3 contract; the proof checklist with separate `[REF]` and live columns; the exact/lossy/unsupported mapping table; every measurement the issue lists; and an exit section that names exactly one exit decision and exactly one roadmap disposition, with the evidence and flip conditions.
- IF a live proof or measurement has not been observed from mctl-api/mctl-portal THEN THE SYSTEM SHALL record it as `unknown (not observed)` and never as passed or absent.
- WHEN the change lands THE SYSTEM SHALL add a Spikes entry for the Phase B report in `AGENTS.md`.

## Out of scope

- Any change to mctl-api, mctl-portal, mctl-agents or mctl-gitops (S1/S2/S3 live code, deployment, feature flags). Those happen in their own repositories against the contract written here.
- Production rollout, a new public mctl-agents endpoint, websockets or a new event platform, CopilotKit, a general chat UI.
- TEXT_MESSAGE_* streaming, SUBAGENT_*, REASONING_* or any chain-of-thought.
- Recording the owner's `decision` on the new manifest. Only the owner does that after reading the report.
- Changes to `roadmap/spikes/agent-ui-ag-ui.yaml` (already `decided`) or the epic manifests.
- Vendoring AG-UI TypeScript packages into this repository.

## Open questions

- Live proofs. The required proofs (streaming with a real recorded tool call, reconnect, cancel, latency/CPU/memory overhead, portal footprint) need the mctl-api and mctl-portal slices, which a `.github` change cannot deliver. Assumption: those slices are tracked as owner-filed issues in mctl-api and mctl-portal. The report links them when they exist and marks live cells `unknown (not observed)` until then.
- Recorded tool invocations. Phase A could not observe whether the policy checkpoint durably records MCP invocations (D1, "unknown (not observed)"). If no such record exists, the "at least one real recorded tool call" streaming proof cannot pass live. The reference model proves only the projection rule (emit iff recorded). The exit section must treat a missing live source as blocking `PROMOTE_AG_UI_ADAPTER`.
- Exit verdict before live evidence. With only `[REF]` evidence the report cannot honestly claim PROMOTE. Assumption: the report states the verdict the available evidence supports. The expected default is `KEEP_LIMITED_OPERATOR_ADAPTER` with `KEEP_AS_AGENT_PLATFORM_FOLLOWUP`. If S2 cannot fail closed without a second authority, the verdict is `STOP_AG_UI_EXPERIMENT`. The verdict is labelled a recommendation, and the owner records the binding decision on the manifest.
- `timebox.decisionBy` is not given in the issue. Assumption: `2026-12-15`, after the Phase A timebox of 2026-11-30. The owner may change it.
- Exact numeric bounds (event cap, byte cap, retention, write budget) are not specified. Assumption: 512 events, 256 KiB per stream window, the last 24 h of history before snapshot-only, and a 5 s write budget. These are recorded in the contract as experiment defaults.
