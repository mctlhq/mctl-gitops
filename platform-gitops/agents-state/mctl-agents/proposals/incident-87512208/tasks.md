# Tasks: incident-87512208

1. [ ] Verify the volume mount configuration in the mctl-agents service Helm values
2. [ ] Ensure the volume includes a mount for /workdir/mctl-gitops/platform-gitops/agents-state
3. [ ] Confirm the shared gitops volume is properly configured in the cluster
4. [ ] Redeploy the mctl-agents service with corrected volume mounts
5. [ ] Verify the shepherd workflow runs without "state_dir not found" warnings
6. [ ] Confirm post-deploy-verify check passes in the next shepherd run
