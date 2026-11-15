# Design: incident-94297793

## Confidence: LOW

## Diagnosis
The implement workflow for proposal mctl-api/issue-989-feat-glovo-m1b-2-single-authoritative-aa
did not fail because of a defect in a config or rule. The implementer's
execution-authorization gate refused the run: the proposal's .status.yaml says
`accepted`, but there is no verifiable approval grant behind it ("approved with
no verifiable approval grant"). This is the safety control working as intended.
Secondary observations: the run-token exchange was refused (HTTP 403
agent_run_exchange_refused), the evidence record was refused (HTTP 400
evidence_execution_ref_invalid), and the account-2 fallback token
(claude-code-oauth-token-2) is not set, so the fallback attempt could not run.
The generic skill did not match because this is a workflow_failed incident with no
mapped skill. The service logs tool could not be used (service admins/mctl-agents
not found as a tenant service); diagnosis relies on the Argo workflow logs.

## Proposed Fix
No automated change to bypass, weaken or relax the approval gate. Do not edit the
issue-989 proposal's .status.yaml to force acceptance. The correct remediation is
human action: approve the proposal through the DevLoop approve path
(mctl_approve_dev_loop) so a verifiable grant exists, then re-run the implementer.
Optional, separate follow-up for a human: set the fallback secret
claude-code-oauth-token-2 in Vault if a second-account fallback is wanted.

## Scope
Minimal. No file change is proposed. Implementer should verify and make no edits.
