# C2 production-quota-domain gate for autopilot mode

## Context

C1 (draft-and-approve mode, `db.AgentModeObserve`) is live and has completed
one full live Saved Messages approval round trip (see
`docs/reports/communication-agent-c1.md`, 2026-07-26). C2 is the promotion of
`db.AgentModeGuarded` ("guarded autopilot" in `docs/plans/communication-agent.md`)
to real production traffic: the server-side policy engine
(`internal/agent/policy/policy.go`) is allowed to auto-send allowlisted
discovery-intent replies without an owner approving each one. That removes
the human checkpoint that currently bounds the blast radius of a bad model
output or a runaway conversation loop.

The canonical plan already lists "production quota domain provisioned" as a
blocking rollout gate before guarded autopilot (`docs/plans/communication-agent.md`,
"Rollout gates" item 2), and the C1 report tracks it as a separate item
(`docs/reports/communication-agent-c1.md`, "Remaining checklist": *"Provision
a production quota domain isolated from interactive sessions and
claude-review.yml before C2"*, cross-referenced from issue #334). This issue
(#347) is the design/implementation ticket for that gate itself: a scoped,
auditable spend/rate ceiling that sits in mctl-telegram, in addition to (not
instead of) whatever org-wide Agent SDK spend cap mctl-agents enforces
upstream, so that C2 traffic cannot silently exhaust a shared pool other
services depend on, and so that an anomaly (repeated denials, a runaway
send loop, a cost spike) can shut C2 down automatically, not just manually.

## User stories

- AS a platform operator I WANT a per-account and per-conversation send-rate
  ceiling (messages/hour, messages/day) enforced server-side SO THAT a
  looping or compromised conversation cannot flood a peer or burn quota
  before a human notices.
- AS an on-call engineer I WANT a kill switch that can trip itself
  automatically on anomaly detection (repeated policy-denied attempts,
  abnormal send velocity, cost-ceiling breach) SO THAT C2 traffic stops
  within one detection cycle without waiting for a person to be paged and to
  act.
- AS a platform operator I WANT C2 spend tracked and capped against its own
  ceiling, separate from the org-wide Agent SDK credit pool SO THAT a
  runaway communication-agent account cannot starve unrelated services
  (`claude-review.yml`, interactive sessions) that share the same upstream
  pool.
- AS an on-call engineer I WANT an AlertManager warning when any C2 ceiling
  is approached (not only when breached) SO THAT there is time to intervene
  before the hard gate denies traffic.
- AS a platform operator I WANT `autopilot_paused` to default to `true` for
  every new account and C2 opt-in to be an explicit, audited, per-account
  action SO THAT no account can end up in autopilot by a global flag flip,
  a missed default, or an unreviewed profile edit.
- AS a compliance/audit reviewer I WANT every C2 opt-in and every automatic
  or manual kill-switch trip recorded with actor, reason, and timestamp SO
  THAT the safety history of guarded autopilot is reconstructable after the
  fact.

## Acceptance criteria (EARS)

- WHEN an account's rolling per-account send count exceeds its configured
  hourly ceiling THE SYSTEM SHALL deny further autonomous sends for that
  account until the rolling window admits capacity again.
- WHEN an account's rolling per-account send count exceeds its configured
  daily ceiling THE SYSTEM SHALL deny further autonomous sends for that
  account until the rolling window admits capacity again.
- WHEN a conversation's rolling send count exceeds its per-conversation
  ceiling (extending the existing `MaxMsgsPerMinute`/`ReserveAgentActionSend`
  window mechanism to hour/day windows) THE SYSTEM SHALL deny further
  autonomous sends for that conversation until the window admits capacity
  again.
- WHEN the number of policy-denied autonomous-send attempts for an account
  within a short rolling window exceeds a configured anomaly threshold THE
  SYSTEM SHALL automatically trip the C2 kill switch for that account.
- WHEN the observed send velocity for an account exceeds a configured
  anomaly multiple of its steady-state rate ceiling THE SYSTEM SHALL
  automatically trip the C2 kill switch for that account.
- WHEN an account's rolling C2-scoped spend exceeds its configured cost
  ceiling THE SYSTEM SHALL automatically trip the C2 kill switch for that
  account and deny further autonomous sends.
- WHILE the C2 kill switch is tripped for an account THE SYSTEM SHALL deny
  every autonomous (non-owner-approved) send for that account, independent
  of `AGENT_KILL_SWITCH`, `agent_profiles.mode`, and
  `agent_profiles.autopilot_paused`.
- IF an operator manually clears a tripped C2 kill switch THEN THE SYSTEM
  SHALL require an explicit, audited admin action naming the account and
  SHALL record actor, timestamp, and the original trip reason in the audit
  log.
- WHEN any per-account or per-conversation rate ceiling, or the cost
  ceiling, is approached (a configured warning threshold, e.g. 80%) THE
  SYSTEM SHALL emit an alert through the existing AlertManager path
  (`deploy/alerts/mctl-telegram.rules.yaml` conventions) distinct from the
  breach alert.
- WHEN any per-account or per-conversation rate ceiling, or the cost
  ceiling, is breached THE SYSTEM SHALL emit a higher-severity AlertManager
  alert distinct from the approach-warning alert.
- WHEN a new `agent_profiles` row is created THE SYSTEM SHALL set
  `autopilot_paused = true` regardless of any other field supplied (this is
  already `EnsureAgentProfile`'s behavior in `internal/db/agent_domain.go`
  and MUST NOT regress).
- IF an admin request would result in `mode = guarded` AND
  `autopilot_paused = false` for an account simultaneously (i.e. the
  transition into live C2 traffic) THEN THE SYSTEM SHALL treat that request
  as a distinct, explicitly named C2-opt-in action, require non-default rate
  and cost ceilings to already be configured for that account, and record a
  dedicated audit entry (actor, account, ceilings in effect, timestamp)
  separate from routine profile field edits.
- IF the C2-scoped cost ceiling or rate ceilings are unset (zero/default) for
  an account THEN THE SYSTEM SHALL refuse to transition that account into
  the C2-opt-in state described above.
- WHILE `AGENT_KILL_SWITCH=true` THE SYSTEM SHALL continue to deny all
  agent actions exactly as today, unaffected by whether the new C2 kill
  switch is tripped or clear (the two gates are independent and both must be
  open for a send to proceed).

## Out of scope

- Re-designing C1's approval flow, policy engine core (`policy.Evaluate`),
  executor crash-recovery, or approval-code invariants — those are done and
  stable (per the issue's own non-goals).
- Implementing or changing the org-wide Agent SDK spend cap itself (that
  lives in mctl-agents); this proposal only adds a scoped ceiling
  in mctl-telegram that sits alongside it.
- A full anomaly-detection/ML system. "Anomaly detection" here means simple,
  auditable threshold rules (denial rate, send velocity, cost rate) — the
  same class of check `policy.Evaluate` already applies for
  `MaxMsgsPerMinute`, not a new statistical subsystem.
- Building a fourth `agent_profiles.mode` value. "C2 autopilot mode" is
  guarded mode (`db.AgentModeGuarded`) promoted to production; this proposal
  gates that promotion, it does not add a new mode.
- Real production namespace/network isolation (`tenants/comms`,
  FQDN-filtered egress) — tracked separately in the canonical plan's C2
  section as a namespace/network concern, not a spend/rate gate concern.
- The `random_id` MTProto-dedup drill and the remaining kill-switch-after-
  approval live drill — separate rollout-gate items already tracked in
  `docs/reports/communication-agent-c1.md`.

## Open questions

- Exact numeric defaults for hourly/daily/cost ceilings and the anomaly
  thresholds (denial-rate window size, velocity multiple, warning-threshold
  percentage) are not specified in the issue. Interpretation: ship
  conservative, explicit, non-zero defaults (see design.md) that an operator
  must deliberately raise per account, mirroring the existing
  `MaxMsgsPerMinute` default-of-2 pattern; do not block design on picking
  the "correct" numbers, since the schema and enforcement points are the
  architectural decision here, not the constants.
- Whether the cost ceiling should be enforced pre-flight (deny a job claim
  before `claude -p` runs) or only post-hoc (block future jobs once observed
  spend crosses the ceiling), given `total_cost_usd` is only known after a
  job completes (`internal/agentworker/worker.go`). Interpretation: enforce
  post-hoc against a rolling window (same pattern as the rate ceilings) plus
  keep the existing per-job `--max-budget-usd` hard cap
  (`internal/agentworker/claudeinvoker.go`) as the pre-flight backstop on any
  single job's worst case; a true pre-flight aggregate check is not possible
  without knowing a job's cost before it runs.
- Whether the C2 kill switch is per-account only or also supports a
  cross-account "pause all C2 traffic" switch. Interpretation: per-account is
  the required primitive (matches `autopilot_paused`'s existing scope and
  the issue's "per-account and/or per-conversation" framing); a global C2
  pause is achievable today via `AGENT_KILL_SWITCH` and is out of scope to
  duplicate.
- Whether alert "approach" thresholds should be configurable per account or
  a single global percentage. Interpretation: a single global percentage
  (env-configured, like other `AGENT_*` settings in
  `internal/config/config.go`) is enough for the first version; per-account
  overrides can follow if operational experience shows it's needed.
