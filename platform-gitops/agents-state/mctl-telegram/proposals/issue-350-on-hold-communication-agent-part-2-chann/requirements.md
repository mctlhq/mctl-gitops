# Communication Agent Part 2 — Channels Preview (`communication-agent-preview`)

## Context

Issue #350 tracks Part 2 of `docs/plans/communication-agent.md` (sections
2.1-2.15): an experimental, feature-flagged preview that would let the
communication agent run through Claude Code's Channels feature — a
persistent interactive CLI session under a PTY, driven via
`mctl-claude-remote` — as an alternative transport to the headless
`claude -p` worker (`cmd/agent-worker`, "Option C") that already ships as
production for the communication agent (Part 1).

The issue is explicitly deferred and marked "do not pick up via any
automated pipeline." It is not a bug and not scoped, prioritized work — it
is a placeholder tracking a design that already exists in full detail in the
plan document but has zero lines of implementation in this repo (`grep` for
`cmd/agent-channel` or `internal/agentchannel` in `mctl-telegram` returns
nothing outside the plan doc itself). The 2026-07-25 transport decision
recorded in the plan is unambiguous: Option C is production, Channels is not
a dependency of it, and there is no current product need pulling Part 2
forward. Since that decision, C1 (Part 1's staging validation) has continued
to mature — as of the 2026-07-31 entry in
`docs/reports/communication-agent-c1.md`, every item on C1's own remaining
checklist is now checked off (30/30-fixture gate, live approve cycle,
kill-switch-after-approval drill, `random_id` retry drill, encrypted
approval codes/profiles, dedicated worker OAuth quota domain). C1 being
further along changes nothing about whether Part 2 should be picked up —
the issue is explicit that Part 2 has "no reason to move faster than C1's
own maturity," not that C1 finishing is a green light for Part 2.

This proposal exists to give a future Tier 2 implementer a spec-driven,
code-grounded starting point *if and when* an operator explicitly
re-authorizes Part 2 — not to authorize starting Workstream T/R/G now.

## User stories

- AS an mctl-telegram maintainer I WANT the Channels preview scoped as an
  isolated, reversible, feature-flagged deployment SO THAT experimenting
  with it can never regress or gate the production Option C transport.
- AS an operator I WANT every step that changes blast radius (scaling the
  preview above zero, disabling its kill switch, approving a real reply,
  expanding beyond one conversation) to require my explicit sign-off SO
  THAT an automated pipeline cannot silently escalate an experimental
  feature into something touching real user data.
- AS a security reviewer I WANT the Channels preview's Claude session to see
  only the same 11 restricted Agent API tools Option C already exposes, with
  no shell/filesystem/generic-HTTP/GitHub/Kubernetes/MTProto access SO THAT
  untrusted Telegram content reaching a persistent session cannot escalate
  beyond what the existing policy/executor layer already allows.
- AS a Tier 2 implementer picking this up later I WANT the shared Agent API
  client/tool surface (`internal/agentworker`) reused rather than
  reimplemented for Channels SO THAT there is never a second,
  independently-maintained list of the 11 tools that can drift from the
  server-side contract.
- AS the mctl-telegram on-call I WANT the preview's crash/recovery semantics
  to be provably equivalent in safety to Option C's (durable claim,
  visibility-timeout requeue, fenced attempt, idempotent `random_id` send)
  SO THAT a Claude/PTY-specific failure mode cannot lose a job or duplicate
  a Telegram send.

## Acceptance criteria (EARS)

- IF this proposal is picked up by any automated pipeline (mctl-agents,
  pr-steward, or similar) without a preceding explicit operator
  re-affirmation THEN THE SYSTEM SHALL refuse to open any implementation PR
  for Workstream T, R, or G.
- WHEN an operator re-affirms scope THE SYSTEM SHALL still require going
  through PR sequence order 2.12 of the plan (R0 docs -> T1 shared-tool
  refactor -> T2 `cmd/agent-channel` -> R1 runtime mode/PTY driver -> G1
  disabled GitOps manifest -> G2 first replica) as independently reversible
  PRs, never combined into one review unit.
- WHEN `cmd/agent-channel` is implemented THE SYSTEM SHALL expose exactly
  the same restricted tool set as `internal/agentworker.NewMCPServer`
  (`get_event`, `get_conversation_context`, `get_recruiter_profile`,
  `get_lead`, `get_policy`, `propose_reply`, `save_job_lead`,
  `request_owner_approval`, `send_owner_summary`, `pause_autopilot`,
  `complete_agent_job`) via the shared client/tool definitions, not a second
  independently maintained list.
- WHEN `cmd/agent-channel` has no active job THE SYSTEM SHALL reject every
  tool call.
