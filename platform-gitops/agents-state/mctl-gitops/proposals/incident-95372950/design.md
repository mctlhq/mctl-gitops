# Design: incident-95372950

## Confidence: LOW

## Diagnosis
The investigate workflow for mctl-api issue 549 failed after about 566 seconds. The first run-investigator attempt produced a large log; the second attempt exited immediately because the fallback token claude-code-oauth-token-2 is not set, so there was no account to fall back to. assert-attempt reports both attempts Failed and names the likely cause as the Claude five_hour usage limit / HTTP 429, or an unset token-2. The Claude quota cause is transient and cannot be fixed by a config change. The log tails read were short, so the primary failure reason was not directly confirmed. A side effect was observed: commit-and-push still pushed a partial staging directory (proposals/.staging-kptjmuhc under mctl-api) to main even though the run failed. That directory should not be treated as a valid proposal.

## Proposed Fix
1. Verify (read-only) that the secret key claude-code-oauth-token-2 exists in the Vault/ExternalSecret mapping used by the mctl-agents-investigate workflow template in mctl-gitops. If the ExternalSecret mapping lacks this key, add the remote key reference. Do NOT write any secret value; if the Vault value itself is missing, record that as a manual operator follow-up in the PR description.
2. Check whether the stray directory platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc exists on main; if so, remove it (it is an incomplete artifact of a failed run).
3. Otherwise make no change; re-running the investigation for issue 549 after quota reset is the remedy.

## Scope
Minimal. Only the ExternalSecret key mapping for the fallback token and the stray staging directory. No change to workflow logic.
