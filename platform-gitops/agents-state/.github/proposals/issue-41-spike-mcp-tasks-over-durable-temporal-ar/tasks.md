# Tasks: issue-41-spike-mcp-tasks-over-durable-temporal-ar

Revision 2. Every task is Phase 0 and changes files only in mctlhq/.github,
under `docs/spikes/mcp-tasks-durable-execution*`, plus the AGENTS.md index
line. The only exception is an optional `spec.evidence.report` line in
`roadmap/spikes/mcp-tasks-durable-execution.yaml`.

No task may touch:

- mctl-api, mctl-agents or mctl-gitops;
- the Portal, a production endpoint or a database;
- a real approval grant or an external host;
- the implementer.

Every commit carries the `Agent:` trailer (AGENTS.md). Gates G1-G4 are
listed for traceability only. They are NOT tasks of this proposal.

- [ ] 1. Write `docs/spikes/mcp-tasks-durable-execution.md`: question,
  non-claims, evidence tags and evidence pins. The pins are .github
  `60e9db5`, mctl-api `80f7a011...` with the `execution_requests.go` blob
  `913924a3...`, mctl-agents `eec4fdd8...`, the mcp-go tag `v1.0.0`, and the
  spec URL with its retrieval date. Add the legacy SEP-1686 versus 2026-07-28
  table. — DoD:
  - every source in design.md "Current state" is pinned and tagged;
  - mctl-api runtime, the Portal and the hosts are marked
    `unknown (not observed)`.
- [ ] 2. (depends on 1) Add the finding-to-change matrix for P1-TS-01 to
  P2-TS-06. — DoD: each finding names its revision 2 section, its Phase 0
  test ids and its later gate.
- [ ] 3. (depends on 1) Write the ADR and the revised lifecycle mapping
  (design.md section 3). — DoD:
  - `input_required` appears only with a non-empty elicitation
    `inputRequests`;
  - the approval wait and human-only input map to `working`;
  - the decide-link permission rule is stated;
  - a read failure maps to `-32603`.
- [ ] 4. (depends on 3) Specify durable create-before-return: design A
  (`Store.CreateTaskExecution`, its lock order, commit order and collision
  rules) and fallback design B (`reserving`, then `bound`, plus the recovery
  sweep). — DoD:
  - each step names the `withTx` or lock it runs under;
  - the report says in words that Phase 0 does not prove Postgres atomicity
    and that G1 does.
- [ ] 5. (depends on 3) Specify the `tasks/update` trust boundary: the
  eight-step check order, reason codes, the `respondent_policy` dependency
  on an ADR 013 extension, and the OAuth-client rules. Specify TTL as null
  while non-terminal, terminal-only expiry and scope retention. Specify
  cancellation, revocation, audit, notification and fallback. — DoD: every
  rule names its outcome or error code.
- [ ] 6. (depends on 3) Add Mermaid sequence diagrams. — DoD: six diagrams,
  and none holds an HTTP request open across a gate. The diagrams are:
  - create/poll;
  - client input through `input_required` and `tasks/update`;
  - an approval wait that stays `working` and is decided on the decide
    page;
  - cancel, including the race with completion;
  - reconnect/retry with the same key;
  - a crash during create under design A and design B.
- [ ] 7. (depends on 4, 5) Build the stdlib Go model in
  `docs/spikes/mcp-tasks-durable-execution/model/`. It contains:
  - the adapter;
  - a fake `workitems` store implementing designs A and B, with injected
    crash points before and after each step;
  - a fake Temporal (describe, `human_input_state`, signal spy, cancel,
    time-skipping clock);
  - a fake grant store;
  - an `Mcp-Name` transport shim.

  — DoD: `go test ./...` passes offline, with no network.
- [ ] 8. (depends on 7) Add `schemas/vendor/` (the official schema at a
  pinned commit with its sha256, or a recorded reason why it could not be
  obtained), `fixtures/responses/`, `fixtures/negative/` and
  `checks/validate_fixtures.py`. The script runs with `python -I` and
  `jsonschema==4.25.1`, with no imports from the model. — DoD:
  - every positive fixture validates;
  - every negative fixture fails, with the expected error path.
- [ ] 9. (depends on 7) Add the opt-in `temporal-integration/` module with
  `TaskProbeWorkflow`, mirroring
  `docs/spikes/automation-control-plane/temporal-integration/`. Its phases
  are a sleep, a client-relayable input gate, a human-only input gate, an
  approval wait, and a result or business error. — DoD:
  - the tests are tagged `[TEMPORAL_DEV]` and skip without a local dev
    server;
  - the worker-restart, disconnect and 8-day time-skipped approval tests
    pass.
- [ ] 10. (depends on 1) Add the verdict-vocabulary map and
  `checks/verdict_consistency.py`. The script reads the manifest with
  PyYAML and the report's pinned issue-outcome line. — DoD:
  - checks C1-C3 pass;
  - the report labels `BOUNDED_PILOT` "recommendation, not decision";
  - the manifest `lifecycle`, `outcomes` and `decision` are unchanged.
