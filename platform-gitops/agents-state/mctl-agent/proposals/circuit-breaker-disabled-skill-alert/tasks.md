# Tasks: circuit-breaker-disabled-skill-alert

- [ ] 1. Add transition hook to breaker — DoD: callback invoked once on open/close.
- [ ] 2. Add gauge and register it (depends on 1) — DoD: visible on /metrics.
- [ ] 3. Telegram notification (depends on 1) — DoD: message sent on disable.
- [ ] 4. Add alert rule in gitops (depends on 2) — DoD: rule fires in test.

## Tests
The skill circuit breaker auto-disables failing skills. ADR 0001 notes this can hide real problems and that an alert is needed. Currently no alert exists.0

## Rollback
Revert the change; no data migration is involved.
