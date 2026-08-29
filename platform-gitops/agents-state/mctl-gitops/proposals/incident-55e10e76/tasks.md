# Tasks: incident-55e10e76

1. [ ] Check if directory platform-gitops/services/admins/openclaw/ exists and contains valid Helm values.yaml
2. [ ] Query ArgoCD for application admins-openclaw status and sync error messages
3. [ ] Search mctl-agents workflow history for OpenClaw deployment workflows for tenant admins
4. [ ] Review the deployment workflow logs to identify the failure point
5. [ ] Either: a) retry/complete the deployment, or b) delete the orphaned ArgoCD application
6. [ ] Verify the ArgoCDApplicationOutOfSyncLong alert clears
