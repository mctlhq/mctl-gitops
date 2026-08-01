# Tasks: issue-350-on-hold-communication-agent-part-2-chann

- [ ] 0. **Operator re-affirmation gate** — DoD: an explicit, recorded
      operator statement authorizing Workstream T/R/G to begin exists
      (e.g. an unlabeled comment on issue #350 from the operator, or a new
      tracking issue they open). No task below this line may start without
      it, regardless of C1's validation status. This is not a formality —
      it is the issue's own stated precondition ("this issue being open is
      not authorization to start Workstream T/R/G").

- [ ] 1. Re-verify the Channels/`-p` transport facts (depends on 0) — DoD:
      reproduce the minimal `server.notification()` MCP server matrix from
      plan §2.3 against the Claude Code version current at pickup time
      (plan records `2.1.220`); confirm `-p` and `-p --input-format
      stream-json` (stdin held open) still never register
      `notifications/claude/channel`, and that a persistent interactive
      PTY session still does. Record only the sanitized pass/fail matrix
      (never raw spike logs, per plan §2.3's explicit prohibition on
      committing them — they may contain account identifiers, prompts, or
      session IDs).

- [ ] 2. **R0 — docs** (depends on 1) — DoD: `mctl-claude-remote/docs/claude-channels-spike.md`
      updated with the re-verified facts and the corrected org-tier framing
      (a Team/Enterprise org removes the per-launch confirmation dialog but
      does not make Channels viable headless — the file currently overstates
      this per plan §2.7/R1). This is in the `mctl-claude-remote` repo, out
      of this clone's write scope — file as a PR there.

- [ ] 3. **T1 — shared Agent API tool/client refactor** (depends on 1) — DoD:
      `internal/agentworker`'s `agentAPI` interface, `Client`
      (`client.go`), and the 11 tool builders (`mcpserver.go`) are
      restructured so both `cmd/agent-worker` and the new
      `cmd/agent-channel` import the same definitions — no behavior change
      to Option C; existing `internal/agentworker` tests
      (`worker_test.go`, `mcpserver_test.go`, `client_test.go`,
      `eval_test.go`) pass unmodified in intent (test file moves/renames
      are fine, assertions are not weakened). One focused PR, not combined
      with T2.

- [ ] 4. **T2 — `cmd/agent-channel` + `internal/agentchannel`** (depends on
      3) — DoD: new stdio MCP server declaring
      `capabilities.experimental["claude/channel"] = {}`; long-polls
      `POST /jobs/claim` exactly like `agentworker.Worker.Loop`; exposes
      only the shared 11 tools from task 3, no built-in/generic tools; wake-up
      notification text matches plan §2.6 exactly (no Telegram IDs, event
      IDs, message bodies, or the Agent API token in notification text or
      process arguments); rejects every tool call with no active job;
      serializes to one active job per process (reuse the `guarded()`
      mutex-per-job pattern from `mcpserver.go`); clears the active slot
      only after `complete_agent_job` durably succeeds; redacts
      bodies/profile data/tokens/proposed text from all logs via the
      existing `internal/audit` redacting handler. Docker build updated so
      the preview image contains a statically linked
      `mctl-telegram-agent-channel` binary (parallel to
      `Dockerfile.agent-worker`'s existing build stage for
      `mctl-telegram-agent-worker`).

- [ ] 5. **T3 — recovery semantics** (depends on 4) — DoD: claim -> set
      active job locally -> emit notification -> tool calls -> durable
      write -> `complete(attempt=N)` -> clear active job, with no local
      "complete" state set before server confirmation; on crash, the
      existing `RequeueStaleAgentJobs` visibility-timeout requeue picks the
      job back up under a higher/current attempt; stale tool calls from an
      old process attempt receive conflict/not-found (extend the fencing
      `GET /jobs/{id}`-style check `agentworker/worker.go` already performs
      for Option C); notification redelivery returns the persisted exact
      action/body rather than re-deriving or re-generating it.

- [ ] 6. **T4 — context-isolation policy for preview phase 1** (depends on
      4) — DoD: hard-coded to one test owner, one allowlisted
      sender/conversation, one active job, no concurrent conversation
      interleaving (reuse the existing `agent_profiles.sender_allowlist`
      gate already shipped for C1, per
      `docs/reports/communication-agent-c1.md`'s 2026-07-26 entry). Document
      which of the plan's three post-preview context strategies (bounded
      rotation / per-conversation process / per-job session) is chosen
      before ever expanding past this single-conversation preview — do not
      silently promote strategy 1.

