# Design: incident-0313b448

## Confidence: LOW

## Diagnosis
The CPUThrottlingHigh alert fired for the argocd-notifications-controller container, meaning its CFS-throttled periods exceeded the alert threshold. The likely cause is a CPU limit that is too low for the workload. Service logs could not be fetched (argocd is not a registered tenant), so this was not independently verified from logs or pod state. The alert is on mctl-agent's human-review-only list, so the implementer must verify before applying.

## Proposed Fix
Locate the Argo CD Helm values in mctl-gitops (the argocd application values, key `notifications.resources`). Inspect the current `resources.limits.cpu` for the notifications controller. If it is set and low (for example 100m or less), raise it modestly (about 2x), or remove the CPU limit while keeping the request. If no CPU limit is set or the file cannot be found, make no change and note it in the PR. Exact current and new values must be read from the repo.

## Scope
Minimal. Only touch the notifications controller CPU limit in the Argo CD values.
