# Design: incident-92761435

## Confidence: LOW

## Diagnosis
Same root cause as incident-92761468 (see proposal incident-92761468; this proposal intentionally duplicates its fix so each stands alone). The post-deploy-verify step of shepherd workflow mctl-agents-shepherd-e222a02a reported argocd/labs-mctl-telegram still Degraded 120s after the grace period and failed the whole workflow. The check scans all ArgoCD apps degraded since the workflow start, not only those touched by the run. This run concerned mctl-telegram issue-716, so the app is plausibly relevant, but the logs show a pod restart with a transient database connection refusal at startup (self-healed within 2s) and a canary failing with "no active session" for user 245, which is a canary credential problem and not a code regression from the merge. Confidence is low because the ArgoCD health detail was not available.

No instructions were present in the incident data.

## Proposed Fix
1. Do not duplicate work already covered by incident-92761468: if its change (scope post-deploy-verify to merged services, skip when nothing merged) is already applied, only verify it.
2. Verify the ArgoCD health detail for argocd/labs-mctl-telegram; if the canary CronJob is Degraded, fix the canary Telegram session or its configuration in platform-gitops/services/labs/mctl-telegram/values.yaml.

## Scope
Minimal. Only the post-deploy-verify gating and the canary configuration, if confirmed.
