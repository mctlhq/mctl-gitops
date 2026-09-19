# Design: incident-89820765

## Diagnosis
The Tier-2 implementer workflow (mctl-agents-implement-1318e8f2) ran against proposal
mctl-telegram/proposals/issue-510-add-self-identification-tool-get-my-iden. Both the
primary and the account-2 fallback Claude Code sessions completed successfully
(ResultMessage subtype=success, is_error=False, stop_reason=end_turn) and independently
verified that the requested `get_my_identity` MCP tool already exists in the
mctl-telegram repo, fully implemented and tested on main (HEAD `0896685`). Because the
implementer correctly declined to duplicate existing work, there was nothing to commit
("nothing to commit, working tree clean"). The workflow's `assert-attempt` step treats
"no diff produced" as an unconditional failure for every attempt — it does not
distinguish a genuine implementer failure (crash, API error, timeout) from a correct
no-op outcome (stale proposal already satisfied upstream). The assert step's own
boilerplate message ("Most often the Claude five_hour/seven_day usage limit / HTTP 429
on both accounts, or token-2 unset") is generic and misleading here — both attempts
succeeded at the API level; the actual reason is a stale/duplicate proposal.

Note: incident argo-mctl-agents-implement-c36902fb-1789820445 (proposal
.github/issue-67-feat-roadmap-control-plane-reconcile-epi) failed for the identical
reason in the same time window — the implementer found `roadmap/scripts/reconcile.py`
already exists with the requested functionality in mctlhq/.github. This looks like a
systemic classification gap in the implementer/assert-attempt path, not a one-off.

## Proposed Fix
In the mctl-agents implementer wrapper / Argo `assert-attempt` step (repository:
mctlhq/mctl-agents — exact file not confirmed from this vantage point, since this
responder only has read access to mctl-gitops, not mctl-agents source):
1. Have the implementer wrapper detect and surface a distinct "stale proposal / already
   implemented, no changes needed" outcome (e.g. a marker in its result JSON or a
   dedicated exit code) separate from a hard failure.
2. Update `assert-attempt` (or the step preceding it) to treat that outcome as
   non-fatal: skip the "produced a diff" assertion and instead write the proposal's
   `.status.yaml` with `status: rejected` (or a new `status: superseded`) and a `notes`
   field quoting the implementer's stale-proposal finding.
3. Only fall through to the current hard-failure / needs-triage path when neither
   attempt reports success at all (crash, non-zero exit without a "success"
   ResultMessage, or an actual API error).

## Scope
Minimal: change only the outcome classification in the implement-proposals Argo
workflow / implementer wrapper so a correctly-identified stale proposal no longer
surfaces as a workflow failure incident. Do not change retry/fallback account logic,
which is unrelated to this failure.

## Confidence: LOW
Root cause (stale proposal treated as hard failure) is well evidenced by the two
implementer run logs. The exact file/line to patch in mctl-agents is not confirmed —
this responder does not have source access to that repository. The implementer should
locate the `assert-attempt` / result-classification logic in mctl-agents before
applying a fix.
