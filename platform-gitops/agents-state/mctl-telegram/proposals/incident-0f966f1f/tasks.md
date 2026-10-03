# Tasks: incident-0f966f1f

1. [ ] In `mctlhq/mctl-telegram`, search for `mctl_sessions_borrow_total` and
   the `Pool.Borrow()` implementation to confirm whether a WARN/ERROR log
   line already exists at its `result="error"` branch.
2. [ ] If missing, add a structured log line there with the underlying error,
   the tenant/user identifier, and the session identifier if available (no
   secrets or tokens).
3. [ ] If already present, add a note to the PR description that incident
   d685163c-9ba9-4453-b968-38090f966f1f still showed no corresponding
   error-level log line in the sampled window, and flag the idle-client
   eviction angle from incident b87ca113-2bf5-4793-8b44-d343e22f370d as a
   follow-up to investigate separately.
4. [ ] Verify the change builds and does not alter `Pool.Borrow()` control
   flow, retry behavior, or timing.
