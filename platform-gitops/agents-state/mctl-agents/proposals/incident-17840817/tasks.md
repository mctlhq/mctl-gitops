# Tasks: incident-17840817

1. [ ] Open the Argo Workflow UI and identify the failing step:
       https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784081700
2. [ ] Read the step logs to find the exit reason (look for: budget/USD exhausted,
       MCP error, Python traceback, or OOMKilled in the pod events).
3. [ ] If budget exhaustion: locate the BUDGET_USD (or equivalent) constant in
       mctl-agents/workflows/incident_responder.py and increase it (e.g. 2.0 -> 5.0),
       OR reduce the number of tool calls per incident to stay within $2.
4. [ ] If MCP error: add retry/error-handling around the failing mctl tool call in
       the incident-responder workflow step.
5. [ ] If Python traceback: fix the unhandled exception at the line shown in the trace,
       add logging for the failure, and add a try/except to prevent silent crashes.
6. [ ] If OOMKilled: update the memory limit for the mctl-agents workflow pod in the
       Helm values (mctl-gitops), doubling the current limit.
7. [ ] Verify the fix by triggering a manual incident-responder run via
       mctl_trigger_incident_responder and confirming the workflow reaches Succeeded
       in the Argo UI within 10 minutes.
8. [ ] Confirm that subsequent cron-triggered runs (at :15 and :45 past each hour)
       also complete with Succeeded status for at least two consecutive cycles.
