# Spike: MCP Tasks over durable Temporal/Argo executions (SEP-2663), revision 2

## Context

mctlhq/.github#41 asks whether mctl can expose its existing durable
executions (Temporal workflows in `mctl-agents`, plus Argo where isolation
is needed) as negotiated MCP Tasks without adding a second executor, queue
or workflow store, and without weakening canonical authority. Canonical
authority here means:

- tenant and principal checks;
- exact approval grants (`aar_`);
- the human-input contract (mctl-agents ADR 013);
- the WorkItem chain `wi_` -> `xr_` -> `we_` -> `cs_`.

The MCP Tasks extension is `io.modelcontextprotocol/tasks`: Final SEP-2663,
spec `2026-07-28`, negotiated per request. It is not the legacy SEP-1686
shape. The owner refresh of 2026-11-22 made this a P1 investigation, not an
implementation. The executable pilot stays mctlhq/mctl-api#284.

This is revision 2. It answers the independent review of 2026-11-22
(REQUEST_CHANGES, findings P1-TS-01, P1-TS-02 and P2-TS-03 to P2-TS-06).
Revision 1 made four errors, and this revision fixes them:

- It published `input_required` without `inputRequests` for an approval wait.
- It claimed a three-object atomic commit that the current mctl-api `Store`
  API cannot give.
- It left the `tasks/update` trust boundary loose.
- It let the TTL hide a live execution.

It also tested only one result shape and drifted between two verdict
vocabularies. design.md carries the finding-to-change matrix.

Phase 0, the only phase this proposal authorizes, is limited to three
things in mctlhq/.github:

- documentation;
- an offline stdlib Go reference model;
- an opt-in integration module against a LOCAL Temporal dev server.

Phase 0 touches no mctl-api production endpoint, database migration,
external host or real approval, and starts no implementer. Each later phase
needs its own review and a digest-bound owner approval.

## User stories

- AS an AI-host user I WANT a long-running mctl tool call to return a task
  handle at once SO THAT I can disconnect and later fetch the same result
  without starting the work twice.
- AS an AI-host user I WANT a task to ask me only for input my client is
  allowed to answer SO THAT the run resumes without an open HTTP request,
  and my client's answer is never treated as an approval.
- AS a tenant owner I WANT approval of a task's consequential step to stay
  on the existing fresh-sign-in decide page, bound to exact content, SO THAT
  neither a task handle nor `tasks/update` nor a chat "yes" can approve
  anything.
- AS a platform operator I WANT task status derived from canonical execution
  state, and a task row that cannot be orphaned from its execution request,
  SO THAT no second state machine drifts and no execution runs without a
  handle that can be recovered.
- AS a security reviewer I WANT task IDs that are unguessable and
  owner-checked, the respondent and OAuth client checked on every input,
  and expiry only after a terminal state SO THAT a leaked, replayed or
  expired handle reveals nothing, changes nothing and hides nothing.
- AS the spike owner I WANT one canonical outcome vocabulary, schema-checked
  fixtures for every response shape and explicit decision gates SO THAT the
  verdict rests on evidence and is recorded in exactly one place.

## Acceptance criteria (EARS)

### Phase 0 deliverables (this repository only)

- THE SYSTEM SHALL deliver `docs/spikes/mcp-tasks-durable-execution.md`
  with these sections:
  - an evidence-pin table: 40-hex SHAs for this repo, mctl-api and
    mctl-agents, the mcp-go tag, and the spec URL with retrieval date;
  - the finding-to-change matrix;
  - the lifecycle mapping and sequence diagrams;
  - the ADR;
  - the host/SDK compatibility matrix;
  - the test matrix;
  - decision gates G0-G4, exact scope and rollback.
- THE SYSTEM SHALL deliver a stdlib Go reference model and offline tests in
  `docs/spikes/mcp-tasks-durable-execution/`. It SHALL also deliver an
  opt-in `temporal-integration/` module run only against a local Temporal
  dev server, in the layout of `docs/spikes/automation-control-plane/`.
