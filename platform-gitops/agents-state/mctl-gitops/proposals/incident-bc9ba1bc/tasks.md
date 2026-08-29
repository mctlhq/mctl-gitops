# Tasks: incident-bc9ba1bc

1. [ ] Check if directory platform-gitops/services/ovk/openclaw/ exists and contains valid Helm values.yaml
2. [ ] Query ArgoCD for application ovk-openclaw status and sync error messages
3. [ ] Search mctl-agents workflow history for OpenClaw deployment workflows for tenant ovk
4. [ ] Review the deployment workflow logs to identify the failure point
5. [ ] Either: a) retry/complete the deployment, or b) delete the orphaned ArgoCD application
6. [ ] Verify the ArgoCDApplicationOutOfSyncLong alert clears
