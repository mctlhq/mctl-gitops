# Design: incident-9dfc9185

## Confidence: LOW

## Diagnosis
CPUThrottlingHigh fired for erpact-shared-scheduler. mctl-agent diagnosed CPU throttling (medium confidence) but the alert is human-review-only, so no fix was proposed. No logs were available and no current limit or usage was observed. A scheduler may throttle in short bursts; verify before changing anything.

## Proposed Fix
Locate the values for erpact-shared-scheduler in mctl-gitops (likely under platform-gitops/services/erpact/). Check resources.limits.cpu. If it is low relative to usage, raise it moderately (for example by 50 percent). If not clearly too low, make no change and explain in the PR.

## Scope
Minimal. Only touch the single CPU limit field for this service.
