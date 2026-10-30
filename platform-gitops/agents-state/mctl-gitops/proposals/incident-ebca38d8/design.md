# Design: incident-ebca38d8

## Confidence: LOW

## Diagnosis
The CPUThrottlingHigh alert fired for platform-events/valkey-0. mctl-agent's advisory analysis says the CPU limit is too low, but it escalated because this alert is on the human-review-only list. No service logs were available, and I could not find the service's values file under platform-gitops/services, so the current limit is unknown. The cause is plausible but unverified.

## Proposed Fix
Locate the values file that defines resources.limits.cpu for valkey (tenant platform-events). Raise the CPU limit modestly, for example by 50 to 100 percent, or remove the CPU limit if platform policy allows. Keep the CPU request unchanged.

## Scope
Minimal. Only touch the single CPU limit field that causes this alert.
