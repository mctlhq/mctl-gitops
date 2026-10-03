# Tasks: incident-cc221e40

1. [ ] In platform-gitops/tenants/labs/values.yaml, under tenant.quotas, change
       limits.cpu from "12" to "14". Add a dated comment above the line
       explaining why (quota exhaustion stalled agent-worker-preview's
       rolling update; see design.md for the exact comment text).
2. [ ] Verify the edited YAML is still valid (correct indentation under
       tenant.quotas, value quoted as a string "14" to match the existing
       style of the other quota fields in this file).
3. [ ] No other files need to change. Do not touch
       services/labs/agent-worker-preview/values.yaml — its resource
       requests/limits are already correctly sized and have their own
       documented history of not being trimmed further.
