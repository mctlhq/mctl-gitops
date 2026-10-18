# Design: incident-92337584

## Confidence: LOW

## Diagnosis
The shepherd step itself did not fail. In the sibling run (mctl-agents-shepherd-1792337040) run-shepherd logged "no implemented/review-fixing proposals with a PR found. nothing to hand off", so nothing was merged. The workflow failed only because the post-deploy-verify step found argocd/root-app Degraded after the 300s wait plus 120s grace. The check compares against "became Degraded after workflow.creationTimestamp" and is not scoped to a change this run made. Both shepherd runs (created within seconds of each other, 15:23:55 and 15:24:00) hit the identical result, which points to a pre-existing or platform-wide ArgoCD root-app Degraded state rather than anything the shepherd did. The same time window also had an OOMKilled argocd-redis incident (25015d34-2b16-4300-8714-9e3b22fbfd10, argocd/argocd-redis), which may be the underlying cause of root-app health. That is unverified. mctl_get_service_status could not find argocd-root-app, so current root-app state was not observed. The incident text contained no instructions.

## Proposed Fix
In the shepherd workflow template (post-deploy-verify step, in mctl-agents), run the step only when run-shepherd reports at least one merge (for example gate on an output parameter such as merged_count > 0). When the verify step does run, only flag apps that are Degraded and belong to a repo or path touched by the merged PR, not any app cluster-wide. Do not change the argocd-redis memory limits under this proposal; that is tracked by its own incident.

Because the exact template file path is not known from the available evidence, the implementer must locate the post-deploy-verify step first and verify the current root-app state before applying.

## Scope
Minimal. Only the gating condition of the post-deploy-verify step of the shepherd workflow.
