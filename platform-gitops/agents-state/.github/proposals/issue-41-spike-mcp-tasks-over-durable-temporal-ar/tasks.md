# Tasks: issue-41-spike-mcp-tasks-over-durable-temporal-ar

All tasks change only files in mctlhq/.github. None of them touches
mctl-api, mctl-agents, mctl-gitops, the Portal or a live host. Every commit
carries the `Agent:` trailer (AGENTS.md).

- [ ] 1. Pin evidence and write the report skeleton at
  `docs/spikes/mcp-tasks-durable-execution.md`. It covers question,
  non-claims, evidence tags, and an evidence-pin table (40-hex SHAs for
  .github, mctl-api, mctl-agents and mcp-go v1.0.0/v1.6.0, plus the spec URL
  for 2026-07-28 and SEP-2663). It distinguishes legacy SEP-1686 from the
  modern extension. — DoD: every source in design.md "Current state" is
  pinned and tagged. `unknown (not observed)` is used for mctl-api runtime,
  the Portal and the hosts.
- [ ] 2. (depends on 1) Write the ADR-41 section and the lifecycle mapping
  table from design.md. Include the protocol-state vs execution-state split
  and the `mcp_tasks` column list (no status column). — DoD: each MCP status
  has exactly one canonical source, and the read-failure row maps to
  `-32603`.
- [ ] 3. (depends on 2) Add Mermaid sequence diagrams for create/poll,
  input_required/resume, approval wait via the decide page, cancel (including
  the race with completion), and reconnect/retry with the same
  `idempotency_key`. — DoD: five diagrams. None keeps an HTTP request open
  across a gate.
