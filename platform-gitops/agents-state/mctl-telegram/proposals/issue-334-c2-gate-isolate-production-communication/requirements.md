# C2 gate: isolate production communication-agent quota domain

## Context

The Option C headless worker (`cmd/agent-worker`) drives the communication
agent by shelling out to `claude -p` for every claimed job
(`internal/agentworker.ClaudeInvoker.Run`). Today that invocation
authenticates through whatever `CLAUDE_*`/`ANTHROPIC_*` credential material
is present in the worker pod's environment/HOME (see `minimalEnv()` in
`internal/agentworker/claudeinvoker.go`), and `docs/plans/communication-agent.md`
records that this credential pool was, at least once, the same shared
interactive/`claude-review.yml` pool: a documented incident (the plan's
"Appendix — claude-review.yml cost investigation") shows that pool being
exhausted by ordinary review/session activity and blocking both PR review
and agent work. Admin-merging around a failed review check is called out
explicitly, in both the issue and the plan, as not an acceptable production
mitigation — it hides a capacity problem instead of fixing it.

The plan already names a "production quota domain" as an explicit go/no-go
prerequisite for C2 (production promotion, guarded autopilot), but as of
this writing that prerequisite is not implemented: the worker has a
dedicated Kubernetes Secret/credential volume (per
`docs/runbook.md`'s "Credential rotation" section: "Never reuse the
PR-review credential pool"), but nothing in the codebase verifies, measures,
or alerts on that separation, no per-job cost telemetry exists
(`internal/agentworker/worker.go`'s `ClaudeResult.TotalCostUSD` is parsed
but never recorded anywhere), and no drill has exercised "the worker keeps
working while the interactive/review pool is unavailable." This issue turns
that prerequisite into a concrete, evidenced, testable gate before C2 can
close.

## User stories

- AS an on-call operator I WANT the communication-agent worker's Claude
  credential to draw from a billing/quota domain that is provisioned and
  monitored independently of interactive Claude Code sessions and
  `claude-review.yml` SO THAT exhausting one pool never blocks the other,
  and I can tell which pool is degraded from an alert alone.
- AS a platform engineer I WANT the worker credential to exist only in
  Vault and be mounted only into the worker pod SO THAT no other service,
  human session, or CI job can consume its quota or leak it.
- AS a release approver I WANT an explicit go/no-go check that references
  this issue SO THAT production promotion cannot happen while the quota
  domain, its budget controls, or its rotation procedure are unverified.
- AS an incident responder I WANT a documented, previously-exercised
  revocation/rotation procedure for the worker credential SO THAT a
  suspected leak can be contained without guessing under pressure.

## Acceptance criteria (EARS)

- WHEN the worker pod starts THE SYSTEM SHALL expose a non-secret
  identifier for the Claude credential domain it is configured to use (an
  account/org alias or metered-key label, never the credential itself).
- WHEN a `claude -p` job invocation completes THE SYSTEM SHALL record its
  reported `total_cost_usd` against a per-credential-domain metric so
  cumulative spend is observable without depending solely on the upstream
  provider's own billing dashboard.
- WHEN a `claude -p` invocation fails with a quota/usage-limit-shaped error
  THE SYSTEM SHALL count and surface that failure distinctly from other
  job failures (not as an undifferentiated dead-letter) so an operator can
  tell "our quota domain is exhausted" apart from "a job is broken."
- IF the worker credential's monthly budget or rate-limit alert thresholds
  fire THEN THE SYSTEM SHALL page/ticket through the existing
  `mctl-telegram` alert routing, not silently degrade.
- WHILE the interactive Claude Code / `claude-review.yml` credential pool
  is exhausted or independently rate-limited THE SYSTEM SHALL continue to
  let the worker successfully claim and complete a job using its own
  quota domain (verified by a controlled drill, not assumed from
  configuration alone).
- WHEN the worker credential is rotated or revoked THE SYSTEM SHALL
  continue operating (or fail closed, per the documented procedure)
  without the credential's plaintext value ever appearing in chat, shell
  history, commit history, or logs.
- IF any of the C2 prerequisites (dedicated domain in use, budget/alert
  tests, rotation drill, controlled-outage drill) is missing THEN THE
  SYSTEM SHALL keep C2/guarded-autopilot blocked — the existing
  `AGENT_ENABLED`/`AGENT_KILL_SWITCH`/`autopilot_paused`/worker-replica
  containment controls stay in their closed state.
- WHEN production promotion is proposed THE SYSTEM SHALL require an
  explicit go/no-go check that names issue #334 and records the evidence
  above before the change is allowed to proceed.

## Out of scope

- Enabling Channels, opening a Telegram test window, or moving
  `mode` out of `observe` / lifting `autopilot_paused` — unrelated to
  quota-domain isolation and explicitly excluded by the issue's
  non-goals.
- Re-implementing Anthropic's (or any provider's) own billing/budget/alert
  system. This proposal adds local, defense-in-depth cost/error telemetry
  in `mctl-telegram`; the authoritative budget ceiling, rate limits, and
  alerting configuration live in the provisioned account/console itself.
- Actually creating the new org/account or metered API key, and the
  Vault/Kubernetes secret plumbing to mount it only into the worker pod —
  that provisioning and the `mctl-gitops` deployment wiring are
  operational/infrastructure actions outside this repository, tracked here
  as an explicit dependency (see design.md and tasks.md).
- A cross-repo automated CI gate in `mctl-gitops`'s promotion workflow.
  This proposal defines what the go/no-go check must verify; wiring it as
  an automated status check is a `mctl-gitops` workstream.
- Multi-tenant/multi-account quota routing beyond the single production
  communication-agent worker deployment.

## Open questions

- **Credential mechanism**: the issue allows either "a separate org/account
  or metered API credential." The worker's `minimalEnv()` passthrough
  already forwards any `ANTHROPIC_*`/`CLAUDE_*` environment variable
  verbatim, which makes a metered `ANTHROPIC_API_KEY`-style credential the
  lower-friction option (no interactive OAuth re-login flow in a headless
  pod). Proceeding on the assumption that a metered API credential is
  acceptable unless platform/finance ops decide a fully separate org login
  is required; either choice is compatible with the design below since
  both are opaque credential material to the worker.
- **Exact budget/rate-limit thresholds**: the issue requires budget and
  rate-limit alerts to be "tested," not specific numbers. Proceeding with
  placeholder thresholds derived from the existing per-job
  `AGENT_MAX_BUDGET_USD` cap and expected C1/C2 job volume; final numbers
  need operator/finance sign-off and are recorded as configuration, not
  code.
- **Go/no-go check mechanism**: whether the "explicit go/no-go check" must
  be an automated CI status check in `mctl-gitops`'s release-please/deploy
  workflow, or a documented manual gate recorded in a C2 evidence report
  reviewed by a human before flipping production values. Proceeding with
  the manual-gate interpretation as the minimum viable implementation
  (a reviewable evidence document plus a required-reviewer checklist),
  with an automated cross-repo check noted as a follow-up, since building
  the latter is `mctl-gitops` work with no visibility into this repo's
  clone.
- **Drill fidelity**: "a controlled worker invocation succeeds while the
  interactive/review quota pool is unavailable or independently
  rate-limited" could be simulated (point the worker's Claude credential
  at a deliberately invalid/rate-limited *interactive* credential in a
  non-production check) or observed opportunistically during a real
  shared-pool exhaustion event. Proceeding with a simulated drill as the
  primary evidence path (repeatable, doesn't require waiting for an
  incident) with a note that a real-world observation, if one occurs
  first, also satisfies the criterion.
