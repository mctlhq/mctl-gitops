# Tasks: incident-4331f490

1. [ ] In the mctl-telegram repo, locate the session pool's Borrow() implementation — the code path that increments `mctl_sessions_borrow_total{result="error"}` (per internal/metrics/metrics.go).
2. [ ] Add a structured log line (WARN or ERROR level) at that error-return path recording the borrow failure reason and an identifying context (user/session id), without changing control flow, retries, or return values.
3. [ ] Confirm the chosen log level is actually emitted at the deployed `LOG_LEVEL: info` (platform-gitops/services/labs/mctl-telegram/values.yaml) — do not log at DEBUG.
4. [ ] Confirm no change to `Pool.Borrow()` behavior, retry logic, session pool sizing, or the mctl-telegram-slo.yaml burn-rate thresholds/expressions.
5. [ ] Check whether this same fix was already proposed by incident-0f966f1f or incident-776dd0cd in this same proposals directory and, if a PR for one of those was opened but not merged, prefer completing/rebasing that one over opening a fourth duplicate.
6. [ ] Once released, bump the mctl-telegram image tag in platform-gitops/services/labs/mctl-telegram/values.yaml (currently "0.69.0") so the fix deploys.
