# Design: incident-bc9ba1bc

## Diagnosis
The OpenClaw service ovk-openclaw was never fully deployed to the platform. An ArgoCD application exists and is firing OutOfSync alerts, but the service cannot be found in the platform database (mctl_get_service_config returns 404), and no logs are available from the running container. This indicates either:
1. An OpenClaw deployment workflow (mctl_deploy_openclaw or mctl_resume_openclaw_deploy) was initiated but failed to complete, leaving orphaned ArgoCD application resources, OR
2. The deployment completed but the service registration in mctl-gitops is missing or corrupted.

The OutOfSync state is firing because ArgoCD detects a difference between desired and live state that it cannot reconcile.

## Proposed Fix
Investigate the deployment workflow state:
1. Check platform-gitops/services/ovk/openclaw/ directory - verify the Helm values and service configuration exist and are committed
2. Examine the ArgoCD application ovk-openclaw status and sync error details
3. Review mctl-agents workflow logs for the deployment (search for mctl-deploy-openclaw-* or mctl-resume-openclaw-* workflows for tenant ovk)

Once the root cause is identified, either:
- Complete the failed deployment if it should exist, OR
- Delete the orphaned ArgoCD application if the service should not exist

## Confidence: LOW
Diagnosis is based on the absence of service configuration and logs. The actual remediation requires investigation of the deployment workflow logs to determine whether the service should be deployed or the ArgoCD application should be deleted.

## Scope
Minimal - investigate and complete or rollback the incomplete OpenClaw deployment for tenant ovk.
