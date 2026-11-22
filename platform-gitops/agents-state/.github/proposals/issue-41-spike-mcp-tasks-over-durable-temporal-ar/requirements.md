# Spike: MCP Tasks over durable Temporal/Argo executions (SEP-2663)

## Context

mctlhq/.github#41 asks whether mctl can expose its existing durable
executions (Temporal workflows in `mctl-agents`, Argo where isolation is
needed) as negotiated MCP Tasks (`io.modelcontextprotocol/tasks`, final
SEP-2663, spec `2026-07-28`) without adding a second executor, queue or
workflow store, and without weakening canonical authority: tenant and
principal checks, exact approval grants (`aar_`), the human-input contract
(ADR 013 in mctl-agents), and the WorkItem identity chain
(`wi_` -> `xr_` -> `we_` -> `cs_`). The owner refresh of 2026-11-22 made this
a P1 **investigation**: requirements, design, ADR, test matrix, decision
gates and a reference fixture. Implementation, deployment, account linking
and new spend are not authorized. The executable pilot against
`api.mctl.ai/mcp` stays mctlhq/mctl-api#284. The single decision for both
issues is carried by `roadmap/spikes/mcp-tasks-durable-execution.yaml`.

It matters because Tasks are the portable way for AI hosts (Claude Code,
ChatGPT, Codex, Antigravity and others) to start long-running tool work,
poll it after a disconnect, answer input, and cancel it. Most mctl
operations already have these properties internally. Without a decided
mapping, each host or surface would create its own polling contract, or a
library task store would quietly become a second, non-durable executor.
The pinned mcp-go v1.0.0 (and v1.6.0) ships such a store: an in-memory map
that runs the handler in a goroutine and uses the legacy SEP-1686 method set.

## User stories

- AS an AI-host user I WANT a long-running mctl tool call to return a task
  handle at once SO THAT my client can disconnect and later get the same
  result without starting the work twice.
- AS an AI-host user I WANT to be asked for missing input inside the task
  SO THAT the run can resume without an HTTP request held open.
- AS a tenant owner I WANT approvals for a task's consequential step to stay
  on the existing fresh-sign-in decide page, bound to the exact content
  SO THAT having a task handle or a chat "yes" can never approve anything.
- AS a platform operator I WANT the task status to be derived from the
  canonical execution state (Temporal plus WorkItem records) SO THAT no
  second state machine can drift from the truth.
- AS a security reviewer I WANT task IDs to be unguessable, owner- and
  tenant-checked on every call, and expired by TTL SO THAT a leaked or
  replayed handle reveals nothing and changes nothing.
- AS the spike owner I WANT a runnable reference fixture with a test matrix
  SO THAT the verdict rests on evidence and not on assumed host or SDK
  behaviour.

## Acceptance criteria (EARS)

Spike deliverables (this repository):

- THE SYSTEM SHALL deliver `docs/spikes/mcp-tasks-durable-execution.md` with
  an evidence-pin table (40-hex SHAs for mctl-api, mctl-agents, mcp-go and
  this repo, plus the spec URL), a lifecycle mapping, sequence diagrams for
  create/poll, input-required/resume, approval wait, cancel and
  reconnect/retry, an ADR section, a host/SDK compatibility matrix, a test
  matrix, decision gates, scope and rollback.
- THE SYSTEM SHALL deliver a stdlib Go reference model in
  `docs/spikes/mcp-tasks-durable-execution/` with offline tests, plus an
  opt-in `temporal-integration/` module run against a local Temporal dev
  server, following the layout of `docs/spikes/automation-control-plane/`.
- THE SYSTEM SHALL tag every claim `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`,
  `[MODEL]` or `[TEMPORAL_DEV]`, and SHALL write `unknown (not observed)`
  wherever a claim was not observed, never "absent".
- THE SYSTEM SHALL keep the spike manifest at `lifecycle: proposed` and
  record only a *proposed* verdict. The owner decides.

Protocol contract (specified by the spike; the fixture proves it):

- WHEN a client that declared `io.modelcontextprotocol/tasks` in
  `params._meta["io.modelcontextprotocol/clientCapabilities"].extensions`
  calls a task-capable tool THE SYSTEM SHALL return `resultType: "task"`
  only after the task row and its execution request (`xr_`) are durably
  committed, so that `tasks/get` for the returned `taskId` succeeds at once.
- IF a client has not declared the extension THEN THE SYSTEM SHALL NOT return
  a `CreateTaskResult`. It SHALL use the defined fallback: a normal
  `CallToolResult` carrying the WorkItem and execution references that the
  existing status tools already read. It SHALL answer `tasks/*` from such a
  client with `-32021`.
- WHILE a task exists THE SYSTEM SHALL derive its `status` on every read from
  the canonical execution state (the `xr_`/`we_` records, the Temporal
  describe result, the `human_input_state` query and the approval-grant
  state). It SHALL NOT persist a second copy of execution state.
- IF the canonical execution state cannot be read THEN THE SYSTEM SHALL
  return `-32603` (retryable). It SHALL NOT report a guessed `working` or a
  terminal status.
- WHEN a task-creating `tools/call` is retried with the same
  `idempotency_key`, principal, tenant, tool and canonical-argument digest
  THE SYSTEM SHALL return the same `taskId` and start no second execution.
  IF the same key arrives with a different digest THEN it SHALL refuse with
  `idempotency_key_reused`.
- IF a consequential task-capable tool is called without an
  `idempotency_key` THEN THE SYSTEM SHALL refuse the call.
