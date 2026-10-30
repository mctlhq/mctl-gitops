# Design: incident-92743401

## Confidence: LOW

## Diagnosis
The shepherd step itself succeeded: it evaluated PR mctl-telegram#839, decided "wait" (merge_state BLOCKED) and merged nothing. The workflow then failed in the post-deploy-verify step, which sleeps 300s, lists every ArgoCD application that became Degraded after the workflow creation timestamp, and fails if any remains Degraded. The flagged app, argocd/labs-mctl-telegram, was Degraded at the time of this review (sync Synced, health Degraded, image 0.88.3) while its pod logs show normal traffic and no errors, so the cause of the Degraded health is not visible from logs and was not confirmed. The check is global rather than scoped to the service the shepherd touched, and it runs even when nothing was merged, so it produces a failed shepherd workflow for an unrelated or pre-existing condition. Root cause of the Degraded state of labs-mctl-telegram itself is unverified (possibly a Deployment/PVC/DB health condition); the implementer should verify before applying.

## Proposed Fix
In the shepherd workflow template (post-deploy-verify step; verify whether it lives in mctl-agents or mctl-gitops workflow templates):
1. Skip the 300s sleep and the Degraded check entirely when the run-shepherd step reports no merge (decision != merge).
2. When a merge happened, restrict the Degraded check to ArgoCD apps for the merged service (map repo to app name, e.g. mctlhq/mctl-api -> admins-mctl-api) instead of all apps.
Independently, an operator should inspect why argocd app labs-mctl-telegram is Degraded; that is a separate issue not addressed by this change.

## Scope
Minimal. Only the post-deploy-verify step gating and app filter.
