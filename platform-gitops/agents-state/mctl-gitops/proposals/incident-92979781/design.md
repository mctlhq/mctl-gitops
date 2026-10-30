# Design: incident-92979781

## Confidence: LOW

## Diagnosis
The implement workflow for proposal issue-2103-feat-gitops-code-scanning-webhook-endpoi failed after about 2 minutes. The implementer log shows the primary Claude account was rate-limited (the rate-limit info seen in the log reported five_hour utilization near 3 percent and seven_day near 32 percent at the end, so the limit appears transient) and the implementer exited 1. No fallback token (claude-code-oauth-token-2) is configured, so no fallback ran. The workflow then moved the proposal to needs-triage via a status commit. This is a transient quota failure, not a defect in the proposal content. The exact limit cause could not be fully confirmed because the implementer log is very large and was only searched, not read in full.

## Proposed Fix
1. In platform-gitops/agents-state/mctl-gitops/proposals/issue-2103-feat-gitops-code-scanning-webhook-endpoi/.status.yaml, verify status is needs-triage with a rate-limit reason, and only then set status back to accepted so the implementer retries once.
2. Do not change the proposal content files.
3. Optional, out of scope for this change: note that the fallback token claude-code-oauth-token-2 is unset in Vault; do not touch secrets.

## Scope
Minimal. Only the single .status.yaml of the named proposal. If the status is not needs-triage caused by rate limiting, make no change.