- [ ] 7. **T5 — mctl-telegram unit/integration tests** (depends on 4, 5, 6)
      — DoD: all of plan §2.6/T5's listed cases implemented — capability
      declaration, exact shared tool list, no built-in tools in generated
      launch config, rejection without active job, stale-attempt rejection,
      job/conversation identity not model-suppliable, duplicate
      notification does not double-write, complete clears active slot only
      after server success, zero event body/token/proposed-text in logs;
      plus integration cases (fake Agent API claim -> notification -> tool
      -> complete; crash at each of the three boundaries in task 5;
      visibility-timeout requeue; stale old-process write after new claim).
      `go test -count=1 ./...`, `go vet ./...`,
      `go test -race ./internal/agentchannel/... ./internal/agentworker/...
      ./internal/agentapi/...`, `govulncheck ./...` all pass.

- [ ] 8. **R1-R7 — `mctl-claude-remote` communication-agent mode** (depends
      on 2, 4) — DoD: as specified in plan §2.7 (`CLAUDE_RUNTIME_MODE`,
      exact-match fail-closed PTY warning driver, restricted
      `--tools ""` / `--allowedTools` / `--strict-mcp-config` launch,
      no `AGENT_API_TOKEN`/GitHub/Kubernetes/MinIO credentials in the
      Claude process env, loopback-only readiness reflecting MCP connection
      state not Remote Control relay health, init-container binary copy
      packaging per R6.1). This work is entirely in the `mctl-claude-remote`
      repo, out of this clone's scope — file as a separate PR there,
      following its own `AGENTS.md`.

- [ ] 9. **G1-G5 — `mctl-gitops` preview deployment** (depends on 8) — DoD:
      `platform-gitops/services/labs/communication-agent-preview/values.yaml`
      added at `replicaCount: 0`; production
      `services/labs/mctl-telegram/values.yaml` and release PR #303 left
      untouched; `mctl-telegram-preview` gets `AGENT_ENABLED=true`,
      `AGENT_KILL_SWITCH=true` (dark phase); no ingress, no public Service,
      no ServiceAccount token automount, no Role/ClusterRole/RoleBinding, no
      GitHub App secret; dedicated Agent API token and dedicated Claude
      credentials/state (PVC or MinIO prefix per G4, chosen only after
      checking current `labs` PVC quota — decision requires operator
      sign-off per gate 1 in requirements.md). Human-reviewed only, never
      auto-merged, per the plan's explicit "never auto-merge mctl-gitops"
      instruction.

- [ ] 10. **Rollout phases 0-3** (depends on 9) — DoD: executed in order per
       plan §2.9 — Phase 0 dark validation, Phase 1 channel-runtime smoke
       test with a synthetic job (kill switch still on), C1-equivalent
       validation hardening reused as-is (sender allowlist, eval harness),
       Phase 2 one real test conversation with kill-switch flip drills,
       Phase 3 bounded observe soak (>=30 fixtures) comparing Option A vs
       Option C on partitioned queues. Every operator decision gate in plan
       §2.14 / requirements.md is honored at the point it applies, not
       batched or skipped.

- [ ] 11. **Failure drills** (depends on 10) — DoD: every drill in plan
       §2.10 executed with expected DB/job/action state recorded (not just
       logs) — crash at each of the three claim/notify/complete boundaries,
       full pod restart, delayed restart past visibility timeout, stale
       write after new attempt claims, two jobs close together (strict
       serialization), source-message edit/delete mid-job, owner takeover
       mid-job, kill-switch flip before send, Agent API token revocation,
       malformed MCP response, changed development-warning text, channel
       subprocess exit while Claude stays alive, Claude exit while the
       channel subprocess has an active job.

- [ ] 12. **Phase 4 decision** (depends on 11) — DoD: an explicit
       keep/diagnostic-only/drop decision recorded against the comparison
       data from task 10 (claim-to-first-action latency, cost per job,
       valid-completion rate, context leakage, stale-attempt rejections,
       restart recovery duration, dead-letter rate, operator interventions).
       Passing the happy path alone is explicitly insufficient per plan
       §2.9.

