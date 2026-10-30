# Design: incident-92775228

## Confidence: LOW

## Diagnosis
The shepherd workflow failed after about 507 seconds and its post-deploy-verify step flagged argocd/labs-mctl-telegram. No skill matched and the workflow step logs were not examined by this responder. Current labs/mctl-telegram logs show the service healthy on 0.90.0 with a passing canary, with only a transient shared-pg-rw "connection refused" on first DB connect during rollout. Note the incident's own fingerprint names mctl-agents while the flagged app is labs-mctl-telegram, and a near-identical failure (incident 92775878) hit 10 minutes later with the same flagged app, so a recurring post-deploy-verify problem against labs-mctl-telegram is plausible. This is a hypothesis, not an observed fact.

## Proposed Fix
No change is justified yet. The implementer should read the archived step logs of workflow mctl-agents-shepherd-05d7208e (post-deploy-verify) and the sibling workflow mctl-agents-shepherd-467f8fe7, and decide jointly with proposal incident-92775878 (which carries the same likely fix, so do not make the change twice). If both point to a verify timeout shorter than rollout plus DB reconnect time, raise that timeout minimally in one place. If the app is healthy and the cause is a one-off, make no change.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
