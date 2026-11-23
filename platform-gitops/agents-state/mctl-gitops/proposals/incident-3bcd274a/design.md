# Design: incident-3bcd274a

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy but reports OutOfSync, and the workload itself runs normally (pod logs show no errors). So the problem is drift between the live state and the rendered manifests, not a runtime failure. The incident carries no sync-error detail, and the application revision field was empty in the status read. Likely causes: a field mutated by a controller or HPA that ArgoCD diffs against (missing ignoreDifferences), a recent gitops commit still pending sync, or a manual live change. mctl-agent has no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. Note the status shows imageTag 1.117.0, and the app has a companion "-exec" deployment (admins-mctl-agents-worker-exec) that may share chart values.

## Proposed Fix
The implementer must verify before changing anything:
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the ArgoCD Application definition for admins-mctl-agents-worker, and compare against the rendered chart for obvious drift sources (replicas vs autoscaling, fields mutated by controllers, ExternalSecret defaults, resource fields).
2. If a specific field is mutated by a controller, add a narrowly scoped ignoreDifferences entry for that field to the Application. Otherwise correct the values so they match live state intentionally.
3. If no drift source is found in git, make no change and report that a manual ArgoCD sync or diff inspection is required.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync diff for admins-mctl-agents-worker.
