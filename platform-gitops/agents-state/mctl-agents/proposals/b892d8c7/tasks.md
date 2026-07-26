# Tasks: b892d8c7

1. [ ] Access Argo Workflow logs: https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1785053700
2. [ ] Retrieve full container logs and pod events for incident-responder job
3. [ ] Identify root cause from exit code/error message (OOM, timeout, config error, or app exception)
4. [ ] Determine target fix:
   - If resource exhaustion: increase CPU/memory limits in mctl-agents Helm values (platform-gitops/charts/mctl-agents/values.yaml)
   - If config error: fix environment variables or job parameters in Helm chart
   - If app error: debug incident-responder Python script and patch code
5. [ ] Apply fix to appropriate repository (mctl-gitops for Helm changes, mctl-agents for code changes)
6. [ ] Verify fix: trigger new mctl-agents-run workflow and confirm incident-responder job completes successfully
7. [ ] Re-run incident responder if fixes are applied, to process outstanding incidents
