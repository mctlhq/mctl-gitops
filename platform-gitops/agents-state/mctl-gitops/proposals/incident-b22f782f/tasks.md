# Tasks: incident-b22f782f

1. [ ] Edit `platform-gitops/services/labs/pelican-proxy-staging/values.yaml`
   to add a `probes.startup` block (path `/readyz`, port `http`,
   initialDelaySeconds 5, periodSeconds 5, timeoutSeconds 2,
   failureThreshold 24), giving the login + R2 catalog-seed sequence
   roughly 2 minutes of startup grace before Kubernetes marks the pod
   unhealthy.
2. [ ] Verify the rendered `helm-charts/base-service` deployment template
   picks up the new `probes.startup` block correctly (it already has the
   conditional `{{- if .Values.probes.startup }}` wiring — no chart change
   needed, values-only change).
3. [ ] No image tag bump needed — this is a values-only/config change.