- WHEN any `tasks/get`, `tasks/update` or `tasks/cancel` arrives THE SYSTEM
  SHALL authenticate the caller and check that its tenant and principal
  match the task's owner. A foreign, unknown, malformed or expired `taskId`
  SHALL get the same `-32602`, so a probe cannot tell them apart.
- THE SYSTEM SHALL mint `taskId` with at least 128 bits of CSPRNG entropy.
  It SHALL never derive it from a Temporal workflow ID, issue URL or other
  guessable value, and SHALL expose no task enumeration.
- WHEN the Temporal execution reaches `Completed` THE SYSTEM SHALL report
  `completed` with the tool result inline. A business-level failure SHALL be
  `completed` with `isError: true`. An execution or infrastructure failure
  (`Failed`, `TimedOut`, `Terminated`, rejected `xr_`) SHALL be `failed`
  with a classified `error`.
- WHILE the workflow reports `WAITING_FOR_INPUT` THE SYSTEM SHALL report
  `input_required`, with one `inputRequests` entry keyed by the sealed
  `request_id`. That key SHALL never be reused within the task.
- WHEN `tasks/update` carries an `inputResponses` entry for the open key
  THE SYSTEM SHALL forward it as the existing human-input response signal,
  bound to `request_id` and `request_hash`, and acknowledge with an empty
  result. Responses for unknown, already-answered or expired keys SHALL be
  ignored and recorded in the audit trail.
- WHILE a task waits on an approval grant THE SYSTEM SHALL report
  `input_required` with a status message naming the decide page. It SHALL
  NOT accept an approval through `tasks/update`, `inputResponses`, an MCP
  App or chat text. Approval stays bound to `aar_` `artifact_hash` and
  `context_digest`.
- WHEN `tasks/cancel` is received THE SYSTEM SHALL record the request, ask
  the Temporal execution to cancel, and return an empty acknowledgement. It
  SHALL report `cancelled` only after Temporal reports the execution
  `Canceled` at its defined cancellation boundary.
- IF the execution reaches another terminal state before the cancel takes
  effect THEN THE SYSTEM SHALL report that state. The first terminal state
  recorded by Temporal is the truth.
- WHEN a task's `ttlMs` has elapsed THE SYSTEM SHALL answer `-32602` and
  remove the protocol row. Canonical WorkItem and execution records SHALL
  be kept under their own retention.
- WHEN a principal's access is revoked during a task THE SYSTEM SHALL refuse
  further `tasks/*` calls from that principal. The workflow's action-time
  checkpoint (see #375) SHALL deny pending side effects.
- THE SYSTEM SHALL audit task creation, every `tasks/update`, every
  `tasks/cancel` and every refusal, with principal, tenant, `taskId`,
  `wi_`/`xr_`/`we_` and outcome. It SHALL never log input or result
  content.
- WHILE Tasks notifications are not decided in #377 (SEP-3415 events), THE
  SYSTEM SHALL support polling only, with `pollIntervalMs`. It SHALL
  advertise no `subscriptions/listen` delivery for tasks, so nothing is
  delivered twice.

Pilot scope:

- THE SYSTEM SHALL prove the contract first on a synthetic, read-only
  fixture workflow with an intentional input gate, an approval-wait gate and
  a cancellable sleep, and no production side effects.
- THE SYSTEM SHALL treat Portal (`mcp.mctl.ai`) pass-through and each real
  host as separate, measured operator gates. Each host SHALL stay
  `unknown` until it is measured.

## Out of scope

- Any change to mctl-api, mctl-agents, mctl-gitops or the Portal.
  Implementation is mctl-api#284, behind the owner's decision.
- Deployment, account linking, DevLoop/implementer start, or any new spend.
- A generic scheduler, a new queue, or replacing Temporal or Argo.
- `tasks/list` and `tasks/result` (absent from the modern extension), and the
  legacy SEP-1686 method set.
- Making existing MCP tools asynchronous beyond the one pilot tool.
- Treating a task handle as authorization, or letting MCP Apps (#376) confer
  approvals.
- Choosing the business-event delivery model. That is #377. This proposal
  only defers task notifications to it.

## Open questions

- Outcome vocabulary conflict: the issue lists
  `ADOPT_THIN_TASKS_ADAPTER | BOUNDED_PILOT | DEFER`, while the manifest
  `roadmap/spikes/mcp-tasks-durable-execution.yaml` lists
  `GO_ADAPTER_IN_MCTL_API | GO_UPSTREAM_ONLY | NO_GO`. This proposal reports
  the verdict in the manifest vocabulary, which is canonical for the roadmap
  validator. The proposed verdict is `GO_ADAPTER_IN_MCTL_API` scoped as a
  bounded pilot, with the issue-vocabulary equivalent (`BOUNDED_PILOT`) shown
  next to it. The owner should confirm which vocabulary wins.
- Whether the existing `xr_` ID already has at least 128 bits of entropy.
  That decides whether a separate `tk_` handle could be dropped. The design
  assumes a separate `tk_` handle until `xr_` generation is read.
- How mcp-go lets the server register custom methods (`tasks/update`, modern
  `tasks/get` shape) without enabling its built-in legacy task store. Not
  read; `unknown (not observed)`.
- Host support is `unknown` for ChatGPT, Claude (web), Antigravity, Grok Bot,
  Codex and agy. For Claude Code the only evidence is the manifest's `[DOC]`
  note (public beta from v2.1.304).
- Whether the Portal forwards the `Mcp-Name` header and the `tasks/*`
  methods. This is the mcp-gateway G2 gate; `unknown`.
- Exact cancellation boundary per execution class for Argo and external
  CI/deploy steps that are already submitted. The design proposes one;
  each later real workflow must declare its own.
