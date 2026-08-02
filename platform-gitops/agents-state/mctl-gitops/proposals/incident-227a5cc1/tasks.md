# Tasks: incident-227a5cc1

1. [ ] Check ArgoCD controller pod logs for any sync-related errors (look for backoff or retry patterns)
2. [ ] Locate the ArgoCD Application manifest for admins-openclaw
3. [ ] Verify or add syncPolicy.automated.prune=true and selfHeal=true
4. [ ] Commit and push the change to main
5. [ ] Wait for ArgoCD to auto-reconcile (2-5 minutes)
6. [ ] Verify in ArgoCD UI that admins-openclaw is "Healthy" and "Synced"
7. [ ] If this matches incident-1164fda3 pattern, check if there are other OutOfSync OpenClaw apps and apply the same fix
