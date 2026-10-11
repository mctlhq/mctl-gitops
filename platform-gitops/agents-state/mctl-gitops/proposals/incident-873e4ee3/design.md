# Design: incident-873e4ee3

## Confidence: LOW

## Diagnosis
The CPUThrottlingHigh alert fired for erpact/erpact-control-scheduler. mctl-agent diagnosed the CPU limit as too low but escalated because this alert is on its human-review-only list, so it proposed no fix. No logs were returned for the service, and mctl_get_service_config reported the service as not found, so current limits could not be confirmed. The implementer must verify before applying.

## Proposed Fix
Locate the values file for the erpact-control-scheduler service under platform-gitops/services/erpact/ in mctl-gitops. Raise resources.limits.cpu modestly (for example by 50 percent), keeping the request unchanged. If the service or file does not exist, make no change and report that in the PR description.

## Scope
Minimal. Only touch the single CPU limit field for this service.
