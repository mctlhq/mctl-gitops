# Tasks: incident-92775878

1. [ ] Read the archived post-deploy-verify step logs for workflow mctl-agents-shepherd-467f8fe7 and identify why argocd/labs-mctl-telegram was flagged.
2. [ ] If the cause is a verify timeout shorter than rollout plus DB reconnect time, raise that timeout minimally; otherwise make no change.
3. [ ] Confirm labs-mctl-telegram is Healthy/Synced in ArgoCD.
