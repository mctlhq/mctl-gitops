# Design: incident-94285749

## Diagnosis
The implement workflow for proposal issue-989-feat-glovo-m1b-2-single-authoritative-aa failed after about 150s. The primary attempt (account 1) failed; the fallback step reported that no claude-code-oauth-token-2 is configured, so no fallback ran. The primary log shows the seven_day usage window at 0.84 utilization with overage rejected (out_of_credits), but status was still allowed_warning, so quota exhaustion is plausible but not proven as the cause of the primary failure. The proposal's .status.yaml was pushed to main by the workflow (needs-triage projection). This is a workflow/quota/secret-wiring problem, not a defect in the Glovo proposal content. mctl-agent skills did not match (generic workflow_failed).

## Proposed Fix
1. Inspect the durable needs-triage reason in the issue-989 proposal .status.yaml to confirm the real primary failure.
2. If the cause is a transient usage limit: no code change; after the usage window resets, move that single proposal back to accepted so the implementer retries. Do not alter secrets from this proposal.
3. If the fallback secret is simply not referenced: check the mctl-agents implement CronWorkflowTemplate / ExternalSecret in mctl-gitops for the claude-code-oauth-token-2 reference and, only if the reference is missing from the manifest, add it (the Vault value itself must be supplied by an operator).

## Confidence: LOW
The primary failure reason was not directly visible (log was very large and only rate-limit metadata was found). Verify before applying; if nothing in the manifests is wrong, make no change.

## Scope
Minimal. Only the single secret reference or the single proposal status for issue-989. No unrelated changes.