- WHEN `cmd/agent-channel` claims a job THE SYSTEM SHALL bind every
  subsequent tool call to that job's `job_id + attempt + conversation_id`
  pinned server-side (never as a model-suppliable argument), matching
  `JobContext`'s existing pinning pattern in `internal/agentworker/mcpserver.go`.
- WHEN a crash occurs between claim and notification, between notification
  and the first tool call, or between a durable action write and
  `complete_agent_job` THE SYSTEM SHALL leave the job to the existing
  visibility-timeout requeue rather than mark it complete from in-process
  state, and a new claim SHALL receive a higher/current attempt that fences
  out any stale write from the old process.
- WHEN `complete_agent_job` is called for an attempt that is no longer the
  active claim THE SYSTEM SHALL reject it (conflict/not-found), mirroring
  Option C's atomic exact-result completion linkage
  (`internal/agentapi`/PR #316's `GET /jobs/{id}` postcondition check).
- WHILE the communication-agent-preview deployment exists THE SYSTEM SHALL
  keep it fully isolated from the production `tg.mctl.ai` deployment and
  from the existing `claude-remote` PR-steward session — separate
  credentials, separate Claude state/HOME, no shared workspace, no GitHub
  App secret, no Kubernetes RBAC, no ingress, no public Service.
- WHILE `communication-agent-preview` is at `replicaCount: 0` or
  `AGENT_KILL_SWITCH=true` THE SYSTEM SHALL guarantee no Telegram send can
  originate from this transport (same server-side kill-switch re-check the
  executor already performs immediately before every send RPC).
- IF the PTY development-warning prompt text, heading, or channel name shown
  by the Claude CLI does not exactly match what Workstream R's driver
  expects THEN THE SYSTEM SHALL fail closed (nonzero exit, no keystroke
  sent) rather than blindly accept or pipe input.
- IF an operator has not explicitly approved one of the eight Decision
  Gates listed in plan section 2.14 (PVC vs MinIO state, scaling 0->1,
  `claude auth login` in the new state volume, flipping
  `AGENT_KILL_SWITCH` off, approving the first real test reply, expanding
  beyond one allowlisted conversation, moving out of `labs`, promoting past
  experimental status) THEN THE SYSTEM SHALL NOT perform that action
  autonomously.
- WHEN comparing Option A (Channels) against Option C on the same fixture
  set THE SYSTEM SHALL run them against partitioned/non-overlapping queues
  or accounts, never let both claim from the same live queue unpartitioned.

## Out of scope

- Actually starting Workstream T (`cmd/agent-channel`), Workstream R
  (`mctl-claude-remote` communication-agent mode), or Workstream G
  (`communication-agent-preview` GitOps deployment) — this proposal is a
  spec artifact only, per the issue's explicit "do not pick up" status.
- Any change to the production `mctl-telegram` deployment, the production
  `tg.mctl.ai` values file
  (`platform-gitops/services/labs/mctl-telegram/values.yaml`), or Option C
  (`cmd/agent-worker`), which remains the sole production transport.
- Guarded autopilot or any auto-send capability for the Channels preview —
  Part 2's definition of done never includes promotion past experimental/
  observe.
- A dedicated `comms` tenant namespace or FQDN-filtered egress — deferred to
  C2 per Part 1, not part of this preview.
- Team/Enterprise `allowedChannelPlugins` packaging (Option A-Team) —
  optional future hardening, not required for the Pro-tier preview.
- Any decision on whether Channels is ultimately kept, dropped, or promoted
  — that is Phase 4's explicit decision gate, not something this proposal
  can or should predetermine.

## Open questions

- Whether the 2026-07-25 transport-decision facts (Claude Code 2.1.220,
  Pro account, no Team/Enterprise org: `-p` and stream-json never register a
  Channels listener) still hold at whatever Claude Code version is current
  when this is eventually picked up. Plan section 2.7/R1 already requires
  re-verifying this against the pinned image before proceeding — treat that
  re-verification as a hard blocking first step, not optional.
- Whether C1's now-complete checklist (as of 2026-07-31) changes the
  operator's appetite for re-scoping Part 2, given the issue frames C1
  maturity as a floor, not a trigger. Resolution: do not infer authorization
  from C1's completion; wait for an explicit operator statement, as the
  issue requires.
- Whether `mctl-claude-remote`'s current image pin (`2.1.198` per the plan)
  should move to `2.1.220` as part of R1, or whether the preview should
  stay pinned and document why. The plan defers this decision to whoever
  implements Workstream R; this proposal does not resolve it.
- Whether Claude state storage for the preview should use a dedicated PVC or
  a dedicated MinIO prefix (G4) — the plan requires checking current `labs`
  PVC quota/usage at implementation time, which is out of this proposal's
  read-only investigation scope.
- Exact current image tag / GitOps quota state at pickup time — the plan's
  own instructions (2.13) require confirming these live rather than trusting
  any value recorded here or in the plan doc, since both drift over time.
