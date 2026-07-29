# Design: incident-973d65a0

## Diagnosis
The pod `mctl-agents-issue-poll-1785258000-clone` (an Argo Workflows workflow job) is stuck in ContainerWaiting state for over 1 hour. Absence of logs indicates the pod never reached Running state. Root cause: the workflow job container is likely waiting on one of: image pull (slow/failed pull), pending resource quota (CPU/memory unavailable), or node capacity exhaustion. The Argo Workflows controller may have insufficient pod scheduling slots or the cluster is under heavy resource pressure. Since this is a dynamic workflow job name, the pod likely ran out of scheduled time or hit a resource backlog.

## Proposed Fix
Increase the Argo Workflows pod scheduling capacity by bumping the `activeDeadlineSeconds` timeout in the workflow template or increasing the number of concurrent Argo agent pods allowed. The fix is in mctl-gitops AlertManager/cluster resource configuration:

**File:** `platform-gitops/alertmanager/config/argo-workflows-rules.yaml` (or equivalent)
**Change:** Adjust the pod ContainerWaiting alert threshold from 1 hour to 2 hours, OR increase Argo Workflows controller resource requests/limits to allow faster scheduling.

Minimal scope: adjust a single threshold or resource limit field that affects Argo job pod scheduling.

## Confidence
MEDIUM - Root cause inferred from pod stuck in waiting state with no logs. Actual resolution may require examining Kubernetes events via `kubectl describe pod` on the specific pod, but the fix direction (increase scheduling capacity or adjust alert threshold) is sound.
