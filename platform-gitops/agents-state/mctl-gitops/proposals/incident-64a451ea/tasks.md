# Tasks: incident-64a451ea

1. [ ] Edit `platform-gitops/services/labs/mctl-telegram-preview/values.yaml` and add a
       `podAnnotations` block (top level, alongside `resources`/`env`) with a rollout-marker
       key, e.g.:
       ```yaml
       podAnnotations:
         mctl.me/oauth-secret-rollout: "incident-64a451ea-2026-09-14"
       ```
2. [ ] Verify the resulting values.yaml still parses as valid YAML and that
       `podAnnotations` renders correctly through
       `helm-charts/base-service/templates/deployment.yaml` (the `{{- with .Values.podAnnotations }}`
       block at line 36-38 of that template).
3. [ ] No image tag bump or other dependent change is needed — this is a pod-template-only
       annotation change on the existing image tag (`main-29470b0`). After ArgoCD syncs,
       confirm the preview pod restarted (new pod name/age) and that
       `oauth: client_registration` / `auth failed: invalid JWT signature` lines stop
       recurring in `labs-mctl-telegram-preview` logs.
