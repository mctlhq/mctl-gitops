# Design: incident-c2aaafe3

## Diagnosis
The mctl-agents service is failing at startup because the Dockerfile is missing the `temporalio` Python SDK. The incident-responder orchestrator workflow requires the Temporal client to connect to the Temporal workflow engine, but the import fails before the orchestrator can initialize. This is the same root cause as the shepherd workflow failure: a missing dependency in the container image.

## Proposed Fix
Add `temporalio` to the Python dependencies in the mctl-agents Dockerfile. This is the same fix as incident-d51a3c44 and will resolve both failures simultaneously.

File: `services/admins/mctl-agents/Dockerfile`
Current: The pip install line does not include temporalio
New: Add temporalio to the requirements or pip install command (e.g., `pip install temporalio`)

## Scope
Minimal. Only add the missing dependency to the existing Dockerfile pip install command. No configuration changes or orchestrator code changes required.
