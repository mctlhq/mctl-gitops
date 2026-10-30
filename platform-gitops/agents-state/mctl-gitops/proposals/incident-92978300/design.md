# Design: incident-92978300

## Confidence: LOW

## Diagnosis
The implement workflow for proposal issue-778-feat-agents-securityfinding-remediation (service mctl-agents) failed after about 160 seconds. The primary implementer attempt exited 1 with "implementer produced no commits". The fallback could not run because the secret claude-code-oauth-token-2 is not set, so the workflow had no second account to fall back to. The logged rate-limit event reported status 'allowed' for the five_hour window, so a usage-limit cause is not confirmed; the primary failure reason is unclear from the available logs. The proposal's .status.yaml was projected to needs-triage by the failed run, and automatic retry does not happen.

## Proposed Fix
1. Verify whether Vault/ExternalSecret provisioning of claude-code-oauth-token-2 exists for the mctl-agents implement workflow in mctl-gitops. If the key or its ExternalSecret mapping is missing, add it so the fallback path can work (do not write any secret value into git).
2. Move the proposal issue-778-feat-agents-securityfinding-remediation under platform-gitops/agents-state/mctl-agents/proposals/ from needs-triage back to accepted so the implementer retries once. Only do this after step 1 is checked.

The implementer must verify the actual primary failure cause (the run-implementer-690537798 step log of workflow mctl-agents-implement-0101fd24) before applying anything.

## Scope
Minimal. Only the fallback token reference and the single proposal status.
