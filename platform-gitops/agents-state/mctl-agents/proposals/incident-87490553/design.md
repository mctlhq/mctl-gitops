# Design: incident-87490553

## Diagnosis
The shepherd workflow's post-deploy-verify step is checking for ArgoCD applications that become Degraded after the workflow merges changes. When the labs-mctl-telegram application was detected as Degraded, the verification step waited 120 seconds to see if it would recover (rolling-update grace period), but the application remained unhealthy. This caused the verification to fail, which failed the entire shepherd workflow.

The root cause is either: (1) the grace period is too short for applications with slow startup times or more complex deployments, or (2) there is an actual underlying issue with the labs-mctl-telegram deployment that needs investigation. The current implementation has no retry mechanism; it fails after a single 120-second window.

## Proposed Fix
Increase the grace period for post-deploy-verify from 120 seconds to 240 seconds, and add retry logic that allows one additional wait cycle if the application remains Degraded. This accommodates slower deployments while still detecting persistent failures.

File: `platform-gitops/orchestrator/src/shepherd/post_deploy_verify.py` (or equivalent post-deploy-verify implementation)
Change: Increase `DEGRADED_STATE_GRACE_PERIOD_SECONDS` from 120 to 240
Add: Retry loop that permits up to 2 checks with the extended grace period

## Scope
Minimal. Only modify the grace period and add basic retry logic in the post-deploy-verify step. Do not change alert thresholds, exclusion lists, or other verification logic.

## Confidence: LOW
The logs do not reveal why labs-mctl-telegram became Degraded. If it was a real deployment issue (not a transient startup delay), increasing the grace period alone will not fix the underlying problem. Recommendation: after applying this change, monitor the next shepherd run and inspect the labs-mctl-telegram deployment logs if it remains Degraded. If the issue is persistent, a separate incident should be filed specifically for the mctl-telegram service health.
