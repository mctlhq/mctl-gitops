# Design: incident-92743304

## Confidence: LOW

## Diagnosis
The shepherd step succeeded: it merged mctlhq/mctl-api#766 (policy ALLOW, checks green). The post-deploy-verify step then failed because argocd/labs-mctl-telegram, an application unrelated to mctl-api, was Degraded after the 120s grace period. The check lists all apps that became Degraded after the workflow creation timestamp and is not scoped to the merged service. At review time labs-mctl-telegram was still Degraded (Synced, image 0.88.3) with healthy-looking logs, so the true cause of that Degraded state is unverified. This is the same pattern as incident argo-mctl-agents-shepherd-316d1c4b-1792743401: one unrelated Degraded app fails every shepherd run.

## Proposed Fix
Same change as proposal incident-92743401 (do it once; deduplicate with that proposal): in the post-deploy-verify step, only consider ArgoCD apps belonging to the service of the merged PR (mctl-api here), and skip the step when no merge occurred. Verify where the step is defined (mctl-agents or mctl-gitops workflow templates) before editing.

## Scope
Minimal. Only the post-deploy-verify app filter; do not touch the labs-mctl-telegram application.
