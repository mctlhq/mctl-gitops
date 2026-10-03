# Distinguish a quota-exhausted implementer run from "produced no commits"

## Context

`orchestrator/run_implementer.py` performs no rate-limit detection. When the
Claude Agent SDK returns a terminal `ResultMessage` with `is_error=True` and
`api_error_status=429` — the shape emitted when the run's OAuth account has
already exhausted its `five_hour` / `seven_day` window — the implementer never
looks at it. Control falls through to the `_has_new_commits()` check at
`orchestrator/run_implementer.py:1437`, which is false because the agent never
got a turn, and the proposal is written to `.status.yaml` as
`status: needs-triage`, `failure.code: no-commits`,
`failure.message: "implementer produced no commits"`. That is the exact record
an agent gets when it ran successfully and decided nothing needed changing, or
when it simply failed the task. Triage and the Tier 3 shepherd then chase an
agent that "did nothing" instead of a credential that could not be used, and
the proposal is parked in `needs-triage`, which no path retries automatically
(`README.md:139-145`).

The sibling agent already gets this right:
`orchestrator/run_issue_investigator.py:1296-1310` inspects the terminal
`ResultMessage`, raises `RateLimitExhaustedError`, and deliberately keeps that
outcome off the generic agent/tooling failure path
(`run_issue_investigator.py:1239-1250`, `1869-1876`), with tests at
`tests/test_run_issue_investigator.py:418-449` pinning both the positive case
and the "a different `api_error_status` is NOT a rate limit" case. This
proposal closes the gap between the two implementations, records the durable
evidence at the time it is observed (the Argo Workflow object and its pods are
gone within the hour under `ttlStrategy.secondsAfterFailure: 3600`, so nothing
can be recovered afterwards), and makes the condition reach a signal the
workflow layer can act on instead of prose that guesses at the cause.

## User stories

- AS an operator triaging `needs-triage` proposals I WANT a quota-exhausted run
  recorded as a distinct, self-describing cause SO THAT I do not investigate an
  agent that never received a turn.
- AS an operator responsible for the pipeline's redundancy I WANT the account
  identity and the quota reset time written into `.status.yaml` at the moment
  of failure SO THAT I can tell that a fallback OAuth leg is inert for the next
  three days without reading an archived pod log.
- AS the Tier 3 shepherd I WANT a rate-limited `--review-feedback` run reported
  with its own exit code SO THAT it is treated as transient and does not
  consume one of the proposal's bounded review attempts.
