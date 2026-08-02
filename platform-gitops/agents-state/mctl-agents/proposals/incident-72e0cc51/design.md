# Design: incident-72e0cc51

## Diagnosis
The mctl-agents incident-responder workflow failed after 150 seconds. Given the short duration (not a timeout waiting for external resources) and zero archived logs, the most likely causes are: (1) a Python/startup error in the responder script before it reaches Loki logging, (2) a missing environment variable or credentials, (3) an API connection error to mctl (rate limit, auth, or network), or (4) an unhandled exception in the incident querying logic. The incident responder is a critical Argo Workflow that runs on a 30-minute cron. Its failure blocks the entire incident diagnosis pipeline.

## Proposed Fix
1. Examine the mctl-agents deployment and incident-responder workflow template in mctl-gitops:
   - File: `platform-gitops/services/admins/mctl-agents/templates/incident-responder.yaml`
   - Check environment variables (MCTL_API_URL, auth tokens, etc.)
2. Review the incident-responder Python entrypoint for syntax errors or missing dependencies.
3. Add verbose logging to stdout/stderr in the workflow template to capture startup errors before Loki ingestion.
4. Verify the workflow's ServiceAccount has permissions to query the mctl-api.
5. If auth is the issue, ensure the API token in Vault is current and not expired.

## Scope
Minimal. Only update the incident-responder workflow template and environment if needed. No changes to other mctl-agents workflows.

## Confidence: LOW
Without access to the pod logs or workflow status details, the exact failure point is unclear. The implementer should add debug logging and re-run to capture the actual error.
