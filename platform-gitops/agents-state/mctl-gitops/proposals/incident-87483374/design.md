# Design: incident-87483374

## Diagnosis
The mctl-agents service cannot locate the state directory `/workdir/mctl-gitops/platform-gitops/agents-state` required for the agent infrastructure to function. This directory is mounted from the mctl-gitops repository and is essential for storing proposals, incident state, and coordinating with the implementer pipeline. The recurring warning (every 15 minutes) indicates the volume mount is either missing from the Kubernetes pod specification or the directory does not exist in the mctl-gitops source. The shepherd workflow hangs waiting for state operations that cannot complete, eventually timing out after 543 seconds.

## Proposed Fix
Ensure the mctl-agents Kubernetes deployment has a proper EmptyDir or persistent volume mount at `/workdir/mctl-gitops/platform-gitops/agents-state`, or mount it from a shared volume with mctl-gitops. This can be addressed by:

1. Verifying the mctl-agents Helm values specify a volume mount for the agents-state directory.
2. Creating the directory structure if it does not exist in the mounted path.
3. Ensuring proper permissions so the mctl-agents container can read/write to this directory.

File: `platform-gitops/services/admins/mctl-agents/values.yaml`
Field: `volumeMounts` (add if missing) and `volumes` (add if missing)

## Scope
Minimal. Only fix the volume mount configuration for mctl-agents to access the agents-state directory.
