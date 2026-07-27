# Design: incident-76440436

## Diagnosis
The mctl-agents implementer workflow fails when processing a batch of accepted proposals (status=accepted). The workflow reaches exactly 391 seconds before failing, which suggests a hard timeout constraint in the Argo Workflow configuration or the implementer job specification. The task "implement implement (all accepted)" is the critical path for opening PRs from agent-generated proposals. When multiple proposals are queued, the workflow cannot process them all within the 391-second (6.5-minute) window. The root cause is insufficient timeout budget in the workflow specification or inefficient batch processing that should be parallelized or split into smaller jobs.

## Proposed Fix
Increase the Argo Workflow timeout for the implementer job from 391 seconds to at least 1800 seconds (30 minutes), or implement parallel task processing to handle multiple proposals concurrently instead of sequentially.

Option A (simpler, immediate):
- File: mctl-agents Argo Workflow template (likely in mctl-agents repo or mctl-gitops/services/admins/mctl-agents/templates/)
- Field: spec.activeDeadlineSeconds or individual task timeouts
- Current: 391 seconds
- New: 1800 seconds

Option B (preferred, scalable):
- Modify the implementer loop to process proposals in parallel (fan-out N workers) instead of serial, bounded to ~5-10 concurrent PRs per batch.

## Scope
Minimal. Only adjust the timeout threshold or parallelism parameter. Do not alter the core logic of proposal→PR mapping.

## Confidence: MEDIUM
The 391-second boundary is a hard timeout (no logs available to confirm exact failure mode). The diagnosis assumes Argo activeDeadlineSeconds constraint; implementer should verify the actual timeout configuration in the workflow spec before applying.
