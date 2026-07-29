# Design: incident-c33cf596

## Diagnosis
The quirestack-web Next.js application deployed successfully and is running, but is experiencing two concurrent issues that degrade the ArgoCD health status:

1. **Environment variable missing**: The application logs show "You are using the default secret. Please set `BETTER_AUTH_SECRET` in your environment variables". This is a configuration issue — the secret is required by the better-auth library but is not set in the pod's environment.

2. **Server action serialization failure**: Every few seconds, the app logs "Error: The Server Reference ID did not match the expected format. Received '0000000000000000000000000000000000000000'". This indicates a build cache or function reference mismatch in Next.js server actions. The all-zero server reference ID is a known issue when:
   - The server action bundle was built with different settings than the runtime expects (e.g., dev vs. prod mode mismatch).
   - The build cache contains stale references and needs invalidation.
   - The server and client bundles are out of sync.

The pod is alive and readiness probes may pass (since HTTP is responding), but the repeated errors cause the ArgoCD sync to mark the application as Degraded.

## Proposed Fix
Apply a minimal rolling restart to the quirestack-web deployment to invalidate build caches and force environment variable re-injection.

**File**: `service-templates/nfc/quirestack-web/values.yaml` (or the ArgoCD Application definition)

**Change**: Add/update a `restartPolicy` or `podAnnotations` to force a rolling restart. The simplest approach is to add a timestamp annotation to the deployment template so ArgoCD triggers a rolling update:

```yaml
spec:
  template:
    metadata:
      annotations:
        mctl.ai/restart-timestamp: '2026-07-29T04:20:00Z'
```

Alternatively, ensure the Helm deployment includes all required secrets in the values and re-deploy via ArgoCD with `argocd app sync`.

## Confidence
MEDIUM. The root cause is clear from the logs (missing BETTER_AUTH_SECRET + server action cache mismatch), but the exact Helm values file path and how to fix it depends on the quirestack-web service definition. The implementer should verify the secrets are properly injected in the Helm values and perform a rolling restart if needed.
