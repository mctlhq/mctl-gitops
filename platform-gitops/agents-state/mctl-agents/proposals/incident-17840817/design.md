# Design: incident-17840817

## Confidence: LOW

## Diagnosis

The `mctl-agents-run incident-responder` Argo Workflow has been failing deterministically
every 30 minutes since at least 00:18 UTC on 2026-07-15. This incident is the most recent
in a run of at least 5 consecutive failures (also see proposals incident-17840799,
incident-17840781, incident-17840763, incident-17840745). Each run crashes after 170-220
seconds (~3 minutes), which is too short for a timeout and too consistent for a transient
failure, pointing to a deterministic code or configuration defect.

Loki returned zero log lines for `admins/mctl-agents` over a 24-hour window, so the
diagnosis below is inferred from timing patterns only. The Argo Workflow UI at
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784081700 is
the primary source for the exact failure reason.

Most likely root causes in rank order:

1. Token budget exhaustion: The incident-responder agent enforces a per-run Claude API
   budget (typically $2). If there are many `analyzing` incidents queued and the agent
   performs numerous tool calls (list, get, logs, write, resolve per incident), the budget
   may be exhausted mid-run, causing the Argo step to exit non-zero after ~3 minutes.
   The $2 budget divided by the per-tool-call cost is consistent with a ~3 minute runtime.

2. MCP connectivity error: The mctl MCP server may be returning an unretried error (auth
   failure, tool not found, rate limit) that causes the Python workflow to raise an
   unhandled exception and exit 1.

3. Python runtime exception: An unhandled exception in the incident-responder workflow
   step (e.g. KeyError, AttributeError, or network timeout without retry) causes the
   step to exit non-zero. This would also produce a consistent crash time if the
   exception is triggered by the first tool call.

4. OOMKilled: Less likely given the consistent timing, but possible if the workflow pod
   memory limit is too low.

The `workflow_failed` alert type has no pattern-matched skill in the platform, which is
why it lands in `analyzing` indefinitely without auto-resolution.

## Proposed Fix

Implementer must first retrieve the actual failure reason:

```
kubectl logs -n argo-workflows <pod-for-mctl-agents-incidents-1784081700> --all-containers
# OR view in Argo UI: https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784081700
```

Then apply the matching fix:

A. If budget exhaustion (exit log contains "budget" or "USD"):
   - File: mctl-agents/workflows/incident_responder.py (or equivalent)
   - Field: BUDGET_USD or equivalent constant
   - Current value: ~2.0
   - New value: increase to 5.0, or reduce per-incident tool call count

B. If MCP error (exit log contains tool name + error):
   - Add retry logic or graceful error handling around the failing MCP tool call
   - File: the workflow step that calls the failing tool

C. If Python exception (exit log shows traceback):
   - Fix the specific unhandled exception shown in the traceback
   - Add a try/except with logging so failures produce actionable output

D. If OOMKilled (exit reason in Argo UI shows OOMKilled):
   - File: mctl-gitops Helm values for mctl-agents
   - Field: resources.limits.memory
   - New value: double the current limit (e.g. 512Mi -> 1Gi)
   - Target service for this sub-fix: mctl-gitops

## Scope

Minimal. Fix only the single root cause identified from the Argo Workflow logs. Do not
refactor the incident-responder workflow beyond the specific failing condition.