## Tests

- [ ] T1. Unit: `cmd/agent-channel` declares
      `capabilities.experimental["claude/channel"]` and registers exactly
      the shared 11-tool list — no drift from `internal/agentworker`'s
      definitions (task 3/7).
- [ ] T2. Unit: every tool call is rejected when no job is active; a
      job/conversation/attempt id cannot be supplied by the model in any
      tool argument (task 7).
- [ ] T3. Unit: a duplicate wake-up notification for the same
      job+attempt does not produce a second durable action or a second
      `complete_agent_job` success (task 5/7).
- [ ] T4. Integration: fake Agent API — claim -> notification -> tool call
      -> `complete_agent_job`; assert `GET /jobs/{id}`-equivalent state is
      terminal exactly once (task 7).
- [ ] T5. Integration: crash injected at each of claim-before-notify,
      notify-before-first-tool, and durable-write-before-complete; assert
      the job is requeued (not silently lost, not double-completed) and a
      later attempt succeeds cleanly (task 5/7).
- [ ] T6. Integration: an old process's stale attempt attempts a write
      after a new claim has advanced the attempt counter; assert the write
      is rejected, not silently applied (task 5/7).
- [ ] T7. `mctl-claude-remote`: PTY driver accepts the exact expected
      prompt/channel name and rejects any deviation (changed text, wrong
      channel, login prompt, permission prompt) with a nonzero exit and no
      keystrokes sent (task 8).
- [ ] T8. `mctl-claude-remote`: no `AGENT_API_TOKEN` or other unrelated
      credential appears in the Claude process environment or
      `/proc/<pid>/cmdline` (task 8).
- [ ] T9. End-to-end (staging, Phase 2): a real Telegram DM from the
      dedicated test account produces an event -> job -> Channels wake-up
      -> `propose_reply` -> `require_approval` -> Saved Messages draft ->
      `/mctl approve` -> reply delivered to the original peer only, audit
      chain rows present; kill-switch flip between approval and send blocks
      the send (task 10).
- [ ] T10. Fleet regression: full existing suite still passes after the T1
      refactor — `go test -count=1 ./...`, `go vet ./...`, race tests on
      `internal/agentworker`/`internal/agentapi`, `govulncheck ./...` (task
      3, 7).

## Rollback

- **Before any code exists (current state):** nothing to roll back — the
  issue stays open, on hold, and this proposal is inert documentation.
- **During Workstream T (mctl-telegram):** each PR (T1, T2/T3/T4/T5 taken
  together as "T2" in the PR sequence) is independently revertible via
  normal squash-merge revert; none of it is wired into Option C's path, so
  reverting it cannot affect production. `cmd/agent-channel` ships gated by
  the fact that nothing invokes it unless `mctl-claude-remote` is configured
  with `CLAUDE_RUNTIME_MODE=communication-agent`, which defaults off.
- **During Workstream R (mctl-claude-remote):** the new runtime mode is
  opt-in via `CLAUDE_RUNTIME_MODE`; default remains `remote-control`. Revert
  is a config no-op — no code needs to be pulled to disable it.
- **During Workstream G / rollout phases 0-3 (mctl-gitops):** the fastest
  rollback at any point is `replicaCount: 0` on
  `communication-agent-preview` (scale-to-zero, no code change, no data
  loss — the job that was in flight gets requeued by the existing
  visibility timeout exactly like any other worker crash) combined with
  `AGENT_KILL_SWITCH=true` on `mctl-telegram-preview` if a send-path concern
  is suspected. Full removal is deleting the
  `communication-agent-preview` values.yaml and its GitOps-managed
  resources; `mctl-telegram-preview` and Option C are unaffected either way
  since G1 explicitly forbids touching them.
- **If Phase 4 decides "drop":** scale to zero permanently, leave the code
  behind as a documented, disabled spike (per plan Phase 4 option 2/3) or
  remove it in a follow-up cleanup PR — either is acceptable per the plan;
  neither requires touching Option C or any production path.
- **At any point:** because Option C never depends on Channels code or
  deployment existing, there is no scenario in this proposal's scope where
  rolling back Part 2 requires touching, redeploying, or pausing Part 1.
