# Tasks: incident-2f3d7db1

1. [ ] Locate the rule MctlTelegramToolAvailabilitySlowBurn in mctl-gitops
2. [ ] Check whether its error numerator excludes slo_status="caller_error"; if not, exclude it
3. [ ] If it already excludes caller errors, make no change and note that in the PR or status
4. [ ] Verify the edited expression is valid PromQL and no thresholds were changed
