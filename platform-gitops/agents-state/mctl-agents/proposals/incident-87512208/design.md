# Design: incident-87512208

## Diagnosis
The mctl-agents shepherd workflow crashed because the Temporal activities cannot locate the state directory at `/workdir/mctl-gitops/platform-gitops/agents-state`. This directory is mounted as part of the gitops bootstrap and is required for the `discover_and_project` and related activities to function. The repeated "not found" warnings in the logs indicate this directory is missing from the pod's filesystem, causing the entire reconciliation workflow to fail. The shepherd workflow depends on this path to read incident proposals and manage the dev-loop pipeline.

## Proposed Fix
Ensure the state directory is properly created and mounted in the mctl-agents service deployment. This is likely a volume mount configuration issue in the Helm values or service deployment. The path `/workdir/mctl-gitops/platform-gitops/agents-state` must:
1. Exist on the shared persistent volume or mount path
2. Be correctly mounted into the pod at that exact location
3. Have read access for the mctl-agents worker pod

The fix involves verifying or adding the volume mount in the mctl-agents service values.yaml to include the gitops state directory mount point.

## Scope
Minimal. Only fix the volume mount configuration for the mctl-agents service to include the required state directory path.
