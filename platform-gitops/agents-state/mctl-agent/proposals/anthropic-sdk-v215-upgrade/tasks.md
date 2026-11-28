# Tasks: anthropic-sdk-v215-upgrade

- [ ] 1. Check whether the SDK is a dependency — DoD: result recorded.
- [ ] 2. Bump to v2.15.0 (depends on 1) — DoD: go build passes.
- [ ] 3. Run test suite and diagnose fixtures (depends on 2) — DoD: green.

## Tests
anthropic-sdk-go v2.15.0 was released on 24 Nov with a date-time serialization fix and new APIs. The diagnose phase uses Claude, either via the SDK or direct HTTP.0

## Rollback
Revert the change; no data migration is involved.
