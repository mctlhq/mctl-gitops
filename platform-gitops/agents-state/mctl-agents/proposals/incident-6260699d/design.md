# Design: incident-6260699d

## Confidence: LOW

## Diagnosis

The `mctl-agents-run implement` Argo Workflow has been failing deterministically. The workflow fails after 1418 seconds (approximately 23.6 minutes), suggesting a timeout or resource exhaustion during the implement phase (processing all accepted proposals).

Loki returned zero log lines for `admins/mctl-agents` over a 6-hour window. The Argo Workflow UI at https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-1785006900 is the primary source for the exact failure reason.

Most likely root causes in rank order:

1. API budget exhaustion: The orchestrator workflow may be running multiple agents simultaneously to process all accepted proposals. If the total API cost exceeds the allocated budget, the workflow exits non-zero after consuming the budget (~23 minutes into execution).

2. Timeout during batch processing: The implement phase processes all proposals atomically. A timeout in the external system (Git, GitHub, or deployment infrastructure) during batch file writes could cause the entire operation to fail.

3. MCP connectivity error: The mctl MCP server or downstream services (GitHub API, Git operations) may be returning transient errors that are not retried properly.

4. Python runtime exception: An unhandled exception in the implement workflow step, possibly related to Git conflict resolution or API rate limiting.

5. Resource contention: High memory or CPU usage during parallel proposal processing causing OOMKill or CPU throttling.

The `workflow_failed` alert type has no pattern-matched skill, causing incidents to stay in `analyzing` indefinitely.

## Proposed Fix

Implementer must first retrieve the actual failure reason from the Argo UI:
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-1785006900

Likely remediation actions, in priority order:

1. **Increase API budget** for the implement workflow step (if budget exhaustion is the cause). Check MCTL configuration for orchestrator budget limits and increase the implement phase budget.

2. **Increase timeout** for the implement workflow step (if external timeout is the cause). Update the Argo workflow timeout from the current value to 30+ minutes.

3. **Enable verbose logging** on the mctl-agents service to capture detailed error output during the next implement run, then re-run manually to observe the exact error.

4. **Check for upstream infrastructure issues** (GitHub rate limiting, Git server availability, DNS resolution) that may be blocking batch file operations.

## Scope

Minimal. Fix only the single root cause identified from the Argo Workflow logs. Do not refactor the implement logic unless diagnosis confirms a bug in proposal application.
