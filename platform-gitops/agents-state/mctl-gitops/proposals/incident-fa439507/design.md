# Design: incident-fa439507

## Diagnosis
The KubeQuotaAlmostFull alert fired for the labs tenant's ResourceQuota
(rendered from `platform-gitops/tenants/labs/values.yaml` via
`helm-charts/tenant/templates/resourcequota.yaml`). No skill matched because
there is no existing auto-fix rule for this generic AlertManager signal.
Live usage from `mctl_get_resource_usage(labs)` shows `services` at 19/20
(95%) — the tightest of all tracked quota dimensions (`limits.cpu` 12050m/14000m
= 86%, `limits.memory` 9504Mi/10.5Gi = 88%, `pods` 18/25 = 72%,
`requests.cpu`/`requests.memory` well under half). `mctl_get_tenant(labs)`
confirms 19 deployed services in the namespace today. This is a repeat of a
previously documented incident: the same `values.yaml` file has a comment
dated 2026-08-15 noting `services` hit 14/15 and was bumped to 20 for exactly
this alert (incident 3ec8a575). The tenant has since grown to 19/20 and
tripped the same threshold again.

## Proposed Fix
File: `platform-gitops/tenants/labs/values.yaml`
Field: `tenant.quotas.services`
Current value: `"20"`
New value: `"26"`

Add a dated comment above the field (matching the file's existing history
style) explaining the bump, e.g.:
```
# Bumped 2026-09-20: 19/20 services in use (KubeQuotaAlmostFull alert,
# incident 93397112-4e5f-4156-b7e0-138dfa439507) — repeat of the 2026-08-15
# bump (incident 3ec8a575); tenant grew from 14 to 19 services since then.
services: "26"
```

`26` mirrors the margin used for the 2026-08-03 `pods` bump (11/15 used ->
bumped to 25, landing at ~72% used immediately after) applied to the current
`services` usage of 19: 19/26 ~= 73% used post-bump.

## Scope
Minimal. Only the `tenant.quotas.services` field. Note for follow-up (not
part of this change): `limits.cpu` (86%) and `limits.memory` (88%) are also
elevated but are not the documented trigger for this alert pattern and are
not yet the binding constraint; if a future KubeQuotaAlmostFull incident
lands with those closer to 100%, they should be bumped in a separate,
targeted proposal.

## Confidence: MEDIUM
The incident carried no `labels` and no logs (monitoring-kube-state-metrics
is a metrics target, not a log-emitting service), so the exact quota
dimension that tripped the generic alert text is inferred from live usage
numbers plus a documented identical prior incident against the same field,
rather than confirmed directly from alert metadata.
