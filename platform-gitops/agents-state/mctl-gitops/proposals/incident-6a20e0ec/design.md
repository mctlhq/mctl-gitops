# Design: incident-6a20e0ec

## Diagnosis
CPUThrottlingHigh fired for erpact/erpact-control-scheduler. mctl-agent diagnosed CPU limit as too low (confidence MEDIUM) but escalated because the alert is on its human-review-only list. No logs were available in Loki and the service was not found via the service config API, so current limit values could not be observed.

## Proposed Fix
Locate the values file for the erpact-control-scheduler workload under platform-gitops/services/erpact/ and raise resources.limits.cpu moderately (for example by 50 percent), or remove the CPU limit if platform policy permits. Record the current value before editing.

## Scope
Minimal. Only touch the CPU limit of this one workload.

## Confidence: LOW
Current limits and actual usage were not observed. The implementer must verify the workload exists, check its CPU usage versus limit, and note that the alert is on the human-review-only list, so the resulting PR should get human review before merge.
