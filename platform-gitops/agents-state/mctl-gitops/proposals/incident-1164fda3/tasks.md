# Tasks: incident-1164fda3

1. [ ] Locate the ArgoCD Application manifest for ovk-openclaw in platform-gitops
2. [ ] Verify or add syncPolicy.automated.prune=true and selfHeal=true
3. [ ] Commit and push the change to main
4. [ ] Wait for ArgoCD to auto-reconcile (2-5 minutes)
5. [ ] Verify in ArgoCD UI that ovk-openclaw health is "Healthy" and sync status is "Synced"
6. [ ] If already synced, manually trigger sync via `argocd app sync ovk-openclaw` instead
