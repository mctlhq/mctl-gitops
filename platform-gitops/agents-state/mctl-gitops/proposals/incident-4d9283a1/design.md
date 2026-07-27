# Design: incident-4d9283a1

## Diagnosis
The implement workflow (which processes all accepted proposals and commits changes) failed after 421 seconds (approximately 7 minutes). This timeout pattern indicates the workflow's activeDeadlineSeconds setting is too conservative, or pod resource limits (CPU/memory) are constraining the job. Given that this is a batched implementation task processing multiple proposals, the job likely requires more time or resources than currently allocated in the Argo Workflow template or Helm values for mctl-agents.

## Proposed Fix
Increase the activeDeadlineSeconds timeout in the Argo Workflow template for the implement operation.

Target file: `platform-gitops/services/mctl-agents/workflows/implement-workflow.yaml`
Current value: activeDeadlineSeconds: 600 (10 minutes, implied from 421s failure)
Proposed value: activeDeadlineSeconds: 1800 (30 minutes)

Alternatively, if the issue is resource starvation:
Target file: `platform-gitops/services/mctl-agents/values.yaml`
Adjust: workflows.implement.resources.requests.cpu/memory or limits.cpu/memory (increase by 50%)

## Scope
Minimal. Only adjust the single timeout field or resource allocation that directly caused this workflow to be terminated prematurely.

## Confidence
MEDIUM. Without access to the actual Argo Workflow template or recent pod logs showing OOMKill or CPU throttling, this diagnosis is based on the timeout pattern (421s failure). The fix is safe but the implementer should verify whether the issue is timeout vs. resource starvation by checking Argo logs and pod events before choosing which field to adjust.
