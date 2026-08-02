# Design: incident-6ab54770

## Diagnosis
The mctl-agents implementer workflow failed after 2722 seconds (45 minutes), and has recurred at least twice. This is significantly longer than the incident-responder failure (150s), suggesting the implementer ran for a while before crashing. Common causes for long-running workflow failures: (1) a timeout waiting for a subprocess (e.g., git clone, model API call), (2) memory exhaustion processing many proposals, (3) an error in the PR-creation logic that only surfaces after processing several proposals, or (4) a rate-limit or quota hit from an external service (GitHub API, Claude API). The workflow name suggests it processes "all accepted" proposals, so a backlog of proposals may be triggering the failure.

## Proposed Fix
1. Check the mctl-agents implementer workflow template and configuration:
   - File: `platform-gitops/services/admins/mctl-agents/templates/implement.yaml`
   - Verify timeout is sufficient (should be > 1 hour for large proposal batches)
   - Check resource requests/limits (CPU and memory may be insufficient)
2. Review the implementer's Python code for any unbounded loops or memory leaks when processing many proposals.
3. Check if there are API rate-limit headers in GitHub or Claude API responses in prior successful runs.
4. Consider adding batching: if processing 100+ proposals, split into smaller sub-runs to avoid timeouts.
5. Add detailed logging to track which proposal is being processed when the failure occurs.

## Scope
Moderate. May require adjusting workflow timeout, resource limits, or batch size. Possibly a minor code change to add logging or implement batching.

## Confidence: MEDIUM
The extended runtime (45 minutes) and recurrence suggest a systematic issue rather than transient failure. Without logs, the exact bottleneck (API rate limit, memory, subprocess hang, etc.) is not confirmed.
