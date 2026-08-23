# Design: incident-87476157

## Diagnosis
The mctl-agents service pods are unable to access the required `/workdir/mctl-gitops/platform-gitops/agents-state` directory. Workflow activities (ReconcileWorkflow and IncidentLoopWorkflow) attempt to read from this mount point at regular 15-minute intervals but consistently fail with "state_dir not found" warnings. This is a volume mount configuration issue in the Helm deployment for mctl-agents. The directory must be mounted from the mctl-gitops repository volume that contains the agent state tracking and proposal directories.

## Proposed Fix
Verify or add a volume mount in the mctl-agents Helm values (services/admins/mctl-agents/values.yaml) that:
1. Mounts the mctl-gitops repository to /workdir/mctl-gitops
2. Ensures platform-gitops/agents-state is accessible at the expected path
3. Sets appropriate read permissions for the workflow pods to access agent state files

Check the init container or volume configuration in the Helm chart to ensure the GitOps repository is cloned and mounted before workflow pods start executing activities.

## Scope
Minimal. Only adjust the volume mount configuration for mctl-agents in mctl-gitops values.yaml to ensure the state directory is accessible. No changes to mctl-agents application code required.
