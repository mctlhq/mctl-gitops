# Tasks: incident-c314e426

1. [ ] In `platform-gitops/bootstrap/templates/data/temporal.yaml`, under the
       `admintools.resources.limits` block, change `cpu: 500m` to
       `cpu: 1000m`.
2. [ ] Update the comment immediately above that block (currently describing
       the 2026-06-27 100m->500m bump) to also note this 500m->1000m bump,
       the date, and the reason (CPUThrottlingHigh recurred, incident
       0c937c79-60ef-494a-8680-476ac314e426), matching the style of the
       `history` component's resource-bump comment earlier in the same file.
3. [ ] Verify the diff touches only the `admintools.resources.limits.cpu`
       value and its comment — no changes to `requests`, `memory`, or any
       other Temporal component (`frontend`, `history`, `matching`,
       `worker`).
4. [ ] No image tag or other dependent changes are needed for this fix.
