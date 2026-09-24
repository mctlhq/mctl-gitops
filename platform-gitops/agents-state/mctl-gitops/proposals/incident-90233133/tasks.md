# Tasks: incident-90233133

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
   template `notify-telegram`: add a `WORKFLOW_FAILURES` env var sourced from
   `{{workflow.failures}}`, alongside the existing `WORKFLOW_STATUS` /
   `WORKFLOW_SERVICE` / `WORKFLOW_SLUG` / `WORKFLOW_NAME` / `WORKFLOW_DURATION`
   env vars on that step.
2. [ ] In the same step's `source:` script, extend the incident-leg
   `BODY=$(jq -nc ...)` call to accept `--arg failures "$WORKFLOW_FAILURES"`
   and add `analysis: $failures` to the emitted JSON object, next to the
   existing `summary` field.
3. [ ] Verify the change renders sane output: check `{{workflow.failures}}`'s
   actual shape on a real or synthetic Failed run of this CWFT (Argo docs:
   it is a JSON array of `{displayName, message, templateName, phase,
   finishedAt}` objects per failed node) — confirm it is safe to pass
   through `jq --arg` as a single string, or switch to `--argjson` /
   truncate if it turns out to be large or already-JSON. Do not change
   `assert-attempt`'s exit logic, retry counts, or the fallback-account
   mechanism — this proposal only makes the resulting incident
   self-describing.
4. [ ] No image tag bump needed — this is a ClusterWorkflowTemplate manifest
   change picked up on next ArgoCD sync, not a code change to the
   `mctl-agents` image.
