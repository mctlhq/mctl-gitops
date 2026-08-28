# Design: incident-87925783

## Diagnosis
The mctl-agents service image is missing the `temporalio` Python module, causing the Temporal worker process to fail on startup. Additionally, the working directory `/workdir/mctl-gitops/platform-gitops/agents-state` is not mounted in the container, preventing the orchestrator from accessing agent state. These are blocking issues for all agent workflows (issue investigator, implementer, shepherd, mentor).

## Proposed Fix
1. Update the mctl-agents Dockerfile to include `temporalio` in the Python dependencies (requirements.txt or equivalent)
2. Verify the volume mount for `/workdir/mctl-gitops` is configured in the Kubernetes deployment manifest (values.yaml)
3. Ensure the state directory structure is created during pod initialization if not present

## Scope
- Update Python dependencies in Dockerfile
- Verify volume mounts in Helm values
- Minimal scope: only fix the critical blockers preventing Temporal worker startup
