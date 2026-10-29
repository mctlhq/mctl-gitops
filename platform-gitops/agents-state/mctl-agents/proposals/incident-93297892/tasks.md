# Tasks: incident-93297892

1. [ ] Locate the shepherd post-deploy-verify script in the mctl-agents repo and read how it selects "newly Degraded" ArgoCD apps.
2. [ ] If it attributes by health transition time only, change it to also require that the app's last sync/operation finished after the workflow creation timestamp; otherwise make no change and set the proposal to needs-triage.
3. [ ] Verify the change by reading the diff; confirm argocd/labs-mctl-telegram (unchanged since 2026-10-28) would not be flagged while an app synced after the merge still would.
4. [ ] Make no changes to labs/mctl-telegram values, secrets or sessions.