- THE SYSTEM SHALL tag every claim `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`,
  `[MODEL]` or `[TEMPORAL_DEV]`. It SHALL write `unknown (not observed)`
  wherever a claim was not observed.
- THE SYSTEM SHALL NOT claim that the model proves Postgres atomicity.
  Commit-order claims SHALL be tagged `[MODEL]`. The Postgres fault-injection
  proof SHALL stay an explicit, unmet gate (G1).
- THE SYSTEM SHALL NOT change `roadmap/spikes/mcp-tasks-durable-execution.yaml`
  `lifecycle`, `outcomes` or `decision`. The recommendation in the report
  SHALL be labelled "recommendation, not decision".

### Verdict vocabulary (P2-TS-06)

- THE SYSTEM SHALL treat the manifest `spec.outcomes`
  (`GO_ADAPTER_IN_MCTL_API | GO_UPSTREAM_ONLY | NO_GO`) as the only
  canonical vocabulary, because `roadmap/scripts/validate.py` checks
  `spec.decision.verdict` against it.
- THE SYSTEM SHALL publish one compatibility map from the issue vocabulary
  (`ADOPT_THIN_TASKS_ADAPTER | BOUNDED_PILOT | DEFER`) onto it. The map SHALL
  live in the report.
- WHEN the consistency check runs THE SYSTEM SHALL fail in these cases:
  - an issue outcome has no mapping entry;
  - a mapping target is not a manifest outcome;
  - the report names a final verdict while the manifest has no `decision`.

### Negotiation and result shapes (P2-TS-05)

- WHEN a client has declared `io.modelcontextprotocol/tasks` in
  `params._meta["io.modelcontextprotocol/clientCapabilities"].extensions`
  and calls a task-capable tool THE SYSTEM SHALL return `resultType: "task"`.
  The returned `taskId` SHALL be bound durably, so that `tasks/get` for it
  succeeds at once.
- IF the client has not declared the extension on that request THEN THE
  SYSTEM SHALL return a normal `CallToolResult` with `work_item_id` and
  `execution_request_id`. It SHALL answer that client's `tasks/get`,
  `tasks/update` and `tasks/cancel` with `-32021`.
- THE SYSTEM SHALL set `resultType: "complete"` on every `tasks/get`,
  `tasks/update` and `tasks/cancel` result. It SHALL include:
  - `result` exactly when `completed`;
  - `error` exactly when `failed`;
  - `inputRequests` exactly when `input_required`.
- IF a Streamable HTTP `tasks/*` request lacks the `Mcp-Name` header, or its
  value differs from `params.taskId` byte for byte, THEN THE SYSTEM SHALL
  refuse the request with `-32602`.
- THE SYSTEM SHALL validate every emitted response fixture against a pinned
  copy of the official schema, with Python `jsonschema` (pinned in
  `roadmap/requirements.txt`). This check SHALL be independent of the Go
  model's own validators.

### Lifecycle mapping (P1-TS-01)

- WHILE the workflow reports `WAITING_FOR_INPUT` for a request whose
  respondent policy allows client-relayed answers THE SYSTEM SHALL report
  `input_required`. `inputRequests` SHALL hold exactly one elicitation
  (form-mode) entry, keyed by the sealed `request_id`.
- THE SYSTEM SHALL NEVER emit `input_required` without a non-empty
  `inputRequests` map. It SHALL never emit `input_required` for an approval
  wait.
- WHILE a task waits on an approval grant (`aar_` pending), or on a
  human-only input request that MCP cannot answer, THE SYSTEM SHALL report
  `working`. The `statusMessage` SHALL be advisory and SHALL name the gate
  kind.
- THE SYSTEM SHALL include a decide link in that `statusMessage` only when
  the calling principal is authorized to decide that grant. Otherwise it
  SHALL include no link and no grant content.
