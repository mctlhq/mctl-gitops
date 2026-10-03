# Design: incident-1e0f735d

## Confidence: LOW

## Diagnosis
The argocd-applicationset-controller (an ArgoCD control-plane component, not a
tenant-onboarded mctl service) is triggering the CPUThrottlingHigh alert,
indicating its pods are being CFS-throttled because the configured CPU limit
is too low relative to actual usage. mctl-agent's Tier-1 pipeline already
diagnosed this the same way (see the advisory analysis quoted in
requirements.md) but never proposes a fix for this alert by policy, since
CPUThrottlingHigh is on its human-review-only list; that policy governs
Tier-1 auto-fix, not this responder, so a proposal is written here per the
"human-review-only" qualifying reason. No service logs or current resource
values were reachable through mctl tooling (mctl_get_service_logs returned
zero lines and mctl_get_service_config reported the service as not found,
both because this is a platform infra component rather than a registered
tenant service), so the exact current CPU request/limit values and the Helm
values file path could not be confirmed independently. Confidence is
therefore marked LOW; the implementer should verify the actual current
values in the ArgoCD chart configuration before applying a change.

## Proposed Fix
In the platform-gitops repo, locate the Helm values controlling the ArgoCD
installation's applicationset-controller resources (typically under an
`infrastructure/argocd/` or similar chart-values path, under a key such as
`applicationSet.resources.limits.cpu` / `applicationSet.resources.requests.cpu`,
naming depends on the chart in use). Increase the CPU limit for the
applicationset-controller container (and raise the CPU request
proportionally, keeping a sane request:limit ratio) enough to stop CFS
throttling under normal load — a reasonable starting point is doubling the
current limit (e.g. 200m -> 400m; adjust to whatever the current value
actually is once located).

## Scope
Minimal. Only touch the CPU resource request/limit fields for the
argocd-applicationset-controller component. Do not change other ArgoCD
components, replica counts, or unrelated settings.
