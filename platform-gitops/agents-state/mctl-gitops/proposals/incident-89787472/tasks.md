# Tasks: incident-89787472

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
   change `spec.activeDeadlineSeconds` from `7200` to `12000`.
2. [ ] Update the comment block above that field to note the new value covers
   a full primary + fallback `run-implementer` pair
   (2 x IMPLEMENTER_TIMEOUT_SECONDS = 10800s) plus clone/commit/assert
   overhead, and that IMPLEMENTER_TIMEOUT_SECONDS must stay comfortably under
   half of this value if either is changed again in the future.
3. [ ] Verify the YAML still parses/lints cleanly (no other field references
   `activeDeadlineSeconds` or assumes the old 7200 value elsewhere in this
   file or a sibling template).
4. [ ] No image tag bump or other dependent change needed — this is a
   values-only change to an existing ClusterWorkflowTemplate.
