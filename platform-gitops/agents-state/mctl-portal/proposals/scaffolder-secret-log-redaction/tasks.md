# Tasks: scaffolder-secret-log-redaction

- [ ] 1. Implement `SecretRedactingLogger` class in `plugins/scaffolder-backend-module-mctl/src/lib/SecretRedactingLogger.ts` — DoD: class wraps a Winston-compatible logger; replaces all occurrences of provided secret strings (length ≥ 8) with `[REDACTED]`; unit tests pass.
- [ ] 2. Write unit tests for `SecretRedactingLogger` (depends on 1) — DoD: tests cover: single secret, multiple secrets, empty secret (skip), short secret (skip), secret appearing multiple times per line, non-secret values unchanged.
- [ ] 3. Integrate `SecretRedactingLogger` into the Scaffolder task execution context in `packages/backend/src/plugins/scaffolder.ts` (depends on 1) — DoD: every Scaffolder task uses the redacting logger; secret values from `task.spec.parameters` (filtered to `secret: true` fields) are passed to the logger at task initialisation.
- [ ] 4. Add an integration test with a synthetic template that has a `secret: true` parameter (depends on 3) — DoD: after the template runs, no log line in the captured output contains the plaintext secret value.
- [ ] 5. Benchmark redaction overhead (depends on 1) — DoD: processing 10,000 log lines with 5 secrets each completes in < 100 ms total (< 0.01 ms per line).
- [ ] 6. Deploy to staging and run a real Scaffolder onboarding (depends on 3) — DoD: Loki query for the task ID returns no lines containing the known test-secret value; template completes successfully.
- [ ] 7. Document the mitigation and the minimum-secret-length policy in `docs/scaffolder-security.md` — DoD: document merged, linked from the Scaffolder plugin README.

## Tests
- [ ] T1. Unit: `SecretRedactingLogger` replaces a known secret value in a log line with `[REDACTED]`.
- [ ] T2. Unit: Non-secret log content is unchanged after passing through the redacting logger.
- [ ] T3. Unit: Secrets shorter than 8 characters are not redacted (to avoid masking common tokens); a warning is emitted.
- [ ] T4. Integration: Full Scaffolder onboarding template run produces zero plaintext secret occurrences in captured logs.
- [ ] T5. Performance: 10,000-line benchmark completes within budget.

## Rollback
1. Remove the `SecretRedactingLogger` integration from `packages/backend/src/plugins/scaffolder.ts` and redeploy.
2. The underlying logger reverts to the standard Scaffolder task logger with no other side effects.
3. No data migrations are required.
