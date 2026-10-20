# Design: incident-a34324b7

## Confidence: LOW

## Diagnosis
The PreviewReaperNotTriggered alert fired for tenant erpact because the preview-reaper job has not run for 3h. mctl-agent had no skill for this alert. No service logs were available, so the cause is unconfirmed. The same alert fired in the same minute for the mctl and commerce-proof tenants, which points to a shared cause: a platform-wide reaper schedule problem, or an alert rule that fires for tenants with no previews to reap.

## Proposed Fix
Same root cause as incident-cc0b6c7d and incident-3f0270f0; coordinate with those proposals so only one change is made. In mctl-gitops, locate the PreviewReaperNotTriggered alert rule and the preview-reaper CronJob/CronWorkflow. Check for a suspended or broken schedule; if the reaper is healthy and only runs when previews exist, fix the alert expression so it does not fire for idle tenants. Verify before applying.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
