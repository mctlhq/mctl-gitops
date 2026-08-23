# Tasks: incident-87483374

1. [ ] Inspect mctl-agents Helm values to verify volumeMounts and volumes configuration
2. [ ] Add volumeMount for `/workdir/mctl-gitops/platform-gitops/agents-state` if missing
3. [ ] Add corresponding volume definition (tempDir, emptyDir, or persistent volume reference)
4. [ ] Verify the mctl-gitops source repository is accessible and the agents-state directory exists
5. [ ] Redeploy mctl-agents with updated Helm values
6. [ ] Verify shepherd workflow completes successfully and no "state_dir not found" warnings appear in logs
