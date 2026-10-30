# Design: incident-3f0270f0

## Confidence: LOW

## Diagnosis
The PreviewReaperNotTriggered alert fired for tenant mctl because the preview-reaper job has not run for 3h. mctl-agent had no skill for this alert. No service logs or workflows were visible, so the cause is unconfirmed. The same alert fired in the same minute for erpact and commerce-proof, which points to a shared cause: a platform-wide reaper schedule problem, or an alert rule that fires for tenants with no previews to reap.

## Proposed Fix
Same root cause as incident-cc0b6c7d and incident-a34324b7; coordinate so only one change is made. In mctl-gitops, locate the PreviewReaperNotTriggered alert rule and the preview-reaper CronJob/CronWorkflow. Check for a suspended or broken schedule; if the reaper is healthy and only runs when previews exist, fix the alert expression so it does not fire for idle tenants. Verify before applying.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
