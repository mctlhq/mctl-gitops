# Tasks: incident-776dd0cd

1. [ ] In the mctl-telegram repo, locate the code path that increments the
   `mctl_sessions_borrow_total{result="error"}` metric (search for
   `mctl_sessions_borrow_total` or the `Pool.Borrow()` method implementation,
   likely under an `internal/session` package).
2. [ ] At that error branch, add a structured log line (WARN or ERROR level,
   matching this service's existing structured-logging style) that records the
   underlying error, the session/identity key (e.g. `tg_user_id`), and enough
   detail to distinguish failure causes. Do not log session secrets or bearer
   tokens.
3. [ ] Verify the change builds and does not alter `Pool.Borrow()` return
   values, control flow, retry behavior, or timing.
4. [ ] Bump the mctl-telegram image tag/version per the repo's normal release
   process so the change ships; no Helm values changes are required in
   mctl-gitops for this fix.
5. [ ] Confirm no existing unit test asserts on the absence of logging in this
   path; update/add a test only if one already covers this branch.
