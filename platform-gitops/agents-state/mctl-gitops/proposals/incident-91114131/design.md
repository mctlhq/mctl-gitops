# Design: incident-91114131

## Confidence: LOW

## Diagnosis
The implement workflow mctl-agents-implement-e3b1c8f5 for proposal issue-561-scheduled-dispatch-converge-actions-gc-u failed because both the primary implementer attempt and the account-2 fallback attempt failed. The assert-attempt step names the usual cause as a Claude usage limit (HTTP 429) on both accounts, or an unset token-2. The step logs do not show the actual per-attempt error, so this is inferred rather than observed. The failure looks transient and not tied to any config rule. The commit-and-push step then pushed the needs-triage status update to mctl-gitops main. Separately, worker logs show the implement sweep quarantining 105 legacy auto-accepted proposals that carry no execution authorization, so a proposal written by this responder may also be quarantined until a human authorizes it.

## Proposed Fix
No Helm, rule or code change is justified by the evidence. Implementer should verify before acting:
1. Read the needs-triage reason in platform-gitops/agents-state/mctl-agents/proposals/issue-561-scheduled-dispatch-converge-actions-gc-u/.status.yaml.
2. If the reason is a usage limit / 429, take no code change; the proposal can be moved back to accepted once quota resets (operator-reviewed).
3. If the reason is that token-2 is unset, that is a Vault secret matter for a human; do not change secrets from this proposal.

## Scope
Minimal. Do not modify anything unless step 1 shows a concrete config defect.
