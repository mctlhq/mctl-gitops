# Design: issue-350-on-hold-communication-agent-part-2-chann

## Current state

The communication agent's Part 1 backend is fully implemented and merged in
this repo. What exists today, verified by reading the actual code:

- **Ingest.** `internal/telegram/clientpool.go` keeps one long-lived `gotd`
  client per user; agent-enabled users get a pinned, GC-exempt entry with a
  custom `UpdateHandler` (`ClientPool.WithAgentRuntime`, referenced around
  line 96/329-336). `internal/agent/listener` wraps `tg.NewUpdateDispatcher`
  in `updates.New` and maps updates to durable `incoming_events` rows.
- **Queue.** `internal/agent/queue` (`agent_jobs` /
  `agent_job_attempts`) provides `EnqueueAgentJob` (idempotent by
  `event_id`), `ClaimAgentJobs` (`FOR UPDATE SKIP LOCKED` on Postgres, a
  two-step claim on sqlite), and `RequeueStaleAgentJobs` on a visibility
  timeout — this is the durability backbone every transport (Option C today,
  Option A if ever built) claims jobs through identically.
- **Agent-facing HTTP surface.** `internal/agentapi` mounts
  `/api/agent/v1` with `aud=agent` JWTs (cloned from the `internal/bridge`
  pattern). `POST /jobs/claim` is the long-poll claim path; `GET /jobs/{id}`
  is the minimal durable-completion postcondition a worker uses to decide
  whether an attempt actually reached a terminal state, independent of
  whatever the model's final turn text says.
