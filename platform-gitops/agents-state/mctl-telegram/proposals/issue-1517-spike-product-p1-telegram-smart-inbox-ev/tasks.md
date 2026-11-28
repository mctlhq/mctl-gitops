# Tasks: issue-1517-spike-product-p1-telegram-smart-inbox-ev

- [ ] 1. SI0 inventory. Write the inventory section of `docs/research/smart-inbox-1517.md`.
  - Cover these items, each with file and symbol references at the pinned SHA:
    - `telegram_dashboard` and `workspaceSnapshot` (`internal/mcp/workspace.go`);
    - `setWorkspaceToolVisibility` (`internal/mcp/apps.go`);
    - `toolPassesFilter` and `withoutWorkspaceMedia` (`internal/mcp/server.go`);
    - the Workspace HTML sections (`internal/mcpui/workspace.html`);
    - the #1152 layers (`internal/mcp/hidden.go`, `internal/db/hidden_dialogs.go`,
      `internal/web/manage_hidden.go`) and the tests that cover them;
    - hosted versus `s.Hub.Call` dispatch (`internal/mcp/tools.go`);
    - #1155 reads (`list_folders`, `list_topics`) and #1175 writes (`mark_read`, `save_draft`,
      `draft_reply`).
  - DoD: every claim cites a path and symbol. The report records that the projection gap
    (`telegram.Message` lacks out, reply-to, edit date and topic) is in `decodeMessagesRaw`. It
    lists any #1152 coverage gaps it found, and states that #650 remains the canonical rollout.
- [ ] 2. Synthetic fixtures (depends on 1). Add `internal/inbox/testdata/fixtures/*.json` covering
  every case listed in requirements.md, each labeled with an expected status and reason code.
  - DoD: only the Alice, Bob, Carol and Dana personas are used, with ids checked against
    `git grep`. Every required case has at least one fixture. The incomplete-history,
    bridge-offline and field-absent fixtures all expect UNCLEAR.
- [ ] 3. Harness package `internal/inbox` (depends on 2). Implement these pure functions with no
  I/O, logging, network or model call:
  - `Scope` (using `telegram.HiddenPeers`);
  - `Baseline` (the unread/mentions rule);
  - `Classify` (the deterministic rules in design.md section 3);
  - `validateEvidence`;
  - `Evaluate`.
  - DoD: `go vet` and `golangci-lint` are clean. `internal/inbox` is not imported by
    `internal/mcp`, `cmd/server` or `cmd/local`.
- [ ] 4. Evaluation run (depends on 3). Add a test that prints a metrics table. The test runs
  with `go test ./internal/inbox -run TestEvaluateReport -v`. Copy the table into the report.
  - DoD: the report shows, separately for the baseline and the candidate:
    - per-status precision and recall;
    - NEEDS_REPLY false negatives;
    - the abstention rate;
    - reads per fixture.
  - The numbers are reproducible across runs.
- [ ] 5. Decision and SI1 analysis (depends on 4). In the report, state the decision:
  EXTEND_READ_MODEL, PROMPT_ONLY or DEFER. Add these parts:
  - the evidence contract;
  - uncertainty handling;
  - the freshness model (recompute on refresh, no persisted state);
  - bounded-read cost and latency estimates;
  - a paper-only budget for the optional LLM path, with its consent preconditions.
  - DoD: the decision follows from the measured numbers. The report states plainly that the
    results are synthetic-only and that demand is unproven.
- [ ] 6. SI2 and SI3 design (depends on 5). In the report, specify the following:
  - the optional `Triage` section in `workspaceSnapshot` (`telegram-workspace/v2`);
  - the Inbox status filter, sort and evidence expansion, using the existing `get_messages`;
  - the text-fallback line in `summarizeWorkspace`;
  - the Local Bridge field-absent behaviour, a dedicated new flag, and the SI3 protocol with
    proposed thresholds.
  - DoD: the design adds no new tool, App resource, iframe capability or scheduler. It states
    that a future write uses only the existing confirmation, consent and scope paths. It lists
    the owner GOs required.

## Tests

- [ ] T1. `TestClassifyFixtures`: every fixture's output matches its expected status and reason
  code.
- [ ] T2. `TestHiddenPeerNeverInOutput`: a hidden peer is absent from the following, including
  when it was mentioned by a visible peer's message reference:
  - classifier input and items;
  - evidence refs and counts;
  - the metrics inputs.
- [ ] T3. `TestScopeMutation`: run the pipeline with `Scope` replaced by identity. T2's assertions
  must fail. This guards against a test that passes vacuously.
- [ ] T4. `TestRevokeBetweenRefreshes`: the hidden set grows, or `telegram:messages:read` is
  dropped, between refresh 1 and refresh 2. Refresh 2 output contains none of the affected
  entries, and nothing is reused from refresh 1.
- [ ] T5. `TestEvidenceProvenance`: every `Ref` exists in the scoped input, and no item has an
  empty reason or an empty `ObservedAt`. Absent fields yield UNCLEAR, never ANSWERED or
  NEEDS_REPLY.
- [ ] T6. `TestCrossAccountIsolation`: items computed for account A never reference account B's
  fixture peers.
- [ ] T7. `TestFixturesSynthetic`: the fixtures contain only allowlisted synthetic ids and
  persona names. A lint test rejects unknown digit runs and handles.
- [ ] T8. `TestInboxNotLinkedIntoServer`: `go list -deps` for `./cmd/server`, `./cmd/local` and
  `./internal/mcp` excludes `internal/inbox`.
- [ ] T9. The existing suites (`internal/mcp/hidden_test.go`, `workspace_test.go`,
  `apps_surface_test.go`, `internal/mcpui/app_test.go`) pass unchanged, which proves no served
  behaviour or golden hash changed.

## Rollback

The spike only adds `docs/research/smart-inbox-1517.md` and the unlinked `internal/inbox` package
with its testdata. To roll back, revert the merge commit. No flags, migrations, gitops values,
tool registrations or deployments are involved, so no runtime rollback is needed.
