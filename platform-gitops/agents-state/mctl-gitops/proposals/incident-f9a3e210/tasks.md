# Tasks: incident-f9a3e210

1. [ ] Locate the ArgoCD Application CR for ovk-openclaw in platform-gitops/tenants/ovk/openclaw/
2. [ ] Verify syncPolicy.automated is enabled; if not, add: spec.syncPolicy.automated: { allow: true, prune: true, selfHeal: true }
3. [ ] If already enabled, trigger manual sync via ArgoCD UI or: argocd app sync ovk-openclaw
4. [ ] Verify the application syncs successfully and OutOfSync alert clears within 2 minutes
