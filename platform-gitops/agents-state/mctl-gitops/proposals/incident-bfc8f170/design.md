# Design: incident-bfc8f170

## Confidence: LOW

## Diagnosis
The CPUThrottlingHigh alert fired for erpact/erpact-shared-scheduler. mctl-agent's
advisory analysis says the CPU limit is too low; the alert is on its human-review-only
list so it did not propose a fix. No logs or labels were available, so the actual CPU
usage versus limit is unverified. The implementer must verify before applying.

## Proposed Fix
Locate the service values file (likely platform-gitops/services/erpact/erpact-shared-scheduler/values.yaml;
the exact path could not be confirmed). Check resources.limits.cpu against observed usage.
If the limit is low or tight, raise it modestly (for example double it) and keep
resources.requests.cpu unchanged. Respect the tenant CPU quota. If limits are already
generous, or the file does not exist, make no change and note it in the PR.

## Scope
Minimal. Only touch the single CPU limit field for this service.
