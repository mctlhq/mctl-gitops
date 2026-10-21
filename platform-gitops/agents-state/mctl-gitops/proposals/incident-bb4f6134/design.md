# Design: incident-bb4f6134

## Confidence: LOW

## Diagnosis
The CPUThrottlingHigh alert fired for platform-events/valkey-0. mctl-agent's advisory
analysis says the CPU limit is too low; the alert is on its human-review-only list so it
did not propose a fix. No logs or labels were available. "valkey-0" looks like a
StatefulSet pod name, not a service name, so it is likely a Valkey deployment managed
by a Helm chart or operator, not a catalogue service. Actual CPU usage versus limit is
unverified. The implementer must verify before applying.

## Proposed Fix
Find where the platform-events Valkey is configured in mctl-gitops (search for "valkey"
under platform-gitops). Check its resources.limits.cpu. If the limit is low or tight,
raise it modestly (for example double it), keeping requests unchanged and within
namespace quota. If the config cannot be located or limits are already generous, make
no change and note it in the PR.

## Scope
Minimal. Only touch the single CPU limit field for the Valkey workload.
