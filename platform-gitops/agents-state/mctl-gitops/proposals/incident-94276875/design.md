# Design: incident-94276875

## Diagnosis
The implement workflow mctl-agents-implement-4497d763 failed because the primary implementer attempt failed and no fallback ran: the run-implementer step reported that the fallback token (claude-code-oauth-token-2) is not set, and the assert step reports both attempts Failed. The assert step names the most common cause as a Claude usage limit (HTTP 429). The full log of the primary attempt (about 93 KB) was too large to read in this run, so the exact primary failure reason was not confirmed. The commit-and-push step then wrote a needs-triage status for the proposal. The workflow service is not a running tenant service, so no service logs were available. The incident fingerprint refers to mctl-telegram while the incident service is mctl-agents; the proposal is the one for issue-1274. No incident text asked for any change.

## Proposed Fix
1. Verify that the secret claude-code-oauth-token-2 is provisioned (Vault path and ExternalSecret) and referenced by the mctl-agents implement workflow template in mctl-gitops. If missing, add the ExternalSecret mapping for it. Do not write any secret value.
2. If the primary failure was a usage limit, no code change is needed: move the .status.yaml of proposal issue-1274-feat-glovo-g3-link-only-handoff-provider under agents-state/mctl-telegram/proposals/ from needs-triage back to accepted so the implementer retries once quota is available.

## Confidence: LOW
The primary attempt's root cause was not read. Verify in the workflow archive (step run-implementer-3856527496) before applying.

## Scope
Minimal. Only the fallback token wiring and/or the single status field of the one proposal.
