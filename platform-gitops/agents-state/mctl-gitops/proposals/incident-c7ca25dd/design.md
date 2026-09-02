# Design: incident-c7ca25dd

## Diagnosis
The ArgoCD application for tenant ovk's OpenClaw service has been OutOfSync for over an hour. This indicates either that automatic synchronization is disabled for this application, or that there is a persistent error preventing the sync operation. Without direct access to ArgoCD state, the most likely cause is that the application's sync policy does not have automatic sync enabled, or the cluster cannot reach the desired state due to a configuration mismatch between the GitOps repository and the cluster.

## Proposed Fix
Enable automatic sync on the ovk-openclaw ArgoCD Application, or verify that the application's GitOps manifest in platform-gitops/services/ovk/openclaw is correct and that automatic sync is configured. If sync errors are present, they must be resolved.

The fix path is: platform-gitops/services/ovk/openclaw/application.yaml or values.yaml - ensure argocd.autosync is enabled (typically `syncPolicy.automated.prune=true, syncPolicy.automated.selfHeal=true`).

## Confidence: LOW
Without access to ArgoCD's detailed state or recent application logs, this diagnosis is based on the alert name and duration. Verification through ArgoCD UI or logs is recommended before applying.
