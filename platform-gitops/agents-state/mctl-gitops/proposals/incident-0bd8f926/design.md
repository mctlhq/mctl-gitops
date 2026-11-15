# Design: incident-0bd8f926

## Confidence: LOW

## Diagnosis
ArgoCD application erpact-shared has been OutOfSync for over an hour. mctl-agent had no skill for this alert. Service logs are unavailable: the service is not in the erpact workspace catalogue (list_services returned zero services), so the app is probably deployed outside the catalogue (the ERPact site deployer path). The root cause of the drift is not determined. The sibling apps erpact-control, erpact-deployer and erpact-infra fired the same alert, which suggests a shared cause (a common source revision, a missing path in gitops, or a sync/permission problem on the erpact ArgoCD project).

## Proposed Fix
Verify first. In mctl-gitops, locate the manifests or ArgoCD Application definition for erpact-shared (search for "erpact"). Compare the target revision, source path and values with what exists on main. If the source path or revision is missing or stale, correct that single field. If the diff is only an ignorable live-state difference (e.g. a controller-mutated field), add a narrowly scoped ignoreDifferences entry. If the cause is not visible in gitops, make no change and note this in the PR.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
