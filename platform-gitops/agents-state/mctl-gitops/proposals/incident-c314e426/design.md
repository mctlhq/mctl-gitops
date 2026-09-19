# Design: incident-c314e426

## Diagnosis
`platform-gitops/bootstrap/templates/data/temporal.yaml` configures the
Temporal `admintools` container with a CPU limit of `500m` (requests `50m`).
The chart's own commit history in this file records that the limit was
already raised once, from `100m` to `500m` on 2026-06-27, specifically because
admintools was observed at ~53% CFS throttling from bursty sub-period CPU
usage despite a low ~6m average — i.e. this is a recurring pattern for this
container, not a one-off spike. The current escalated incident
(`CPUThrottlingHigh`, tenant `temporal`, service `temporal-admintools`) is the
same signature recurring against the doubled limit, which indicates 500m is
still undersized for the container's burst behavior. Because
`CPUThrottlingHigh` is on the human-review-only auto-fix list, mctl-agent
diagnosed but never proposed a fix, and the incident escalated here instead.
No fresh logs were available to further quantify the throttling ratio, but
the alert firing again after a prior 5x increase is itself strong evidence
that another headroom increase (not some other root cause) is the fix.

## Proposed Fix
File: `platform-gitops/bootstrap/templates/data/temporal.yaml`

Under `admintools.resources.limits`, change:
- `cpu: 500m` -> `cpu: 1000m`

Leave `memory: 256Mi` and the `requests` block (`cpu: 50m`, `memory: 64Mi`)
unchanged — the incident is CPU-throttling specific, and average usage was
previously measured at ~6m, so requests do not need to move.

Update the surrounding comment block (lines 133-138) to record this second
bump, following the same style as the existing 2026-06-27 note and the
`history` component's resource-bump comment further up in the same file, so
future readers see continuity: raised 500m -> 1000m on
{updated_at from .status.yaml}, because CPUThrottlingHigh recurred against
the previous 500m limit (incident 0c937c79-60ef-494a-8680-476ac314e426).

## Scope
Minimal. Only touch `admintools.resources.limits.cpu` (and its explanatory
comment) in `platform-gitops/bootstrap/templates/data/temporal.yaml`. Do not
touch `requests`, other Temporal components (`frontend`, `history`,
`matching`, `worker`), or any other file.
