# Tasks: incident-b43fe94c

1. [ ] Find the values.yaml for erpact-shared-scheduler and note the current resources.limits.cpu.
2. [ ] Raise the CPU limit modestly (about 50 percent); change nothing else.
3. [ ] Verify the diff touches only that field; flag the PR for human review (CPUThrottlingHigh is human-review-only).
