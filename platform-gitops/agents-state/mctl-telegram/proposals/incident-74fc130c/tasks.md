# Tasks: incident-74fc130c

1. [ ] Check whether incident-4331f490 (this incident's slow-burn sibling, same proposals directory) already covers this fix — if so, treat this as a duplicate and apply/verify only once.
2. [ ] In the mctl-telegram repo, locate the session pool's Borrow() implementation — the code path that increments `mctl_sessions_borrow_total{result="error"}` (per internal/metrics/metrics.go).
3. [ ] Add a structured log line (WARN or ERROR level) at that error-return path recording the borrow failure reason and an identifying context (user/session id), without changing control flow, retries, or return values.
4. [ ] Confirm the chosen log level is actually emitted at the deployed `LOG_LEVEL: info` (platform-gitops/services/labs/mctl-telegram/values.yaml) — do not log at DEBUG.
5. [ ] Confirm no change to `Pool.Borrow()` behavior, retry logic, session pool sizing, or the mctl-telegram-slo.yaml burn-rate thresholds/expressions.
6. [ ] Once released, bump the mctl-telegram image tag in platform-gitops/services/labs/mctl-telegram/values.yaml (currently "0.69.0") so the fix deploys.
