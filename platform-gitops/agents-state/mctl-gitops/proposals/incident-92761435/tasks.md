# Tasks: incident-92761435

1. [ ] Check whether incident-92761468 already changed the post-deploy-verify gating; if so, skip to task 3.
2. [ ] Otherwise scope post-deploy-verify to merged services and skip it when nothing merged.
3. [ ] Verify the ArgoCD health detail of argocd/labs-mctl-telegram and fix the canary configuration only if confirmed as the cause.
