# Design: incident-1ad5823f

## Confidence: LOW

## Diagnosis
CPUThrottlingHigh fired for erpact-control-scheduler. mctl-agent diagnosed CPU throttling (medium confidence) but the alert is human-review-only, so no fix was proposed. No logs were available and no current limit or usage was observed. It fired at the same time as the erpact-shared-scheduler alert, which suggests a common cause such as a shared chart default for CPU limits.

## Proposed Fix
Locate the values for erpact-control-scheduler in mctl-gitops (likely under platform-gitops/services/erpact/). Check resources.limits.cpu. If it is low relative to usage, raise it moderately (for example by 50 percent). If a shared default is the cause, note that in the PR. If not clearly too low, make no change and explain.

## Scope
Minimal. Only touch the single CPU limit field for this service.