- [ ] 4. (depends on 2) Specify the identity, ownership, TTL, idempotency,
  cancellation-boundary, revocation/fencing (#375), audit, notification
  (#377) and fallback rules. — DoD: each rule names its error code or
  outcome, and `isError` vs `failed` is stated explicitly.
- [ ] 5. (depends on 2) Build the stdlib Go reference model in
  `docs/spikes/mcp-tasks-durable-execution/model/`. It has:
  - an adapter with a fake WorkItem store (`wi_`/`xr_`/`we_`);
  - a fake Temporal (describe, query `human_input_state`, signal, cancel);
  - a fake grant store;
  - a fake clock;
  - JSON fixtures in `fixtures/` and schemas for `CreateTaskResult` and
    `tasks/get` in `schemas/`.

  — DoD: `go test ./...` passes offline. There is no network and no
  `Mcp-Session-Id`.
- [ ] 6. (depends on 5) Add an opt-in
  `docs/spikes/mcp-tasks-durable-execution/temporal-integration/` module
  with `TaskProbeWorkflow` (cancellable sleep, input gate, approval-wait
  gate, deterministic result) on a local Temporal dev server through
  `go.temporal.io/sdk`, mirroring
  `docs/spikes/automation-control-plane/temporal-integration/`. — DoD: the
  tests are tagged `[TEMPORAL_DEV]` and are skipped without a dev server.
  Worker-restart and client-disconnect tests pass.
- [ ] 7. (depends on 5, 6) Fill in the test matrix (T1-T20 below) with
  results. Each result is tagged `[MODEL]` or `[TEMPORAL_DEV]`, and the two
  are never merged. — DoD: every row has a result, or `not run` with a
  reason.
- [ ] 8. (depends on 1) Write the host/SDK compatibility matrix:
  - Claude Code `[DOC]` only;
  - ChatGPT, Claude web, Codex, Antigravity, agy and Grok Bot `unknown`;
  - mcp-go legacy-only `[CODE]`;
  - the Portal `Mcp-Name`/`tasks/*` pass-through `unknown`, gated on
    mcp-gateway G2.

  — DoD: no cell claims support without evidence.
- [ ] 9. (depends on 2-8) Write the repository decomposition, the decision
  gates G0-G3, the exact scope of mctl-api#284 (one pilot tool, one table,
  one cancel method) and the rollback, plus a proposed verdict
  `GO_ADAPTER_IN_MCTL_API` (issue vocabulary: `BOUNDED_PILOT`). — DoD: the
  manifest stays `lifecycle: proposed`, and the open questions are copied
  into the report.
- [ ] 10. (depends on 9) Index the report in the AGENTS.md "Spikes" list and
  link it from `roadmap/spikes/mcp-tasks-durable-execution.yaml` comments
  without changing `lifecycle` or `outcomes`. Run the roadmap validators
  under `roadmap/tests`. — DoD: the validators pass, and the PR is opened
  for independent review and not merged by the author.

## Tests

- [ ] T1. Create/poll: `tools/call` returns `resultType: "task"`, and an
  immediate `tasks/get` succeeds (durable create-before-return).
- [ ] T2. Non-negotiating client: the call returns `CallToolResult` with
  `wi_`/`xr_` refs, and `tasks/get` returns `-32021`.
- [ ] T3. Disconnect/reconnect: the client drops after create. A new
  connection with the same `taskId` gets the same terminal `result`.
- [ ] T4. Worker restart mid-run `[TEMPORAL_DEV]`: the task still completes
  with the same result. No second execution starts.
- [ ] T5. Duplicate create: the same key and digest return the same
  `taskId`, with one `xr_` and one `we_`.
- [ ] T6. Key reuse: the same key with a different digest gets
  `idempotency_key_reused`. A missing key on a consequential tool is
  refused.
- [ ] T7. Cross-tenant: tenant B's principal calls get/update/cancel on
  tenant A's task and gets `-32602`, identical to an unknown ID.
- [ ] T8. Same tenant, other principal: `-32602`.
- [ ] T9. Malformed, unknown and expired-TTL IDs all return the identical
  `-32602`. No timing or field difference is observable in the model.
- [ ] T10. Entropy: 10^6 minted IDs show no collision. IDs never contain a
  workflow ID or issue reference.
- [ ] T11. Input pause/resume: `input_required` shows `inputRequests` keyed
  by `request_id`. `tasks/update` with the correct key resumes, and the
  status returns to `working`, then `completed`.
- [ ] T12. Input replay: re-sending an answered key is ignored and audited.
  A stale or expired `request_id`, or a wrong `request_hash`, is rejected by
  the workflow and does not resume.
- [ ] T13. Approval binding: `tasks/update` cannot approve. Approving a grant
  with a different `artifact_hash` or `context_digest` gives `mismatch`.
  Only the matching, unexpired, unconsumed grant resumes the task once.
- [ ] T14. Cancel while waiting for input: the acknowledgement is empty, and
  the task is `cancelled` only after Temporal reports `Canceled`.
- [ ] T15. Cancel during the activity: during the heartbeat window,
  `tasks/get` shows `working` plus "cancellation requested". Then the task
  is `cancelled`.
- [ ] T16. Cancel vs completion race: when the completion is recorded first,
  the task stays `completed`. A cancel after a terminal state is a no-op
  acknowledgement.
- [ ] T17. Business error is `completed` with `isError: true`. A workflow
  failure is `failed` with a classified `error`.
- [ ] T18. Unreadable Temporal or store: `tasks/get` gives `-32603`, never a
  guessed status.
- [ ] T19. Revocation: the principal is revoked mid-task. Further `tasks/*`
  calls are refused, and the probe's simulated side effect is denied at the
  action-time checkpoint.
- [ ] T20. Legacy surface absent: `tasks/list` and `tasks/result` return
  method-not-found. No `subscriptions/listen` for tasks is advertised.

## Rollback

This proposal only adds documentation and a self-contained fixture
directory in mctlhq/.github. To roll back, revert the spike PR, which
removes the report, the fixture directory and the AGENTS.md index line. The
manifest's `lifecycle` and `outcomes` are never changed, so there is no
roadmap state to undo. No service, database, Temporal namespace, gitops
value or host was touched, so nothing runtime needs reverting. For the later
mctl-api#284 pilot, the design defines this rollback, which that issue must
re-confirm:

1. Remove the `server/discover` extension advertisement. Clients then fall
   back to plain `CallToolResult`.
2. Leave the additive `mcp_tasks` table inert.
3. Keep the canonical `wi_`/`xr_`/`we_` records and Temporal executions,
   which were never owned by the adapter.
