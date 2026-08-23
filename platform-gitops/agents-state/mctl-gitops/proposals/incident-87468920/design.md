# Design: incident-87468920

## Diagnosis
The mctl-agents pod is executing Temporal workflows (ReconcileWorkflow, IncidentLoopWorkflow) that attempt to discover and project agent state from `/workdir/mctl-gitops/platform-gitops/agents-state`, but this directory is not mounted into the pod's filesystem. This causes repeated "state_dir not found" warnings every 15 minutes in the reconciliation loop, which eventually times out the shepherd workflow (512s timeout on post-deploy verification). The mctl-agents service is deployed via Helm chart but is missing the gitops repository volume mount configuration that other services use.

## Proposed Fix
Add a volume mount in the mctl-agents Helm values to mount the mctl-gitops repository at `/workdir/mctl-gitops`. This is a standard configuration pattern in the platform for services that read or write state files from the gitops repo. Update `platform-gitops/services/admins/mctl-agents/values.yaml` to include a gitops volume mount similar to other service charts.

Specifically, add to the pod spec:
```yaml
volumeMounts:
  - name: gitops
    mountPath: /workdir/mctl-gitops
```

and in the volumes section:
```yaml
volumes:
  - name: gitops
    emptyDir: {}  # or use appropriate gitops repo sync mechanism
```

## Scope
Minimal. Only add the required volume mount configuration to the mctl-agents service in the admins namespace so its Temporal workflows can access the agents-state directory.
