# Tasks: incident-a59cdaab

1. [ ] Edit `platform-gitops/infra-components/data/valkey/statefulset.yaml`:
       in the `valkey` container's `resources` block, change
       `requests.cpu` from `25m` to `50m` and `limits.cpu` from `500m` to
       `1000m`. Leave `memory` requests/limits and the `exporter` container
       unchanged.
2. [ ] Verify the edited YAML is still valid (proper indentation under
       `containers[0].resources`) and that only the `valkey` container's cpu
       fields changed.
3. [ ] No image tag bump or other dependent change is required — this is a
       resource-limit-only change to an existing StatefulSet.
