# Design: incident-d51a3c44

## Diagnosis
The mctl-agents service is failing to start because the Dockerfile does not include the `temporalio` Python SDK dependency. The orchestrator code at `/app/orchestrator/temporal/worker.py` imports from `temporalio.client`, which is required for the Temporal workflow orchestration features. This import fails at container startup, causing the pod to exit with a ModuleNotFoundError. The shepherd workflow and other agent orchestrations that depend on the Temporal client cannot execute.

## Proposed Fix
Add `temporalio` to the Python dependencies in the mctl-agents Dockerfile. The fix requires updating the package installation step to include the temporalio SDK.

File: `services/admins/mctl-agents/Dockerfile`
Current: The pip install line does not include temporalio
New: Add temporalio to the requirements or pip install command (e.g., `pip install temporalio`)

## Scope
Minimal. Only add the missing dependency to the existing Dockerfile pip install command. No configuration changes or orchestrator code changes required.
