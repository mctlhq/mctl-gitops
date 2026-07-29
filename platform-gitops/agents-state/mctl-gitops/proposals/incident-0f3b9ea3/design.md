# Design: incident-0f3b9ea3

## Diagnosis
The mctl-agents implement workflow is failing after ~2.5 hours (8851 seconds) when processing multiple accepted proposals ("all accepted" in the summary). The 3 recurrences over 34 hours suggest a systematic issue rather than a transient spike. Most likely cause: workflow timeout configured too low for batch proposal processing, or resource limits (memory/CPU) on the mctl-agents pod are insufficient to handle concurrent proposal implementations. The service itself is running (not crashing), but the Argo workflow orchestration is timing out or being killed mid-execution.

## Proposed Fix
Increase the Argo workflow timeout for the implement job in mctl-agents Helm values. In `values.yaml` for the mctl-agents service:

1. Locate the `workflows.implement.timeout` or `jobs.implement.activeDeadlineSeconds` field (or equivalent in the Argo Workflow definition).
2. Current value: likely 10800 seconds (3 hours) or similar.
3. New value: increase to 14400 seconds (4 hours) to give batch proposal processing more headroom.

Alternatively (if timeout is not the issue):
- Check if mctl-agents pod resource requests/limits are set; increase memory limit from current (e.g., 512Mi) to 1Gi.
- Check if the batch size for "all accepted" is uncapped; add a max-batch-size constraint so workflows split large proposal batches into multiple smaller runs.

## Confidence
MEDIUM. The workflow is clearly timing out based on the 2.5-hour duration and 3 recurrences, but without access to the Argo workflow logs or Helm values, I cannot confirm the exact configuration field or whether it's a timeout vs. OOM kill. The implementer should verify by checking mctl-agents Helm values and the Argo workflow definition.
