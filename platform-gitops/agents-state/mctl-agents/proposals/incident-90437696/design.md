# Design: incident-90437696

## Confidence: LOW

## Diagnosis

The Argo Workflow `mctl-agents-implement-8aa4cbe4` (CWFT
`cwft-mctl-agents-implement`, admins tenant) ran the Tier 2 implementer against
an accepted proposal (`mctl-gitops/proposals/issue-1416-chore-cloudflare-iac-import-the-tg-seerr`)
and failed on both its primary attempt and its account-2 fallback attempt. The
`assert-attempt` step, which decides the workflow's terminal status, only knows
that both legs returned non-success; it cannot distinguish "Claude
five_hour/seven_day usage limit exhausted on both OAuth accounts (HTTP 429)"
from "the account-2 fallback token secret is unset" from any other implementer
failure, so it prints all three as one ambiguous guess. Because `analysis` on
the incident is empty, no `mctl-agent` skill matched, and the incident
escalated here.

This is not a new failure mode. `mctl-agents` issue #364 ("run-implementer
records a quota-exhausted run as `no-commits`/`needs-triage`") diagnosed the
same underlying gap in detail: `orchestrator/run_implementer.py` streams the
Claude Agent SDK's messages and discards the terminal `ResultMessage`,
including `api_error_status == 429` and any `RateLimitEvent`. Falling through
to the "did the agent commit anything" check produces the same durable record
for a blameless 429 as for a genuine no-op run. The sibling agent,
`orchestrator/run_issue_investigator.py`, already inspects this signal and
raises a dedicated `RateLimitExhaustedError` that its caller classifies
separately (see that file around the `ResultMessage`/`is_error`/
`api_error_status` check, and the `RateLimitExhaustedError` class it defines).

A full design for closing this gap already exists at
`platform-gitops/agents-state/mctl-agents/proposals/issue-364-run-implementer-records-a-quota-exhauste/design.md`
in this repo. Its `.status.yaml` shows `status: rejected` — PR
`https://github.com/mctlhq/mctl-agents/pull/409` was closed without merging on
2026-09-23. I cannot see why it was closed (no comment or reason is recorded in
`.status.yaml` beyond "PR was closed without merging"), and I have no read
access to the `mctl-agents` source tree from this responder to confirm whether
the referenced line numbers and surrounding contracts (exit codes, batch
accounting, the in-progress lease, worker-isolation test) still match current
`main`. That prior closure, combined with my inability to re-verify the source
against the existing design, is why this proposal is marked low confidence:
the implementer should re-check the current state of
`orchestrator/run_implementer.py` and `orchestrator/run_issue_investigator.py`
against the existing design before applying anything, and should look at why
PR #409 did not land (review comments, CI failure, or a change of direction)
rather than resubmitting it unchanged.

## Proposed Fix

Re-apply (after verifying against current `main`) the design already recorded
in `issue-364-run-implementer-records-a-quota-exhauste/design.md`:

1. Add an SDK-free `orchestrator/rate_limit.py` module exposing
   `RateLimitExhaustedError`, `RateLimitObservation`, `is_rate_limit_result()`,
   `observe_rate_limit_event()`, `account_label()`, `build_observation()`
   (duck-typed on `api_error_status` / `rate_limit_info`, so it never imports
   `claude_agent_sdk` and does not break `tests/test_worker_isolation.py`).
2. In `_run_implementer_agent`, raise `RateLimitExhaustedError` when the
   terminal `ResultMessage` has `is_error=True` and `api_error_status == 429`,
   the same condition `run_issue_investigator.py` already uses.
3. In `implement_one()`, add an `except RateLimitExhaustedError` branch (before
   the generic `Exception` branch, after `ImplementerOperationTimeout`) that
   writes `.status.yaml` with `status: accepted` (not `needs-triage`), clears
   the in-flight `attempt` lease, and records a `rate_limited` block
   (`code`, `account`, `rate_limit_type`, `resets_at`,
   `overage_disabled_reason`, `since`, `observed_at`, `message`) so the
   proposal is retried automatically once the window resets instead of sitting
   in a manually-gated `needs-triage` state.
4. Add a dedicated `EXIT_RATE_LIMITED` exit code and one stable stderr line
   naming the account and reset time, so the mctl-gitops CWFT's
   `assert-attempt` step (tracked separately as mctl-gitops#1206, out of scope
   here) can eventually key its message on a real signal instead of guessing
   between three causes.
5. Ensure a rate-limited result does not count against `--max-proposals` or
   the shepherd's `review_attempts` budget, matching the investigator's
   existing contract.

## Scope

Minimal and orchestrator-only: `orchestrator/rate_limit.py` (new),
`orchestrator/run_implementer.py` (new except branch, new exit code, batch
classification), and re-exporting `RateLimitExhaustedError` from
`orchestrator/run_issue_investigator.py` for backward compatibility. No change
to the mctl-gitops CWFT templates (`cwft-mctl-agents-implement.yaml`,
`cwft-mctl-agents-approve.yaml`) — that follow-up is out of scope and tracked
by mctl-gitops#1206. No change to `run_service_agent.py`, `run_mentor.py`,
`run_shepherd.py`, or `run_incident_responder.py`.
