# Tasks: incident-210417c4

1. [ ] Locate the Tier-1 alert-classification/skill-dispatch code in
       mctl-agent (`internal/monitor/alerthandler.go::classifyAlert` and the
       skill registry it dispatches to) and confirm the shape used by
       existing SLO burn-rate skills, if any exist, for
       `MctlTelegramToolAvailabilityFastBurn` / `MctlTelegramOAuthAvailabilityFastBurn`.
2. [ ] Add a new skill for alert `MctlTelegramSessionBorrowFastBurn` that:
       fetches recent labs/mctl-telegram logs, checks for corroborating
       error signals (Telegram client errors, DB/session errors, non-"ok"
       tool-call results), and either escalates (if found) or auto-resolves
       with a note citing the documented low-traffic-crossing caveat in
       `vm-rules/mctl-telegram-slo.yaml` (if not found).
3. [ ] Verify the new skill is registered/wired into the same dispatch table
       as the other SLO burn-rate skills, and does not change behavior for
       any other alert name.
4. [ ] Add/update tests covering both branches (corroborating errors found /
       not found) if the existing skill test pattern supports it.
