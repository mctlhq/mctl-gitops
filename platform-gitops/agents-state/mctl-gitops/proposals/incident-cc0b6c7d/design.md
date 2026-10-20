# Design: incident-cc0b6c7d

## Confidence: LOW

## Diagnosis
The PreviewReaperNotTriggered alert fired for tenant commerce-proof because the preview-reaper job has not run for 3h. mctl-agent had no skill for this alert. No service logs were available, so the cause is unconfirmed. Likely candidates: the preview-reaper CronJob or CronWorkflow is suspended or failing to schedule, or the alert rule fires for tenants that legitimately have no previews (an idle tenant never triggers the reaper). The same alert fired at the same minute for the mctl and erpact tenants, which points to a shared cause (a platform-wide reaper schedule or the alert rule itself) and not a tenant-specific fault.

## Proposed Fix
Verify first. In mctl-gitops, locate the preview-reaper schedule definition and the PreviewReaperNotTriggered alert rule (grep for the alert name). Check whether the CronJob/CronWorkflow is suspended, has a broken schedule, or never runs per tenant. If the reaper is healthy and runs only when previews exist, adjust the alert expression so it only fires when previews exist for the tenant or the last-run metric is truly stale. If the schedule is broken, fix it. Apply nothing beyond the one field or rule involved.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
