# Tasks: incident-b5d6684e

1. [ ] In mctl-telegram, locate the session pool's Borrow() implementation
       (the call site that increments mctl_sessions_borrow_total{result=...})
       and add a WARN-level structured log line whenever result is "error"
       (not for expired_idle/expired_absolute, which are expected), including
       tg_user_id and the underlying error/reason.
2. [ ] Verify the added log line compiles, matches the existing logging
       conventions in the package (e.g. the same logger/msg style used
       elsewhere in internal/metrics and the session pool), and does not log
       any secret material (auth key bytes, session tokens).
3. [ ] Bump the mctl-telegram image tag in
       platform-gitops/services/labs/mctl-telegram/values.yaml (image.tag,
       currently "0.62.2") once the fix is released, so the new log line is
       live in labs.
4. [ ] Flag for operator follow-up (not part of this change): confirm
       whether the mctl-telegram-canary Secret's tg_user_id is still
       210408407 per the unresolved warning in
       platform-gitops/services/labs/mctl-telegram/values.yaml (canary
       CronJob comment), and if so remint it to 924671154 via
       POST /api/mcp/worker-token rather than hand-editing the Secret.