- [ ] 11. (depends on 7-10) Fill in the test matrix with results tagged
  `[MODEL]`, `[TEMPORAL_DEV]` or `[SCHEMA]`, with the tags never merged.
  Write the host/SDK matrix with `unknown` cells, gates G0-G4, the exact
  scope and the rollback. — DoD: every row has a result, or `not run` with a
  reason.
- [ ] 12. (depends on 11) Index the report in the AGENTS.md "Spikes" list.
  Optionally set `spec.evidence.report` in the manifest. Run
  `python -m unittest` under `roadmap/tests`. — DoD:
  - the validators pass;
  - the PR is opened for independent review and is not merged by its
    author;
  - the proposal stops at proposed.

## Tests

### Lifecycle and protocol `[MODEL]`, re-run `[TEMPORAL_DEV]` where marked

- [ ] T1. Create/poll: create returns `resultType: "task"`. An immediate
  `tasks/get` returns `resultType: "complete"`, `working`. Also
  `[TEMPORAL_DEV]`.
- [ ] T2. Non-negotiating client: the call returns `CallToolResult` with
  `wi_`/`xr_` references. `tasks/get`, `tasks/update` and `tasks/cancel`
  return `-32021`. The extension declared on an earlier request only still
  gives `-32021`.
- [ ] T3. Disconnect/reconnect: a new connection, and a different OAuth
  client of the same principal, gets the same terminal `result`. Also
  `[TEMPORAL_DEV]`.
- [ ] T4. Worker restart mid-run: same result, one execution.
  `[TEMPORAL_DEV]`.
- [ ] T5. Duplicate create: same key and digest return the same `taskId`,
  with one `xr_` and one `we_`.
- [ ] T6. Key reuse with a different digest gets `idempotency_key_reused`.
  A missing key on a consequential tool is refused.
- [ ] T7. Cross-tenant get, update and cancel return `-32602`, identical to
  an unknown id.
- [ ] T8. Same tenant, other principal: `-32602`.
- [ ] T9. Malformed, unknown and expired ids return identical `-32602`
  bodies.
- [ ] T10. Entropy: 10^6 ids show no collision. No id contains a workflow
  id, issue reference or `xr_` id.
- [ ] T11. Client-relayable input: `input_required` with one form
  elicitation keyed by `request_id`. A valid `tasks/update` returns
  `working`, then `completed`. Also `[TEMPORAL_DEV]`.
- [ ] T12. Business error: `completed` with `isError: true`. A workflow
  failure: `failed` with a classified `error`.
- [ ] T13. An unreadable store or Temporal gives `-32603`, never a status.
- [ ] T14. Legacy surface absent: `tasks/list` and `tasks/result` return
  method not found. No task `subscriptions/listen` is advertised.

### Approval and input boundary (P1-TS-01, P2-TS-03)

- [ ] N1. Approval wait: the status is `working` with an advisory
  `statusMessage` and no `inputRequests`. The schema accepts it.
- [ ] N2. Decide link: present only for a principal authorized to decide
  the grant. The task owner without decide rights gets no link and no grant
  content.
- [ ] N3. Human-only input request (no `mcp/client_relayed` policy): the
  status is `working` and the request is not emitted.
- [ ] N4. A caller who is not in `actor_refs`, on a client-relayable
  request: `working` and no `inputRequests`.
- [ ] N5. `tasks/update` with a key equal to the pending `aar_` id: ignored
  (`not_open`). The signal spy shows zero `SignalApprove` or approval-wake
  calls. The grant is untouched.
- [ ] N6. Replay of an answered key, a key from a prior round, or an
  arbitrary key: ignored and audited. Workflow state is unchanged.
- [ ] N7. Expired request, exhausted rounds, or a changed `request_hash`:
  ignored (`expired`, `rounds_exhausted`, `hash_mismatch`). The workflow
  does not resume. Also `[TEMPORAL_DEV]`.
- [ ] N8. A value that fails the `ResponseSpec` or exceeds the ADR 013
  limits: `invalid_value`.
- [ ] N9. Service, agent and relayed-surface credentials are refused for
  `tasks/update` and `tasks/cancel`. A `same_client` policy refuses a
  different `client_id`. `any_client_of_owner` accepts it and records the
  `client_id`.
- [ ] N10. An approval grant with a different `artifact_hash` or
  `context_digest` gives `mismatch`. Only the matching, unexpired and
  unconsumed grant resumes the task, exactly once.

### Durable create (P1-TS-02) `[MODEL]` only. Postgres proof is G1.

- [ ] D1. Design A, crash at each of the seven steps: no `xr_` and no
  binding persist. A retry creates exactly one of each.
- [ ] D2. Design A, a concurrent same-scope race (100 goroutines): one
  `xr_`, and all callers get the same `taskId` or `idempotency_key_reused`.
