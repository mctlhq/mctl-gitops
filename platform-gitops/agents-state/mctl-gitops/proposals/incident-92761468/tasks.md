# Tasks: incident-92761468

1. [ ] Locate the shepherd workflow template containing the post-deploy-verify step and change it to skip when run-shepherd merged zero PRs, and otherwise check only the ArgoCD apps of merged services.
2. [ ] Verify the template change renders correctly and the step still fails when a merged service's app is Degraded.
3. [ ] Check the ArgoCD health detail of argocd/labs-mctl-telegram; only if the canary CronJob is the cause, fix its Telegram session or config in platform-gitops/services/labs/mctl-telegram/values.yaml.
