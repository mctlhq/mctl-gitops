# Design: incident-92746868

## Confidence: LOW

## Diagnosis
The shepherd run merged mctlhq/mctl-agents#761 (a mctl-agents change, not a labs/mctl-telegram change). Post-deploy-verify then found argocd/labs-mctl-telegram Degraded after the 09:35Z threshold and still Degraded after the 120s grace, and failed the workflow. The Degraded app is unrelated to the merged repo, and the same flag appears on sibling incidents incident-92747073 and incident-92747006, so the check attributes a pre-existing Degraded app to an unrelated merge. The service logs show the labs mctl-telegram canary failing with "no active session" for user_id 245, which is runtime session state. Root cause of the Degraded health is not established.

## Proposed Fix
Investigate argocd/labs-mctl-telegram health. Scope post-deploy-verify to apps belonging to the merged repo or service rather than every app that became Degraded after the workflow start. Locate the post-deploy-verify step in the shepherd workflow template under platform-gitops and confirm the exact file before editing. Do not duplicate the change from incident-92747073. Verify before applying.

## Scope
Minimal. Only touch the post-deploy-verify scoping or the single Degraded resource.
