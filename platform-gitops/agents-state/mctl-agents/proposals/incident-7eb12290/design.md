# Design: incident-7eb12290

## Diagnosis
The mctl-agents-implement workflow processes accepted proposals through the implementer agent. It consistently fails after 571 seconds (9.5 minutes), suggesting a hard timeout or resource limit is being hit. This is the second occurrence, indicating it is not a transient error but a systematic issue. The workflow timeout is likely set too aggressively for the volume of proposals being processed, or the implement agent is consuming more resources than the current limits allow.

## Confidence: MEDIUM
The diagnosis is based on the consistent 571-second failure pattern and the nature of the workflow (implementer processing all accepted proposals). Without direct access to Argo Workflow error logs or detailed service traces, the exact cause cannot be definitively determined. However, the regular failure interval strongly suggests a timeout mechanism.

## Proposed Fix
**File:** mctl-gitops/argo-workflows/templates/implement.yaml (or similar Argo workflow manifest)

**Current Issue:**
- Workflow timeout: likely set to 600-900 seconds (10-15 minutes)
- Actual execution time: ~571 seconds consistently
- This suggests the timeout is barely being triggered or there is a hard stop at this interval

**Solution:**
1. Increase the Argo Workflow timeout to 1800 seconds (30 minutes) to provide buffer for large batch implementations
2. Alternatively, add resource requests/limits to the implement workflow pod to ensure it has sufficient CPU and memory

**Specific Changes:**
- Update the activeDeadlineSeconds or timeout field in the implement Argo Workflow manifest to a higher value (e.g., 1800)
- Verify that the implement agent pod has adequate CPU (suggest 2+ cores) and memory (suggest 2Gi+)

## Scope
Minimal. Only adjust the timeout value in the Argo Workflow template that defines the implement workflow. No changes to agent logic or other services.
