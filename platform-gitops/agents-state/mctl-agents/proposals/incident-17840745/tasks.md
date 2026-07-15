# Tasks: incident-17840745

1. [ ] Open the Argo Workflow UI and identify the failing step:
       https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784074500
2. [ ] Note: this is the EARLIEST failure in the batch (00:18 UTC 2026-07-15). Check
       for any deployments or config changes to mctl-agents that landed just before this
       time — that change is the likely regression trigger.
3. [ ] Compare the failure reason with incident-17840817 to confirm the same root cause.
4. [ ] Apply the fix identified in incident-17840817 (see tasks.md in that proposal).
5. [ ] Verify the fix by triggering a manual incident-responder run and confirming the
       workflow reaches Succeeded status in the Argo UI.
