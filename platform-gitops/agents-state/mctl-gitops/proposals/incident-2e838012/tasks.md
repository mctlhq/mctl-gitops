# Tasks: incident-2e838012

1. [ ] Locate the labs mctl-telegram service's Helm values file in
   platform-gitops (e.g. `services/labs/mctl-telegram/values.yaml`) and
   identify the field controlling the Telegram client session idle-timeout
   and/or session pool size.
2. [ ] Increase the idle timeout from its current ~10.85-minute behavior to a
   longer value (e.g. 30 minutes), and/or raise the pool's max size, using
   whichever field the chart actually exposes.
3. [ ] If no such tunable exists in the chart/values, instead widen the
   `MctlTelegramSessionBorrowFastBurn` AlertManager rule's threshold/window
   for the labs tenant only, and note in the PR description that this is the
   fallback path because no pool-sizing knob was found.
4. [ ] Verify the edited values/rules file is still valid YAML and the change
   is scoped only to the labs tenant / mctl-telegram service.
5. [ ] Double-check no other tenant's configuration was modified.
