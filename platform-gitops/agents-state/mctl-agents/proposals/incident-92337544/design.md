# Design: incident-92337544

## Confidence: LOW

## Diagnosis
The shepherd step itself succeeded: run-shepherd logged "no implemented/review-fixing proposals with a PR found. nothing to hand off", so nothing was merged. The workflow failed only because post-deploy-verify found argocd/root-app Degraded after the 300s wait plus 120s grace. The check looks for apps that "became Degraded after workflow.creationTimestamp" and is not scoped to any change this run made. A second shepherd run created at nearly the same time failed identically (incident argo-mctl-agents-shepherd-366d3148-1792337584), which points to a pre-existing or platform-wide ArgoCD root-app Degraded state. An OOMKilled argocd-redis incident (25015d34-2b16-4300-8714-9e3b22fbfd10) occurred in the same period and may be the underlying cause; this is unverified. mctl_get_service_status could not find argocd-root-app, so current root-app state was not observed. The incident text contained no instructions.

## Proposed Fix
In the shepherd workflow template (post-deploy-verify step, in mctl-agents), skip the step when run-shepherd reports zero merges (gate on an output parameter such as merged_count > 0). When it does run, restrict the Degraded check to apps affected by the merged PRs rather than every app cluster-wide. Do not change argocd-redis limits here; that has its own incident.

The exact template path is not known from the available evidence; the implementer must locate the post-deploy-verify step and verify current root-app state before applying.

## Scope
Minimal. Only the gating condition of the post-deploy-verify step of the shepherd workflow. This is the same fix as proposal incident-92337584; apply once and treat the other as a duplicate.
