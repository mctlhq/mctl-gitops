# Design: incident-5137bd2c

## Confidence: LOW

## Diagnosis
The alert ArgoCDApplicationOutOfSyncLong fired for ArgoCD application erpact-infra, which has been OutOfSync for over an hour. mctl-agent had no skill for this signal. Independent checks show that erpact-infra is not a catalogue service: the service logs call returns "service not found", and the erpact workspace lists zero services (ArgoCD read OK, complete). So erpact-infra is most likely a tenant-owned or platform-deployed ArgoCD Application (for example the infrastructure app created for ERPact site provisioning) that is not onboarded as a service. The likely causes are a stale or deleted Application whose source path or target revision no longer exists in gitops, or a drifting resource that the app does not ignore. The root cause could not be confirmed from the available evidence.

## Proposed Fix
Verify first, then apply the smallest change:
1. Search mctl-gitops for the Application named erpact-infra (and any ApplicationSet that generates it).
2. If its source path or targetRevision no longer exists, or the tenant was retired, remove the Application manifest (or ApplicationSet entry) so it stops being reconciled.
3. If the source exists and the app is OutOfSync because of a field mutated by a controller, add the matching `ignoreDifferences` entry for that single field.
4. If neither applies, make no change and report that a human needs to inspect the app diff in ArgoCD.

## Scope
Minimal. Only touch the single Application or ignoreDifferences entry that causes this specific alert.
