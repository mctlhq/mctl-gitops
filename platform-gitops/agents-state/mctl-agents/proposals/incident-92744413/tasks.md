# Tasks: incident-92744413

1. [ ] Grep the mctl-agents repo for "Newly Degraded apps detected" and read the surrounding logic.
2. [ ] Make the check a no-op when no PR was merged by the run, and filter by health transition time before workflow creation.
3. [ ] Verify the change does not suppress genuinely new post-merge degradations.