- IF the canonical execution state cannot be read THEN THE SYSTEM SHALL
  return `-32603`, and SHALL NOT report a guessed status.
- WHEN the Temporal execution completes with a business refusal THE SYSTEM
  SHALL report `completed` with `result.isError: true`.
- WHEN the execution fails at the execution or infrastructure layer THE
  SYSTEM SHALL report `failed` with a classified `error`. Such failures are
  `Failed`, `TimedOut`, `Terminated` and a rejected `xr_`.

### Durable create-before-return (P1-TS-02)

- THE SYSTEM SHALL specify one of these two designs for the later mctl-api
  phase:
  - (A) a single new `workitems.Store` method that creates or joins the
    `wi_`, creates the `xr_` and inserts the task binding inside one
    `withTx`, under a documented advisory-lock order;
  - (B) a protocol intent committed before any `xr_` exists, completed by
    replayable steps and a recovery sweep.
  The design SHALL state the commit order of the chosen design.
- WHILE no task binding row exists for an `(owner, tool, idempotency_key)`
  scope THE SYSTEM SHALL NOT allow a pending `xr_` for that scope to exist.
  `ClaimExecutionRequest` could claim such an `xr_`.
- WHEN a create is retried after a crash at any step THE SYSTEM SHALL return
  the same `taskId` and leave exactly one `xr_`.
- IF two creates with the same scope race THEN THE SYSTEM SHALL let exactly
  one commit. The other SHALL replay the winner's `taskId` when the digest
  is equal, or fail with `idempotency_key_reused`.

### `tasks/update` trust boundary (P2-TS-03)

- THE SYSTEM SHALL accept an `inputResponses` entry only when all of these
  hold:
  - its key is the currently open `request_id`;
  - its value matches the sealed request's typed `ResponseSpec`;
  - the request is unexpired and within `MAX_CLARIFICATION_ROUNDS`;
  - its `request_hash` is unchanged;
  - the authenticated principal resolves to one of the request's
    `requested_from.actor_refs`;
  - the request's respondent policy allows `surface: mcp` with
    client-relayed assurance.
- IF any of those checks fails THEN THE SYSTEM SHALL ignore the entry. It
  SHALL audit the reason code, acknowledge with `resultType: "complete"`,
  and leave the workflow state unchanged.
- THE SYSTEM SHALL NEVER route an `inputResponses` value to an approval
  signal, a grant decision or `ApprovalWaitWorkflow`. A key that equals an
  `aar_` id, or any other non-open key, SHALL be ignored.
- THE SYSTEM SHALL refuse `tasks/update` and `tasks/cancel` from service,
  agent or relayed-surface credentials. It SHALL record the OAuth
  `client_id` of every accepted response.

### Identity, ownership, idempotency

- THE SYSTEM SHALL mint `taskId` as `tk_` plus at least 128 bits of CSPRNG
  output. The `xr_` id (`"xr_"` + UUIDv4 hex, 122 random bits) SHALL NOT be
  exposed as the handle.
- WHEN any `tasks/*` call arrives THE SYSTEM SHALL re-authorize the caller
  and compare tenant and owner principal. A foreign, unknown, malformed or
  expired `taskId` SHALL get the same `-32602`.
- WHEN a task-creating call is retried with the same `idempotency_key`,
  principal, tenant, tool and argument digest THE SYSTEM SHALL return the
  same `taskId`.
- IF a consequential task-capable tool is called without an
  `idempotency_key` THEN THE SYSTEM SHALL refuse the call.

### TTL and retention (P2-TS-04)

- WHILE the canonical execution is non-terminal THE SYSTEM SHALL report
  `ttlMs: null` and SHALL NOT expire, fail or delete the task. This includes
  waits on approval or input that last a week or longer.
- WHEN the execution becomes terminal THE SYSTEM SHALL set
  `ttlMs = (terminal_at - createdAt) + terminal_retention` (default
  terminal retention 24 h).
