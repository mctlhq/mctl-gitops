# Design: issue-334-c2-gate-isolate-production-communication

## Current state

**Worker invocation and credential path.** `cmd/agent-worker/main.go`'s
`run()` long-polls `/api/agent/v1/jobs/claim` and, per job, calls
`agentworker.ClaudeInvoker.Run` (`internal/agentworker/claudeinvoker.go`).
`Run` shells out to the `claude` binary (`exec.CommandContext`) with
`cmd.Env = minimalEnv()`. `minimalEnv()` forwards only `HOME`, `PATH`,
`USER`, proxy vars, and *any* environment variable prefixed `CLAUDE_` or
`ANTHROPIC_` from the worker process's own environment — i.e. whatever
credential material (OAuth token file under `HOME`, or an
`ANTHROPIC_API_KEY`-style env var) is present in the pod is what
authenticates every `claude -p` call. Nothing in this path currently
labels, measures, or asserts which billing/quota domain that credential
belongs to.

**Existing isolation is credential-storage isolation, not quota-domain
isolation.** `docs/runbook.md`'s "Credential rotation" section already
requires a "dedicated credential volume/secret" per worker deployment and
says "Never reuse the PR-review credential pool" — but this is a
convention recorded in a runbook, not something the code verifies. The
canonical plan (`docs/plans/communication-agent.md`, Transport decision
section) documents the actual failure mode this issue is closing: the
worker's `claude -p` credential shared the same interactive-OAuth pool as
`claude-review.yml`'s PR review jobs, that pool exhausted under ordinary
review-comment traffic (see the plan's closed-incident Appendix), and nothing
detected or alerted on it as a distinct condition — it looked like generic
job failure until someone read GitHub Action logs.

**Cost is parsed but discarded.** `internal/agentworker/worker.go` defines
`ClaudeResult` with `TotalCostUSD float64 \`json:"total_cost_usd"\`` (line
177) and `ParseClaudeResult` extracts it from the CLI's `--output-format
json` result object. `ClaudeInvoker.Run` calls `CheckResult(res)` (which
only inspects `IsError`) and then verifies job completion via the API — the
parsed `TotalCostUSD` value is never recorded, logged as a metric, or used
anywhere. There is no `mctl_agent_*` cost or budget metric today:
`internal/metrics/metrics.go` defines exactly two agent-domain metrics,
`AgentDeadLetterTotal` and `AgentActionsExecutingStuck` (plus job-transition
counters and approval latency), none of them cost- or quota-related. There
is also no way, today, to distinguish "the model hit the CLI's own
`--max-budget-usd` per-job cap" from "the underlying Anthropic
account/credential itself hit its usage limit" — both currently surface as
an opaque `is_error: true`/nonzero-exit failure that `worker.Loop` logs and
retries like any other job failure.

**Alerting today.** `deploy/alerts/mctl-telegram.rules.yaml` has exactly two
agent alerts: `MctlAgentDeadLetter` (`increase(mctl_agent_dead_letter_total[15m])
> 0`, warning) and one on `mctl_agent_actions_executing_stuck` (critical).
Neither distinguishes a quota-domain exhaustion from any other repeated job
failure, so today's runbook response to a quota outage ("close unexplained
test traffic, inspect job/attempt metadata, fix the cause") gives the
on-call no signal that the actual cause is credential-domain exhaustion.

**Deployment image and secret boundary.** `Dockerfile.agent-worker` builds a
dedicated image (`node:22-slim` + pinned `@anthropic-ai/claude-code` + the Go
binary) specifically so the main `mctl-telegram` server image never needs
Claude CLI credentials at all (`docs/agent-worker.md`, "Deployment note").
The actual Kubernetes Secret/Vault mount that supplies the worker's Claude
credential lives in `mctl-gitops` (`platform-gitops/services/labs/
communication-agent-worker-preview/values.yaml` per `docs/agent-worker.md`),
which is out of this repository's tree — this repo can only make the
credential's *identity* (not its value) observable and make the worker's
behavior around quota exhaustion distinct and alertable.

**Rollout gate already named, not yet satisfied.**
`docs/plans/communication-agent.md`'s Rollout gates section (item 2) already
lists "Production quota domain provisioned and in use (separate from
interactive Claude Code + `claude-review.yml` pool)" as a hard prerequisite
before guarded autopilot, and `docs/reports/communication-agent-c1.md`'s
remaining checklist has an open item: "Provision a production quota domain
isolated from interactive sessions and `claude-review.yml` before C2" and
"create the separate C2 quota-domain gate issue" (this issue, #334). This
proposal is that gate's implementation plan.

## Proposed solution

Two things change: (1) the credential domain and its consumption become
observable and alertable from inside `mctl-telegram`, and (2) a C2-specific
evidence report and go/no-go check formalize the drills the issue requires.
Actual provisioning of the new billing/quota domain and its Vault/Kubernetes
plumbing happens in `mctl-gitops` and the provider's own console — this repo
cannot create an Anthropic org/account or a Vault path, but it can require
and verify that one is in use before allowing C2 to proceed.

**1. Non-secret credential-domain identity (`cmd/agent-worker`,
`internal/metrics`).** Add an `AGENT_CREDENTIAL_DOMAIN_ID` environment
variable to `cmd/agent-worker/main.go`'s `run()`, read the same way
`AGENT_API_BASE_URL`/`AGENT_API_TOKEN` are read today (`requireEnv`/
`os.Getenv`). Its value is a short human-assigned label (e.g.
`comms-worker-prod-2026`), never a credential — analogous to a Prometheus
"info" metric pattern. Expose it as a new `AgentWorkerCredentialDomainInfo`
`GaugeVec` (label `credential_domain`, value always `1`) registered in
`internal/metrics/metrics.go` next to the existing `AgentJobsTotal`/
`AgentDeadLetterTotal` definitions, and include it in the worker's
`/livez`/`/healthz` JSON body (`cmd/agent-worker/health_server.go`) so both
Prometheus and a human `curl` against the running pod can confirm which
domain is configured — this directly satisfies the "C1/C2 evidence records
the credential domain (non-secret identifier)" criterion without relying on
someone remembering to copy it into a report by hand. Treat the variable as
required once `AGENT_ENABLED=true` in any non-dark deployment; missing it
is a startup failure, matching the existing fail-fast pattern for
`AGENT_API_BASE_URL`/`AGENT_API_TOKEN`.

**2. Per-job cost telemetry (`internal/agentworker`, `internal/metrics`).**
Add `AgentWorkerJobCostUSD` (a `prometheus.Histogram` or `CounterVec`
accumulating `TotalCostUSD`, labeled by `credential_domain`) to
`internal/metrics/metrics.go`. Thread the registry (or a narrow recorder
interface) into `ClaudeInvoker` the same way the invoker already holds
`APIBaseURL`/`APIToken`, and record `res.TotalCostUSD` immediately after
`ParseClaudeResult` succeeds in `Run` (`internal/agentworker/claudeinvoker.go`,
right after line 182), before the `CheckResult`/completion-verification
steps — cost is incurred whether or not the job's result was ultimately
valid, so it must be recorded on every parsed result, not only successful
ones. This is additive: `TotalCostUSD` is already being parsed, this only
stops discarding it. It gives an operator a local, drill-testable
approximation of spend against the *worker's own* domain, as a
defense-in-depth signal alongside the provider's own budget/rate-limit
alerts (which remain the authoritative source — see Alternatives).

**3. Distinguish quota/usage-limit failures from generic job failures
(`internal/agentworker/worker.go`).** `CheckResult` currently returns
`ErrClaudeReportedError` uniformly for any `is_error: true` result. Add a
narrower check — matched against the CLI's documented usage-limit error
shape referenced in the plan's Appendix (`"You've hit your org's monthly
usage limit"` and equivalent CLI-reported quota/rate-limit conditions) —
that returns a distinguishable `ErrAgentCredentialQuotaExhausted` wrapping
`ErrClaudeReportedError`, and increment a new
`AgentWorkerQuotaExhaustedTotal` `CounterVec` (labeled `credential_domain`)
when it fires. `worker.Loop`'s existing failure-logging path
(`internal/agentworker/worker.go`) already distinguishes failure causes for
logging; this only adds one more case, it does not change control flow —
the job still fails/retries/dead-letters through the existing queue
machinery (`internal/db` visibility timeout, `RetryAgentJob` backoff).

**4. Alert rules (`deploy/alerts/mctl-telegram.rules.yaml`).** Add
`MctlAgentWorkerQuotaExhausted`
(`increase(mctl_agent_worker_quota_exhausted_total[15m]) > 0`, critical) —
mirroring the existing `MctlAgentDeadLetter` rule's structure — so quota
exhaustion pages distinctly instead of blending into the generic
dead-letter alert. Document it in `docs/runbook.md`'s "Agent alert
response" subsection alongside `MctlAgentDeadLetter` and
`MctlAgentActionsExecutingStuck`, with a response procedure: check
`mctl_agent_worker_credential_domain` to confirm which domain is affected,
confirm interactive Claude Code / `claude-review.yml` are unaffected (proof
of isolation), and escalate to the provisioned domain's own console/billing
alert rather than treating it as a code bug. The provider-side monthly
budget and rate-limit alerts themselves (the issue's actual "budget/alerts
tested" requirement) are configured in the Anthropic account/console for
the new domain — out of this repo's tree, tracked as a coordination task in
tasks.md — but this repo's alert is what proves the *consequence* of
hitting them is visible and distinguishable in `mctl-telegram`'s existing
on-call surface.

**5. C2 evidence report (`docs/reports/communication-agent-c2.md`, new).**
Mirror the structure of `docs/reports/communication-agent-c1.md` (Scope and
acceptance / Evidence / Remaining checklist) but scoped to exactly this
issue's acceptance criteria: the credential domain's non-secret identifier,
a description of its budget/rate-limit controls and a link/reference to the
tested-alert evidence (not the credential or console screenshots
themselves), the rotation/revocation drill result, and the controlled
worker-invocation-during-outage drill result. End with an explicit
`Go/no-go: <go|no-go>, referencing issue #334` line — this is the "explicit
go/no-go check" the acceptance criteria require, in reviewable-document
form (see Alternatives for why not a cross-repo CI check). Update
`docs/plans/communication-agent.md`'s Rollout gates item 2 to link this new
report instead of only asserting the prerequisite in prose, and update
`docs/reports/communication-agent-c1.md`'s remaining checklist to point to
it once filed (this is a doc-linking change in an existing file, not
new C1 scope).

**6. Rotation/revocation drill (`docs/runbook.md`).** Extend the existing
"Credential rotation" subsection's Claude-credential bullet into a full
domain-aware procedure: scale worker to zero, revoke at the provisioned
domain's own console (not by deleting a Kubernetes Secret alone, since that
only stops new pod use, matching the same stateless-JWT caveat already
documented for the Agent API token), replace the Vault-sourced
credential/secret, start one replica, verify the *old* credential now fails
authentication, and verify `mctl_agent_worker_credential_domain` reports the
new label. Record one exercised run of this procedure (not just the
written steps) in the new C2 report.

## Alternatives

- **Re-implement budget/rate-limit enforcement inside `mctl-telegram`
  itself** (e.g., track cumulative spend in Postgres and block further
  `claude -p` calls past a threshold). Rejected as the primary mechanism:
  the issue asks for "its own budget, rate limits, and alerts" at the
  *credential domain* level, which is a provider/account-level control —
  duplicating it in application code would drift from the authoritative
  source and give false confidence if the two ever disagree. The local
  cost histogram (item 2 above) is kept only as an observability
  supplement, not a replacement, for the provider's own limits. The
  existing per-job `AGENT_MAX_BUDGET_USD` (`ClaudeInvoker.MaxBudgetUSD`)
  already covers the one thing that *does* belong in this codebase — a
  single job cannot itself blow the whole budget — and is left unchanged.
- **Build a fully automated cross-repo CI gate in `mctl-gitops`'s
  release-please/deploy workflow that blocks promotion unless the C2
  report says "go."** More robust long-term, but this repository's clone
  has no visibility into `mctl-gitops`'s workflow files, and the plan's own
  precedent (Workstream C in `docs/plans/communication-agent.md`) treats
  `mctl-gitops` changes as a separate, human-reviewed track ("Never
  auto-merge `mctl-gitops`"). Scoped out of this proposal's mctl-telegram
  deliverables; recorded as a follow-up coordination task instead of a
  code change here.
- **Detect quota exhaustion purely by CLI exit code / generic `is_error`
  without adding a distinguishing metric.** Simpler, but this is exactly
  the status quo that let the original incident (Appendix, "closed
  2026-07-22") look like an ordinary job failure until someone manually read
  Action logs — the entire point of this issue is to make quota-domain
  exhaustion a first-class, alertable signal distinct from "a job had a
  bug." Rejected as insufficient for the acceptance criteria's alerting
  requirement.

## Platform impact

- **Migrations**: none. No schema changes; all additions are new
  Prometheus metrics, one new required env var for the worker deployment,
  a new alert rule, and new/updated documentation.
- **Backward compatibility**: `AGENT_CREDENTIAL_DOMAIN_ID` is a new
  required-when-enabled env var for `cmd/agent-worker` — any existing
  worker Deployment values (C1 preview included) must set it before
  upgrading past this change, or the worker fails fast at startup (same
  pattern as a missing `AGENT_API_TOKEN` today). This is a deliberate
  fail-closed choice: silently defaulting the label would defeat the "C1/C2
  evidence records the credential domain" requirement. Document the
  required values-file change in tasks.md so the `mctl-gitops` side isn't
  surprised by a rollout that otherwise looks like an ordinary image bump.
- **Resource impact**: negligible — a few counters/gauges/a histogram, no
  new goroutines, no new network calls, no new storage.
- **Risks + mitigations**:
  - *Risk*: teams read "quota domain isolated" as done once the new
    Secret exists, without ever exercising the outage drill. Mitigated by
    making the C2 report's go/no-go line require a recorded drill result,
    not just a provisioned credential.
  - *Risk*: the new required env var makes an operator's manual `kubectl`
    patch or ad hoc redeploy fail unexpectedly. Mitigated by documenting it
    in `docs/agent-worker.md`'s configuration table (same table
    `AGENT_API_BASE_URL` etc. are already documented in) and in the
    `mctl-gitops` values-file coordination task.
  - *Risk*: the local cost histogram double-counts or under-counts spend
    relative to the provider's real invoice (e.g. retried jobs, partial
    turns). Mitigated by treating it explicitly as a secondary/defense-in-depth
    signal in both the code comments and the runbook, never the number used
    to reconcile a bill.
  - *Risk*: the quota-exhausted error-string match in `CheckResult` is
    provider-CLI-version-dependent and could silently stop matching after a
    `claude-code` npm bump in `Dockerfile.agent-worker`. Mitigated by unit
    tests (tasks.md) asserting the match against the exact fixture string
    already recorded in the plan's Appendix, and a code comment pointing at
    that Appendix so a future CLI-version bump prompts someone to re-check
    it, the same way `Dockerfile.agent-worker`'s pinned
    `CLAUDE_CODE_NPM_VERSION` already forces deliberate version bumps.
