# Design: incident-ea2c2de3

## Confidence: LOW

## Diagnosis
CPUThrottlingHigh fired for valkey-0 in platform-events. mctl-agent diagnosed CPU throttling (medium confidence) but the alert is on its human-review-only list, so no fix was proposed. No logs were available to confirm, and no current limit or usage data was observed. The throttling may be a limit set too low, or a short burst; verify before applying.

## Proposed Fix
Locate the valkey values in mctl-gitops for platform-events. Check the current resources.limits.cpu. If it is low relative to observed usage, raise it moderately (for example by 50 percent), keeping requests unchanged. If the limit is already generous or usage is low, make no change and note that in the PR.

## Scope
Minimal. Only touch the single CPU limit field for valkey in platform-events.
