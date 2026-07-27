# Design: incident-b738c48a

## Diagnosis
The Argo Workflow for `mctl-agents-implement` failed after 414 seconds of execution. This suggests one of three possible root causes: (1) the workflow timed out waiting for a downstream operation (e.g., a remote call, CI/CD job, or external queue), (2) the mctl-agents pod ran out of memory or CPU, causing the orchestrator to terminate it, or (3) an internal orchestration error in the implement phase (e.g., malformed proposal, missing dependency, or code error when processing accepted proposals). The incident type `workflow_failed` with no detailed error message indicates this was caught at the workflow level rather than within application logic.

## Proposed Fix
Without access to detailed workflow logs, a confidence check and incremental fixes are needed:

1. **Increase mctl-agents resource requests and limits** (most likely cause): The implement phase processes all accepted proposals, which can be resource-intensive. Current pod spec likely has insufficient CPU or memory.
   - File: `mctl-gitops/agents-state/mctl-agents/values.yaml` (or similar Helm values)
   - Current: Check existing `resources.requests` and `resources.limits` for mctl-agents
   - Proposed: Increase CPU from (e.g., 500m to 1000m) and memory from (e.g., 512Mi to 1Gi)

2. **Increase Argo Workflow timeout**: If the workflow is timing out waiting for a remote operation, increase the activeDeadlineSeconds.
   - File: mctl-agents workflow template in Argo Workflows ConfigMap or ArgoCD app
   - Proposed: Bump timeout from 600s to 900s (15 min)

## Scope
Minimal. Only adjust resource limits and workflow timeout. No code changes required at this stage.

## Confidence: MEDIUM
The diagnosis is based on workflow failure metadata only. Without detailed logs, we cannot rule out application-level errors. The implementer should verify that logs are available in the workflow run details before applying resource changes.
