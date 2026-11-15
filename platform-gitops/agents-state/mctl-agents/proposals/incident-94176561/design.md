# Design: incident-94176561

## Confidence: LOW

## Diagnosis
The implement workflow did not fail from a platform defect. The implementer refused to run because the proposal mctl-telegram/issue-1250-test-finance-l2-c-agent-api-isolation-re was marked accepted without a verifiable approval grant (execution-authorization: "approved with no verifiable approval grant", exit 45, outcome blocked). This is a deliberate safety gate working as intended, most likely triggered by a hand-edited or non-grant-backed .status.yaml flip. Secondary noise: the evidence post was refused (evidence_execution_ref_invalid, a consequence of there being no execution/approval ref), the run token exchange returned 403, and the account-2 fallback token (claude-code-oauth-token-2) is unset so no fallback was possible. The log tail confirms the failure is the authorization block, not a code or Helm defect. No service logs were available (admins/mctl-agents is not a deployed service).

## Proposed Fix
Do NOT weaken, bypass or auto-grant the execution-authorization check. No code or values change is justified by the evidence. Recommended actions are operational and belong to a human admin: approve the proposal through the proper grant path (mctl_approve_dev_loop or mctl_trigger_approve with the content digest), and optionally configure the fallback token secret claude-code-oauth-token-2. The only repo-level change worth considering is a clearer needs-triage note on that proposal's .status.yaml, if the implementer deems it useful.

## Scope
Minimal. Verification only; touch nothing that alters authorization behavior.
