# Design: incident-89820445

## Diagnosis
The Tier-2 implementer workflow (mctl-agents-implement-c36902fb) ran against proposal
.github/issue-67-feat-roadmap-control-plane-reconcile-epi. The fallback Claude Code
session completed successfully (ResultMessage subtype=success, is_error=False,
stop_reason=end_turn) and found that the proposed roadmap-control-plane reconcile
functionality already exists in mctlhq/.github: `roadmap/scripts/reconcile.py` already
implements the desired/observed graph diff, the required diagnostic classes,
deterministic output, exit codes, and CLI flags the proposal asked for. As with
incident argo-mctl-agents-implement-1318e8f2-1789820765 (proposal mctl-telegram/issue-510,
same time window), the implementer correctly produced no diff because the work is
already done, but the `assert-attempt` step treats "no diff" as an unconditional
failure regardless of why, so the workflow failed and generated this incident. A
Claude seven-day rate-limit utilization of 0.76 ("allowed_warning") appears in the log
but is a warning, not a block — it did not cause the run to fail (the ResultMessage
confirms the turn completed normally); it should not be read as the root cause here
even though the generic assert-attempt failure message suggests rate limiting as the
likely cause.

## Proposed Fix
Same underlying issue as incident-89820765 (the mctl-agents implementer wrapper /
`assert-attempt` step in mctlhq/mctl-agents does not distinguish "correct no-op
because the proposal is already satisfied upstream" from "implementer genuinely
failed to make progress"). See the design.md of
platform-gitops/agents-state/mctl-agents/proposals/incident-89820765 for the
recommended classification fix; apply the same change here. No .github-specific code
change is required — the reconcile functionality already exists and is out of scope.

## Scope
Minimal: same classification fix as incident-89820765, applied once in the shared
implementer/assert-attempt path — not a per-proposal fix.

## Confidence: LOW
Root cause is well evidenced (implementer explicitly reports the feature already
exists, and the ResultMessage shows a successful, non-erroring turn). The exact
file/line to patch in mctl-agents is not confirmed — this responder has no source
access to that repository.
