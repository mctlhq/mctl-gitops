# Design: incident-92775878

## Confidence: LOW

## Diagnosis
The shepherd workflow failed after about 518 seconds and its post-deploy-verify step flagged argocd/labs-mctl-telegram. No skill matched the incident and the workflow step logs were not examined by this responder. Current labs/mctl-telegram logs show the service healthy on version 0.90.0 with a passing canary, and show only a transient shared-pg-rw "connection refused" on first DB connection attempt at rollout, recovered on the next attempt. The most likely explanation is that post-deploy-verify ran while the app was rolling out and the shared Postgres endpoint was briefly refusing connections, so the verify step timed out or saw an unhealthy app. This is a hypothesis, not an observed fact. The same failure signature appears in incident 92775228 (a second shepherd run flagged for the same app).

## Proposed Fix
No change is justified yet. The implementer should read the archived step logs of workflow mctl-agents-shepherd-467f8fe7 (post-deploy-verify step) to see why labs-mctl-telegram was flagged. If the cause is a verify timeout shorter than the rollout plus DB retry time, raise that timeout in the shepherd/post-deploy-verify configuration (mctl-gitops workflow template) by the minimum needed. If the app is healthy and the cause is a one-off, make no change.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
