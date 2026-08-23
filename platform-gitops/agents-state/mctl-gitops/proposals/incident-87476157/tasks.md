# Tasks: incident-87476157

1. [ ] Review the mctl-agents Helm chart values to identify the volume mount configuration
2. [ ] Verify that the mctl-gitops repository volume is mounted at /workdir/mctl-gitops in workflow pods
3. [ ] Check that platform-gitops/agents-state subdirectory exists and is accessible
4. [ ] Update the Helm values if the mount is missing or misconfigured
5. [ ] Verify the change in a test environment or by monitoring logs for the state_dir warning to disappear
6. [ ] Confirm shepherd workflow completes successfully on next scheduled run