- [ ] D3. Design A: the dispatcher's claim scan never sees an `xr_` without
  a binding, checked at every interleaving of the fake scheduler.
- [ ] D4. Design B, crash after `xr_` but before `bound`: a retry returns
  the same `taskId`. The sweep binds stale `reserving` rows, and no second
  `xr_` is created.
- [ ] D5. The report's G1 row says `not run: requires Postgres, owner-gated`.

### TTL (P2-TS-04)

- [ ] T21. An 8-day approval wait (fake clock, plus `[TEMPORAL_DEV]`
  time-skipping): `ttlMs` stays `null`, `tasks/get` keeps answering, and
  the task is never `-32602` while running.
- [ ] T22. Terminal: `ttlMs` equals `(terminal_observed_at - createdAt) +
  24h`. After it elapses the task gives `-32602`, and the WorkItem tools
  still return the result.
- [ ] T23. Expired-task retry with the same key inside the scope window:
  the same `taskId` (`-32602`) and no new `xr_`. After the window the
  documented new-item behaviour applies.
- [ ] T24. An orphan-closed execution reads `failed`
  (`execution_orphaned`) and is then reclaimed.

### Cancellation

- [ ] T15. Cancel while waiting for input: the acknowledgement has
  `resultType: "complete"`, and the task is `cancelled` only after
  `Canceled`. Also `[TEMPORAL_DEV]`.
- [ ] T16. Cancel during an activity: `working` with "cancellation
  requested", then `cancelled`.
- [ ] T17. Cancel versus completion race: the first terminal state wins. A
  cancel after a terminal state is a no-op acknowledgement.
- [ ] T18. Cancel before `we_` exists: the `xr_` is rejected with reason
  `cancelled_by_task`, and the task reads `cancelled`. A rejection for any
  other reason reads `failed` (`execution_request_rejected`).
- [ ] T19. Revocation mid-task: further `tasks/*` calls are refused, and the
  probe's side effect is denied at the checkpoint.

### Schema and transport (P2-TS-05) `[SCHEMA]`

- [ ] S1. The pinned vendor schema's sha256 matches the report.
- [ ] S2. Positive fixtures validate:
  - create (`resultType: "task"`);
  - get in each of the five statuses;
  - the update acknowledgement and the cancel acknowledgement;
  - errors `-32602`, `-32603` and `-32021`.
- [ ] S3. Each of these negative fixtures fails validation:
  - `input_required` without `inputRequests`;
  - `input_required` with an empty `inputRequests` map.
- [ ] S4. Each of these negative fixtures fails validation:
  - `completed` without `result`;
  - `failed` without `error`.
- [ ] S5. Negative: get with `resultType: "task"`, and update or cancel
  without `resultType`, each fail.
- [ ] S6. Negative: `inputRequests` on `working` fails. The model also
  refuses to emit it.
- [ ] S7. Negative: a sampling entry and an approval-shaped entry in
  `inputRequests` are refused by the model.
- [ ] S8. Go model output for T1-T24 is captured and validated by the
  Python checker, as a cross-check that does not trust the Go validators.
- [ ] S9. `Mcp-Name` missing, case-changed, whitespace-padded or naming
  another task's id: `-32602`, before lookup.
- [ ] S10. The `tasks/update` partial set: one valid key and one invalid key
  in one call. The valid key is applied, the invalid key is ignored, and the
  result is one `resultType: "complete"` acknowledgement.

### Verdict consistency (P2-TS-06)

- [ ] C1. Every issue outcome has exactly one mapping row. A mutated map
  that drops `DEFER` fails.
- [ ] C2. Every mapping target is in the manifest `spec.outcomes`. A mutated
  target `BOUNDED_PILOT` fails.
- [ ] C3. The report contains no "Decision:" line while the manifest lacks
  `spec.decision`. `roadmap/tests` still pass.

## Rollback

Phase 0 adds only documentation, a self-contained fixture directory, an
AGENTS.md index line and, optionally, one `spec.evidence.report` line. To
roll back, revert the spike PR. The manifest `lifecycle`, `outcomes` and
`decision` are never changed, so there is no roadmap state to restore.
After the revert, `roadmap/tests` must pass. Nothing at runtime was touched:
no service, database, Temporal namespace (only a disposable local dev
server), gitops value, host or approval grant.

For the gated later phases, which their own reviews must re-confirm:

- **G1 (branch only).** Delete the branch. Design A's tables are additive
  and unused by existing paths. `CreateExecutionRequest` keeps its
  behaviour through the wrapper, and reverting the refactor is a pure code
  revert.
- **G2 and after.**
  1. Remove the `server/discover` extension advertisement. Clients fall back
     to `CallToolResult`.
  2. Leave `mcp_tasks` and `mcp_task_scopes` inert.
  3. Keep the canonical `wi_`, `xr_` and `we_` records and the Temporal
     executions. The adapter never owned them.
