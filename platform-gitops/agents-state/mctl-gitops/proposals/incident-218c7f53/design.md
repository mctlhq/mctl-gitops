# Design: incident-218c7f53

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-api was reported Degraded for 30 minutes. mctl-agent had no skill for this alert type and did not analyse it. The responder could not independently confirm a root cause: the platform API does not know a tenant "mctl-api" or a service "admins-mctl-api"/"mctl-api" in workspace "admins", and no matching ArgoCD application is visible, so no pod state, events or logs could be read. Possible explanations: the application is not catalogue-managed (external/platform app), it was renamed or retired after the alert fired, or the alert labels map tenant/service incorrectly. No cause is established.

## Proposed Fix
No concrete change can be justified from the available evidence. The implementer should verify first:
1. Search mctl-gitops (platform-gitops/services and ArgoCD application definitions) for an application named admins-mctl-api.
2. If it exists and its manifests are wrong (bad image tag, failing probe, missing secret reference, resource limits), fix only that single field.
3. If it does not exist (stale or retired app), check whether the AlertManager rule's tenant/service label mapping is wrong, or whether the alert is stale, and make no change if so.
If no defect is found, make no change and close the task with a note.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not make speculative changes.
