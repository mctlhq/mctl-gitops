# Design: incident-92754275

## Confidence: LOW

## Diagnosis
The shepherd workflow mctl-agents-shepherd-05e64dbc did not fail in its own logic. Its commit-and-push step reported nothing to commit. The failure came from the post-deploy-verify step, which found argocd/labs-mctl-telegram newly Degraded after the merge and still Degraded after a 120s grace period. At 12:10 UTC the app was still Degraded with sync status Synced, image tag 0.88.3, and a database. So the root cause is in the labs/mctl-telegram deployment, and the shepherd workflow only reported it. No service logs were collected, so the Degraded reason (crash loop, failing probe, database or secret problem) is unknown.

## Proposed Fix
Inspect the Degraded resources of argocd/labs-mctl-telegram and its pod logs. Correct whichever configuration in platform-gitops/services/labs/mctl-telegram caused the Degraded state. If the cause is the image tag 0.88.3, roll back to the previous tag. If the cause is a code bug, open a separate issue against mctl-telegram. Do not change the shepherd workflow.

## Scope
Minimal. Fix only the telegram deployment configuration that is Degraded.
