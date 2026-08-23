# Tasks: incident-87468920

1. [ ] Read current mctl-agents Helm values configuration in platform-gitops/services/admins/mctl-agents/values.yaml
2. [ ] Add gitops volume mount to the pod spec to mount repository at /workdir/mctl-gitops
3. [ ] Verify mount path and volume name are consistent with platform conventions used in other services
4. [ ] Commit changes to platform-gitops repository
5. [ ] Monitor mctl-agents pod logs to confirm /workdir/mctl-gitops/platform-gitops/agents-state is now accessible
6. [ ] Verify ReconcileWorkflow runs complete without "state_dir not found" warnings
7. [ ] Confirm shepherd workflow completes successfully on next scheduled run
