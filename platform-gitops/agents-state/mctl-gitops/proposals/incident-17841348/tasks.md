# Tasks: incident-17841348

1. [ ] Find the Argo WorkflowTemplate / CronWorkflow manifest that defines the `shepherd`
       operation (the one triggered by `mctl-agents-shepherd`) and locate its
       `activeDeadlineSeconds` field.
2. [ ] Confirm the current value is at or near 8250 seconds; if a different value is
       found, re-check the Argo UI links in requirements.md before proceeding
       (https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1784134800
       and https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1784124000)
       to confirm the failure reason is DeadlineExceeded and not something else.
3. [ ] Raise `activeDeadlineSeconds` to 21600 (6 hours), or a value appropriate for the
       number of open PRs the shepherd sweep typically processes.
4. [ ] Find the Sensor/Trigger template (or notification-building step) that renders
       `workflow.outputs.parameters.degraded_apps` into the incident/alert summary and
       add a default value for the case where the parameter was never set.
5. [ ] Verify both changes look correct (deadline field increased; template default
       added, no syntax errors in the manifest).
6. [ ] No image tag bump expected — this is a manifest/config-only change.
