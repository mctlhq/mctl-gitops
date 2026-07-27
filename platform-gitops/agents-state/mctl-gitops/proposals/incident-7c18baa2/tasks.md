# Tasks: incident-7c18baa2

1. [ ] Locate the ArgoCD Application CR for admins-openclaw in platform-gitops/tenants/admins/openclaw/
2. [ ] Verify syncPolicy.automated is enabled; if not, add: spec.syncPolicy.automated: { allow: true, prune: true, selfHeal: true }
3. [ ] If already enabled, trigger manual sync via ArgoCD UI or: argocd app sync admins-openclaw
4. [ ] Verify the application syncs successfully and OutOfSync alert clears within 2 minutes
