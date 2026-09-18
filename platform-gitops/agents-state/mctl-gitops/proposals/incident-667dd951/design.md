# Design: incident-667dd951

## Diagnosis
The `KubeQuotaAlmostFull` alert fired generically (type=generic) with no
skill match, so mctl-agent escalated without analysis. Pulling the tenant's
live ResourceQuota usage (`mctl_get_resource_usage` for team `labs`) shows
`limits.cpu` at 11300m used against a 12000m (12 cpu) hard limit — 94.2%
utilized, the tightest of all seven quota dimensions on this tenant and the
one that best matches "namespace quota is going to be full". This is a
recurrence of a pattern already documented in
`platform-gitops/tenants/labs/values.yaml`: the `labs` tenant has been bumped
five times before (2026-05-06 through 2026-08-15) as its service count grew,
most recently for `pods` and `services`. `limits.cpu` was last set to `12` on
2026-05-10 and has not been raised since, while the tenant has continued
onboarding services (16 services currently deployed, up from the ~5 present
at the last cpu-limit bump), consuming the added headroom.

No other quota dimension is within the same danger band (`limits.memory`
81.2%, `services` 85.0%, the rest below 75%), so `limits.cpu` is the field
driving this specific alert.

## Proposed Fix
File: `platform-gitops/tenants/labs/values.yaml`
Field: `tenant.quotas.limits.cpu`
Current value: `"12"`
New value: `"14"`

This follows the tenant's own documented bump convention (each prior bump
targeted ~2000m-2700m of headroom above current usage); 14000m against
11300m used leaves ~2700m headroom, consistent with the margin used in the
2026-05-10 and 2026-07 bumps recorded in the same file. Add a dated comment
line above the changed field, matching the existing history-of-bumps comment
style already present in that file, so the next responder has the same
context this one used.

## Scope
Minimal. Only touch `tenant.quotas.limits.cpu` in
`platform-gitops/tenants/labs/values.yaml`. No other quota field, service
values.yaml, or code path needs to change to relieve this specific alert.

## Confidence: LOW
No application logs exist for this alert (it is a cluster metrics signal, not
a service with request logs), so the diagnosis rests entirely on the
ResourceQuota snapshot taken at investigation time rather than on
alert-attached usage data. The 94.2% `limits.cpu` figure is a strong signal
given the tenant's own bump history for the same reason, but the implementer
should re-check current usage via `mctl_get_resource_usage` before applying,
in case usage has already dropped (e.g. a preview environment or workflow
pod that was transiently running was cleaned up).
