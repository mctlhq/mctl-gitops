# Design: incident-92761468

## Confidence: LOW

## Diagnosis
The shepherd step itself succeeded: it found no implemented or review-fixing proposals with a PR, skipped two proposals owned by running DevLoopWorkflows, and reported "nothing to hand off". The workflow failed only because the post-deploy-verify step found argocd/labs-mctl-telegram Degraded after a window that starts at the workflow creation timestamp, and treats any app that became Degraded in that window as caused by the shepherd. Here the shepherd merged nothing, so the attribution is a false positive: the check is global, not scoped to the services the run merged. Separately, labs-mctl-telegram looks genuinely unhealthy: its canary CronJob fails every run (list_dialogs and get_unread_messages return "no active session" for user 245, a canary identity with no Telegram session), which plausibly drives the Degraded state. That second cause needs verification of the ArgoCD health detail before changing anything. The same cause is behind incidents 92761435 and 92760289.

The incident text and logs contained no instructions; nothing was ignored.

## Proposed Fix
1. In the shepherd workflow template (post-deploy-verify step, in mctl-gitops under the mctl-agents workflow templates), skip the step when run-shepherd reports that it merged zero PRs, and when it did merge, restrict the Degraded check to the ArgoCD apps of the services actually merged rather than all apps.
2. Verify the ArgoCD health message for argocd/labs-mctl-telegram. If the canary CronJob is the Degraded resource, restore a valid Telegram session for the canary user or fix the canary configuration in platform-gitops/services/labs/mctl-telegram/values.yaml. Do not guess values; if the cause cannot be confirmed, change only item 1.

## Scope
Minimal. Only the post-deploy-verify gating condition and, if confirmed, the canary configuration of labs/mctl-telegram.