- WHEN that `ttlMs` elapses THE SYSTEM SHALL answer `-32602`, and the
  canonical records SHALL remain reachable through the WorkItem tools.
- WHILE a task binding's idempotency scope row is retained THE SYSTEM SHALL
  replay it. The scope row SHALL be retained for at least the task row's
  lifetime plus the `xr_` replay window, so an expired-task retry cannot
  start a duplicate.

### Cancellation, revocation, audit, notifications

- WHEN `tasks/cancel` is received THE SYSTEM SHALL record the request and
  ask the execution to cancel. It SHALL acknowledge with
  `resultType: "complete"`. It SHALL report `cancelled` only after Temporal
  reports `Canceled` at the workflow's declared cancellation boundary.
- IF another terminal state is recorded first THEN THE SYSTEM SHALL report
  that state.
- WHEN a principal is revoked (#375) THE SYSTEM SHALL refuse that
  principal's further `tasks/*` calls. Pending side effects SHALL be denied
  at the action-time checkpoint.
- THE SYSTEM SHALL audit every create, update entry, cancel and refusal
  with its reason code. It SHALL never log input or result content.
- WHILE #377 (SEP-3415 events) is undecided THE SYSTEM SHALL support polling
  only. It SHALL advertise no task `subscriptions/listen`.

## Out of scope

- Any change to mctl-api, mctl-agents, mctl-gitops, the Portal or a live
  host in Phase 0. This includes any database migration, production endpoint,
  real approval grant, DevLoop or implementer start, deployment, account
  linking and new spend.
- An opt-in local Postgres in Phase 0. Postgres fault-injection proof
  belongs to G1, which needs separate owner approval.
- `tasks/list`, `tasks/result` and the legacy SEP-1686 method set, and
  mcp-go's built-in in-memory task store.
- Sampling-type `inputRequests`. The pilot emits form-mode elicitation only.
- A generic scheduler or queue, or replacing Temporal or Argo.
- Letting MCP Apps (#376) confer approvals, and choosing the business-event
  model (#377).
- Changing the manifest outcome list or recording a decision.

## Open questions

- Vocabulary: this revision makes the manifest vocabulary canonical and maps
  `BOUNDED_PILOT` to `GO_ADAPTER_IN_MCTL_API` with a scope-limiting
  `decision.followUps`. If the owner instead wants `BOUNDED_PILOT` as its own
  outcome, a separate, reviewed manifest change is needed before any
  decision is recorded.
- Design (A) or (B) for P1-TS-02. This revision recommends (A). (A) needs
  the mctl-api owner to accept a new `Store` method inside package
  `workitems`, because `getItem`, `replayed`, `openExecutionRequest` and
  `remember` are package-private. Only G1 can confirm it.
- ADR 013 has no respondent-assurance or surface policy field today.
  `requested_from.actor_refs` names the issue author. Exposing any request
  as an MCP `inputRequest` needs an mctl-agents ADR 013 extension
  (`respondent_policy`). Until then, real DevLoop clarifications map to
  `working`. Only the synthetic probe has a client-relayed policy.
- How an mctl principal resolves to an ADR 013 `actor_ref` (GitHub login)
  is `unknown (not observed)`. The canonical principal ids from mctl-api#373
  may be the join.
- Retention of `work_item_create_requests` and `work_item_requests`
  idempotency rows was not read: `unknown (not observed)`. The TTL rule
  depends on it.
- Whether mcp-go v1.0.0 allows custom `tasks/*` method handlers and
  `server/discover` extension advertisement without its legacy store:
  `unknown (not observed)`. This is gate G2.
- Host support for ChatGPT, Claude (web/desktop), Codex, Antigravity, agy and
  Grok Bot is `unknown`. Claude Code has only the manifest's `[DOC]` note
  (public beta from v2.1.304).
- Portal pass-through of `tasks/*` and `Mcp-Name` (mcp-gateway G2) is
  `unknown`.
- mctl-api's deployed image and flags were not observable through the
  catalogue: `unknown (not observed)`.