- AS the owner of the `cwft-mctl-agents-implement` workflow template I WANT the
  implementer to exit with a code and a stable stderr line that name the
  condition SO THAT `assert-attempt` can stop printing an identical guess for
  every possible failure (the template-side change itself is tracked in
  mctl-gitops#1206).
- AS a proposal author I WANT a proposal that only failed because of quota to
  stay in the queue SO THAT it runs again on its own once the window resets,
  without an operator manually moving it back to `accepted`.

## Acceptance criteria (EARS)

- WHEN the implementer's SDK message stream ends with a `ResultMessage` whose
  `is_error` is true AND whose `api_error_status` is 429 THE SYSTEM SHALL raise
  a dedicated `RateLimitExhaustedError` from `_run_implementer_agent` instead of
  returning normally.
- WHEN the implementer observes a `RateLimitEvent` whose
  `rate_limit_info.status` is `"rejected"` during the stream THE SYSTEM SHALL
  retain `rate_limit_type`, `resets_at` and `overage_disabled_reason` from that
  event for use in the durable record.
- IF the stream ends with a `ResultMessage` whose `is_error` is true AND whose
  `api_error_status` is any value other than 429 THEN THE SYSTEM SHALL leave
  today's behaviour unchanged (no rate-limit classification).
- WHEN `implement_one()` catches `RateLimitExhaustedError` THE SYSTEM SHALL
  write `.status.yaml` with `status: accepted`, remove the in-flight `attempt`
  lease, and record a top-level `rate_limited` block containing at least
  `code: rate-limited`, `account`, `rate_limit_type`, `resets_at`,
  `observed_at` and `message`.
- WHEN `implement_one()` catches `RateLimitExhaustedError` THE SYSTEM SHALL NOT
  write `status: needs-triage` and SHALL NOT write
  `failure.code: no-commits` for that attempt.
- WHILE a proposal carries a `rate_limited` block THE SYSTEM SHALL clear that
  block on the next transition that already clears `failure` (the
  `implemented` / `merged` / `rejected` / `in-progress` writes in
  `implement_one`).
- IF the `rate_limited` block that would be written is byte-identical in
  `code`, `account`, `rate_limit_type` and `resets_at` to the one already on
  disk THEN THE SYSTEM SHALL leave `since`/first-seen intact so a repeated
  observation does not produce one GitOps commit per tick.
- WHEN a result is classified as rate-limited THE SYSTEM SHALL set
  `ImplementResult.counts_toward_limit` to false SO THAT the attempt is never
  counted against `--max-proposals`, matching the investigator's contract.
- WHEN a batch produces a rate-limited result THE SYSTEM SHALL stop processing
  further proposals in that run, because an exhausted account is
  workflow-global rather than proposal-specific.
- WHEN a batch run ends with at least one rate-limited result and no successful
  implementation THE SYSTEM SHALL exit with the dedicated non-zero exit code
  `EXIT_RATE_LIMITED` and SHALL print one stable, greppable stderr line naming
  the account, the limit type and the reset time.
- WHILE `--review-feedback` mode is active THE SYSTEM SHALL classify a
  429-terminated run as rate-limited, return `EXIT_RATE_LIMITED` from
  `_review_feedback_exit_code()`, and SHALL NOT modify `.status.yaml` (the
  shepherd owns status in that mode).
- WHEN the shepherd's `apply_followup()` observes `EXIT_RATE_LIMITED` from the
  implementer subprocess THE SYSTEM SHALL treat the failure as transient and
  SHALL NOT consume a `review_attempts` slot.
- IF a proposal's recorded `rate_limited.resets_at` lies in the future AND its
  recorded `account` equals the account label of the current run THEN THE
  SYSTEM SHALL skip the model call for that proposal, report it as skipped with
  `counts_toward_limit` false, and SHALL NOT rewrite `.status.yaml`.
- IF the account label of the current run cannot be determined THEN THE SYSTEM
  SHALL record `account: unknown` and SHALL still run the proposal (fail open).
- WHILE recording a rate-limit event THE SYSTEM SHALL NOT write any credential
  value, token prefix or token suffix into `.status.yaml` or any log line.
- WHEN the rate-limit classifier module is imported by the long-lived Temporal
  worker's import graph THE SYSTEM SHALL NOT import `claude_agent_sdk` at
  module scope, so `tests/test_worker_isolation.py` keeps passing.

## Out of scope

- Any change to `cwft-mctl-agents-implement.yaml` / `cwft-mctl-agents-approve.yaml`,
  including the `assert-attempt` message and the `implement-fallback` `when`
  gate. Those live in `mctl-gitops` and are tracked by mctl-gitops#1206; this
  proposal only produces the exit code and stderr line they will key on.
- New Prometheus alerts or recording rules (`MctlAgentClaudeUsageLimit`,
  `MctlAgentsPipelineStale`). A short-lived Argo pod has no scrape target and
  the platform has no pushgateway; the alert belongs with the CWFT work.
- In-process credential rotation. `orchestrator/auth.py:84
  rotate_to_secondary_auth()` exists with no caller; wiring it into the
  implementer would double a single run's quota burn and duplicate the CWFT's
  own fallback leg.
- Rate-limit handling for `run_service_agent.py`, `run_mentor.py`,
  `run_shepherd.py` and `run_incident_responder.py`. The shared helper this
  proposal introduces makes those a one-line adoption each, but they are not
  changed here.
- Recovering or pushing work an agent committed locally before the 429; a
  partially completed implementation is still discarded with the temp clone.

## Open questions

- How the account label reaches the pod. The repo has no env var naming the
  OAuth account: `orchestrator/auth.py` only distinguishes
  `CLAUDE_CODE_OAUTH_TOKEN` from `CLAUDE_CODE_OAUTH_TOKEN_SECONDARY`, and the
  CWFT fallback leg injects token-2 under the primary variable name, so the
  variable name alone cannot tell account 1 from account 2. This proposal reads
  an optional, non-secret `CLAUDE_OAUTH_ACCOUNT` label (matching the `_2`
  suffix convention already used in `.github/workflows/claude-review.yml:44`),
  falls back to deriving `primary`/`secondary` from the active variable name,
  and records `unknown` otherwise. Setting that label on the fallback leg is a
  one-line `mctl-gitops` change and should be folded into mctl-gitops#1206.
- Whether the "skip while the recorded window is still open" guard should ship
  in the same change or behind a follow-up. It is the only part that changes
  which proposals run, and it is only as good as the account label. It is
  specified here as fail-open (never skip when the label is `unknown`), and is
  split into its own task so it can be dropped without touching the rest.
- Whether `resets_at` should also be surfaced on the issue or PR as a comment.
  The issue does not ask for it and it would spend GitHub API calls on a
  self-healing condition; not proposed.

Proceeding with the interpretation above; nothing here blocks implementation.
