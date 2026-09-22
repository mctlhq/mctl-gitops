# Tasks: incident-6670553a

1. [ ] In the mctl-telegram repo, locate the session pool code that registers
       `mctl_sessions_borrow_total` (internal/metrics/metrics.go defines the
       metric; find its callers) and find the `Pool.Borrow()` code path(s)
       that increment it with `result="error"`.
2. [ ] Check whether that error path already logs the failure (error cause,
       tenant/user id, session id) at WARN/ERROR level elsewhere in the call
       chain. If it does, close this proposal without a code change and note
       why in the PR description / proposal update.
3. [ ] If it does not, add a structured log line at WARN or ERROR level at
       the error-return point, including the underlying error, the
       tenant/user identifier, and the session identifier if available.
4. [ ] Verify the change builds and existing tests pass. If the package has
       log-assertion test coverage, add/update a test for the new log line.
5. [ ] No image tag bump or gitops values change is needed for this proposal;
       the standard CI pipeline builds and deploys mctl-telegram on merge to
       main.
