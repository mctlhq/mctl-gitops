# Design: incident-87878910

## Diagnosis
The mctl-agents Temporal worker pod fails to locate the agents state directory at /workdir/mctl-gitops/platform-gitops/agents-state, causing all workflow reconciliation and implementer runs to timeout after exhausting their time budgets. The directory must be mounted from the mctl-gitops repository clone that is present in the pod at deploy time. The Helm chart for the mctl-agents service is missing or has misconfigured the volume mount for this path, or the mctl-gitops PVC is not available to the mctl-agents pod.

## Proposed Fix
1. Verify that mctl-gitops/platform-gitops/agents-state exists and is accessible on the mctl-gitops service/PVC.
2. Ensure the mctl-agents Helm values chart has a volumeMount for /workdir/mctl-gitops/platform-gitops/agents-state that references the mctl-gitops volume or a similarly populated clone.
3. If the volume is sourced from a PVC, verify the PVC is bound and available in the admins namespace.
4. Update the mctl-agents service Helm values in platform-gitops/services/admins/mctl-agents/values.yaml to mount the agents-state directory if not already present.

## Scope
Minimal. Only add or correct the volume mount configuration for the agents-state directory in the mctl-agents Helm chart, without modifying other service configuration.
