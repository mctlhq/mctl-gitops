# Tasks: incident-6d4454cb

1. [ ] Before editing, query
   `container_cpu_cfs_throttled_periods_total{namespace="platform-events"}`
   (and the matching `..._periods_total`) by container to confirm whether
   `valkey` or `exporter` is the one currently being throttled.
2. [ ] If `valkey` is confirmed (or metrics are unavailable): edit
   `platform-gitops/infra-components/data/valkey/statefulset.yaml`, changing
   the `valkey` container's `resources.limits.cpu` from `500m` to `750m`.
   Leave `requests.cpu`, memory limits/requests, and the `exporter` container
   untouched.
3. [ ] If `exporter` is confirmed instead: change the `exporter` container's
   `resources.limits.cpu` from `300m` to `450m` (same proportional bump) and
   leave `valkey` untouched. Do not change both containers in one proposal.
4. [ ] Verify the edited YAML is still valid (correct indentation, only the
   one `cpu` value changed) and that `mctl.ai/config-revision` does not need
   bumping (it only tracks `valkey.conf`/ACL changes, not resource limits).
5. [ ] After rollout, confirm CPUThrottlingHigh stops firing for
   platform-events/valkey.
