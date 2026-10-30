# Design: incident-92747006

## Confidence: LOW

## Diagnosis
The shepherd run decided "wait" for mctlhq/mctl-telegram#839 (merge state BLOCKED) and merged nothing. The workflow was marked Failed only because post-deploy-verify found argocd/labs-mctl-telegram Degraded and still Degraded after the 120s grace. Since no merge happened in this run, the Degraded state is pre-existing or caused by something else. Sibling incidents incident-92747073 and incident-92746868 show the same flag. The service logs show the labs mctl-telegram canary failing with "no active session" for user_id 245, which is runtime session state. Root cause of the Degraded health is not established.

## Proposed Fix
Investigate argocd/labs-mctl-telegram health. Make post-deploy-verify skip when the shepherd run performed no merge, or scope it to the service whose PR was merged. Locate the post-deploy-verify step in the shepherd workflow template under platform-gitops and confirm the exact file before editing. This is the same change as incident-92747073; the implementer should avoid duplicating it. Verify before applying.

## Scope
Minimal. Only touch the post-deploy-verify scoping or the single Degraded resource.