- **Production transport (Option C).** `cmd/agent-worker/main.go` runs a
  Go poll loop (`internal/agentworker.Worker.Loop`, see `worker.go`) that
  long-polls `PollEvents` (`client.go`, `POST /jobs/claim`), invokes
  `claude -p` per job, and only treats a job as done once
  `GET /jobs/{id}` confirms the same attempt is terminal
  (`ErrAgentDidNotCompleteJob` guards the "model exited without calling
  `complete_agent_job`" case). The 11-tool restricted MCP surface is defined
  once in `internal/agentworker/mcpserver.go`
  (`get_event`, `get_conversation_context`, `get_recruiter_profile`,
  `get_lead`, `get_policy`, `propose_reply`, `save_job_lead`,
  `request_owner_approval`, `send_owner_summary`, `pause_autopilot`,
  `complete_agent_job`). Every tool proxies 1:1 onto `/api/agent/v1` via the
  `agentAPI` interface — there is no shell, filesystem, or generic-HTTP tool
  registered, by construction (nothing else is ever added to the server).
  `JobContext` (job_id/attempt/event_id/conversation_id) is populated from
  the worker's own claim, never from a model-supplied argument — the doc
  comment on `JobContext` explicitly frames this as "server derives it,
  caller can't override," the same shape `getLead()`'s doc comment and
  `pauseAutopilot()`'s doc comment independently re-derive for their own
  tools. `toolBuilder.guarded()` serializes all state-changing tool calls
  behind one mutex per job and refuses any call after `complete_agent_job`
  succeeds.
- **Runtime image split.** `Dockerfile.agent-worker` builds a dedicated
  `node:22-slim`-based image (pinned `CLAUDE_CODE_NPM_VERSION=2.1.220`)
  separate from the Go-only main `mctl-telegram` server image, specifically
  because the worker needs the `claude` CLI and the main image deliberately
  doesn't carry it.
- **Deployment/observability.** C1 (staging validation of Part 1) is
  deployed to the existing `labs` namespace as `mctl-telegram-preview` /
  `agent-worker-preview`, per `docs/plans/communication-agent.md` and
  `docs/reports/communication-agent-c1.md`. As of the 2026-07-31 entry in
  that report, every item on C1's own checklist is closed: the 30-fixture
  real-Claude-Code evaluation passed 30/30, the live Saved-Messages approve
  cycle and kill-switch-after-approval drill both passed live, approval
  codes are hashed/encrypted, and the worker runs against its own dedicated
  OAuth quota domain isolated from interactive sessions and
  `claude-review.yml`. C2 (production promotion) remains separately gated
  (tracked as issue #347) and is unrelated to this proposal.
- **What does not exist.** `cmd/agent-channel` and `internal/agentchannel`
  do not exist anywhere in this clone — confirmed by search; the only
  references to either name are inside `docs/plans/communication-agent.md`
  itself. There is no Channels-mode code in `mctl-telegram` today. (The
  corresponding `mctl-claude-remote` PTY/communication-agent-mode work and
  the `mctl-gitops` preview deployment live in their own repos, which are
  outside this clone's scope — this proposal only covers the mctl-telegram
  side, Workstream T, and describes T/R/G's relationship for context.)

## Proposed solution

Do not implement anything now. The proposed "solution" for this proposal is
the spec itself: a faithful, code-grounded restatement of the plan's
already-detailed Part 2 design (sections 2.1-2.15), scoped so a future Tier
2 implementer can build it directly from `tasks.md` once an operator
explicitly re-authorizes it, without having to re-derive intent from the
80KB plan doc under time pressure.

If and when authorized, the architecture is exactly what section 2.5-2.8 of
the plan already specifies, and this proposal does not deviate from it:

```
labs namespace (existing)
├── mctl-telegram-preview          (existing, C1 baseline — unchanged)
│   └── agent_jobs queue / Agent API / policy / executor (all unchanged)
│
├── communication-agent-preview    (new — Workstream G)
│   ├── mctl-claude-remote container, CLAUDE_RUNTIME_MODE=communication-agent
│   │   ├── persistent Claude CLI under a PTY (Workstream R)
│   │   ├── exact-match development-warning driver (R3, fail-closed)
│   │   └── separate Claude credentials/state (own PVC or MinIO prefix)
│   ├── init container: copies mctl-telegram-agent-channel binary in (R6.1)
│   └── cmd/agent-channel stdio MCP subprocess (Workstream T, mctl-telegram)
│       └── same 11 restricted Agent API tools as agent-worker, shared code
│
└── claude-remote                  (existing PR steward — unchanged, isolated)
```

Key design decisions this proposal carries forward from the plan, with the
mctl-telegram-side reasoning grounded in code already read:

1. **`cmd/agent-channel` must reuse, not duplicate, `internal/agentworker`'s
   tool definitions and client (T1).** The tool list, `JobContext` pinning
   pattern, `guarded()` serialization, and redacting logging in
   `internal/agentworker/mcpserver.go` already encode every safety
   invariant Channels needs (no model-suppliable job identity, no
   free-text `note` field bypassing encryption, pause-only
   `pause_autopilot`, exact-once `complete_agent_job`). The concrete
   refactor: extract the `agentAPI` interface, the tool builders, and
   `Client` (`internal/agentworker/client.go`) into a shape both
   `cmd/agent-worker` and `cmd/agent-channel` import, so there is never a
   second hand-maintained copy of the 11 tool schemas that can silently
   drift from the server-side contract in `internal/agentapi`.
2. **Recovery is queue-durability-based, not in-process (T3).** Because
   `ClaimAgentJobs`/`RequeueStaleAgentJobs` (`internal/agent/queue`) and the
   attempt-fencing already used by Option C's completion check
   (`GET /jobs/{id}`, `internal/agentworker/worker.go`'s terminal-status
   check) are transport-agnostic, `cmd/agent-channel` gets crash safety for
   free by following the same protocol: claim -> notify -> tool calls ->
   durable write -> `complete(attempt=N)` -> clear local active-job slot.
   Never mark complete from in-memory state before the server confirms it.
3. **The channel notification is a wake-up, not an acknowledgement (T3).**
   This is the one genuinely new correctness property Channels introduces
   that Option C's per-process-per-job model didn't need: because
   `cmd/agent-channel` is a persistent subprocess that could, in principle,
   hold one job across multiple Claude turns/notifications, every tool
   handler must re-validate "is this the currently active job+attempt"
   before touching durable state — the same fencing idea as
   `toolBuilder.guarded()`, extended to survive redelivery.
4. **Separate deployment, separate credentials, always (2.5).** Reusing
   `claude-remote`'s (PR-steward) session/workspace/credentials is
   explicitly prohibited — untrusted Telegram content must never enter the
   same context as GitHub/Kubernetes-scoped tooling. This mirrors why
   `Dockerfile.agent-worker` is already a separate image from the main
   server image in this repo: different credentials, different failure
   blast radius, independent scale-to-zero.
5. **Everything stays behind explicit kill switches and operator gates.**
   `AGENT_KILL_SWITCH`, `replicaCount: 0`, and the eight operator decision
   gates in plan 2.14 are the actual safety mechanism, not a policy
   statement — e.g. the executor's existing re-check of the kill switch
   immediately before every send RPC (Part 1, already implemented) applies
   unconditionally to whichever transport proposed the reply, so Channels
   inherits that protection automatically rather than needing its own copy.

## Alternatives

1. **Skip the spec, close the issue as unnecessary.** Rejected: the issue
   is deliberately kept open as a tracked, explicit placeholder — closing it
   would discard a design that took real investigation (the 2.1.220
   Pro-account Channels/`-p` verification work in section 2.3) and make a
   future re-visit start from zero. Writing the spec now (without
   implementing it) preserves that investigation as an actionable artifact
   without violating the "do not pick up" instruction.
2. **Treat C1's now-fully-closed checklist as authorization to start
   Workstream T/R/G immediately.** Rejected per the issue text itself: "C1
   being further along" is a floor Part 2 shouldn't outpace, not a trigger
   that authorizes it. The issue separately and explicitly requires
   re-affirming scope with the operator regardless of C1's state before any
   PR is opened. Proceeding on C1's completion alone would be inferring
   authorization the issue explicitly says not to infer.
3. **Design a different Channels architecture than the one already in the
   plan (e.g. skip the PTY driver, use Team/Enterprise `allowedChannelPlugins`
   from day one, or drop Option A entirely in favor of a hybrid B).**
   Rejected: the plan's section 2.3-2.4 already reflects concrete, dated
   verification work (Claude Code 2.1.220, Pro-account, no-org) establishing
   that `-p`/stream-json never register a Channels listener regardless of
   org tier, and that Option A-Team only removes a confirmation dialog, not
   the core architecture. Re-deriving this from scratch without repeating
   that verification would be strictly worse than restating the
   already-verified design; changing course purely on that history would
   need a fresh verification pass, not a fresh design.

## Platform impact

- **Migrations.** None from this proposal itself (no code changes). If
  Workstream T is later implemented, it introduces no new DB schema — it
  reuses `agent_jobs`/`agent_job_attempts`/`agent_actions`/`job_leads`
  exactly as Option C does; no migration is anticipated in the plan.
- **Backward compatibility.** Zero risk from this proposal: it is
  documentation only, written to a proposals directory outside the
  mctl-telegram repo. If later implemented, Workstream T/R/G are each
  designed to be independently reversible (plan 2.12) and the production
  `tg.mctl.ai` values file and Option C path are explicitly untouched (G1).
- **Resource impact.** None from this proposal. A future
  `communication-agent-preview` deployment would need its own compute
  (persistent Claude CLI process), its own Claude credentials/state storage
  (dedicated PVC or MinIO prefix, decision deferred per G4), and would run
  entirely within the existing `labs` namespace's already-allowed egress —
  no new namespace, no new egress policy, at preview scope.
- **Risks + mitigations (from the plan, restated for this proposal's
  scope):**
  - *Risk: an automated pipeline picks this up and opens implementation
    PRs.* Mitigation: this proposal's own acceptance criteria (see
    `requirements.md`) make operator re-affirmation a hard precondition,
    matching the issue body verbatim; `tasks.md`'s first task is that
    re-affirmation checkpoint, not code.
  - *Risk: Channels-specific PTY/session state becomes a second,
    inconsistent source of truth about job identity.* Mitigation: T3's
    "notification is a wake-up, not an acknowledgement" rule plus reuse of
    the existing queue/attempt-fencing primitives (§ Proposed solution,
    point 2-3) — already proven correct for Option C.
  - *Risk: Telegram-sourced content reaches the PR-steward's credentials or
    vice versa.* Mitigation: hard separation (point 4 above), independently
    verifiable by checking `communication-agent-preview`'s GitOps values
    have no GitHub App secret, no Kubernetes RBAC, no shared workspace.
  - *Risk: quota/version drift between when this proposal was written and
    whenever it's implemented.* Mitigation: `tasks.md` task 1 requires
    re-verifying the Claude Code 2.1.220 Channels/`-p` facts against
    whatever version is current before any other work starts (plan R1).
